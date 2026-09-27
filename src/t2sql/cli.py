"""Command line: ask questions, run benchmarks, build reports, serve the API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from t2sql.config import get_settings
from t2sql.llm.client import LLMClient

app = typer.Typer(add_completion=False, help="Text-to-SQL: ask, eval, report, serve.")


def _client(model: str | None = None, base_url: str | None = None) -> LLMClient:
    s = get_settings()
    return LLMClient(
        base_url or s.llm_base_url,
        model or s.llm_model,
        s.llm_api_key,
        s.llm_timeout_s,
        s.llm_max_concurrency,
        s.llm_cache_path,
    )


@app.command()
def ask(
    db: Path = typer.Option(..., help="Path to a .sqlite file"),
    question: str = typer.Argument(...),
    evidence: str = typer.Option("", help="Optional domain hint"),
    candidates: int = typer.Option(5, help="Self-consistency samples"),
):
    """Answer one question against a SQLite database and print the SQL + rows."""
    from t2sql.db.executor import execute
    from t2sql.pipeline.context import DatabaseContext
    from t2sql.pipeline.pipeline import Pipeline, PipelineOptions

    async def go():
        llm = _client()
        try:
            ctx = DatabaseContext.open(db)
            res = await Pipeline(llm, PipelineOptions(n_candidates=candidates)).run(
                ctx, question, evidence or None
            )
        finally:
            await llm.aclose()
        typer.echo(f"\n{res.sql}\n\nconfidence={res.confidence}  value_hints={res.value_hints}")
        if res.sql:
            out = execute(db, res.sql, max_rows=20)
            typer.echo(
                json.dumps(
                    {"columns": out.columns, "rows": out.rows[:20], "error": out.error},
                    default=str,
                    indent=1,
                )
            )

    asyncio.run(go())


@app.command("eval")
def eval_cmd(
    data: Path = typer.Option(..., help="Dataset JSON (BIRD mini-dev / Spider format)"),
    db_root: Path = typer.Option(..., help="Folder with {db_id}/{db_id}.sqlite"),
    preset: str = typer.Option("full", help="bare | mschema | full"),
    out_dir: Path = typer.Option(Path("runs"), help="Where run folders go"),
    run_name: str = typer.Option("", help="Defaults to the preset name"),
    limit: int = typer.Option(0, help="Stratified subset size (0 = all)"),
    concurrency: int = typer.Option(2, help="Questions in flight"),
    no_evidence: bool = typer.Option(False, help="Drop BIRD evidence hints"),
    model: str = typer.Option("", help="Override T2SQL_LLM_MODEL"),
    base_url: str = typer.Option("", help="Override T2SQL_LLM_BASE_URL"),
    fewshot_pool: Path = typer.Option(
        Path("data/bird/train_filtered.jsonl"), help="JSONL pool of train-split examples"
    ),
):
    """Run a benchmark preset; results stream to runs/<name>/results.jsonl (resumable)."""
    from t2sql.eval.runner import (
        dump_config,
        load_dataset,
        options_for,
        run_benchmark,
        stratified_sample,
        summarize,
    )

    items = load_dataset(data)
    if limit:
        items = stratified_sample(items, limit)
    run_dir = out_dir / (run_name or preset)
    run_dir.mkdir(parents=True, exist_ok=True)
    opts = options_for(preset)
    fewshot = None
    if opts.n_fewshot:
        from t2sql.retrieval.fewshot import FewShotIndex

        # Never let an example come from a database we are evaluating on.
        fewshot = FewShotIndex.from_jsonl(fewshot_pool, exclude_dbs={it.db_id for it in items})
    llm = _client(model or None, base_url or None)
    dump_config(run_dir / "config.json", preset, opts, llm.model, str(data), not no_evidence)

    async def go():
        try:
            await run_benchmark(
                items,
                db_root,
                llm,
                opts,
                run_dir / "results.jsonl",
                use_evidence=not no_evidence,
                concurrency=concurrency,
                fewshot=fewshot,
            )
        finally:
            await llm.aclose()

    asyncio.run(go())
    typer.echo(json.dumps(summarize(run_dir / "results.jsonl"), indent=2))


@app.command("rescore")
def rescore_cmd(
    run_dir: Path = typer.Argument(..., help="A run folder containing results.jsonl"),
    gold: Path = typer.Option(
        Path("data/bird/mini_dev_arcwise.json"), help="Alternative gold set (same question ids)"
    ),
    db_root: Path = typer.Option(Path("data/bird/dev_databases")),
    name: str = typer.Option("arcwise", help="Suffix: writes results_<name>.jsonl"),
):
    """Score an existing run against another gold set, with no new LLM calls."""
    from t2sql.eval.runner import load_dataset, rescore, summarize

    out = rescore(
        run_dir / "results.jsonl", load_dataset(gold), db_root, run_dir / f"results_{name}.jsonl"
    )
    typer.echo(json.dumps(summarize(out), indent=2))


@app.command()
def report(runs_dir: Path = typer.Argument(Path("runs"))):
    """Build runs/REPORT.md from all runs in a folder."""
    from t2sql.eval.report import write_report

    typer.echo(f"wrote {write_report(runs_dir)}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the HTTP API."""
    import uvicorn

    uvicorn.run("t2sql.api.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
