"""Read a SQLite database's schema (tables, columns, keys, sample values) and render it for prompts.

Nothing about any particular database is hard-coded: point it at a .sqlite file and it works.
The rendered format follows the "M-Schema" idea (XiYan-SQL): one line per column with type,
key flags, a short description when available, and a few real example values, because example
values are what let a model map "Alameda" to `County Name` rather than guessing.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from t2sql.db.executor import connect_readonly

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_ident(name: str) -> str:
    """Quote an identifier only when it needs it (spaces, punctuation, leading digit)."""
    return name if _SAFE_IDENT.match(name) else "`" + name.replace("`", "``") + "`"


@dataclass
class Column:
    name: str
    type: str
    primary_key: bool = False
    examples: list[str] = field(default_factory=list)
    description: str = ""
    value_description: str = ""


@dataclass
class ForeignKey:
    table: str
    column: str
    ref_table: str
    ref_column: str

    def render(self) -> str:
        return (
            f"{quote_ident(self.table)}.{quote_ident(self.column)} = "
            f"{quote_ident(self.ref_table)}.{quote_ident(self.ref_column)}"
        )


@dataclass
class Table:
    name: str
    columns: list[Column]

    def column(self, name: str) -> Column | None:
        lname = name.lower()
        return next((c for c in self.columns if c.name.lower() == lname), None)


@dataclass
class Schema:
    db_id: str
    tables: list[Table]
    foreign_keys: list[ForeignKey]

    def table(self, name: str) -> Table | None:
        lname = name.lower()
        return next((t for t in self.tables if t.name.lower() == lname), None)

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def render(
        self,
        keep: dict[str, set[str]] | None = None,
        max_examples: int = 3,
        with_descriptions: bool = True,
    ) -> str:
        """Render as M-Schema text. `keep` maps table -> columns to include (None = everything).

        Primary- and foreign-key columns of kept tables are always included so joins stay possible.
        """
        key_cols: dict[str, set[str]] = {}
        for fk in self.foreign_keys:
            key_cols.setdefault(fk.table.lower(), set()).add(fk.column.lower())
            key_cols.setdefault(fk.ref_table.lower(), set()).add(fk.ref_column.lower())

        lines = [f"【DB_ID】 {self.db_id}", "【Schema】"]
        kept_tables: set[str] = set()
        for t in self.tables:
            if keep is not None and t.name.lower() not in {k.lower() for k in keep}:
                continue
            kept_tables.add(t.name.lower())
            wanted = None
            if keep is not None:
                wanted = {
                    c.lower()
                    for c in next(v for k, v in keep.items() if k.lower() == t.name.lower())
                }
            lines.append(f"# Table: {quote_ident(t.name)}")
            lines.append("[")
            col_lines = []
            for c in t.columns:
                is_key = c.primary_key or c.name.lower() in key_cols.get(t.name.lower(), set())
                if wanted is not None and c.name.lower() not in wanted and not is_key:
                    continue
                parts = [f"{quote_ident(c.name)}:{c.type or 'TEXT'}"]
                if c.primary_key:
                    parts.append("Primary Key")
                if with_descriptions and c.description and c.description.lower() != c.name.lower():
                    parts.append(c.description)
                if with_descriptions and c.value_description:
                    parts.append(f"Values: {c.value_description}")
                if max_examples and c.examples:
                    parts.append("Examples: [" + ", ".join(c.examples[:max_examples]) + "]")
                col_lines.append("(" + ", ".join(parts) + ")")
            lines.append(",\n".join(col_lines))
            lines.append("]")

        fks = [
            fk
            for fk in self.foreign_keys
            if fk.table.lower() in kept_tables and fk.ref_table.lower() in kept_tables
        ]
        if fks:
            lines.append("【Foreign keys】")
            lines.extend(fk.render() for fk in fks)
        return "\n".join(lines)


def _clean_text(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= limit else value[:limit] + "…"


def introspect(
    db_path: str | Path,
    db_id: str | None = None,
    n_examples: int = 3,
    descriptions_dir: str | Path | None = None,
) -> Schema:
    """Build a Schema from a SQLite file. `descriptions_dir` accepts BIRD's database_description/."""
    db_path = Path(db_path)
    conn = connect_readonly(db_path)
    try:
        tables: list[Table] = []
        fks: list[ForeignKey] = []
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        for tname in names:
            qt = _dq(tname)
            cols: list[Column] = []
            for _cid, cname, ctype, _notnull, _default, pk in conn.execute(
                f"PRAGMA table_info({qt})"
            ):
                cols.append(Column(name=cname, type=(ctype or "").upper(), primary_key=bool(pk)))
            for row in conn.execute(f"PRAGMA foreign_key_list({qt})"):
                # (id, seq, table, from, to, on_update, on_delete, match); `to` may be NULL -> PK
                ref_table, from_col, to_col = row[2], row[3], row[4]
                if to_col is None:
                    ref_pk = [
                        r[1] for r in conn.execute(f"PRAGMA table_info({_dq(ref_table)})") if r[5]
                    ]
                    to_col = ref_pk[0] if ref_pk else from_col
                fks.append(ForeignKey(tname, from_col, ref_table, to_col))
            if n_examples:
                for c in cols:
                    c.examples = _sample_values(conn, tname, c.name, n_examples)
            tables.append(Table(tname, cols))
    finally:
        conn.close()

    schema = Schema(db_id or db_path.stem, tables, _dedupe_fks(fks, tables))
    if descriptions_dir and Path(descriptions_dir).is_dir():
        attach_bird_descriptions(schema, Path(descriptions_dir))
    return schema


