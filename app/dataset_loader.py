"""
dataset_loader.py - Loads benchmark queries from the Beaver dataset.
Falls back to curated custom queries if the dataset is unavailable.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger("app.dataset_loader")

# Table name mapping: Beaver names → our schema names
TABLE_MAP = {
    "classroom":  "classrooms",
    "department": "departments",
    "course":     "courses",
    "section":    "sections",
    "instructor": "instructors",
    "student":    "students",
    "advisor":    "advisors",
    "time_slot":  "time_slots",
    "prereq":     "prerequisites",
    "takes":      "enrollments",
}


def adapt_sql(sql: str) -> str:
    """Map Beaver table names to our schema names."""
    for beaver_name, our_name in TABLE_MAP.items():
        sql = re.sub(rf'\b{beaver_name}\b', our_name, sql, flags=re.IGNORECASE)
    return sql.strip()


def load_beaver_queries(max_count: int = 25) -> Optional[list]:
    """
    Try to load queries from beaverbench/beaver-query on HuggingFace.
    Returns a list of {question, gold_sql, gold_tables} dicts, or None if unavailable.
    """
    try:
        from datasets import load_dataset
        logger.info("Attempting to load Beaver dataset from HuggingFace...")
        ds = load_dataset("beaverbench/beaver-query", split="test")
        logger.info("Loaded %d Beaver queries from HuggingFace.", len(ds))

        queries = []
        for item in ds:
            if len(queries) >= max_count:
                break
            q   = item.get("question", "").strip()
            sql = item.get("query", "").strip()
            if not q or not sql:
                continue
            if not sql.upper().startswith("SELECT"):
                continue
            adapted_sql = adapt_sql(sql)
            tables = list(set(re.findall(
                r'\b(?:FROM|JOIN)\s+(\w+)', adapted_sql, re.IGNORECASE
            )))
            queries.append({
                "question":    q,
                "gold_sql":    adapted_sql,
                "gold_tables": tables,
            })

        if queries:
            logger.info("Using %d Beaver queries for benchmark.", len(queries))
            return queries
        logger.warning("Beaver dataset loaded but no valid queries found.")
        return None

    except Exception as e:
        logger.warning("Beaver dataset unavailable (%s). Using custom benchmark queries.", e)
        return None