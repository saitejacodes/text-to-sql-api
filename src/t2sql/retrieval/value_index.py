"""Value retrieval: find database cell values that the question refers to.

Most wrong-but-runnable SQL on real databases is a literal mismatch: the question says
"alameda county", the column stores 'Alameda'; the question says "female", the column stores 'F'.
The model cannot know the stored spelling from column names alone, so we index the distinct text
values of every column and surface the ones that fuzzily appear in the question, e.g.

    schools.County = 'Alameda'

The index is an inverted index (token -> values) plus rapidfuzz scoring on the candidates, which
keeps lookups in the low milliseconds even for databases with hundreds of thousands of values.
It is built once per database file and cached on disk.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from t2sql.db.executor import connect_readonly

_TOKEN = re.compile(r"[a-z0-9]+(?:['.-][a-z0-9]+)*")
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "for",
    "to",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "what",
    "which",
    "who",
    "whom",
    "how",
    "many",
    "much",
    "list",
    "show",
    "give",
    "name",
    "names",
    "with",
    "by",
    "from",
    "at",
    "as",
    "that",
    "this",
    "these",
    "those",
    "all",
    "each",
    "their",
    "its",
    "his",
    "her",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "be",
    "been",
    "it",
    "than",
    "more",
    "most",
    "less",
    "least",
    "number",
    "please",
    "find",
    "among",
    "between",
    "any",
    "there",
    "not",
    "no",
    "yes",
    "id",
    "ids",
    "per",
    "total",
    "average",
    "percentage",
    "count",
}
_SHORT_NUMBER = re.compile(r"[+-]?\d{1,3}(?:\.\d+)?")
_MAX_VALUES_PER_COLUMN = 50_000
_MAX_POSTING = 3_000  # tokens this common ("school", "inc") carry no signal


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class ValueMatch:
    table: str
    column: str
    value: str
    score: float

    def render(self) -> str:
        v = self.value.replace("'", "''")
        return f"`{self.table}`.`{self.column}` = '{v}'"


class ValueIndex:
    def __init__(self, values: list[tuple[str, str, str]]):
        self.values = values  # (table, column, value)
        self.postings: dict[str, list[int]] = {}
        for i, (_, _, v) in enumerate(values):
            for tok in set(_tokens(v)):
                if tok not in _STOP:
                    self.postings.setdefault(tok, []).append(i)

    @classmethod
    def build(cls, db_path: str | Path) -> ValueIndex:
        conn = connect_readonly(db_path)
        values: list[tuple[str, str, str]] = []
        try:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for t in tables:
                qt = '"' + t.replace('"', '""') + '"'
                for _cid, col, ctype, *_ in conn.execute(f"PRAGMA table_info({qt})"):
                    ctype = (ctype or "").upper()
                    if any(
                        k in ctype
                        for k in (
                            "INT",
                            "REAL",
                            "FLOA",
                            "DOUB",
                            "NUM",
                            "DEC",
                            "DATE",
                            "TIME",
                            "BLOB",
                            "BOOL",
                        )
                    ):
                        continue
                    qc = '"' + col.replace('"', '""') + '"'
                    try:
                        rows = conn.execute(
                            f"SELECT DISTINCT {qc} FROM {qt} WHERE typeof({qc})='text' "
                            f"AND length({qc}) BETWEEN 1 AND 80 LIMIT {_MAX_VALUES_PER_COLUMN}"
                        ).fetchall()
                    except Exception:
                        continue
                    for (v,) in rows:
                        v = str(v).strip()
                        if v and not v.startswith(("http://", "https://")):
                            values.append((t, col, v))
        finally:
            conn.close()
        return cls(values)

    @classmethod
    def load_or_build(cls, db_path: str | Path, cache_dir: str | Path | None = None) -> ValueIndex:
        db_path = Path(db_path)
        st = db_path.stat()
        tag = hashlib.sha1(
            f"{db_path.resolve()}:{st.st_size}:{st.st_mtime_ns}".encode()
        ).hexdigest()
        cache_dir = cache_dir or os.environ.get("T2SQL_VALUE_CACHE", ".cache/values")
        cache = Path(cache_dir) / f"{db_path.stem}-{tag[:12]}.pkl"
        if cache.exists():
            with cache.open("rb") as f:
                return pickle.load(f)
        index = cls.build(db_path)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as f:
            pickle.dump(index, f)
        return index

    def search(
        self, question: str, k: int = 12, per_column: int = 2, min_score: float = 88.0
    ) -> list[ValueMatch]:
        q_lower = question.lower()
        q_tokens = [t for t in _tokens(question) if t not in _STOP]
        if not q_tokens:
            return []

        candidates: set[int] = set()
        for tok in q_tokens:
            posting = self.postings.get(tok)
            if posting and len(posting) <= _MAX_POSTING:
                candidates.update(posting)

        q_token_set = set(q_tokens)
        scored: list[ValueMatch] = []
        for i in candidates:
            table, col, value = self.values[i]
            v_lower = value.lower()
            # Short bare numbers in a question are quantities ("top 5") or date parts
            # ("1994/2/19"), not category labels; matching them to a text column such as
            # `Low Grade` = '5' injects filters nobody asked for. Numeric literals need no hint.
            if _SHORT_NUMBER.fullmatch(value.strip()) or len(value.strip()) < 2:
                continue
            v_tokens = [t for t in _tokens(value) if t not in _STOP]
            if not v_tokens:
                continue
            coverage = sum(t in q_token_set for t in v_tokens) / len(v_tokens)
            if coverage < 0.5:
                continue
            # Exact containment beats fuzzy; fuzzy catches plurals/case/punctuation drift.
            if re.search(r"(?<![a-z0-9])" + re.escape(v_lower) + r"(?![a-z0-9])", q_lower):
                score = 100.0
            else:
                score = fuzz.partial_ratio(v_lower, q_lower) * (0.5 + 0.5 * coverage)
            if score >= min_score:
                scored.append(ValueMatch(table, col, value, round(score, 1)))

        # Prefer high score, then longer (more specific) values.
        scored.sort(key=lambda m: (-m.score, -len(m.value)))
        out: list[ValueMatch] = []
        per_col: dict[tuple[str, str], int] = {}
        seen_values: set[str] = set()
        for m in scored:
            key = (m.table, m.column)
            if per_col.get(key, 0) >= per_column:
                continue
            # a value repeated across many columns (e.g. 'Yes') is only shown for its best columns
            if sum(1 for o in out if o.value == m.value) >= 2 or (
                m.value in seen_values and len(m.value) < 4
            ):
                continue
            per_col[key] = per_col.get(key, 0) + 1
            seen_values.add(m.value)
            out.append(m)
            if len(out) >= k:
                break
        return out
