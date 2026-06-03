import sqlite3
import os
import time
from typing import Tuple, List, Any, Optional

DB_PATH = "data/beaver.db"

# ─────────────────────────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────────────────────────
TABLES_DDL = {
    "departments": """
        CREATE TABLE IF NOT EXISTS departments (
            dept_id   INTEGER PRIMARY KEY,
            dept_name TEXT NOT NULL
        )""",
    "courses": """
        CREATE TABLE IF NOT EXISTS courses (
            course_id   INTEGER PRIMARY KEY,
            course_name TEXT NOT NULL,
            dept_id     INTEGER,
            credits     INTEGER,
            is_online   BOOLEAN
        )""",
    "students": """
        CREATE TABLE IF NOT EXISTS students (
            student_id      INTEGER PRIMARY KEY,
            first_name      TEXT,
            last_name       TEXT,
            enrollment_year INTEGER
        )""",
    "enrollments": """
        CREATE TABLE IF NOT EXISTS enrollments (
            enrollment_id INTEGER PRIMARY KEY,
            student_id    INTEGER,
            course_id     INTEGER,
            semester      TEXT,
            grade         TEXT
        )""",
    "instructors": """
        CREATE TABLE IF NOT EXISTS instructors (
            instructor_id INTEGER PRIMARY KEY,
            first_name    TEXT,
            last_name     TEXT,
            dept_id       INTEGER
        )""",
    "classrooms": """
        CREATE TABLE IF NOT EXISTS classrooms (
            classroom_id INTEGER PRIMARY KEY,
            building     TEXT,
            room_number  TEXT,
            capacity     INTEGER
        )""",
    "time_slots": """
        CREATE TABLE IF NOT EXISTS time_slots (
            time_slot_id INTEGER PRIMARY KEY,
            day_of_week  TEXT,
            start_time   TEXT,
            end_time     TEXT
        )""",
    "sections": """
        CREATE TABLE IF NOT EXISTS sections (
            section_id    INTEGER PRIMARY KEY,
            course_id     INTEGER,
            instructor_id INTEGER,
            classroom_id  INTEGER,
            time_slot_id  INTEGER,
            semester      TEXT
        )""",
    "prerequisites": """
        CREATE TABLE IF NOT EXISTS prerequisites (
            course_id INTEGER,
            prereq_id INTEGER,
            PRIMARY KEY (course_id, prereq_id)
        )""",
    "advisors": """
        CREATE TABLE IF NOT EXISTS advisors (
            student_id    INTEGER,
            instructor_id INTEGER,
            PRIMARY KEY (student_id, instructor_id)
        )""",
}

