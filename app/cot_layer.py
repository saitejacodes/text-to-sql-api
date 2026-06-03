"""
Chain-of-Thought (CoT) Reasoning Layer for SQL Generation.

Performs structured analysis of natural language questions:
  1. Intent detection (list, count, filter, rank, aggregate)
  2. Table identification (via keyword → table mapping)
  3. Join path planning (via schema relationship graph)
  4. Filter extraction (WHERE / HAVING conditions)
  5. Aggregation detection (COUNT, SUM, AVG, MAX)
  6. SQL generation from the structured plan

Used in two ways:
  - Enhances LLM prompts with pre-computed reasoning hints
  - Generates SQL directly as a high-quality fallback when LLM is unavailable
"""

import re
import logging

logger = logging.getLogger("app.cot_layer")

# ── Schema relationship graph ──────────────────────────────────────────────
# Maps (table_a, table_b) → (alias_a.col, alias_b.col) for JOIN planning.
SCHEMA_GRAPH = {
    ("departments", "courses"):     ("d.dept_id",        "c.dept_id"),
    ("departments", "instructors"): ("d.dept_id",        "i.dept_id"),
    ("courses", "enrollments"):     ("c.course_id",      "e.course_id"),
    ("courses", "sections"):        ("c.course_id",      "sec.course_id"),
    ("courses", "prerequisites"):   ("c.course_id",      "p.course_id"),
    ("students", "enrollments"):    ("s.student_id",     "e.student_id"),
    ("students", "advisors"):       ("s.student_id",     "a.student_id"),
    ("instructors", "advisors"):    ("i.instructor_id",  "a.instructor_id"),
    ("instructors", "sections"):    ("i.instructor_id",  "sec.instructor_id"),
    ("classrooms", "sections"):     ("cl.classroom_id",  "sec.classroom_id"),
    ("time_slots", "sections"):     ("t.time_slot_id",   "sec.time_slot_id"),
}

TABLE_ALIASES = {
    "departments":   "d",
    "courses":       "c",
    "students":      "s",
    "enrollments":   "e",
    "instructors":   "i",
    "classrooms":    "cl",
    "time_slots":    "t",
    "sections":      "sec",
    "prerequisites": "p",
    "advisors":      "a",
}

# ── Keyword → Table mapping ────────────────────────────────────────────────
KEYWORD_TABLE_MAP = {
    "department": "departments", "dept": "departments",
    "course": "courses", "class": "courses", "credit": "courses",
    "online": "courses", "in-person": "courses", "curriculum": "courses",
    "student": "students", "learner": "students", "pupil": "students",
    "enrollment": "enrollments", "enroll": "enrollments", "registered": "enrollments",
    "grade": "enrollments", "semester": "enrollments",
    "instructor": "instructors", "professor": "instructors",
    "faculty": "instructors", "teacher": "instructors",
    "classroom": "classrooms", "building": "classrooms",
    "capacity": "classrooms", "room": "classrooms", "seating": "classrooms",
    "time": "time_slots", "schedule": "time_slots", "slot": "time_slots",
    "section": "sections", "offering": "sections", "taught": "sections",
    "prerequisite": "prerequisites", "prereq": "prerequisites",
    "advisor": "advisors", "adviser": "advisors", "advised": "advisors",
    "mentor": "advisors",
}


