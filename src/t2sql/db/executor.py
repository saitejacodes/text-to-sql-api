"""Sandboxed SQLite execution.

Generated SQL is untrusted input. The AST guard (t2sql.guard) rejects anything that isn't a single
read-only query, but a parser can be fooled, so the database layer enforces the same policy again:

1. the file is opened read-only via a `mode=ro` URI (the OS-level handle cannot write),
2. `PRAGMA query_only` blocks writes even through virtual tables,
3. an authorizer callback allows only SELECT/READ/FUNCTION/RECURSIVE actions, so ATTACH,
   PRAGMA, temp-table creation and friends are denied inside the SQLite engine itself,
4. a progress handler aborts queries that exceed a wall-clock budget, and
5. rows are fetched with a cap so one query cannot exhaust memory.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"database not found: {path}")
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    return conn


def _authorizer(action: int, *_args: Any) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


@dataclass
class ExecResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    elapsed_ms: float = 0.0
    error: str | None = None
    timed_out: bool = False


def execute(
    db_path: str | Path,
    sql: str,
    timeout_s: float = 5.0,
    max_rows: int | None = 1000,
) -> ExecResult:
    """Run one query under the sandbox. `max_rows=None` fetches everything (evaluation only)."""
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    try:
        conn = connect_readonly(db_path)
    except (FileNotFoundError, sqlite3.Error) as exc:
        return ExecResult(ok=False, error=str(exc))
    conn.set_authorizer(_authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        if max_rows is None:
            rows = cur.fetchall()
            truncated = False
        else:
            rows = cur.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            rows = rows[:max_rows]
        return ExecResult(True, columns, rows, truncated, (time.monotonic() - t0) * 1000)
    except sqlite3.OperationalError as exc:
        timed_out = "interrupted" in str(exc)
        msg = f"query exceeded {timeout_s:.1f}s timeout" if timed_out else str(exc)
        return ExecResult(
            False, elapsed_ms=(time.monotonic() - t0) * 1000, error=msg, timed_out=timed_out
        )
    except sqlite3.DatabaseError as exc:  # includes "not authorized"
        return ExecResult(False, elapsed_ms=(time.monotonic() - t0) * 1000, error=str(exc))
    except Exception as exc:  # e.g. sqlite3.Warning for multiple statements
        return ExecResult(
            False, elapsed_ms=(time.monotonic() - t0) * 1000, error=f"{type(exc).__name__}: {exc}"
        )
    finally:
        conn.close()
