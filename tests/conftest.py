import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolated_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("T2SQL_VALUE_CACHE", str(tmp_path / "values"))


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("db") / "university.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript((ROOT / "examples" / "university.sql").read_text())
    conn.commit()
    conn.close()
    return path
