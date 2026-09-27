"""The generation pipeline: prompt -> N candidates -> guard -> execute -> repair -> vote.

    question ──► value retrieval ──► M-Schema prompt ──► N candidates (1 greedy + N-1 sampled)
                                                            │
                          ┌─────────── per candidate ───────┤
                          ▼                                  │
                   AST guard ──► sandboxed execution ──► error? ──► repair with feedback (≤ k)
                                                            │
                                   group candidates by execution result, pick the largest group

Voting on *results* rather than SQL text is the key idea from self-consistency for SQL:
two differently written queries that return the same rows count as agreement. The size of the
winning group is also a useful confidence score (reported and calibrated in the eval).

Every step is recorded on the result so the eval can derive ablations ("greedy only",
"no repair") from a single run without paying for extra LLM calls.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field

from t2sql.db.executor import ExecResult, execute
from t2sql.guard.sql_guard import check_sql
from t2sql.llm.client import LLMClient, LLMError
from t2sql.llm.prompts import build_generation_prompt, build_repair_prompt, extract_sql
from t2sql.pipeline.context import DatabaseContext
from t2sql.retrieval.fewshot import FewShotIndex


@dataclass
class PipelineOptions:
    n_candidates: int = 5
    temperature: float = 0.7
    max_repair_rounds: int = 2
    use_value_hints: bool = True
    schema_examples: int = 3
    schema_descriptions: bool = True
    exec_timeout_s: float = 10.0
    signature_max_rows: int = 10_000
    max_tokens: int = 1024
    n_fewshot: int = 0
    repair_empty: bool = True  # ask once for a revision when a query returns no/only-NULL rows


@dataclass
class Candidate:
    index: int
    temperature: float
    initial_sql: str = ""
    initial_ok: bool = False
    initial_signature: str | None = None
    sql: str = ""
    ok: bool = False
    signature: str | None = None
    row_count: int = 0
    error: str | None = None
    repairs: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class PipelineResult:
    sql: str
    confidence: float
    candidates: list[Candidate]
    value_hints: list[str]
    prompt: list[dict]
    elapsed_ms: float
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    extras: dict = field(default_factory=dict)

    @property
    def greedy_initial_sql(self) -> str:
        return self.candidates[0].initial_sql if self.candidates else ""

    @property
    def greedy_sql(self) -> str:
        return self.candidates[0].sql if self.candidates else ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["greedy_initial_sql"] = self.greedy_initial_sql
        d["greedy_sql"] = self.greedy_sql
        return d


def _is_empty(res: ExecResult) -> bool:
    return not res.rows or all(v is None for row in res.rows for v in row)


def result_signature(res: ExecResult) -> str:
    """Order-insensitive fingerprint of a result set (BIRD compares results as sets)."""

    def norm(v):
        if isinstance(v, float):
            return round(v, 6)
        return v

    rows = {tuple(norm(v) for v in row) for row in res.rows}
    return repr(sorted(rows, key=repr))


class Pipeline:
    def __init__(
        self,
        llm: LLMClient,
        options: PipelineOptions | None = None,
        fewshot: FewShotIndex | None = None,
    ):
        self.llm = llm
        self.opt = options or PipelineOptions()
        self.fewshot = fewshot

    def build_prompt(
        self, ctx: DatabaseContext, question: str, evidence: str | None = None
    ) -> tuple[list[dict], list[str]]:
        hints: list[str] = []
        if self.opt.use_value_hints:
            hints = [m.render() for m in ctx.values.search(f"{question} {evidence or ''}")]
        schema_text = ctx.schema.render(
            max_examples=self.opt.schema_examples, with_descriptions=self.opt.schema_descriptions
        )
        examples = []
        if self.fewshot is not None and self.opt.n_fewshot > 0:
            examples = [e.render() for e in self.fewshot.search(question, k=self.opt.n_fewshot)]
        return build_generation_prompt(schema_text, question, evidence, hints, examples), hints

    async def run(
        self, ctx: DatabaseContext, question: str, evidence: str | None = None
    ) -> PipelineResult:
        t0 = time.monotonic()
        messages, hints = await asyncio.to_thread(self.build_prompt, ctx, question, evidence)

        n = max(1, self.opt.n_candidates)
        cands = [Candidate(i, 0.0 if i == 0 else self.opt.temperature) for i in range(n)]
        # Candidates run one after another on purpose: they share the whole prompt, so a local
        # server (llama.cpp/Ollama) reuses the cached prefix and each extra sample only costs its
        # completion. Running them in parallel slots re-processes the prompt every time.
        fatal: LLMError | None = None
        for c in cands:
            try:
                await self._run_candidate(ctx, messages, c)
            except LLMError as exc:
                fatal = exc
                break
        if fatal and not any(c.initial_sql for c in cands):
            return PipelineResult(
                "", 0.0, cands, hints, messages, (time.monotonic() - t0) * 1000, error=str(fatal)
            )

        chosen, confidence = self._select(cands)
        return PipelineResult(
            sql=chosen.sql if chosen else cands[0].sql,
            confidence=confidence,
            candidates=cands,
            value_hints=hints,
            prompt=messages,
            elapsed_ms=(time.monotonic() - t0) * 1000,
            llm_calls=sum(c.llm_calls for c in cands),
            prompt_tokens=sum(c.prompt_tokens for c in cands),
            completion_tokens=sum(c.completion_tokens for c in cands),
        )

    async def _run_candidate(
        self, ctx: DatabaseContext, messages: list[dict], cand: Candidate
    ) -> None:
        reply = await self.llm.chat(
            messages, temperature=cand.temperature, seed=cand.index, max_tokens=self.opt.max_tokens
        )
        self._account(cand, reply)
        sql = extract_sql(reply.text)
        cand.initial_sql = sql
        ok, feedback, res = await asyncio.to_thread(self._check_and_execute, ctx, sql)
        cand.initial_ok = ok
        cand.initial_signature = result_signature(res) if ok and res else None

        rounds = 0
        while not ok and rounds < self.opt.max_repair_rounds:
            rounds += 1
            repair_msgs = build_repair_prompt(messages, sql, feedback)
            reply = await self.llm.chat(
                repair_msgs, temperature=0.0, seed=cand.index, max_tokens=self.opt.max_tokens
            )
            self._account(cand, reply)
            new_sql = extract_sql(reply.text)
            if not new_sql or new_sql == sql:
                break
            sql = new_sql
            ok, feedback, res = await asyncio.to_thread(self._check_and_execute, ctx, sql)

        # A query that runs but returns nothing (or only NULLs) is usually a wrong join path or
        # a literal in the wrong format. Ask once for a revision; keep it only if it returns rows.
        if (
            ok
            and res is not None
            and _is_empty(res)
            and self.opt.repair_empty
            and (self.opt.max_repair_rounds > 0)
        ):
            rounds += 1
            feedback = (
                "it ran but returned no rows (or only NULL values). Re-check the join "
                "path and that literal values match the stored format shown in the "
                "Examples / Value matches"
            )
            reply = await self.llm.chat(
                build_repair_prompt(messages, sql, feedback),
                temperature=0.0,
                seed=cand.index,
                max_tokens=self.opt.max_tokens,
            )
            self._account(cand, reply)
            new_sql = extract_sql(reply.text)
            if new_sql and new_sql != sql:
                new_ok, _, new_res = await asyncio.to_thread(self._check_and_execute, ctx, new_sql)
                if new_ok and new_res is not None and not _is_empty(new_res):
                    sql, res = new_sql, new_res

        cand.sql, cand.ok, cand.repairs = sql, ok, rounds
        if ok and res is not None:
            cand.signature = result_signature(res)
            cand.row_count = 0 if _is_empty(res) else len(res.rows)
        else:
            cand.error = feedback

    @staticmethod
    def _account(cand: Candidate, reply) -> None:
        cand.llm_calls += 1
        if not getattr(reply, "cached", False):
            cand.prompt_tokens += reply.prompt_tokens
            cand.completion_tokens += reply.completion_tokens

    def _check_and_execute(
        self, ctx: DatabaseContext, sql: str
    ) -> tuple[bool, str, ExecResult | None]:
        guard = check_sql(sql, allowed_tables=ctx.schema.table_names)
        if not guard.ok:
            return False, guard.reason, None
        res = execute(
            ctx.path, sql, timeout_s=self.opt.exec_timeout_s, max_rows=self.opt.signature_max_rows
        )
        if not res.ok:
            return False, res.error or "execution failed", res
        return True, "", res

    @staticmethod
    def _select(cands: list[Candidate]) -> tuple[Candidate | None, float]:
        groups: dict[str, list[Candidate]] = {}
        for c in cands:
            if c.ok and c.signature is not None:
                groups.setdefault(c.signature, []).append(c)
        if not groups:
            return None, 0.0

        # Non-empty results beat empty ones; then bigger groups; then the group holding the
        # earliest (greedy) candidate.
        def rank(item):
            sig, members = item
            return (members[0].row_count > 0, len(members), -min(m.index for m in members))

        _, best = max(groups.items(), key=rank)
        chosen = min(best, key=lambda c: c.index)
        return chosen, round(len(best) / len(cands), 3)
