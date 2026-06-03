import re
import time
from typing import List
from app.database import execute_query
from app.models import BenchmarkResponse, MetricsDetails, SubtaskBreakdown, ErrorAnalysis

# ─────────────────────────────────────────────────────────────────
# 20 benchmark queries covering all 10 tables
# ─────────────────────────────────────────────────────────────────
BENCHMARK_QUERIES = [
    # 1 — simple SELECT
    {
        "question":    "List all departments.",
        "gold_sql":    "SELECT dept_name FROM departments",
        "gold_tables": ["departments"],
    },
    # 2 — WHERE filter on column value
    {
        "question":    "Which courses offer 4 credits?",
        "gold_sql":    "SELECT course_name FROM courses WHERE credits = 4",
        "gold_tables": ["courses"],
    },
    # 3 — COUNT aggregate
    {
        "question":    "How many students are in the database?",
        "gold_sql":    "SELECT COUNT(*) AS total_students FROM students",
        "gold_tables": ["students"],
    },
    # 4 — two-table JOIN
    {
        "question":    "List all courses with their department names.",
        "gold_sql":    "SELECT c.course_name, d.dept_name FROM courses c JOIN departments d ON c.dept_id = d.dept_id",
        "gold_tables": ["courses", "departments"],
    },
    # 5 — JOIN + WHERE string filter
    {
        "question":    "Which instructors work in the Computer Science department?",
        "gold_sql":    "SELECT i.first_name, i.last_name FROM instructors i JOIN departments d ON i.dept_id = d.dept_id WHERE d.dept_name = 'Computer Science'",
        "gold_tables": ["instructors", "departments"],
    },
    # 6 — GROUP BY COUNT
    {
        "question":    "How many courses does each department offer?",
        "gold_sql":    "SELECT d.dept_name, COUNT(c.course_id) AS course_count FROM departments d JOIN courses c ON d.dept_id = c.dept_id GROUP BY d.dept_name",
        "gold_tables": ["departments", "courses"],
    },
    # 7 — GROUP BY + HAVING
    {
        "question":    "Which departments have more than 1 instructor?",
        "gold_sql":    "SELECT d.dept_name, COUNT(i.instructor_id) AS instructor_count FROM departments d JOIN instructors i ON d.dept_id = i.dept_id GROUP BY d.dept_name HAVING COUNT(i.instructor_id) > 1",
        "gold_tables": ["departments", "instructors"],
    },
    # 8 — Boolean filter
    {
        "question":    "List all online courses.",
        "gold_sql":    "SELECT course_name, credits FROM courses WHERE is_online = 1",
        "gold_tables": ["courses"],
    },
    # 9 — Year filter
    {
        "question":    "Which students enrolled in 2023?",
        "gold_sql":    "SELECT first_name, last_name FROM students WHERE enrollment_year = 2023",
        "gold_tables": ["students"],
    },
    # 10 — Numeric WHERE
    {
        "question":    "Which classrooms can hold more than 200 people?",
        "gold_sql":    "SELECT building, room_number, capacity FROM classrooms WHERE capacity > 200",
        "gold_tables": ["classrooms"],
    },
    # 11 — prerequisites three-table JOIN
    {
        "question":    "What courses have Data Structures as a prerequisite?",
        "gold_sql":    "SELECT c.course_name FROM courses c JOIN prerequisites p ON c.course_id = p.course_id JOIN courses prereq ON p.prereq_id = prereq.course_id WHERE prereq.course_name = 'Data Structures'",
        "gold_tables": ["courses", "prerequisites"],
    },
    # 12 — grade filter
    {
        "question":    "List students who received an A grade.",
        "gold_sql":    "SELECT DISTINCT s.first_name, s.last_name FROM students s JOIN enrollments e ON s.student_id = e.student_id WHERE e.grade = 'A'",
        "gold_tables": ["students", "enrollments"],
    },
    # 13 — SUM aggregate
    {
        "question":    "What is the total seating capacity across all classrooms?",
        "gold_sql":    "SELECT SUM(capacity) AS total_capacity FROM classrooms",
        "gold_tables": ["classrooms"],
    },
    # 14 — sections + courses JOIN
    {
        "question":    "List all courses offered in Fall 2023.",
        "gold_sql":    "SELECT DISTINCT c.course_name FROM courses c JOIN sections s ON c.course_id = s.course_id WHERE s.semester = 'Fall 2023'",
        "gold_tables": ["courses", "sections"],
    },
    # 15 — three-table advisor chain
    {
        "question":    "Which students are advised by Dr. Alan Turing?",
        "gold_sql":    "SELECT s.first_name, s.last_name FROM students s JOIN advisors a ON s.student_id = a.student_id JOIN instructors i ON a.instructor_id = i.instructor_id WHERE i.first_name = 'Dr. Alan' AND i.last_name = 'Turing'",
        "gold_tables": ["students", "advisors", "instructors"],
    },
    # 16 — ORDER BY with GROUP BY
    {
        "question":    "Rank departments by number of courses in descending order.",
        "gold_sql":    "SELECT d.dept_name, COUNT(c.course_id) AS course_count FROM departments d JOIN courses c ON d.dept_id = c.dept_id GROUP BY d.dept_name ORDER BY course_count DESC",
        "gold_tables": ["departments", "courses"],
    },
    # 17 — time_slots filter
    {
        "question":    "What time slots are scheduled on MWF?",
        "gold_sql":    "SELECT start_time, end_time FROM time_slots WHERE day_of_week = 'MWF'",
        "gold_tables": ["time_slots"],
    },
    # 18 — instructor + section + classroom three-table JOIN
    {
        "question":    "List all instructors and the buildings they teach in.",
        "gold_sql":    "SELECT i.first_name || ' ' || i.last_name AS instructor, c.building FROM instructors i JOIN sections s ON i.instructor_id = s.instructor_id JOIN classrooms c ON s.classroom_id = c.classroom_id",
        "gold_tables": ["instructors", "sections", "classrooms"],
    },
    # 19 — NOT IN subquery
    {
        "question":    "Which students are not enrolled in any course?",
        "gold_sql":    "SELECT first_name, last_name FROM students WHERE student_id NOT IN (SELECT DISTINCT student_id FROM enrollments)",
        "gold_tables": ["students", "enrollments"],
    },
    # 20 — AVG aggregate
    {
        "question":    "What is the average number of credits per course?",
        "gold_sql":    "SELECT AVG(credits) AS avg_credits FROM courses",
        "gold_tables": ["courses"],
    },
    # 21 — Subquery with AVG
    {
        "question":    "Which courses have more credits than the average of all courses?",
        "gold_sql":    "SELECT course_name FROM courses WHERE credits > (SELECT AVG(credits) FROM courses)",
        "gold_tables": ["courses"],
    },
    # 22 — Nested query with MAX
    {
        "question":    "Which department offers the course with the highest credits?",
        "gold_sql":    "SELECT d.dept_name FROM departments d JOIN courses c ON d.dept_id = c.dept_id WHERE c.credits = (SELECT MAX(credits) FROM courses)",
        "gold_tables": ["departments", "courses"],
    },
    # 23 — GROUP BY with HAVING on JOIN
    {
        "question":    "List all students enrolled in more than 2 courses.",
        "gold_sql":    "SELECT s.first_name, s.last_name FROM students s JOIN enrollments e ON s.student_id = e.student_id GROUP BY s.student_id, s.first_name, s.last_name HAVING COUNT(e.course_id) > 2",
        "gold_tables": ["students", "enrollments"],
    },
    # 24 — Multi-table COUNT
    {
        "question":    "How many students are enrolled in the Computer Science department's courses?",
        "gold_sql":    "SELECT COUNT(DISTINCT e.student_id) FROM enrollments e JOIN courses c ON e.course_id = c.course_id JOIN departments d ON c.dept_id = d.dept_id WHERE d.dept_name = 'Computer Science'",
        "gold_tables": ["enrollments", "courses", "departments"],
    },
    # 25 — ORDER BY and LIMIT
    {
        "question":    "What are the top 3 departments by number of instructors?",
        "gold_sql":    "SELECT d.dept_name, COUNT(i.instructor_id) AS instructor_count FROM departments d JOIN instructors i ON d.dept_id = i.dept_id GROUP BY d.dept_name ORDER BY instructor_count DESC LIMIT 3",
        "gold_tables": ["departments", "instructors"],
    },
    # 26 — COUNT DISTINCT
    {
        "question":    "How many distinct buildings have classrooms with capacity over 100?",
        "gold_sql":    "SELECT COUNT(DISTINCT building) FROM classrooms WHERE capacity > 100",
        "gold_tables": ["classrooms"],
    },
    # 27 — NOT IN subquery
    {
        "question":    "List departments that do not offer any courses.",
        "gold_sql":    "SELECT dept_name FROM departments WHERE dept_id NOT IN (SELECT dept_id FROM courses)",
        "gold_tables": ["departments", "courses"],
    },
    # 28 — LIKE string matching
    {
        "question":    "Which students have a first name starting with 'J'?",
        "gold_sql":    "SELECT first_name, last_name FROM students WHERE first_name LIKE 'J%'",
        "gold_tables": ["students"],
    },
    # 29 — Triple JOIN with string match
    {
        "question":    "Which courses are taught on Monday?",
        "gold_sql":    "SELECT DISTINCT c.course_name FROM courses c JOIN sections s ON c.course_id = s.course_id JOIN time_slots t ON s.time_slot_id = t.time_slot_id WHERE t.day_of_week LIKE '%M%'",
        "gold_tables": ["courses", "sections", "time_slots"],
    },
    # 30 — Multiple conditions
    {
        "question":    "List in-person courses that offer more than 3 credits.",
        "gold_sql":    "SELECT course_name FROM courses WHERE is_online = 0 AND credits > 3",
        "gold_tables": ["courses"],
    },
]


