import pytest

from t2sql.db.executor import execute


def test_select_works(demo_db):
    res = execute(demo_db, "SELECT COUNT(*) FROM students")
    assert res.ok and res.rows == [(10,)] and res.columns == ["COUNT(*)"]


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM students",
        "CREATE TEMP TABLE t(x)",
        "ATTACH DATABASE ':memory:' AS other",
        "PRAGMA writable_schema = ON",
        "SELECT load_extension('evil')",
    ],
)
def test_sandbox_blocks_even_if_guard_is_bypassed(demo_db, sql):
    res = execute(demo_db, sql)
    assert not res.ok
    assert execute(demo_db, "SELECT COUNT(*) FROM students").rows == [(10,)]


def test_timeout_aborts_runaway_query(demo_db):
    sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    res = execute(demo_db, sql, timeout_s=0.5)
    assert not res.ok and res.timed_out


def test_row_cap_reports_truncation(demo_db):
    res = execute(demo_db, "SELECT * FROM enrollments", max_rows=5)
    assert res.ok and len(res.rows) == 5 and res.truncated


def test_multiple_statements_rejected(demo_db):
    assert not execute(demo_db, "SELECT 1; SELECT 2").ok
