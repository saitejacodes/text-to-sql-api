"""Public web API used by the React frontend (/api/*).

A thin layer over the same pipeline, guard and sandbox as /v1, with a flatter response that a
UI can render directly:

GET  /api/databases          demo databases with their tables and columns
GET  /api/examples?db_id=    example questions for one database
POST /api/query              question -> status (ok | blocked | error), SQL, rows, agreement

`status` separates the three things a user needs to tell apart: an answer, a query the security
layers refused (`blocked_reason` says why), and a failure (model down, unusable SQL).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from t2sql.config import get_settings
from t2sql.db.executor import execute
from t2sql.guard.sql_guard import check_sql
from t2sql.pipeline.pipeline import Pipeline, PipelineOptions

log = logging.getLogger("t2sql.api")

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api", tags=["web"])

QUERY_TOTAL = Counter("t2sql_query_total", "Web queries by outcome", ["status"])
LLM_CALLS = Counter("t2sql_llm_calls_total", "LLM calls made by web queries")
SANDBOX_BLOCKS = Counter("t2sql_sandbox_blocks_total", "Queries refused by the guard or sandbox")
QUERY_LATENCY = Histogram(
    "t2sql_query_latency_seconds",
    "End-to-end web query latency",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)

# Guard reasons that mean "refused for safety", as opposed to SQL the model simply got wrong.
_SECURITY_REASONS = (
    "forbidden",
    "only SELECT",
    "expected exactly one statement",
    "schema-qualified",
)


class TableInfo(BaseModel):
    name: str
    columns: list[str]


class DatabaseInfo(BaseModel):
    id: str
    name: str
    tables: list[TableInfo]


class ExamplesResponse(BaseModel):
    db_id: str
    questions: list[str]


class WebQueryRequest(BaseModel):
    db_id: str = Field(..., examples=["university"])
    question: str = Field(
        ..., min_length=3, max_length=500, examples=["Which instructors teach in the Stata Center?"]
    )


class WebQueryResponse(BaseModel):
    request_id: str
    status: Literal["ok", "blocked", "error"]
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    blocked_reason: str | None
    error: str | None
    agreement: float = Field(description="Share of candidates whose results agree with the answer.")
    candidates_considered: int
    repaired: bool
    latency_ms: float
    model: str


def _ctx(request: Request, db_id: str):
    try:
        return request.app.state.registry.get(db_id)
    except KeyError:
        raise HTTPException(404, f"unknown database '{db_id}'") from None


def _examples() -> dict[str, list[str]]:
    path = Path(get_settings().databases_dir) / "examples.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


@router.get("/databases", response_model=list[DatabaseInfo])
async def databases(request: Request):
    out = []
    for name in sorted(request.app.state.registry.available()):
        ctx = await asyncio.to_thread(_ctx, request, name)
        tables = [
            TableInfo(name=t.name, columns=[c.name for c in t.columns]) for t in ctx.schema.tables
        ]
        out.append(DatabaseInfo(id=name, name=name.replace("_", " ").title(), tables=tables))
    return out


@router.get("/examples", response_model=ExamplesResponse)
async def examples(request: Request, db_id: str = Query(...)):
    await asyncio.to_thread(_ctx, request, db_id)  # 404 for databases outside the allow-list
    return ExamplesResponse(db_id=db_id, questions=_examples().get(db_id, []))


@router.post("/query", response_model=WebQueryResponse)
@limiter.limit(lambda: get_settings().rate_limit)
async def query(body: WebQueryRequest, request: Request):
    t0 = time.monotonic()
    s = request.app.state.settings
    ctx = await asyncio.to_thread(_ctx, request, body.db_id)
    opts = PipelineOptions(
        n_candidates=s.n_candidates,
        temperature=s.candidate_temperature,
        max_repair_rounds=s.max_repair_rounds,
        use_value_hints=s.use_value_hints,
        exec_timeout_s=s.query_timeout_s,
    )
    out = await Pipeline(request.app.state.llm, opts).run(ctx, body.question)

    status, blocked_reason, error = "ok", None, None
    columns: list[str] = []
    rows: list[list] = []
    truncated = False
    # Repair feedback ("only SELECT is allowed") can turn a DELETE into a harmless SELECT; the
    # user still asked for a write, so a forbidden first attempt blocks the whole answer.
    first_tries = [check_sql(c.initial_sql, ctx.schema.table_names) for c in out.candidates]
    refused = next(
        (g for g in first_tries if not g.ok and g.reason.startswith(_SECURITY_REASONS)), None
    )
    sql = refused.sql if refused else out.sql
    if refused:
        status, blocked_reason = "blocked", refused.reason
    elif not out.sql:
        status, error = "error", out.error or "the model did not return a SQL query"
    else:
        guard = check_sql(out.sql, ctx.schema.table_names)
        if not guard.ok:
            if guard.reason.startswith(_SECURITY_REASONS):
                status, blocked_reason = "blocked", guard.reason
            else:
                status, error = "error", f"could not build a valid query: {guard.reason}"
        else:
            res = await asyncio.to_thread(execute, ctx.path, out.sql, s.query_timeout_s, s.max_rows)
            if res.ok:
                columns, rows, truncated = res.columns, [list(r) for r in res.rows], res.truncated
            elif "not authorized" in (res.error or ""):
                status, blocked_reason = "blocked", "refused by the read-only database sandbox"
            else:
                status, error = "error", res.error

    chosen = next((c for c in out.candidates if c.ok and c.sql == out.sql), None)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    resp = WebQueryResponse(
        request_id=request.state.request_id,
        status=status,
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        blocked_reason=blocked_reason,
        error=error,
        agreement=out.confidence,
        candidates_considered=len(out.candidates),
        repaired=status == "ok" and bool(chosen and chosen.repairs),
        latency_ms=latency_ms,
        model=f"{s.llm_provider or 'custom'}/{s.llm_model}",
    )

    QUERY_TOTAL.labels(status=status).inc()
    LLM_CALLS.inc(out.llm_calls)
    QUERY_LATENCY.observe(latency_ms / 1000)
    if status == "blocked":
        SANDBOX_BLOCKS.inc()
    # Questions can contain personal data, so only their length and a hash are logged.
    log.info(
        "query",
        extra={
            "extra_fields": {
                "id": resp.request_id,
                "db_id": body.db_id,
                "status": status,
                "latency_ms": latency_ms,
                "llm_calls": out.llm_calls,
                "prompt_tokens": out.prompt_tokens,
                "completion_tokens": out.completion_tokens,
                "repaired": resp.repaired,
                "agreement": out.confidence,
                "question_len": len(body.question),
                "question_sha": hashlib.sha256(body.question.encode()).hexdigest()[:12],
            }
        },
    )
    return resp