class CoTReasoner:
    """Chain-of-Thought SQL reasoning engine."""

    def analyze(self, question: str) -> dict:
        """Full CoT analysis pipeline. Returns structured reasoning + SQL."""
        q = question.lower().strip()

        intent      = self._detect_intent(q)
        tables      = self._identify_tables(q)
        aggregation = self._detect_aggregation(q, question)
        filters     = self._extract_filters(q, question)
        ordering    = self._detect_ordering(q)
        limit       = self._detect_limit(q)
        joins       = self._plan_joins(tables)

        reasoning = self._build_reasoning(
            question, intent, tables, aggregation, filters, ordering, joins
        )

        sql = self._generate_sql(
            q, question, intent, tables, aggregation, filters, ordering, limit, joins
        )

        logger.debug("CoT reasoning:\n%s", reasoning)
        logger.debug("CoT generated SQL: %s", sql)

        return {
            "intent":        intent,
            "tables":        tables,
            "aggregation":   aggregation,
            "filters":       filters,
            "ordering":      ordering,
            "joins":         joins,
            "reasoning":     reasoning,
            "generated_sql": sql,
        }

    # ── Step 1: Intent Detection ───────────────────────────────────────────
    def _detect_intent(self, q: str) -> str:
        if any(w in q for w in ["how many", "count", "total", "sum"]):
            return "aggregate"
        if any(w in q for w in ["average", "avg"]):
            return "aggregate"
        if any(w in q for w in ["rank", "top", "descending", "ascending", "order by"]):
            return "rank"
        if any(w in q for w in ["not enrolled", "not offer", "not in"]):
            return "exclusion"
        if any(w in q for w in ["more than", "greater than", "at least", "exceed"]):
            return "threshold"
        if any(w in q for w in ["list", "show", "all"]):
            return "list"
        if any(w in q for w in ["which", "what", "who"]):
            return "filter"
        return "query"

    # ── Step 2: Table Identification ───────────────────────────────────────
    def _identify_tables(self, q: str) -> list:
        tables = []
        for keyword, table in KEYWORD_TABLE_MAP.items():
            if keyword in q and table not in tables:
                tables.append(table)
        return tables

    # ── Step 3: Aggregation Detection ──────────────────────────────────────
    def _detect_aggregation(self, q: str, original: str) -> dict:
        agg = {"function": None, "column": None, "group_by": None, "having": None}

        if "how many" in q or "count" in q:
            agg["function"] = "COUNT"
        elif "total" in q or "sum" in q:
            agg["function"] = "SUM"
        elif "average" in q or "avg" in q:
            agg["function"] = "AVG"
        elif "highest" in q or "max" in q or "maximum" in q:
            agg["function"] = "MAX"

        if "more than" in q or "greater than" in q:
            m = re.search(r'(?:more|greater) than (\d+)', q)
            if m:
                agg["having"] = int(m.group(1))

        if any(w in q for w in ["each", "per", "by department", "by course",
                                 "rank", "group"]):
            agg["group_by"] = True

        return agg

    # ── Step 4: Filter Extraction ──────────────────────────────────────────
    def _extract_filters(self, q: str, original: str) -> list:
        filters = []

        # Stopwords that should never be treated as filter values
        STOPWORDS = {
            "which", "what", "who", "where", "how", "list",
            "find", "show", "get", "all", "the", "a", "an",
            "are", "is", "do", "does", "have", "has", "in",
            "that", "this", "each", "every", "any", "some",
        }

        def _add_filter(col, op, val):
            """Only add filter if value is not a stopword."""
            if isinstance(val, str) and val.strip().strip("'\"").lower() in STOPWORDS:
                return
            filters.append((col, op, val))

        # Year filter
        m = re.search(r'(?:in|year)\s*(\d{4})', q)
        if m:
            _add_filter("enrollment_year", "=", m.group(1))

        # Credit filter
        m = re.search(r'(\d+)\s*credit', q)
        if m:
            _add_filter("credits", "=", m.group(1))

        # Capacity filter
        m = re.search(r'(?:more than|over|greater than|above|exceed)\s*(\d+)\s*(?:people|person|seat|capacity)?', q)
        if m and ("classroom" in q or "capacity" in q or "building" in q or "room" in q):
            _add_filter("capacity", ">", m.group(1))

        # Boolean filter
        if "online" in q and ("list" in q or "all" in q):
            _add_filter("is_online", "=", "1")
        if "in-person" in q or "in person" in q:
            _add_filter("is_online", "=", "0")

        # String filters
        if "computer science" in q:
            _add_filter("dept_name", "=", "'Computer Science'")
        elif "mathematics" in q:
            _add_filter("dept_name", "=", "'Mathematics'")

        # Grade filter
        grade_match = re.search(
            r"(?:an?\s+)?([A-F][+-]?)\s+grade|received\s+(?:an?\s+)?([A-F][+-]?)",
            original, re.IGNORECASE
        )
        if grade_match:
            grade = (grade_match.group(1) or grade_match.group(2)).upper()
            _add_filter("grade", "=", f"'{grade}'")

        # Semester filter
        sem_match = re.search(r'(Fall|Spring|Summer)\s*(\d{4})', original)
        if sem_match:
            _add_filter("semester", "=", f"'{sem_match.group(1)} {sem_match.group(2)}'")

        # Day-of-week filter
        day_match = re.search(r'(MWF|TR|MW|TTh)', original)
        if day_match:
            _add_filter("day_of_week", "=", f"'{day_match.group(1)}'")

        # LIKE filter (name starting with)
        like_match = re.search(r"(?:starting|beginning|start|begin)\s+with\s+['\"]?([A-Za-z])", original)
        if like_match:
            letter = like_match.group(1).upper()
            _add_filter("first_name", "LIKE", f"'{letter}%'")

        # Name filter for advisors/instructors
        name_match = re.search(r"(?:by\s+)((?:Dr\.\s+)?[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)", original)
        if name_match and ("advised" in q or "advisor" in q):
            full_name = name_match.group(1).strip()
            parts = full_name.rsplit(' ', 1)
            if len(parts) == 2:
                filters.append(("instructor_name", "=", parts))

        # Course name filter (prerequisite)
        prereq_match = re.search(r"have\s+(.+?)\s+as\s+a\s+prerequisite", original, re.IGNORECASE)
        if prereq_match:
            _add_filter("prereq_course_name", "=", f"'{prereq_match.group(1).strip()}'")

        # Department name filter (generic)
        dept_match = re.search(r"(?:the\s+)?([A-Z][a-zA-Z\s]+?)\s+department", original)
        if dept_match and not any(f[0] == "dept_name" for f in filters):
            _add_filter("dept_name", "=", f"'{dept_match.group(1).strip()}'")

        # Department name filter (possessive form)
        dept_poss_match = re.search(r"(?:the\s+)?([A-Z][a-zA-Z\s]+?)'s\s+course", original)
        if dept_poss_match and not any(f[0] == "dept_name" for f in filters):
            _add_filter("dept_name", "=", f"'{dept_poss_match.group(1).strip()}'")


        return filters

    # ── Step 5: Ordering Detection ─────────────────────────────────────────
    def _detect_ordering(self, q: str) -> dict:
        ordering = {"order_by": None, "direction": "DESC"}
        if "rank" in q or "descending" in q or "most" in q or "top" in q:
            ordering["order_by"] = True
            ordering["direction"] = "DESC"
        elif "ascending" in q or "least" in q:
            ordering["order_by"] = True
            ordering["direction"] = "ASC"
        return ordering

    # ── Step 5b: LIMIT Detection ───────────────────────────────────────────
    def _detect_limit(self, q: str) -> int | None:
        m = re.search(r'top\s+(\d+)', q)
        if m:
            return int(m.group(1))
        return None

    # ── Step 6: Join Path Planning ─────────────────────────────────────────
    def _plan_joins(self, tables: list) -> list:
        joins = []
        for i, t1 in enumerate(tables):
            for t2 in tables[i + 1:]:
                key_fwd = (t1, t2)
                key_rev = (t2, t1)
                if key_fwd in SCHEMA_GRAPH:
                    col_a, col_b = SCHEMA_GRAPH[key_fwd]
                    joins.append({"from": t1, "to": t2, "on": f"{col_a} = {col_b}"})
                elif key_rev in SCHEMA_GRAPH:
                    col_a, col_b = SCHEMA_GRAPH[key_rev]
                    joins.append({"from": t2, "to": t1, "on": f"{col_a} = {col_b}"})
        return joins

    # ── Build human-readable reasoning ─────────────────────────────────────
    def _build_reasoning(self, question, intent, tables, aggregation,
                         filters, ordering, joins) -> str:
        lines = [f"Question: {question}"]
        lines.append(f"Step 1 — Intent: {intent}")
        lines.append(f"Step 2 — Tables needed: {', '.join(tables) if tables else 'unknown'}")

        if joins:
            join_strs = [f"  {j['from']} ↔ {j['to']} ON {j['on']}" for j in joins]
            lines.append("Step 3 — Join path:\n" + "\n".join(join_strs))
        else:
            lines.append("Step 3 — No joins needed (single table query)")

        if filters:
            filter_strs = [f"  {f[0]} {f[1]} {f[2]}" for f in filters]
            lines.append("Step 4 — Filters:\n" + "\n".join(filter_strs))
        else:
            lines.append("Step 4 — No filters")

        if aggregation["function"]:
            lines.append(f"Step 5 — Aggregation: {aggregation['function']}"
                         + (f", HAVING > {aggregation['having']}" if aggregation["having"] else ""))
        else:
            lines.append("Step 5 — No aggregation")

        if ordering["order_by"]:
            lines.append(f"Step 6 — Ordering: {ordering['direction']}")

        return "\n".join(lines)

    # ── Generate SQL from structured analysis ──────────────────────────────
    def _generate_sql(self, q, original, intent, tables, aggregation,
                      filters, ordering, limit, joins) -> str:
        """Build SQL from CoT analysis. Handles all major SQL patterns."""

        # ── NOT IN / exclusion patterns ──
        if intent == "exclusion":
            if "student" in q and "not" in q and "enroll" in q:
                return ("SELECT first_name, last_name FROM students "
                        "WHERE student_id NOT IN "
                        "(SELECT DISTINCT student_id FROM enrollments)")
            if ("department" in q or "dept" in q) and "not" in q and ("offer" in q or "course" in q):
                return ("SELECT dept_name FROM departments "
                        "WHERE dept_id NOT IN (SELECT dept_id FROM courses)")

        # ── Subquery patterns (more/less than average, max) ──
        if ("average" in q or "avg" in q) and ("more" in q or "greater" in q) and "credit" in q:
            return "SELECT course_name FROM courses WHERE credits > (SELECT AVG(credits) FROM courses)"
        if ("highest" in q or "max" in q) and "credit" in q and ("department" in q or "dept" in q):
            return ("SELECT d.dept_name FROM departments d "
                    "JOIN courses c ON d.dept_id = c.dept_id "
                    "WHERE c.credits = (SELECT MAX(credits) FROM courses)")

        # ── Simple aggregates on single table ──
        if aggregation["function"] == "AVG" and "credit" in q:
            return "SELECT AVG(credits) AS avg_credits FROM courses"
        if aggregation["function"] == "SUM" and ("capacity" in q or "seating" in q):
            return "SELECT SUM(capacity) AS total_capacity FROM classrooms"
        if aggregation["function"] == "COUNT" and "student" in q and len(tables) == 1:
            return "SELECT COUNT(*) AS total_students FROM students"
        if aggregation["function"] == "COUNT" and ("building" in q or "distinct" in q) and "capacity" in q:
            cap_filter = next((f for f in filters if f[0] == "capacity"), None)
            n = cap_filter[2] if cap_filter else "100"
            return f"SELECT COUNT(DISTINCT building) FROM classrooms WHERE capacity > {n}"

        # ── Students enrolled in more than N courses ──
        if "student" in q and ("more than" in q or "greater than" in q) and ("course" in q or "enroll" in q):
            m = re.search(r'(?:more|greater) than (\d+)', q)
            n = m.group(1) if m else '2'
            return (f"SELECT s.first_name, s.last_name FROM students s "
                    f"JOIN enrollments e ON s.student_id = e.student_id "
                    f"GROUP BY s.student_id, s.first_name, s.last_name "
                    f"HAVING COUNT(e.course_id) > {n}")

        # ── How many students in a department ──
        if ("how many" in q or "count" in q) and "student" in q and ("department" in q or "dept" in q):
            dept_filter = next((f for f in filters if f[0] == "dept_name"), None)
            if dept_filter:
                return (f"SELECT COUNT(DISTINCT e.student_id) FROM enrollments e "
                        f"JOIN courses c ON e.course_id = c.course_id "
                        f"JOIN departments d ON c.dept_id = d.dept_id "
                        f"WHERE d.dept_name = {dept_filter[2]}")

        # ── Department + course HAVING ──
        if ("department" in q or "dept" in q) and aggregation["having"] and "course" in q:
            return (f"SELECT d.dept_name, COUNT(c.course_id) AS course_count "
                    f"FROM departments d JOIN courses c ON d.dept_id = c.dept_id "
                    f"GROUP BY d.dept_name HAVING COUNT(c.course_id) > {aggregation['having']}")

        # ── Department + instructor HAVING ──
        if ("department" in q or "dept" in q) and aggregation["having"] and "instructor" in q:
            return (f"SELECT d.dept_name, COUNT(i.instructor_id) AS instructor_count "
                    f"FROM departments d JOIN instructors i ON d.dept_id = i.dept_id "
                    f"GROUP BY d.dept_name HAVING COUNT(i.instructor_id) > {aggregation['having']}")

        # ── Top N departments by instructors ──
        if limit and ("department" in q or "dept" in q) and "instructor" in q:
            return (f"SELECT d.dept_name, COUNT(i.instructor_id) AS instructor_count "
                    f"FROM departments d JOIN instructors i ON d.dept_id = i.dept_id "
                    f"GROUP BY d.dept_name ORDER BY instructor_count DESC LIMIT {limit}")

        # ── Rank departments by courses ──
        if "rank" in q and ("department" in q or "dept" in q) and "course" in q:
            return ("SELECT d.dept_name, COUNT(c.course_id) AS course_count "
                    "FROM departments d JOIN courses c ON d.dept_id = c.dept_id "
                    "GROUP BY d.dept_name ORDER BY course_count DESC")

        # ── How many courses per department ──
        if ("how many" in q) and "course" in q and ("department" in q or "dept" in q):
            return ("SELECT d.dept_name, COUNT(c.course_id) AS course_count "
                    "FROM departments d JOIN courses c ON d.dept_id = c.dept_id "
                    "GROUP BY d.dept_name")

        # ── Courses with department names ──
        if "course" in q and ("department" in q or "dept" in q) and ("list" in q or "with" in q or "their" in q):
            return ("SELECT c.course_name, d.dept_name FROM courses c "
                    "JOIN departments d ON c.dept_id = d.dept_id")

        # ── Instructors in a specific department ──
        if ("instructor" in q or "professor" in q) and ("department" in q or "dept" in q):
            dept_filter = next((f for f in filters if f[0] == "dept_name"), None)
            if dept_filter:
                return (f"SELECT i.first_name, i.last_name FROM instructors i "
                        f"JOIN departments d ON i.dept_id = d.dept_id "
                        f"WHERE d.dept_name = {dept_filter[2]}")

        # ── Instructors + buildings ──
        if ("instructor" in q or "professor" in q) and ("building" in q or "teach" in q):
            return ("SELECT i.first_name || ' ' || i.last_name AS instructor, c.building "
                    "FROM instructors i JOIN sections s ON i.instructor_id = s.instructor_id "
                    "JOIN classrooms c ON s.classroom_id = c.classroom_id")

        # ── In-person courses + credits ──
        if ("in-person" in q or "in person" in q) and "credit" in q:
            m = re.search(r'more than (\d+)', q)
            n = m.group(1) if m else '3'
            return f"SELECT course_name FROM courses WHERE is_online = 0 AND credits > {n}"

        # ── Course credit filter ──
        credit_filter = next((f for f in filters if f[0] == "credits"), None)
        if credit_filter and "course" in q:
            return f"SELECT course_name FROM courses WHERE credits = {credit_filter[2]}"

        # ── Online courses ──
        if "online" in q and "course" in q:
            return "SELECT course_name, credits FROM courses WHERE is_online = 1"

        # ── Courses on a day ──
        if "course" in q and ("taught" in q or "monday" in q or "tuesday" in q):
            day_match = re.search(r'(monday|tuesday|wednesday|thursday|friday)', q)
            if day_match:
                letter = day_match.group(1)[0].upper()
                return (f"SELECT DISTINCT c.course_name FROM courses c "
                        f"JOIN sections s ON c.course_id = s.course_id "
                        f"JOIN time_slots t ON s.time_slot_id = t.time_slot_id "
                        f"WHERE t.day_of_week LIKE '%{letter}%'")

        # ── Courses offered in semester ──
        sem_filter = next((f for f in filters if f[0] == "semester"), None)
        if sem_filter and "course" in q:
            return (f"SELECT DISTINCT c.course_name FROM courses c "
                    f"JOIN sections s ON c.course_id = s.course_id "
                    f"WHERE s.semester = {sem_filter[2]}")

        # ── List departments (simple) ──
        if ("list" in q or "show" in q or "all" in q) and "department" in q and "course" not in q:
            return "SELECT dept_name FROM departments"

        # ── Student year filter ──
        year_filter = next((f for f in filters if f[0] == "enrollment_year"), None)
        if year_filter and "student" in q:
            return f"SELECT first_name, last_name FROM students WHERE enrollment_year = {year_filter[2]}"

        # ── Student name LIKE ──
        like_filter = next((f for f in filters if f[1] == "LIKE"), None)
        if like_filter and "student" in q:
            return f"SELECT first_name, last_name FROM students WHERE first_name LIKE {like_filter[2]}"

        # ── Student count ──
        if ("how many" in q or "count" in q) and "student" in q:
            return "SELECT COUNT(*) AS total_students FROM students"

        # ── Student grade filter ──
        grade_filter = next((f for f in filters if f[0] == "grade"), None)
        if grade_filter and "student" in q:
            return (f"SELECT DISTINCT s.first_name, s.last_name FROM students s "
                    f"JOIN enrollments e ON s.student_id = e.student_id "
                    f"WHERE e.grade = {grade_filter[2]}")

        # ── Advisor patterns ──
        if "advisor" in q or "adviser" in q or "advised" in q:
            name_filter = next((f for f in filters if f[0] == "instructor_name"), None)
            if name_filter and isinstance(name_filter[2], list) and len(name_filter[2]) == 2:
                first, last = name_filter[2]
                return (f"SELECT s.first_name, s.last_name FROM students s "
                        f"JOIN advisors a ON s.student_id = a.student_id "
                        f"JOIN instructors i ON a.instructor_id = i.instructor_id "
                        f"WHERE i.first_name = '{first}' AND i.last_name = '{last}'")
            return ("SELECT s.first_name, s.last_name, "
                    "i.first_name AS advisor_first, i.last_name AS advisor_last "
                    "FROM students s JOIN advisors a ON s.student_id = a.student_id "
                    "JOIN instructors i ON a.instructor_id = i.instructor_id")

        # ── Prerequisite patterns ──
        if "prerequisite" in q or "prereq" in q:
            prereq_filter = next((f for f in filters if f[0] == "prereq_course_name"), None)
            if prereq_filter:
                return (f"SELECT c.course_name FROM courses c "
                        f"JOIN prerequisites p ON c.course_id = p.course_id "
                        f"JOIN courses prereq ON p.prereq_id = prereq.course_id "
                        f"WHERE prereq.course_name = {prereq_filter[2]}")
            return ("SELECT c.course_name AS course, p.course_name AS prerequisite "
                    "FROM courses c JOIN prerequisites pr ON c.course_id = pr.course_id "
                    "JOIN courses p ON pr.prereq_id = p.course_id")

        # ── Grade filter (generic) ──
        if "grade" in q:
            if grade_filter:
                return (f"SELECT DISTINCT s.first_name, s.last_name FROM students s "
                        f"JOIN enrollments e ON s.student_id = e.student_id "
                        f"WHERE e.grade = {grade_filter[2]}")
            return ("SELECT s.first_name, s.last_name, e.grade "
                    "FROM students s JOIN enrollments e ON s.student_id = e.student_id")

        # ── Instructor (simple) ──
        if "instructor" in q or "professor" in q or "faculty" in q:
            return "SELECT first_name, last_name, dept_id FROM instructors"

        # ── Classroom capacity ──
        if "classroom" in q or "capacity" in q or "building" in q:
            cap_filter = next((f for f in filters if f[0] == "capacity"), None)
            if ("total" in q or "sum" in q):
                return "SELECT SUM(capacity) AS total_capacity FROM classrooms"
            if cap_filter:
                return f"SELECT building, room_number, capacity FROM classrooms WHERE capacity > {cap_filter[2]}"
            return "SELECT building, room_number, capacity FROM classrooms ORDER BY capacity DESC"

        # ── Time slot patterns ──
        if "time" in q or "schedule" in q or "slot" in q:
            day_filter = next((f for f in filters if f[0] == "day_of_week"), None)
            if day_filter:
                return f"SELECT start_time, end_time FROM time_slots WHERE day_of_week = {day_filter[2]}"
            return "SELECT day_of_week, start_time, end_time FROM time_slots"

        # ── Department + enrollment ──
        if ("department" in q or "dept" in q) and ("student" in q or "enroll" in q):
            return ("SELECT d.dept_name, COUNT(DISTINCT e.student_id) AS total_students "
                    "FROM departments d JOIN courses c ON d.dept_id = c.dept_id "
                    "JOIN enrollments e ON c.course_id = e.course_id "
                    "GROUP BY d.dept_name ORDER BY total_students DESC")

        # ── Generic fallback ──
        if tables:
            t = tables[0]
            alias = TABLE_ALIASES.get(t, t[0])
            return f"SELECT * FROM {t} {alias} LIMIT 10"
        return "SELECT * FROM departments LIMIT 10"


# Module-level singleton
reasoner = CoTReasoner()