# ─────────────────────────────────────────────────────────────────
# Metric helpers
# ─────────────────────────────────────────────────────────────────

def normalize_sql(sql: str) -> str:
    sql = sql.upper().strip().rstrip(";")
    sql = re.sub(r"\s+", " ", sql)
    # Normalize INNER JOIN → JOIN
    sql = sql.replace("INNER JOIN", "JOIN")
    # Remove optional AS keyword for aliases (e.g., "COUNT(*) AS total" → "COUNT(*) total")
    sql = re.sub(r'\bAS\s+', '', sql)
    return sql


def calc_retrieval_recall(retrieved: List[str], gold: List[str], k: int) -> float:
    if not gold:
        return 1.0
    hit = set(retrieved[:k]).intersection(set(gold))
    return len(hit) / len(gold)


def check_exact_match(pred: str, gold: str) -> bool:
    return normalize_sql(pred) == normalize_sql(gold)


def check_execution_match(pred: str, gold: str) -> bool:
    p_ok, _, p_rows, _, _, _ = execute_query(pred)
    g_ok, _, g_rows, _, _, _ = execute_query(gold)
    if not p_ok or not g_ok:
        return False
    try:
        return sorted(str(r) for r in p_rows) == sorted(str(r) for r in g_rows)
    except Exception:
        return False


