"""Per-database state that is expensive to build and cheap to reuse: schema + value index."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from t2sql.db.introspect import Schema, introspect
from t2sql.retrieval.value_index import ValueIndex


@dataclass
class DatabaseContext:
    db_id: str
    path: Path
    schema: Schema
    _values: ValueIndex | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def open(
        cls, path: str | Path, db_id: str | None = None, descriptions_dir: str | Path | None = None
    ) -> DatabaseContext:
        path = Path(path)
        if descriptions_dir is None and (path.parent / "database_description").is_dir():
            descriptions_dir = path.parent / "database_description"  # BIRD layout
        schema = introspect(path, db_id=db_id, descriptions_dir=descriptions_dir)
        return cls(db_id or path.stem, path, schema)

    @property
    def values(self) -> ValueIndex:
        with self._lock:
            if self._values is None:
                self._values = ValueIndex.load_or_build(self.path)
            return self._values


class DatabaseRegistry:
    """Maps database names to contexts; only files inside `root` are ever opened."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._cache: dict[str, DatabaseContext] = {}
        self._lock = threading.Lock()

    def available(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        if not self.root.is_dir():
            return found
        for p in sorted(self.root.rglob("*")):
            if p.suffix in {".sqlite", ".db", ".sqlite3"} and p.is_file():
                found.setdefault(p.stem, p)
        return found

    def get(self, name: str) -> DatabaseContext:
        with self._lock:
            if name in self._cache:
                return self._cache[name]
        path = self.available().get(name)
        if path is None:
            raise KeyError(name)
        ctx = DatabaseContext.open(path, db_id=name)
        with self._lock:
            self._cache[name] = ctx
        return ctx
