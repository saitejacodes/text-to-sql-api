"""Few-shot example retrieval (DAIL-SQL style), from a pool that never overlaps the eval set.

v1 retrieved few-shot examples from the same 10 questions it was benchmarked on, so the model
was shown the answers. Here the pool is BIRD's *train* split (bird23-train-filtered: 6,601
question/SQL pairs over 69 databases that are disjoint from the dev/mini-dev databases), so an
example can teach SQL patterns ("ratio -> CAST ... AS REAL", "top n -> ORDER BY LIMIT") but
can never contain the answer.

Similarity follows DAIL-SQL's key idea: mask domain-specific tokens (literals, numbers, proper
nouns) so questions are matched on *structure* ("what is the ratio of X to Y") rather than
topic, then rank with BM25.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TOKEN = re.compile(r"<mask>|[a-z]+")
_STOP = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "is",
    "are",
    "was",
    "to",
    "and",
    "for",
    "by",
    "with",
    "that",
    "which",
    "what",
    "as",
    "at",
    "be",
    "it",
    "its",
    "their",
    "this",
}


def mask_question(q: str) -> str:
    q = re.sub(r"'[^']*'|\"[^\"]*\"", " <mask> ", q)
    q = re.sub(r"\d+(\.\d+)?%?", " <mask> ", q)
    # Capitalised words not at sentence start are usually entity names.
    q = re.sub(r"(?<=[a-z,;:] )[A-Z][\w.-]*(?: [A-Z][\w.-]*)*", "<mask>", q)
    return q.lower()


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text) if t not in _STOP]


@dataclass
class Example:
    question: str
    evidence: str
    sql: str
    db_id: str

    def render(self) -> str:
        ev = f"\nHint: {self.evidence}" if self.evidence else ""
        return f"Question: {self.question}{ev}\nSQL: {self.sql}"


class FewShotIndex:
    def __init__(self, examples: list[Example], exclude_dbs: set[str] | None = None):
        exclude = exclude_dbs or set()
        self.examples = [e for e in examples if e.db_id not in exclude]
        self.docs = [_tokens(mask_question(e.question)) for e in self.examples]
        n = len(self.docs)
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.avgdl = sum(map(len, self.docs)) / max(1, n)
        self.tfs = [Counter(d) for d in self.docs]

    @classmethod
    def from_jsonl(cls, path: str | Path, exclude_dbs: set[str] | None = None) -> FewShotIndex:
        examples = []
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            sql = " ".join((d.get("SQL") or d.get("query") or "").split())
            if sql and len(sql) < 600:
                examples.append(Example(d["question"], d.get("evidence") or "", sql, d["db_id"]))
        return cls(examples, exclude_dbs)

    def search(self, question: str, k: int = 3, max_per_db: int = 1) -> list[Example]:
        q = _tokens(mask_question(question))
        k1, b = 1.2, 0.75
        scores = []
        for i, (tf, doc) in enumerate(zip(self.tfs, self.docs, strict=True)):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * len(doc) / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        out: list[Example] = []
        per_db: Counter[str] = Counter()
        for _, i in scores:
            ex = self.examples[i]
            if per_db[ex.db_id] >= max_per_db:
                continue  # diversity: don't show three questions about the same database
            per_db[ex.db_id] += 1
            out.append(ex)
            if len(out) >= k:
                break
        return out
