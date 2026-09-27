import json
import shutil

from fastapi.testclient import TestClient

from t2sql.eval.metrics import run_gold, score
from t2sql.eval.report import build_report
from t2sql.eval.runner import Item, dump_config, options_for, run_benchmark, summarize
from tests.test_pipeline import FakeLLM, sql_block


def test_ex_is_order_insensitive_and_buckets_errors(demo_db):
    tables = ["students", "enrollments", "courses"]
    gold = run_gold(demo_db, "SELECT first_name FROM students WHERE enrollment_year = 2023")
    assert score(
        demo_db,
        "SELECT first_name FROM students WHERE enrollment_year = 2023 ORDER BY first_name DESC",
        gold,
        tables,
    ).correct
    assert (
        score(
            demo_db,
            "SELECT first_name, last_name FROM students WHERE enrollment_year=2023",
            gold,
            tables,
        ).category
        == "wrong:extra_columns"
    )
    assert (
        score(demo_db, "SELECT nope FROM students", gold, tables).category == "exec:no_such_column"
    )
    assert (
        score(demo_db, "SELECT first_name FROM students WHERE 0", gold, tables).category
        == "wrong:empty_result"
    )


class SeedAwareFakeLLM(FakeLLM):
    """Answers by question text so concurrent questions don't steal each other's replies."""

    def __init__(self, answers: dict[str, str]):
        super().__init__({})
        self.answers = answers

    async def chat(self, messages, temperature=0.0, seed=0, max_tokens=1024, json_mode=False):
        from t2sql.llm.client import LLMResponse

        self.stats["calls"] += 1
        prompt = messages[-1]["content"]
        for q, sql in self.answers.items():
            if q in prompt:
                return LLMResponse(sql_block(sql))
        raise AssertionError("unexpected prompt")


async def test_benchmark_run_summary_and_report(demo_db, tmp_path):
    db_root = tmp_path / "dbs"
    (db_root / "university").mkdir(parents=True)
    shutil.copy(demo_db, db_root / "university" / "university.sqlite")
    items = [
        Item(
            "1",
            "university",
            "How many students?",
            "SELECT COUNT(*) FROM students",
            difficulty="simple",
        ),
        Item(
            "2",
            "university",
            "List online courses",
            "SELECT course_name FROM courses WHERE is_online = 1",
            difficulty="moderate",
        ),
    ]
    llm = SeedAwareFakeLLM(
        {
            "How many students?": "SELECT COUNT(*) FROM students",
            "List online courses": "SELECT course_name FROM courses",
        }
    )
    run_dir = tmp_path / "runs" / "full"
    run_dir.mkdir(parents=True)
    opts = options_for("full", n_candidates=2)
    dump_config(run_dir / "config.json", "full", opts, "fake", "toy.json", True)
    await run_benchmark(items, db_root, llm, opts, run_dir / "results.jsonl", progress=False)

    s = summarize(run_dir / "results.jsonl")
    assert s["n"] == 2 and s["variants"]["final"]["ex"] == 0.5
    report = build_report(tmp_path / "runs")
    assert "self-consistency" in report and "wrong:row_count" in report

    # resume: a second run must not re-ask anything
    before = llm.stats["calls"]
    await run_benchmark(items, db_root, llm, opts, run_dir / "results.jsonl", progress=False)
    assert llm.stats["calls"] == before


def test_api_end_to_end(demo_db, tmp_path, monkeypatch):
    dbs = tmp_path / "dbs"
    dbs.mkdir()
    shutil.copy(demo_db, dbs / "university.sqlite")
    monkeypatch.setenv("T2SQL_DATABASES_DIR", str(dbs))
    monkeypatch.setenv("T2SQL_LLM_CACHE_PATH", str(tmp_path / "cache.sqlite"))
    from t2sql.config import get_settings

    get_settings.cache_clear()
    from t2sql.api.app import app

    with TestClient(app) as client:
        app.state.llm = SeedAwareFakeLLM({"How many students": "SELECT COUNT(*) FROM students"})
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/v1/databases").json()["databases"] == ["university"]
        assert "departments" in client.get("/v1/databases/university/schema").json()["tables"]

        r = client.post(
            "/v1/query",
            json={"db": "university", "question": "How many students", "n_candidates": 3},
        )
        body = r.json()
        assert r.status_code == 200, body
        assert body["result"]["rows"] == [[10]] and body["confidence"] == 1.0
        assert r.headers["x-request-id"]

        bad = client.post("/v1/validate", json={"db": "university", "sql": "DROP TABLE students"})
        assert bad.json()["ok"] is False
        assert (
            client.post("/v1/query", json={"db": "nope", "question": "hi there"}).status_code == 404
        )
    get_settings.cache_clear()
    json.dumps(body)


def test_api_key_required_when_configured(demo_db, tmp_path, monkeypatch):
    dbs = tmp_path / "dbs"
    dbs.mkdir()
    shutil.copy(demo_db, dbs / "university.sqlite")
    monkeypatch.setenv("T2SQL_DATABASES_DIR", str(dbs))
    monkeypatch.setenv("T2SQL_API_KEYS", "k1,k2")
    from t2sql.config import get_settings

    get_settings.cache_clear()
    from t2sql.api.app import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200  # health stays open
        assert client.get("/v1/databases").status_code == 401
        assert client.get("/v1/databases", headers={"X-API-Key": "k2"}).status_code == 200
    get_settings.cache_clear()


async def test_one_failing_question_does_not_kill_the_run(demo_db, tmp_path):
    db_root = tmp_path / "dbs"
    (db_root / "university").mkdir(parents=True)
    shutil.copy(demo_db, db_root / "university" / "university.sqlite")
    items = [
        Item("1", "university", "How many students?", "SELECT COUNT(*) FROM students"),
        Item("2", "university", "Explode please", "SELECT 1"),
    ]

    class Exploding(SeedAwareFakeLLM):
        async def chat(self, messages, **kw):
            if "Explode" in messages[-1]["content"]:
                raise RuntimeError("boom")
            return await super().chat(messages, **kw)

    llm = Exploding({"How many students?": "SELECT COUNT(*) FROM students"})
    out = tmp_path / "r.jsonl"
    await run_benchmark(items, db_root, llm, options_for("bare"), out, progress=False)
    recs = {r["qid"]: r for r in map(json.loads, out.read_text().splitlines())}
    assert recs["1"]["final"]["correct"] is True
    assert recs["2"]["final"]["correct"] is False and "boom" in recs["2"]["harness_error"]
    assert summarize(out)["variants"]["final"]["ex"] == 0.5  # the failure counts as wrong