def calc_column_mapping_score(pred: str, gold: str) -> float:
    pred_toks = set(re.findall(r"\b[a-zA-Z_]+\b", pred.lower()))
    gold_toks = set(re.findall(r"\b[a-zA-Z_]+\b", gold.lower()))
    if not gold_toks:
        return 1.0
    return len(pred_toks & gold_toks) / len(gold_toks)


def check_join_detection(pred: str, gold: str) -> float:
    pattern = r"ON\s+(.*?)(?:\s+(?:JOIN|WHERE|GROUP|ORDER|LIMIT|HAVING)|$)"
    pred_joins = set(re.findall(pattern, pred.upper(), re.IGNORECASE))
    gold_joins = set(re.findall(pattern, gold.upper(), re.IGNORECASE))
    if not gold_joins:
        return 1.0
    hits = sum(
        1 for gj in gold_joins
        if any(gj.replace(" ", "") in pj.replace(" ", "") or
               pj.replace(" ", "") in gj.replace(" ", "") for pj in pred_joins)
    )
    return hits / len(gold_joins)


# ─────────────────────────────────────────────────────────────────
# Main benchmark runner
# ─────────────────────────────────────────────────────────────────

def run_benchmark() -> BenchmarkResponse:
    from app.retrieval import retriever
    from app.llm import generate_sql
    from app.validation import validate_sql
    from app.dataset_loader import load_beaver_queries

    # Try Beaver dataset first; fall back to custom queries
    beaver_queries = load_beaver_queries(max_count=30)
    queries = beaver_queries if beaver_queries else BENCHMARK_QUERIES
    total = len(queries)

    r5_sum = r10_sum = 0.0
    exact_count = exec_count = parse_ok = 0
    latency_sum = col_map_sum = join_sum = 0.0

    errors = ErrorAnalysis(
        retrieval_failures=0,
        parsing_failures=0,
        execution_failures=0,
        logic_errors=0,
    )

    for q in queries:
        t0 = time.time()

        # 1 — Retrieval (ask for top-10 to compute recall@10)
        ret_tables, _, _, _ = retriever.retrieve_tables(q["question"], top_k=10)
        r5  = calc_retrieval_recall(ret_tables, q["gold_tables"], 5)
        r10 = calc_retrieval_recall(ret_tables, q["gold_tables"], 10)
        r5_sum  += r5
        r10_sum += r10
        if r5 < 1.0:
            errors.retrieval_failures += 1

        # 2 — SQL generation (use top-3 for context)
        schemas  = retriever.get_schema_for_tables(ret_tables[:3])
        pred_sql, _ = generate_sql(q["question"], ret_tables[:3], schemas)

        # 3 — Validation
        is_valid, err_msg, norm_sql, _ = validate_sql(pred_sql)
        if is_valid:
            parse_ok += 1
        else:
            errors.parsing_failures += 1

        # 4 — Accuracy metrics
        if check_exact_match(pred_sql, q["gold_sql"]):
            exact_count += 1

        exec_ok = check_execution_match(pred_sql, q["gold_sql"])
        if exec_ok:
            exec_count += 1
        elif is_valid:
            pred_success, _, _, _, _, _ = execute_query(pred_sql)
            if not pred_success:
                errors.execution_failures += 1
            else:
                errors.logic_errors += 1

        # 5 — Subtask metrics
        col_map_sum += calc_column_mapping_score(pred_sql, q["gold_sql"])
        join_sum    += check_join_detection(pred_sql, q["gold_sql"])

        latency_sum += (time.time() - t0) * 1000

        # Delay between queries to avoid LLM rate limits
        time.sleep(15)  # 15s = ~4 RPM, safe for Groq free tier

    return BenchmarkResponse(
        total_queries=total,
        metrics=MetricsDetails(
            retrieval_recall_at_5=round(r5_sum / total, 4),
            retrieval_recall_at_10=round(r10_sum / total, 4),
            sql_exact_match_accuracy=round(exact_count / total, 4),
            sql_execution_match_accuracy=round(exec_count / total, 4),
            parsing_success_rate=round(parse_ok / total, 4),
            average_latency_ms=round(latency_sum / total, 2),
        ),
        subtask_breakdown=SubtaskBreakdown(
            multi_table_retrieval=round(r5_sum / total, 4),
            column_mapping=round(col_map_sum / total, 4),
            join_detection=round(join_sum / total, 4),
            domain_knowledge=round(
                (col_map_sum / total + join_sum / total) / 2, 4
            ),
        ),
        error_analysis=errors,
    )