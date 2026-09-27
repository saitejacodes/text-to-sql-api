import pytest

from t2sql.guard.sql_guard import check_sql

TABLES = ["students", "courses", "enrollments"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT created_at FROM students",  # keyword inside identifier
        "SELECT * FROM students WHERE last_name = 'Deleted'",  # keyword inside literal
        "WITH t AS (SELECT * FROM students) SELECT * FROM t",  # CTE name is not a table
        "SELECT * FROM students UNION SELECT * FROM students",
        "SELECT s.first_name FROM students s JOIN enrollments e ON s.student_id = e.student_id",
        "SELECT COUNT(*) FROM students;",  # trailing semicolon
        "select * from STUDENTS",  # case-insensitive table match
    ],
)
def test_allows_read_only_queries(sql):
    assert check_sql(sql, TABLES).ok


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("SELECT 1; DROP TABLE students", "exactly one statement"),
        ("DELETE FROM students", "only SELECT"),
        ("UPDATE students SET first_name = 'x'", "only SELECT"),
        ("INSERT INTO students VALUES (1)", "only SELECT"),
        ("PRAGMA table_info(students)", "only SELECT"),
        ("ATTACH DATABASE 'x.db' AS x", "only SELECT"),
        ("SELECT * FROM passwords", "unknown table"),
        ("SELECT * FROM main.students", "schema-qualified"),
        ("SELECT * FROM", "syntax error"),
        ("", "empty"),
    ],
)
def test_rejects_unsafe_or_invalid(sql, reason):
    res = check_sql(sql, TABLES)
    assert not res.ok
    assert reason in res.reason


def test_tokenizer_errors_are_reported_not_raised():
    res = check_sql("SELECT * FROM students WHERE last_name = 'O\\'Brien' AND x = 'y", TABLES)
    assert not res.ok and "syntax error" in res.reason
