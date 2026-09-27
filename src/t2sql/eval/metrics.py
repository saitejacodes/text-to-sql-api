"""Execution accuracy (EX) and an automatic error taxonomy.

EX follows the official BIRD evaluator: a prediction is correct iff
    set(rows(predicted)) == set(rows(gold))
i.e. row order and duplicates are ignored, column order is not. Both queries run under the same
timeout (BIRD's `meta_time_out` is 30 s).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from t2sql.db.executor import ExecResult, execute
from t2sql.guard.sql_guard import check_sql


@dataclass
class ExOutcome:
    correct: bool
    category: str  # "correct" or an error bucket
    pred_rows: int = 0
    error: str | None = None


def run_gold(db_path: Path, gold_sql: str, timeout_s: float = 30.0) -> ExecResult:
    return execute(db_path, gold_sql, timeout_s=timeout_s, max_rows=None)


def score(
    db_path: Path,
    pred_sql: str,
    gold: ExecResult,
    allowed_tables: list[str],
    timeout_s: float = 30.0,
) -> ExOutcome:
    if not pred_sql:
        return ExOutcome(False, "no_sql")
    guard = check_sql(pred_sql, allowed_tables)
    if not guard.ok:
        return ExOutcome(False, "guard:" + guard.reason.split(":")[0], error=guard.reason)
    pred = execute(db_path, pred_sql, timeout_s=timeout_s, max_rows=None)
    if not pred.ok:
        return ExOutcome(False, _exec_bucket(pred), error=pred.error)
    if set(pred.rows) == set(gold.rows):
        return ExOutcome(True, "correct", len(pred.rows))
    return ExOutcome(False, _result_bucket(pred, gold), len(pred.rows))


def _exec_bucket(res: ExecResult) -> str:
    msg = (res.error or "").lower()
    if res.timed_out:
        return "exec:timeout"
    if "no such column" in msg:
        return "exec:no_such_column"
    if "no such table" in msg:
        return "exec:no_such_table"
    if "syntax" in msg:
        return "exec:syntax"
    if "ambiguous" in msg:
        return "exec:ambiguous_column"
    return "exec:other"


def _result_bucket(pred: ExecResult, gold: ExecResult) -> str:
    p_cols = len(pred.rows[0]) if pred.rows else len(pred.columns)
    g_cols = len(gold.rows[0]) if gold.rows else len(gold.columns)
    if not pred.rows and gold.rows:
        return "wrong:empty_result"
    if p_cols != g_cols:
        return "wrong:extra_columns" if p_cols > g_cols else "wrong:missing_columns"
    if len(set(pred.rows)) != len(set(gold.rows)):
        return "wrong:row_count"
    return "wrong:values"
