"""Prompt templates. Kept free of any benchmark-specific examples: nothing in here is copied from
an evaluation set, so reported numbers measure generalisation, not memorisation."""

from __future__ import annotations

import re

SYSTEM = (
    "You are an expert data analyst who writes correct, minimal SQLite queries. "
    "You answer with exactly one SQL query."
)

RULES = """Rules:
- SQLite dialect; exactly one SELECT statement (CTEs allowed).
- Return only the columns the question asks for, in the order it asks for them. No extra columns.
- Use the exact table/column names from the schema; quote names containing spaces with backticks.
- When filtering on text, use the exact stored spelling shown in 【Value matches】 or Examples.
- For "highest/lowest/top" questions use ORDER BY ... LIMIT n, and exclude NULLs in the sort key.
- For ratios and percentages, CAST to REAL before dividing.
- Use JOINs only along the listed foreign keys unless the question clearly needs another link."""


def build_generation_prompt(
    schema_text: str,
    question: str,
    evidence: str | None = None,
    value_hints: list[str] | None = None,
    examples: list[str] | None = None,
) -> list[dict]:
    parts = []
    if examples:
        parts.append(
            "【Examples】 (question/SQL pairs from OTHER databases, for SQL style only)\n"
            + "\n\n".join(examples)
        )
    parts.append(schema_text)
    if value_hints:
        parts.append(
            "【Value matches】 (values found in the database, exact spelling)\n"
            + "\n".join(f"- {h}" for h in value_hints)
        )
    if evidence:
        parts.append(f"【Hint】 {evidence}")
    parts.append(f"【Question】 {question}")
    parts.append(RULES)
    parts.append(
        "Think briefly about which tables, joins and filters are needed, then write the "
        "final query in a ```sql code block."
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n\n".join(parts)}]


def build_repair_prompt(
    generation_messages: list[dict],
    failed_sql: str,
    feedback: str,
) -> list[dict]:
    return generation_messages + [
        {"role": "assistant", "content": f"```sql\n{failed_sql}\n```"},
        {
            "role": "user",
            "content": (
                f"That query failed: {feedback}\n"
                "Fix it. Check table and column names against the schema. "
                "Reply with the corrected query in a ```sql code block."
            ),
        },
    ]


_FENCE = re.compile(r"```(?:sql|sqlite)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_SELECT = re.compile(r"\b(WITH|SELECT)\b.*", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Pull the final SQL out of a model reply (last fenced block wins; reasoning is ignored)."""
    text = _THINK.sub("", text or "")
    blocks = [b.strip() for b in _FENCE.findall(text) if b.strip()]
    if blocks:
        sql = blocks[-1]
    else:
        m = _SELECT.search(text)
        sql = m.group(0) if m else text
    sql = sql.strip().rstrip(";").strip()
    # keep only the first statement if the model rambled on after it
    return sql.split(";")[0].strip() if ";" in sql and not _in_quotes(sql) else sql


def _in_quotes(sql: str) -> bool:
    """Crude check: are there semicolons inside string literals? Then don't split."""
    inside = False
    for ch in sql:
        if ch == "'":
            inside = not inside
        elif ch == ";" and inside:
            return True
    return False
