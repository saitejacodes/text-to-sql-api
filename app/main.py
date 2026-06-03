import time
import logging
import json
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

from app.models import (
    RetrieveRequest, RetrieveResponse,
    GenerateSqlRequest, GenerateSqlResponse, ExecutionResult,
    BenchmarkResponse,
)
from app.database import init_database, execute_query
from app.retrieval import retriever
from app.llm import generate_sql
from app.validation import validate_sql
from app.metrics_layer import run_benchmark

# ── Structured JSON logging ──────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "time":   self.formatTime(record, self.datefmt),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        })

def _setup_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG)
    fmt = JsonFormatter()
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/app.log")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger

logger = _setup_logger()

# ── Lifespan: startup / shutdown ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database and embedding model...")
    init_database()
    logger.info("Database ready.")
    retriever.load_model()
    logger.info("Embedding model loaded. Server is ready.")
    yield
    logger.info("Shutting down.")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Enterprise Text-to-SQL API",
    description=(
        "Converts natural language questions into executable SQL queries "
        "using semantic schema retrieval and an LLM generation layer. "
        "Built on the BEAVER benchmark dataset."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        response.headers["X-Process-Time-ms"] = f"{(time.time() - t0) * 1000:.2f}"
        return response

app.add_middleware(TimingMiddleware)

# ── Exception handlers ─────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exc_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url, exc)
    return JSONResponse(status_code=500, content={"message": "Internal server error", "details": str(exc)})

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"message": "Bad request", "details": str(exc)})

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"], summary="Health check")
async def health():
    """Returns service status."""
    return {"status": "ok", "service": "Text-to-SQL API", "version": "1.0.0"}


@app.post(
    "/retrieve",
    response_model=RetrieveResponse,
    tags=["Core"],
    summary="Retrieve relevant tables for a natural language question",
)
async def retrieve_endpoint(request: RetrieveRequest):
    """
    Uses semantic similarity (BAAI/bge-large-en-v1.5 with hybrid keyword boost) to identify
    the most relevant database tables for the given question.
    """
    q = request.question.strip()
    logger.info("/retrieve — question: %r", q)
    tables, scores, confidence, details = retriever.retrieve_tables(q)
    return RetrieveResponse(
        retrieved_tables=tables,
        scores=scores,
        confidence=confidence,
        details=details,
    )


@app.post(
    "/generate-sql",
    response_model=GenerateSqlResponse,
    tags=["Core"],
    summary="Generate and execute a SQL query from a natural language question",
)
async def generate_sql_endpoint(request: GenerateSqlRequest):
    """
    Full pipeline: semantic retrieval → LLM prompt → SQL generation
    → syntax validation → query execution. Returns SQL + results.
    """
    q = request.question.strip()
    logger.info("/generate-sql — question: %r", q)

    # 1. Retrieval
    retrieved_tables, retrieved_schemas, confidence = [], {}, 1.0
    if request.use_retrieved_context:
        retrieved_tables, _, confidence, _ = retriever.retrieve_tables(q)
        retrieved_schemas = retriever.get_schema_for_tables(retrieved_tables)

    # 2. Generate SQL
    sql, prompt = generate_sql(q, retrieved_tables, retrieved_schemas)

    # 3. Validate
    is_valid, err_msg, norm_sql, _ = validate_sql(sql)
    final_sql = norm_sql if is_valid else sql

    # 4. Execute (always attempt — results help the user and satisfy the spec)
    exec_ok, cols, rows, row_count, latency_ms, exec_err = execute_query(final_sql)
    execution_result = ExecutionResult(
        success=exec_ok,
        columns=cols,
        rows=[list(r) for r in rows],
        row_count=row_count,
        execution_time_ms=round(latency_ms, 2),
        error=exec_err,
    )

    logger.info("/generate-sql — valid=%s exec=%s sql=%r", is_valid, exec_ok, final_sql[:80])

    return GenerateSqlResponse(
        sql=final_sql,
        retrieved_tables=retrieved_tables,
        is_valid_syntax=is_valid,
        parsing_errors=err_msg if not is_valid else None,
        confidence=confidence,
        prompt_used=prompt,
        execution_result=execution_result,
    )


@app.post(
    "/benchmark",
    response_model=BenchmarkResponse,
    tags=["Evaluation"],
    summary="Run full benchmark evaluation on 30 curated queries",
)
async def benchmark_endpoint():
    """
    Evaluates the end-to-end pipeline on benchmark queries (Beaver dataset if available,
    otherwise 20 curated custom queries). Reports retrieval recall, SQL accuracy,
    latency, and detailed error analysis.
    """
    logger.info("/benchmark — starting evaluation run")
    result = run_benchmark()
    logger.info("/benchmark — done. total_queries=%d", result.total_queries)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)