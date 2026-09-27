"""Benchmark runner for BIRD / Spider style datasets.

Dataset format: a JSON list of objects with `db_id`, `question`, gold SQL under `SQL` (BIRD) or
`query` (Spider), optional `evidence`, `difficulty` and `question_id`. Databases live at
`{db_root}/{db_id}/{db_id}.sqlite` (the layout both benchmarks ship with).

Results stream to a JSONL file one question at a time, so a long local-model run can be stopped
and resumed. Each record carries three scored variants of the same run:

    greedy_initial   the first (temperature 0) candidate, before any repair
    greedy           that candidate after execution-feedback repair
    final            the self-consistency vote over all candidates

which is how one run yields several ablation rows without extra LLM calls.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from t2sql.eval.metrics import run_gold, score
from t2sql.llm.client import LLMClient
from t2sql.pipeline.context import DatabaseContext
from t2sql.pipeline.pipeline import Pipeline, PipelineOptions
from t2sql.retrieval.fewshot import FewShotIndex

PRESETS: dict[str, dict] = {
    # Each preset adds one idea on top of the previous one; "full" also records its greedy,
    # pre-repair candidate, so repair and voting get their own ablation rows for free.
    "bare": dict(
        schema_examples=0,
        schema_descriptions=False,
        use_value_hints=False,
        n_fewshot=0,
        n_candidates=1,
        max_repair_rounds=0,
    ),
    # + column descriptions and example values (M-Schema)
    "mschema": dict(
        schema_examples=3,
        schema_descriptions=True,
        use_value_hints=False,
        n_fewshot=0,
        n_candidates=1,
        max_repair_rounds=0,
    ),
    # + database value retrieval
    "values": dict(
        schema_examples=3,
        schema_descriptions=True,
        use_value_hints=True,
        n_fewshot=0,
        n_candidates=1,
        max_repair_rounds=0,
    ),
    # + 3 train-split few-shot examples, execution repair, 5-way self-consistency
    "full": dict(
        schema_examples=3,
        schema_descriptions=True,
        use_value_hints=True,
        n_fewshot=3,
        n_candidates=5,
        max_repair_rounds=2,
    ),
}


@dataclass
class Item:
    qid: str
    db_id: str
    question: str
    gold_sql: str
    evidence: str = ""
    difficulty: str = "unknown"


def load_dataset(path: str | Path) -> list[Item]:
    data = json.loads(Path(path).read_text())
    items = []
    for i, d in enumerate(data):
        items.append(
            Item(
                qid=str(d.get("question_id", i)),
                db_id=d["db_id"],
                question=d["question"],
                gold_sql=d.get("SQL") or d.get("query") or d["gold_sql"],
                evidence=d.get("evidence", "") or "",
                difficulty=d.get("difficulty", "unknown"),
            )
        )
    return items


def stratified_sample(items: list[Item], n: int, seed: int = 7) -> list[Item]:
    """Deterministic sample that preserves the difficulty mix."""
    if n >= len(items):
        return items
    rng = random.Random(seed)
    by_diff: dict[str, list[Item]] = {}
    for it in items:
        by_diff.setdefault(it.difficulty, []).append(it)
    out: list[Item] = []
    for group in by_diff.values():
        k = round(n * len(group) / len(items))
        out.extend(rng.sample(group, min(k, len(group))))
    rng.shuffle(out)
    return sorted(out[:n], key=lambda it: items.index(it))


async def run_benchmark(
    items: list[Item],
    db_root: str | Path,
    llm: LLMClient,
    options: PipelineOptions,
    out_path: str | Path,
    use_evidence: bool = True,
    concurrency: int = 2,
    progress: bool = True,
    fewshot: FewShotIndex | None = None,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["qid"])
    todo = [it for it in items if it.qid not in done]

    contexts: dict[str, DatabaseContext] = {}
    ctx_lock = asyncio.Lock()
    write_lock = asyncio.Lock()
    pipeline = Pipeline(llm, options, fewshot)
    sem = asyncio.Semaphore(concurrency)
    counter = {"n": len(done), "correct": 0}
    t_start = time.monotonic()

    async def get_ctx(db_id: str) -> DatabaseContext:
        async with ctx_lock:
            if db_id not in contexts:
                path = Path(db_root) / db_id / f"{db_id}.sqlite"
                ctx = await asyncio.to_thread(DatabaseContext.open, path, db_id)
                await asyncio.to_thread(lambda: ctx.values)  # build value index up front
                contexts[db_id] = ctx
            return contexts[db_id]

    async def one(it: Item) -> None:
        # One bad question must never kill a 500-question run: record the failure and move on.
        try:
            await _one(it)
        except Exception as exc:  # noqa: BLE001
            record = {
                "qid": it.qid,
                "db_id": it.db_id,
                "difficulty": it.difficulty,
                "question": it.question,
                "gold_sql": it.gold_sql,
                "harness_error": f"{type(exc).__name__}: {exc}"[:500],
            }
            # counted as a wrong answer everywhere (never silently dropped from EX)
            for variant in ("final", "greedy", "greedy_initial"):
                record[variant] = {"sql": "", "correct": False, "category": "harness_error"}
            record.update(
                confidence=0.0, elapsed_ms=0.0, llm_calls=0, prompt_tokens=0, completion_tokens=0
            )
            async with write_lock:
                with out_path.open("a") as f:
                    f.write(json.dumps(record) + "\n")
            print(f"[error] {it.qid}: {record['harness_error'][:120]}", flush=True)

    async def _one(it: Item) -> None:
        async with sem:
            ctx = await get_ctx(it.db_id)
            gold = await asyncio.to_thread(run_gold, ctx.path, it.gold_sql)
            record: dict = {
                "qid": it.qid,
                "db_id": it.db_id,
                "difficulty": it.difficulty,
                "question": it.question,
                "evidence": it.evidence,
                "gold_sql": it.gold_sql,
            }
            if not gold.ok:
                record["gold_error"] = gold.error
            else:
                res = await pipeline.run(ctx, it.question, it.evidence if use_evidence else None)
                tables = ctx.schema.table_names
                variants = {
                    "final": res.sql,
                    "greedy": res.greedy_sql,
                    "greedy_initial": res.greedy_initial_sql,
                }
                for name, sql in variants.items():
                    o = await asyncio.to_thread(score, ctx.path, sql, gold, tables)
                    record[name] = {"sql": sql, "correct": o.correct, "category": o.category}
                record.update(
                    {
                        "confidence": res.confidence,
                        "n_candidates": len(res.candidates),
                        "n_ok_candidates": sum(c.ok for c in res.candidates),
                        "repairs": sum(c.repairs for c in res.candidates),
                        "value_hints": res.value_hints,
                        "elapsed_ms": round(res.elapsed_ms, 1),
                        "llm_calls": res.llm_calls,
                        "prompt_tokens": res.prompt_tokens,
                        "completion_tokens": res.completion_tokens,
                        "pipeline_error": res.error,
                    }
                )
                counter["correct"] += record["final"]["correct"]
            async with write_lock:
                with out_path.open("a") as f:
                    f.write(json.dumps(record) + "\n")
                counter["n"] += 1
            if progress:
                el = time.monotonic() - t_start
                print(
                    f"[{counter['n']}/{len(items)}] {it.qid} {it.db_id} "
                    f"final={'✓' if record.get('final', {}).get('correct') else '✗'} "
                    f"({el / 60:.1f} min)",
                    flush=True,
                )

    await asyncio.gather(*(one(it) for it in todo))
    return out_path


def options_for(preset: str, **overrides) -> PipelineOptions:
    return PipelineOptions(**{**PRESETS[preset], **overrides})


def summarize(path: str | Path) -> dict:
    records = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    scored = [r for r in records if "final" in r]
    out: dict = {"n": len(scored), "gold_errors": len(records) - len(scored), "variants": {}}
    for variant in ("greedy_initial", "greedy", "final"):
        by_diff: dict[str, list[bool]] = {}
        for r in scored:
            by_diff.setdefault(r["difficulty"], []).append(r[variant]["correct"])
        allv = [r[variant]["correct"] for r in scored]
        out["variants"][variant] = {
            "ex": sum(allv) / len(allv) if allv else 0.0,
            "by_difficulty": {d: (sum(v) / len(v), len(v)) for d, v in sorted(by_diff.items())},
        }
    return out


def dump_config(
    path: Path, preset: str, options: PipelineOptions, model: str, dataset: str, use_evidence: bool
) -> None:
    path.write_text(
        json.dumps(
            {
                "preset": preset,
                "model": model,
                "dataset": dataset,
                "use_evidence": use_evidence,
                "options": asdict(options),
            },
            indent=2,
        )
    )


def rescore(
    results_path: str | Path, gold_items: list[Item], db_root: str | Path, out_path: str | Path
) -> Path:
    """Re-score the SQL already stored in a run against a different gold set (e.g. the
    expert-corrected Arcwise-Plat-SQL answers) without calling the model again."""
    from t2sql.db.introspect import introspect

    gold_by_id = {it.qid: it for it in gold_items}
    tables_cache: dict[str, list[str]] = {}
    out_path = Path(out_path)
    with out_path.open("w") as f:
        for line in Path(results_path).read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            it = gold_by_id.get(rec["qid"])
            if it is None or "final" not in rec:
                continue
            db_path = Path(db_root) / rec["db_id"] / f"{rec['db_id']}.sqlite"
            if rec["db_id"] not in tables_cache:
                tables_cache[rec["db_id"]] = introspect(db_path, n_examples=0).table_names
            gold = run_gold(db_path, it.gold_sql)
            new = {
                k: rec[k]
                for k in (
                    "qid",
                    "db_id",
                    "difficulty",
                    "question",
                    "confidence",
                    "elapsed_ms",
                    "llm_calls",
                    "prompt_tokens",
                    "completion_tokens",
                )
                if k in rec
            }
            new["gold_sql"] = it.gold_sql
            if not gold.ok:
                new["gold_error"] = gold.error
            else:
                for variant in ("final", "greedy", "greedy_initial"):
                    sql = rec[variant]["sql"]
                    o = score(db_path, sql, gold, tables_cache[rec["db_id"]])
                    new[variant] = {"sql": sql, "correct": o.correct, "category": o.category}
            f.write(json.dumps(new) + "\n")
    return out_path
