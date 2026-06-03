# Enterprise Text-to-SQL API
### NST 48-Hour Build Challenge

A production-grade FastAPI microservice that converts natural language questions
into executable SQLite SQL using semantic schema retrieval + LLM generation.
Built on the BEAVER university benchmark dataset.

---

## System Architecture

```
User Question
     ↓
SchemaContextBuilder   ← sentence-transformers (BAAI/bge-large-en-v1.5)
     ↓
CoT Layer              ← Local chain-of-thought reasoning (intent, tables, joins)
     ↓
LLM Layer              ← Groq llama-3.3-70b → HF sqlcoder-7b-2 → rule-based fallback
     ↓
ValidationLayer        ← sqlglot AST parsing, blocks DROP/DELETE/INSERT
     ↓
DBLayer                ← SQLite execution, returns rows + columns
     ↓
MetricsLayer           ← retrieval recall, exact match, execution match, latency
     ↓
FastAPI Response       ← SQL + results + metrics
```

---

## Module Descriptions

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app, lifespan startup, middleware, endpoint routing |
| `app/models.py` | Pydantic request/response schemas for all 3 endpoints |
| `app/retrieval.py` | Semantic table retrieval via sentence-transformers |
| `app/cot_layer.py` | Chain-of-thought local reasoning: intent, tables, joins, filters |
| `app/llm.py` | Prompt construction, Groq API call, HF fallback, retry logic |
| `app/validation.py` | SQL AST validation via sqlglot; blocks destructive statements |
| `app/database.py` | SQLite schema creation, rich seed data, query execution |
| `app/metrics_layer.py` | 30-query benchmark suite with full metric computation |
| `app/dataset_loader.py` | BEAVER dataset loader from HuggingFace |

---

## Tech Stack

- **FastAPI** — REST API framework with automatic OpenAPI docs at `/docs`
- **sentence-transformers** (`BAAI/bge-large-en-v1.5`) — local semantic embeddings
- **Groq** (`llama-3.3-70b-versatile`) — primary LLM, ultra-fast with CoT
- **defog/sqlcoder-7b-2** — HuggingFace fallback, purpose-built for text-to-SQL
- **sqlglot** — SQL AST parsing and validation
- **SQLite** — embedded database, 10 tables, rich seed data
- **Pydantic v2** — request/response validation
- **uvicorn** — ASGI server

---

## Setup & Running

### 1. Clone and install
```bash
git clone https://github.com/saitejacodes/text-to-sql-api.git
cd text-to-sql-api
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment
Create a `.env` file in the project root:
```env
GROQ_API_KEY=your_groq_api_key_here
HF_API_TOKEN=your_huggingface_token_here
```

- **Groq API key** (free): https://console.groq.com
- **HuggingFace token** (free): https://huggingface.co/settings/tokens
  → Enable **"Make calls to Inference Providers"** permission only.

> The system works without any API keys via the built-in rule-based fallback.

### 3. Run
```bash
python run.py
```
API starts at `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

---

## API Endpoints

### `GET /health`
```json
{ "status": "ok", "service": "Text-to-SQL API", "version": "1.0.0" }
```

---

### `POST /retrieve`
Identifies relevant database tables for a natural language question using semantic similarity.

**Request:**
```json
{ "question": "Which departments have more than 100 students?" }
```

**Response:**
```json
{
  "retrieved_tables": ["departments", "enrollments", "students"],
  "scores": [0.8491, 0.7202, 0.5330],
  "confidence": 0.7008,
  "details": {
    "departments": {
      "relevance_score": 0.8491,
      "reason": "Matched on 'department' — stores academic department info."
    },
    "enrollments": {
      "relevance_score": 0.7202,
      "reason": "Needed to count students per department."
    }
  }
}
```

---

### `POST /generate-sql`
Full pipeline: semantic retrieval → CoT reasoning → LLM generation → validation → execution.

**Request:**
```json
{
  "question": "Which instructor teaches the most courses?",
  "use_retrieved_context": true
}
```

**Response:**
```json
{
  "sql": "SELECT i.first_name, i.last_name, COUNT(s.section_id) AS course_count FROM instructors AS i JOIN sections AS s ON i.instructor_id = s.instructor_id GROUP BY i.instructor_id, i.first_name, i.last_name ORDER BY course_count DESC LIMIT 1",
  "retrieved_tables": ["instructors", "sections", "courses"],
  "is_valid_syntax": true,
  "parsing_errors": null,
  "confidence": 0.7849,
  "prompt_used": "### Task\nYou are an expert SQLite SQL generator..."
}
```

---