def _dq(name: str) -> str:
    """Always-quoted identifier for SQL we build internally."""
    return '"' + name.replace('"', '""') + '"'


def _sample_values(conn: sqlite3.Connection, table: str, column: str, k: int) -> list[str]:
    qt, qc = _dq(table), _dq(column)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {qc} FROM {qt} WHERE {qc} IS NOT NULL AND {qc} != '' LIMIT {k}"
        ).fetchall()
    except sqlite3.Error:
        return []
    out = []
    for (v,) in rows:
        if isinstance(v, bytes):
            continue
        out.append(_clean_text(v, 40))
    return out


def _dedupe_fks(fks: list[ForeignKey], tables: list[Table]) -> list[ForeignKey]:
    """Drop FKs pointing at tables/columns that don't exist (common in BIRD/Spider dumps)."""
    by_name = {t.name.lower(): t for t in tables}
    seen, out = set(), []
    for fk in fks:
        rt = by_name.get(fk.ref_table.lower())
        st = by_name.get(fk.table.lower())
        if not rt or not st or not rt.column(fk.ref_column) or not st.column(fk.column):
            continue
        key = (fk.table.lower(), fk.column.lower(), fk.ref_table.lower(), fk.ref_column.lower())
        if key not in seen:
            seen.add(key)
            out.append(
                ForeignKey(
                    st.name,
                    st.column(fk.column).name,  # type: ignore[union-attr]
                    rt.name,
                    rt.column(fk.ref_column).name,
                )
            )  # type: ignore[union-attr]
    return out


def attach_bird_descriptions(schema: Schema, desc_dir: Path) -> None:
    """BIRD ships one CSV per table: original_column_name, column_name, column_description,
    data_format, value_description. Encodings vary, so try a couple."""
    for t in schema.tables:
        path = next((p for p in desc_dir.glob("*.csv") if p.stem.lower() == t.name.lower()), None)
        if path is None:
            continue
        rows = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                with path.open(encoding=enc, newline="") as f:
                    rows = list(csv.DictReader(f))
                break
            except UnicodeDecodeError:
                continue
        for row in rows or []:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            col = t.column(row.get("original_column_name", ""))
            if col is None:
                continue
            desc = row.get("column_description") or row.get("column_name") or ""
            col.description = _clean_text(desc, 120) if desc else ""
            vdesc = row.get("value_description", "")
            if vdesc and vdesc.lower() not in {"not useful", "commonsense evidence:"}:
                col.value_description = _clean_text(vdesc, 160)
