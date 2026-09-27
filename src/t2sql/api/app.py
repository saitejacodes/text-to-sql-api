"""HTTP API.

GET  /health                         liveness + which model is configured
GET  /v1/databases                   databases this service may query
GET  /v1/databases/{db}/schema       the schema exactly as the model sees it
POST /v1/query                       question -> SQL (+ rows, confidence, candidate trace)
POST /v1/validate                    run the SQL guard on hand-written SQL
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from t2sql import __version__
from t2sql.config import get_settings
from t2sql.db.executor import execute
from t2sql.guard.sql_guard import check_sql
from t2sql.llm.client import LLMClient, LLMError
from t2sql.pipeline.context import DatabaseRegistry
from t2sql.pipeline.pipeline import Pipeline, PipelineOptions

log = logging.getLogger("t2sql.api")


class QueryRequest(BaseModel):
    db: str = Field(..., examples=["university"])
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        examples=["Which instructors teach in the Stata Center?"],
    )
    evidence: str | None = Field(
        None, max_length=2000, description="Optional domain hint, e.g. a metric definition."
    )
    execute: bool = True
    n_candidates: int | None = Field(None, ge=1, le=10)


class ResultTable(BaseModel):
    columns: list[str]
    rows: list[list]
    truncated: bool
    elapsed_ms: float


class CandidateOut(BaseModel):
    sql: str
    ok: bool
    rows: int
    repairs: int
    error: str | None


class QueryResponse(BaseModel):
    request_id: str
    sql: str
    confidence: float = Field(
        description="Share of candidates whose results agree with the answer."
    )
    result: ResultTable | None
    error: str | None
    value_hints: list[str]
    candidates: list[CandidateOut]
    llm_calls: int
    elapsed_ms: float


class ValidateRequest(BaseModel):
    db: str
    sql: str = Field(..., max_length=20_000)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("t2sql")
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    s = get_settings()
    app.state.settings = s
    app.state.registry = DatabaseRegistry(s.databases_dir)
    app.state.llm = LLMClient(
        s.llm_base_url,
        s.llm_model,
        s.llm_api_key,
        s.llm_timeout_s,
        s.llm_max_concurrency,
        s.llm_cache_path,
    )
    log.info(
        "started",
        extra={
            "extra_fields": {
                "model": s.llm_model,
                "databases": list(app.state.registry.available()),
            }
        },
    )
    yield
    await app.state.llm.aclose()


app = FastAPI(title="t2sql — Text-to-SQL API", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    keys = {k.strip() for k in get_settings().api_keys.split(",") if k.strip()}
    if (
        keys
        and request.url.path.startswith("/v1")
        and (request.headers.get("x-api-key") not in keys)
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "missing or invalid X-API-Key"},
            headers={"x-request-id": rid},
        )
    t0 = time.monotonic()
    response = await call_next(request)
    ms = (time.monotonic() - t0) * 1000
    response.headers["x-request-id"] = rid
    response.headers["x-process-time-ms"] = f"{ms:.1f}"
    log.info(
        "request",
        extra={
            "extra_fields": {
                "id": rid,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round(ms, 1),
            }
        },
    )
    return response


@app.exception_handler(LLMError)
async def llm_error(_: Request, exc: LLMError):
    return JSONResponse(status_code=503, content={"detail": f"LLM unavailable: {exc}"})


def _ctx(request: Request, db: str):
    try:
        return request.app.state.registry.get(db)
    except KeyError:
        raise HTTPException(404, f"unknown database '{db}'") from None


_STATIC = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def playground():
    return FileResponse(_STATIC / "index.html")


@app.get("/health")
async def health(request: Request):
    s = request.app.state.settings
    return {"status": "ok", "version": __version__, "model": s.llm_model}


@app.get("/v1/databases")
async def databases(request: Request):
    return {"databases": sorted(request.app.state.registry.available())}


@app.get("/v1/databases/{db}/schema")
async def schema(db: str, request: Request):
    ctx = await asyncio.to_thread(_ctx, request, db)
    return {"db": db, "tables": ctx.schema.table_names, "prompt_schema": ctx.schema.render()}


@app.post("/v1/validate")
async def validate(body: ValidateRequest, request: Request):
    ctx = await asyncio.to_thread(_ctx, request, body.db)
    res = check_sql(body.sql, ctx.schema.table_names)
    return {"ok": res.ok, "reason": res.reason, "tables": res.tables}


@app.post("/v1/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request):
    s = request.app.state.settings
    ctx = await asyncio.to_thread(_ctx, request, body.db)
    opts = PipelineOptions(
        n_candidates=body.n_candidates or s.n_candidates,
        temperature=s.candidate_temperature,
        max_repair_rounds=s.max_repair_rounds,
        use_value_hints=s.use_value_hints,
        exec_timeout_s=s.query_timeout_s,
    )
    out = await Pipeline(request.app.state.llm, opts).run(ctx, body.question, body.evidence)

    result, error = None, out.error
    if out.sql and body.execute:
        guard = check_sql(out.sql, ctx.schema.table_names)
        if not guard.ok:
            error = guard.reason
        else:
            res = await asyncio.to_thread(execute, ctx.path, out.sql, s.query_timeout_s, s.max_rows)
            if res.ok:
                result = ResultTable(
                    columns=res.columns,
                    rows=[list(r) for r in res.rows],
                    truncated=res.truncated,
                    elapsed_ms=round(res.elapsed_ms, 2),
                )
            else:
                error = res.error

    return QueryResponse(
        request_id=request.state.request_id,
        sql=out.sql,
        confidence=out.confidence,
        result=result,
        error=error,
        value_hints=out.value_hints,
        candidates=[
            CandidateOut(sql=c.sql, ok=c.ok, rows=c.row_count, repairs=c.repairs, error=c.error)
            for c in out.candidates
        ],
        llm_calls=out.llm_calls,
        elapsed_ms=round(out.elapsed_ms, 1),
    )
