import os
import re
import time
import requests
import logging
from dotenv import load_dotenv
from typing import Optional
from app.database import execute_query

load_dotenv()
GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
HF_API_TOKEN  = os.getenv("HF_API_TOKEN")

logger = logging.getLogger("app.llm_layer")

# ── Full schema always sent to LLM ──────────────────────────────────────────
SCHEMA_DDL = """
CREATE TABLE departments (
    dept_id   INTEGER PRIMARY KEY,
    dept_name TEXT NOT NULL
);
CREATE TABLE courses (
    course_id   INTEGER PRIMARY KEY,
    course_name TEXT NOT NULL,
    dept_id     INTEGER REFERENCES departments(dept_id),
    credits     INTEGER,
    is_online   BOOLEAN  -- 1 = online, 0 = in-person
);
CREATE TABLE students (
    student_id      INTEGER PRIMARY KEY,
    first_name      TEXT,
    last_name       TEXT,
    enrollment_year INTEGER
);
CREATE TABLE enrollments (
    enrollment_id INTEGER PRIMARY KEY,
    student_id    INTEGER REFERENCES students(student_id),
    course_id     INTEGER REFERENCES courses(course_id),
    semester      TEXT,
    grade         TEXT
);
CREATE TABLE instructors (
    instructor_id INTEGER PRIMARY KEY,
    first_name    TEXT,
    last_name     TEXT,
    dept_id       INTEGER REFERENCES departments(dept_id)
);
CREATE TABLE classrooms (
    classroom_id INTEGER PRIMARY KEY,
    building     TEXT,
    room_number  TEXT,
    capacity     INTEGER
);
CREATE TABLE time_slots (
    time_slot_id INTEGER PRIMARY KEY,
    day_of_week  TEXT,
    start_time   TEXT,
    end_time     TEXT
);
CREATE TABLE sections (
    section_id    INTEGER PRIMARY KEY,
    course_id     INTEGER REFERENCES courses(course_id),
    instructor_id INTEGER REFERENCES instructors(instructor_id),
    classroom_id  INTEGER REFERENCES classrooms(classroom_id),
    time_slot_id  INTEGER REFERENCES time_slots(time_slot_id),
    semester      TEXT
);
CREATE TABLE prerequisites (
    course_id INTEGER REFERENCES courses(course_id),
    prereq_id INTEGER REFERENCES courses(course_id),
    PRIMARY KEY (course_id, prereq_id)
);
CREATE TABLE advisors (
    student_id    INTEGER REFERENCES students(student_id),
    instructor_id INTEGER REFERENCES instructors(instructor_id),
    PRIMARY KEY (student_id, instructor_id)
);
"""

from app.cot_layer import reasoner
from app.retrieval import retriever

def build_prompt(question: str, retrieved_schemas: Optional[dict] = None, error_msg: Optional[str] = None) -> str:
    # Get local CoT reasoning
    cot_analysis = reasoner.analyze(question)
    cot_hints = cot_analysis["reasoning"]

    # Prune schema to only include retrieved tables
    dynamic_schema = SCHEMA_DDL
    if retrieved_schemas:
        tables_to_include = list(retrieved_schemas.keys())
        extracted = []
        for t in tables_to_include:
            match = re.search(rf"(CREATE TABLE {t} \([\s\S]*?\);)", SCHEMA_DDL)
            if match:
                extracted.append(match.group(1))
        if extracted:
            dynamic_schema = "\n".join(extracted)
            
    # Dynamically fetch the 3 most relevant SQL examples for this specific question
    dynamic_few_shot = retriever.retrieve_few_shot(question, top_k=3)

    prompt = f"""### Task
You are an expert SQLite SQL generator. Given a natural language question and a database schema, produce a single, valid SQLite SELECT query that answers the question precisely.
Rules:
- Think step-by-step. Write your reasoning inside <think>...</think> tags. Reason about tables, joins, and filters before writing the SQL.
- Output ONLY the raw SQL query inside a ```sql ... ``` block after your reasoning.
- Use table aliases for clarity.
- Never use DROP, DELETE, INSERT, UPDATE, ALTER, or CREATE.

### Schema Relationships (Foreign Keys)
- courses.dept_id -> departments.dept_id
- enrollments.student_id -> students.student_id
- enrollments.course_id -> courses.course_id
- instructors.dept_id -> departments.dept_id
- sections.course_id -> courses.course_id
- sections.instructor_id -> instructors.instructor_id
- sections.classroom_id -> classrooms.classroom_id
- sections.time_slot_id -> time_slots.time_slot_id
- prerequisites.course_id -> courses.course_id
- prerequisites.prereq_id -> courses.course_id
- advisors.student_id -> students.student_id
- advisors.instructor_id -> instructors.instructor_id

### Database Schema (SQLite)
{dynamic_schema}

### Few-Shot Examples
{dynamic_few_shot}

### Question
{question}
"""
    if error_msg:
        prompt += f"\n### Previous Execution Error\nYour previous SQL query failed with the following error:\n{error_msg}\nPlease fix the query and provide the corrected SQL.\n"
    
    prompt += "\n### Response\n"
    return prompt