# ─────────────────────────────────────────────────────────────────
# Seed data (rich enough to give meaningful benchmark results)
# ─────────────────────────────────────────────────────────────────
SEED_SQL = """
-- Departments
INSERT INTO departments (dept_id, dept_name) VALUES
  (1,'Computer Science'),(2,'Mathematics'),(3,'Physics'),
  (4,'Chemistry'),(5,'Biology');

-- Courses
INSERT INTO courses (course_id, course_name, dept_id, credits, is_online) VALUES
  (101,'Intro to CS',         1, 4, 0),
  (102,'Data Structures',     1, 4, 0),
  (103,'Algorithms',          1, 4, 0),
  (104,'Online ML',           1, 3, 1),
  (201,'Calculus I',          2, 4, 0),
  (202,'Linear Algebra',      2, 4, 0),
  (203,'Statistics Online',   2, 3, 1),
  (301,'Physics I',           3, 4, 0),
  (302,'Quantum Mechanics',   3, 4, 0),
  (401,'Organic Chemistry',   4, 4, 0),
  (402,'Biochemistry Online', 4, 3, 1),
  (501,'Cell Biology',        5, 4, 0);

-- Students
INSERT INTO students (student_id, first_name, last_name, enrollment_year) VALUES
  (1,'Alice',   'Smith',   2023),
  (2,'Bob',     'Jones',   2022),
  (3,'Charlie', 'Brown',   2023),
  (4,'Diana',   'Prince',  2021),
  (5,'Eve',     'Wilson',  2022),
  (6,'Frank',   'Miller',  2023),
  (7,'Grace',   'Lee',     2021),
  (8,'Henry',   'Davis',   2022),
  (9,'Iris',    'Chen',    2023),
  (10,'Jack',   'Taylor',  2021);

-- Enrollments
INSERT INTO enrollments (enrollment_id, student_id, course_id, semester, grade) VALUES
  (1, 1, 101,'Fall 2023',   'A'),
  (2, 2, 102,'Spring 2024', 'B'),
  (3, 1, 104,'Fall 2023',   'A'),
  (4, 3, 101,'Fall 2023',   'B'),
  (5, 4, 202,'Fall 2021',   'A'),
  (6, 5, 201,'Fall 2022',   'C'),
  (7, 6, 301,'Fall 2023',   'B'),
  (8, 7, 501,'Spring 2022', 'A'),
  (9, 8, 102,'Fall 2022',   'B'),
  (10,9, 103,'Fall 2023',   'A'),
  (11,10,401,'Spring 2021', 'C'),
  (12,1, 201,'Spring 2024', 'A'),
  (13,2, 203,'Fall 2022',   'B'),
  (14,3, 104,'Fall 2023',   'A'),
  (15,4, 101,'Fall 2021',   'A');

-- Instructors
INSERT INTO instructors (instructor_id, first_name, last_name, dept_id) VALUES
  (1,'Dr. Alan',    'Turing',    1),
  (2,'Dr. Ada',     'Lovelace',  2),
  (3,'Dr. Richard', 'Feynman',   3),
  (4,'Dr. Marie',   'Curie',     4),
  (5,'Dr. Charles', 'Darwin',    5),
  (6,'Dr. Linus',   'Torvalds',  1);

-- Classrooms
INSERT INTO classrooms (classroom_id, building, room_number, capacity) VALUES
  (1,'Stata Center', '32-123',  100),
  (2,'Building 10',  '10-250',  300),
  (3,'Main Hall',    'MH-100',  500),
  (4,'Science Wing', 'SW-201',  150),
  (5,'Tech Tower',   'TT-301',   75);

-- Time slots
INSERT INTO time_slots (time_slot_id, day_of_week, start_time, end_time) VALUES
  (1,'MWF','10:00','11:00'),
  (2,'TR', '13:00','14:30'),
  (3,'MWF','14:00','15:00'),
  (4,'TR', '09:00','10:30'),
  (5,'MW', '16:00','17:30');

-- Sections
INSERT INTO sections (section_id, course_id, instructor_id, classroom_id, time_slot_id, semester) VALUES
  (1, 101, 1, 1, 1,'Fall 2023'),
  (2, 102, 1, 2, 2,'Spring 2024'),
  (3, 201, 2, 3, 3,'Fall 2023'),
  (4, 301, 3, 4, 4,'Fall 2023'),
  (5, 401, 4, 5, 5,'Fall 2023'),
  (6, 501, 5, 4, 2,'Spring 2022'),
  (7, 103, 6, 1, 3,'Fall 2023');

-- Prerequisites
INSERT INTO prerequisites (course_id, prereq_id) VALUES
  (102,101),
  (103,102),
  (302,301),
  (202,201);

-- Advisors
INSERT INTO advisors (student_id, instructor_id) VALUES
  (1,1),(2,2),(3,1),(4,2),(5,3),
  (6,3),(7,5),(8,1),(9,6),(10,4);
"""


def init_database():
    """Creates tables and seeds data if the database is empty."""
    os.makedirs("data", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for ddl in TABLES_DDL.values():
        cursor.execute(ddl)

    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] == 0:
        cursor.executescript(SEED_SQL)

    conn.commit()
    conn.close()


def execute_query(sql: str) -> Tuple[bool, List[str], List[Any], int, float, Optional[str]]:
    """Executes a SQL query safely and returns (success, columns, rows, row_count, latency_ms, error)."""
    t0 = time.time()
    TIMEOUT_SECONDS = 2.0

    def progress_handler():
        if time.time() - t0 > TIMEOUT_SECONDS:
            return 1  # Abort query (raises sqlite3.OperationalError: interrupted)
        return 0

    try:
        conn   = sqlite3.connect(DB_PATH)
        # Set progress handler to check for timeout every 1000 SQLite VM instructions
        conn.set_progress_handler(progress_handler, 1000)
        
        cursor = conn.cursor()
        cursor.execute(sql)
        rows    = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        conn.close()
        return True, columns, rows, len(rows), (time.time() - t0) * 1000, None
    except sqlite3.OperationalError as exc:
        err_msg = "Query interrupted (Timeout)" if "interrupted" in str(exc) else str(exc)
        return False, [], [], 0, (time.time() - t0) * 1000, err_msg
    except Exception as exc:
        return False, [], [], 0, (time.time() - t0) * 1000, str(exc)