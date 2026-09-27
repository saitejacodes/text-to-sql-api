"""Pipeline tests with a scripted fake LLM (no network): repair loop, voting and confidence."""

from t2sql.llm.client import LLMResponse
from t2sql.llm.prompts import extract_sql
from t2sql.pipeline.context import DatabaseContext
from t2sql.pipeline.pipeline import Pipeline, PipelineOptions


class FakeLLM:
    def __init__(self, replies_by_seed: dict[int, list[str]]):
        self.replies = {k: list(v) for k, v in replies_by_seed.items()}
        self.stats = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}

    async def chat(self, messages, temperature=0.0, seed=0, max_tokens=1024, json_mode=False):
        self.stats["calls"] += 1
        return LLMResponse(self.replies[seed].pop(0))

    async def aclose(self):
        pass


def sql_block(s: str) -> str:
    return f"Reasoning...\n```sql\n{s}\n```"


def test_extract_sql_takes_last_block_and_strips_reasoning():
    text = "<think>maybe SELECT 1</think>\n```sql\nSELECT 1\n```\nbetter:\n```sql\nSELECT 2;\n```"
    assert extract_sql(text) == "SELECT 2"
    assert extract_sql("SELECT a FROM t; -- done") == "SELECT a FROM t"


async def test_repair_loop_fixes_bad_column(demo_db):
    llm = FakeLLM(
        {
            0: [
                sql_block("SELECT nme FROM departments"),
                sql_block("SELECT dept_name FROM departments"),
            ]
        }
    )
    pipe = Pipeline(llm, PipelineOptions(n_candidates=1, use_value_hints=False))
    res = await pipe.run(DatabaseContext.open(demo_db), "List departments")
    cand = res.candidates[0]
    assert not cand.initial_ok and cand.ok and cand.repairs == 1
    assert res.sql == "SELECT dept_name FROM departments"
    assert res.greedy_initial_sql == "SELECT nme FROM departments"


async def test_vote_picks_majority_result_not_greedy(demo_db):
    wrong = "SELECT COUNT(*) FROM courses WHERE credits = 3"
    right_a = "SELECT COUNT(*) FROM courses WHERE credits = 4"
    right_b = "SELECT COUNT(course_id) FROM courses WHERE credits >= 4"  # same rows, other text
    llm = FakeLLM({0: [sql_block(wrong)], 1: [sql_block(right_a)], 2: [sql_block(right_b)]})
    pipe = Pipeline(llm, PipelineOptions(n_candidates=3, use_value_hints=False))
    res = await pipe.run(DatabaseContext.open(demo_db), "How many 4-credit courses?")
    assert res.sql == right_a
    assert res.confidence == round(2 / 3, 3)
    assert res.greedy_sql == wrong


async def test_empty_result_triggers_one_revision(demo_db):
    empty = "SELECT course_name FROM courses WHERE credits = 99"
    fixed = "SELECT course_name FROM courses WHERE credits = 4"
    llm = FakeLLM({0: [sql_block(empty), sql_block(fixed)]})
    pipe = Pipeline(llm, PipelineOptions(n_candidates=1, use_value_hints=False))
    res = await pipe.run(DatabaseContext.open(demo_db), "Which courses have 4 credits?")
    assert res.greedy_initial_sql == empty
    assert res.sql == fixed and res.candidates[0].row_count > 0


async def test_revision_that_is_still_empty_is_discarded(demo_db):
    empty = "SELECT course_name FROM courses WHERE credits = 99"
    also_empty = "SELECT course_name FROM courses WHERE credits = 98"
    llm = FakeLLM({0: [sql_block(empty), sql_block(also_empty)]})
    pipe = Pipeline(llm, PipelineOptions(n_candidates=1, use_value_hints=False))
    res = await pipe.run(DatabaseContext.open(demo_db), "Which courses have 99 credits?")
    assert res.sql == empty