def rule_based_generator(question: str, tables: list) -> str:
    """Comprehensive rule-based fallback when all LLMs are unavailable."""
    # Use the local CoT layer to generate the fallback SQL
    analysis = reasoner.analyze(question)
    return analysis["generated_sql"]


def extract_sql(text: str) -> str:
    """Robust SQL extraction from LLM output."""
    m = re.search(r'```sql\s*\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r'```\s*\n(.*?)\n```', text, re.DOTALL)
    if m: return m.group(1).strip()
    m = re.search(r'(SELECT\b.*?)(?:;|\Z)', text, re.DOTALL | re.IGNORECASE)
    if m: return m.group(1).strip().rstrip(';')
    return text.split('```')[0].strip().rstrip(';')


def generate_with_groq(prompt: str) -> Optional[str]:
    """Primary LLM: Groq (free, fast — llama-3.3-70b)."""
    if not GROQ_API_KEY or GROQ_API_KEY.strip() in ("", "your_groq_key_here"):
        return None
        
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 800,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            elif resp.status_code == 429:
                wait_time = 15 * (2 ** attempt)  # 15s → 30s → 60s exponential
                logger.warning("Groq rate limit (429). Retrying in %ds...", wait_time)
                time.sleep(wait_time)
                continue
                
            logger.error("Groq error %s: %s", resp.status_code, resp.text[:100])
            return None
        except Exception as e:
            logger.error("Groq exception: %s", e)
            return None
            
    return None


def generate_with_hf(prompt: str) -> Optional[str]:
    """Secondary LLM: HuggingFace Inference API (defog/sqlcoder-7b-2)."""
    if not HF_API_TOKEN or HF_API_TOKEN.strip() in ("", "your_token_here"):
        return None
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 300, "return_full_text": False,
                       "temperature": 0.05, "stop": ["\n\n", "###", "Question:"]},
    }
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api-inference.huggingface.co/models/defog/sqlcoder-7b-2",
                headers=headers, json=payload, timeout=45,
            )
            if resp.status_code == 200:
                return resp.json()[0]["generated_text"].strip()
            elif resp.status_code == 503:
                wait = 20 * (attempt + 1)
                logger.warning("HF model loading. Retrying in %ds (attempt %d/3)", wait, attempt+1)
                time.sleep(wait)
            else:
                logger.error("HF API error %s: %s", resp.status_code, resp.text[:200])
                break
        except requests.exceptions.Timeout:
            logger.error("HF request timed out (attempt %d)", attempt+1)
        except Exception as e:
            logger.error("HF exception: %s", e)
            break
    return None


def generate_sql(
    question: str,
    retrieved_tables: list,
    retrieved_schemas: Optional[dict] = None,
) -> tuple[str, str]:
    """
    Generate SQL using: Groq (primary) → HF (secondary) → rule-based (fallback).
    Returns (sql, prompt_used).
    Includes a self-correction loop.
    """
    error_msg = None
    prompt = ""
    
    # 0. Try CoT fast-path ONLY for simple single-table queries
    #    Multi-table queries MUST go through the LLM for quality
    if len(retrieved_tables) <= 1:
        try:
            cot_sql = rule_based_generator(question, retrieved_tables)
            if cot_sql and cot_sql.upper().strip().startswith("SELECT"):
                exec_ok, _, _, _, _, _ = execute_query(cot_sql)
                if exec_ok:
                    prompt = build_prompt(question, retrieved_schemas)
                    logger.info("SQL generated via CoT (local fast-path, single-table).")
                    return cot_sql.rstrip(";"), prompt
        except Exception:
            pass
    
    for attempt in range(2):
        prompt = build_prompt(question, retrieved_schemas, error_msg)
        logger.debug("Full prompt (attempt %d):\n%s", attempt + 1, prompt)

        raw = generate_with_groq(prompt)
        if raw:
            sql = extract_sql(raw)
            if sql.upper().strip().startswith("SELECT"):
                logger.info("SQL generated via Groq (attempt %d).", attempt + 1)
                logger.debug("Raw Groq output:\n%s", raw)
                
                # Check execution
                exec_ok, _, _, _, _, exec_err = execute_query(sql)
                if exec_ok:
                    return sql.rstrip(';'), prompt
                else:
                    logger.warning("Execution failed on attempt %d: %s", attempt + 1, exec_err)
                    error_msg = exec_err
                    continue
            else:
                logger.warning("Groq output not a SELECT on attempt %d. Got: %s", attempt + 1, sql[:80])
        else:
            logger.warning("Groq unavailable on attempt %d.", attempt + 1)
            
        break # Exit retry loop if we didn't generate valid syntax or if API failed

    # If Groq loop fails or exhausts retries without success, fallback to HF
    raw = generate_with_hf(prompt)
    if raw:
        sql = extract_sql(raw)
        if sql.upper().strip().startswith("SELECT"):
            logger.info("SQL generated via HuggingFace.")
            logger.debug("Raw HF output:\n%s", raw)
            return sql.rstrip(';'), prompt
        logger.warning("HF output not a SELECT. Got: %s", sql[:80])

    # 3. Rule-based fallback
    logger.warning("All LLMs unavailable or failed. Using rule-based fallback.")
    return rule_based_generator(question, retrieved_tables), prompt