### `POST /benchmark`
Evaluates the full pipeline on 30 curated queries covering all 10 schema tables.
Measures retrieval recall, SQL exact match, execution match, latency, and error breakdown.

**Response:**
```json
{
  "total_queries": 30,
  "metrics": {
    "retrieval_recall_at_5": 0.92,
    "retrieval_recall_at_10": 0.96,
    "sql_exact_match_accuracy": 0.55,
    "sql_execution_match_accuracy": 0.72,
    "parsing_success_rate": 0.97,
    "average_latency_ms": 1200.0
  },
  "subtask_breakdown": {
    "multi_table_retrieval": 0.92,
    "column_mapping": 0.76,
    "join_detection": 0.70,
    "domain_knowledge": 0.73
  },
  "error_analysis": {
    "retrieval_failures": 2,
    "parsing_failures": 1,
    "execution_failures": 3,
    "logic_errors": 4
  }
}
```

> **Note:** Benchmark takes ~8 minutes to complete (30 queries × 15s delay to respect Groq rate limits).

---

## Database Schema

10 tables from the BEAVER university benchmark:

```
departments ──< courses ──< enrollments >── students
     │               │
     └──< instructors └──< sections >── classrooms
                              └──< time_slots
courses ──< prerequisites
students ──< advisors >── instructors
```

Tables: `departments`, `courses`, `students`, `enrollments`, `instructors`,
`classrooms`, `time_slots`, `sections`, `prerequisites`, `advisors`

---

## Benchmark Query Coverage (30 queries)

| # | Pattern | Tables Involved |
|---|---------|----------------|
| 1 | Simple SELECT | departments |
| 2 | WHERE filter (numeric) | courses |
| 3 | COUNT aggregate | students |
| 4 | Two-table JOIN | courses, departments |
| 5 | JOIN + WHERE string | instructors, departments |
| 6 | GROUP BY + COUNT | departments, courses |
| 7 | GROUP BY + HAVING | departments, instructors |
| 8 | Boolean filter | courses |
| 9 | Year filter | students |
| 10 | Numeric WHERE | classrooms |
| 11 | Three-table prerequisites | courses, prerequisites |
| 12 | Grade filter | students, enrollments |
| 13 | SUM aggregate | classrooms |
| 14 | Sections + courses JOIN | courses, sections |
| 15 | Three-table advisor chain | students, advisors, instructors |
| 16 | ORDER BY + GROUP BY | departments, courses |
| 17 | Time slot filter | time_slots |
| 18 | Instructor + classroom | instructors, sections, classrooms |
| 19 | NOT IN subquery | students, enrollments |
| 20 | AVG aggregate | courses |
| 21 | Subquery with AVG | courses |
| 22 | MAX nested subquery | departments, courses |
| 23 | GROUP BY HAVING on JOIN | students, enrollments |
| 24 | Multi-table COUNT DISTINCT | enrollments, courses, departments |
| 25 | ORDER BY + LIMIT | departments, instructors |
| 26 | COUNT DISTINCT | classrooms |
| 27 | NOT IN (departments) | departments, courses |
| 28 | LIKE string match | students |
| 29 | Triple JOIN + day filter | courses, sections, time_slots |
| 30 | Multiple WHERE conditions | courses |

---

## Key Design Decisions

**Why `BAAI/bge-large-en-v1.5` for retrieval?**
State-of-the-art embedding model for semantic similarity. Schema descriptions are
enriched with synonyms to maximise recall on ambiguous natural language questions.

**Why Groq `llama-3.3-70b`?**
Free tier, extremely fast (~1–2s per query), and highly capable at structured
reasoning tasks like SQL generation with Chain-of-Thought prompting.

**Why a CoT layer before the LLM?**
Local chain-of-thought reasoning (intent detection, table identification, join path
planning) pre-computes hints that are injected into the LLM prompt. This reduces
hallucination on complex multi-table queries.

**Why `defog/sqlcoder-7b-2` as fallback?**
Purpose-built for text-to-SQL tasks. Handles cases where the general-purpose LLM
produces incorrect SQL structure.

**Why `sqlglot` for validation?**
Regex cannot safely validate SQL. AST parsing detects syntax errors, enforces
SELECT-only semantics, and normalises queries for fair exact-match benchmarking.

**Why SQLite?**
Zero infrastructure overhead. The database seeds rich data at startup enabling
real execution-match testing without an external database server.

---

## Screenshots

### FastAPI running on localhost (`/docs`)
[Add screenshot here]

### `POST /retrieve` response
[Add screenshot here]

### `POST /generate-sql` response
[Add screenshot here]

### `POST /benchmark` response
[Add screenshot here]
