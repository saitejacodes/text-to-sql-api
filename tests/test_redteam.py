"""Adversarial SQL: every attack must be stopped by the guard, the sandbox, or both, and the
database file must be byte-for-byte unchanged afterwards. Includes the case where the model
has been prompt-injected (e.g. via a malicious value stored in the database) and emits
hostile SQL: the pipeline's safety cannot depend on the model behaving."""

import hashlib
import logging

import pytest

from t2sql.db.executor import execute
from t2sql.guard.sql_guard import check_sql

logging.getLogger("sqlglot").setLevel(logging.ERROR)

TABLES = [
    "students",
    "enrollments",
    "courses",
    "departments",
    "instructors",
    "classrooms",
    "time_slots",
    "sections",
    "prerequisites",
    "advisors",
]

ATTACKS = {
    "stacked_delete": "SELECT 1; DELETE FROM students",
    "drop": "DROP TABLE students",
    "update": "UPDATE students SET first_name = 'x'",
    "replace_into": "REPLACE INTO students VALUES (1, 'a', 'b', 2020)",
    "attach": "ATTACH DATABASE '/tmp/t2sql_attach.db' AS x",
    "vacuum_into": "VACUUM INTO '/tmp/t2sql_exfil.db'",
    "pragma_write": "PRAGMA writable_schema = 1",
    "temp_trigger": "CREATE TEMP TRIGGER t AFTER INSERT ON students BEGIN SELECT 1; END",
    "load_extension": "SELECT load_extension('/tmp/evil.so')",
    "readfile": "SELECT readfile('/etc/passwd')",
    "blob_bomb": "SELECT length(randomblob(2000000000))",
    "recursive_bomb": "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
    "SELECT max(x) FROM c",
    "system_table": "SELECT sql FROM sqlite_master",
    "fullwidth_semicolon": "SELECT 1； DROP TABLE students",
}


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", list(ATTACKS))
def test_attack_is_contained(demo_db, name):
    sql = ATTACKS[name]
    before = _digest(demo_db)
    guard = check_sql(sql, TABLES)
    res = execute(demo_db, sql, timeout_s=1.0)
    # blocked by at least one layer ...
    assert not guard.ok or not res.ok, f"{name} got through both layers"
    # ... and even when executed directly (guard bypassed), nothing changed on disk
    assert _digest(demo_db) == before


@pytest.mark.parametrize(
    "name",
    [
        "stacked_delete",
        "drop",
        "update",
        "attach",
        "vacuum_into",
        "pragma_write",
        "load_extension",
        "readfile",
    ],
)
def test_guard_alone_blocks_writes_and_file_access(name):
    assert not check_sql(ATTACKS[name], TABLES).ok


@pytest.mark.parametrize(
    "name",
    [
        "drop",
        "update",
        "attach",
        "vacuum_into",
        "pragma_write",
        "load_extension",
        "blob_bomb",
        "recursive_bomb",
    ],
)
def test_sandbox_alone_blocks_them_too(demo_db, name):
    assert not execute(demo_db, ATTACKS[name], timeout_s=1.0).ok


def test_no_files_were_created():
    import os

    assert not os.path.exists("/tmp/t2sql_exfil.db")
    assert not os.path.exists("/tmp/t2sql_attach.db")
