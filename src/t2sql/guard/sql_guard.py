"""AST-level policy check for generated SQL, run before anything touches the database.

Why not keyword matching: `'DELETE' in sql.upper()` rejects `SELECT created_at ...` and
`WHERE status = 'Deleted'`, yet misses tricks like comment-split keywords. Parsing to an AST
answers the actual question: "is this exactly one read-only query over tables that exist?"

The executor enforces read-only access again inside SQLite (see t2sql.db.executor), so this
layer is about fast, explainable rejections that can be fed back to the model for repair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, SqlglotError

# Node types that must never appear anywhere in the tree (matched by class name so the check
# keeps working across sqlglot versions that add/rename some of these classes).
_FORBIDDEN = {
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Drop",
    "Create",
    "Alter",
    "AlterTable",
    "Truncate",
    "TruncateTable",
    "Command",
    "Pragma",
    "Attach",
    "Detach",
    "Transaction",
    "Commit",
    "Rollback",
    "Set",
    "Use",
    "Copy",
    "LoadData",
    "Grant",
    "Revoke",
    "Analyze",
}


# Functions that touch the filesystem, load native code, or leak engine internals.
_FORBIDDEN_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
    "sqlite_compileoption_get",
    "sqlite_compileoption_used",
    "sqlite_source_id",
}


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    sql: str = ""
    tables: list[str] = field(default_factory=list)


def check_sql(
    sql: str, allowed_tables: list[str] | None = None, dialect: str = "sqlite"
) -> GuardResult:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return GuardResult(False, "empty query")
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except ParseError as exc:
        first = exc.errors[0]["description"] if exc.errors else str(exc)
        return GuardResult(False, f"syntax error: {first}", sql)
    except SqlglotError as exc:  # e.g. TokenError on a backslash-escaped quote: 'Women\'s'
        return GuardResult(False, f"syntax error: {str(exc)[:200]}", sql)
    if len(statements) != 1:
        return GuardResult(False, f"expected exactly one statement, got {len(statements)}", sql)

    tree = statements[0]
    if not isinstance(tree, exp.Query):
        return GuardResult(False, f"only SELECT queries are allowed, got {tree.key.upper()}", sql)
    for node in tree.walk():
        if type(node).__name__ in _FORBIDDEN:
            return GuardResult(False, f"forbidden operation: {type(node).__name__.upper()}", sql)

    for fn in tree.find_all(exp.Func):
        name = (fn.name if isinstance(fn, exp.Anonymous) else fn.sql_name()).lower()
        if name in _FORBIDDEN_FUNCTIONS:
            return GuardResult(False, f"forbidden function: {name}", sql)

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = sorted(
        {t.name for t in tree.find_all(exp.Table) if t.name and t.name.lower() not in cte_names}
    )
    if allowed_tables is not None:
        allowed = {t.lower() for t in allowed_tables}
        unknown = [t for t in tables if t.lower() not in allowed]
        if unknown:
            return GuardResult(
                False,
                f"unknown table(s): {', '.join(unknown)}. Available: {', '.join(allowed_tables)}",
                sql,
                tables,
            )
        for t in tree.find_all(exp.Table):
            if t.args.get("db") or t.args.get("catalog"):
                return GuardResult(False, "schema-qualified tables are not allowed", sql, tables)

    return GuardResult(True, "", sql, tables)
