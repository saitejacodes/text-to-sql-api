# REPO_MAP — text-to-sql-api (t2sql v2.0.0)

Snapshot taken 25 Oct 2026, commit `ca03a25`, before any Phase 1 change.

## Status at a glance

- **Tests:** 74 passed (`pytest -q`, Python 3.12, ~5 s, no network: a scripted fake LLM is used).
- **Lint:** `ruff check` + `ruff format --check` clean.
- **CI:** `.github/workflows/ci.yml` runs ruff + pytest on Python 3.11 and 3.12 on every push/PR.
- **Authors in git log:** only you (`saitejacodes` / `sai teja`, same email).

## Layout

```
src/t2sql/
  config.py            Settings from env vars, prefix T2SQL_ (pydantic-settings, reads .env)
  cli.py               `t2sql` CLI: ask, serve, eval, rescore, report
  api/app.py           FastAPI app (all HTTP routes live here)
  api/static/index.html  Plain-HTML playground served at "/"
  llm/client.py        LLMClient: OpenAI-compatible + native Ollama, cache, retries, token stats
  llm/prompts.py       Generation + repair prompts, SQL extraction from model text
  pipeline/pipeline.py prompt -> N candidates -> guard -> execute -> repair -> vote
  pipeline/context.py  DatabaseRegistry: finds *.sqlite in databases_dir, caches schema + value index
  db/introspect.py     Reads tables, PK/FK, example values, descriptions; renders M-Schema
  db/executor.py       Sandbox (layer 2)
  guard/sql_guard.py   AST guard (layer 1, sqlglot)
  retrieval/value_index.py  Fuzzy inverted index over DB cell values (rapidfuzz)
  retrieval/fewshot.py Masked-question BM25 over BIRD *train* split
  eval/runner.py       Resumable BIRD runs -> runs/<preset>/results.jsonl
  eval/metrics.py      Execution accuracy (official BIRD set-equality) + error buckets
  eval/report.py       Bootstrap CIs, McNemar tests -> runs/REPORT.md
tests/                 74 tests (guard, sandbox, red-team, pipeline, schema/values, eval, API)
examples/university.sql  Demo DB source (10 tables); Dockerfile builds university.sqlite from it
runs/                  Committed benchmark outputs (bare, mschema, values, full, full-omnisql-7b)
docs/EVALUATION.md, docs/DESIGN_NOTES.md
```

## HTTP endpoints (today)

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/` | – | playground HTML |
| GET | `/health` | – | `{status:"ok", version:"2.0.0", model}` |
| GET | `/v1/databases` | – | `{databases: [name, ...]}` |
| GET | `/v1/databases/{db}/schema` | – | `{db, tables: [...], prompt_schema: "<M-Schema text>"}` |
| POST | `/v1/validate` | `{db, sql}` | `{ok, reason, tables}` (guard only, no execution) |
| POST | `/v1/query` | `{db, question (3–1000 chars), evidence?, execute=true, n_candidates? (1–10)}` | `QueryResponse` below |

`QueryResponse`: `request_id, sql, confidence, result{columns, rows, truncated, elapsed_ms} | null,
error, value_hints[], candidates[{sql, ok, rows, repairs, error}], llm_calls, elapsed_ms`.

- Optional auth: `T2SQL_API_KEYS=k1,k2` makes every `/v1/*` call need `X-API-Key`.
- Unknown db → 404. LLM failure → 503 `LLM unavailable: ...`.
- Middleware adds `x-request-id` and `x-process-time-ms` and writes one JSON log line per request.
- **Not present yet:** CORS, rate limiting, `/metrics`, `/api/*` paths, `status: ok|blocked|error`
  field, `blocked_reason`, `repaired`, `model` in the response, examples endpoint, column lists
  per table in `/v1/databases`.

## How the LLM is called

- `LLMClient.chat(messages, temperature, seed, max_tokens, json_mode)` in `llm/client.py`.
- Two wire formats: native Ollama `/api/chat` (auto-detected for `:11434`, so `num_ctx` is honoured)
  or OpenAI-compatible `/chat/completions` with `Authorization: Bearer <key>`.
- **That already covers hosted providers with zero new code:** Groq
  (`https://api.groq.com/openai/v1`) and Gemini (`https://generativelanguage.googleapis.com/v1beta/openai`)
  both speak the OpenAI format. Config: `T2SQL_LLM_BASE_URL`, `T2SQL_LLM_MODEL`,
  `T2SQL_LLM_API_KEY`, `T2SQL_LLM_TIMEOUT_S`.
- Every response is cached in SQLite (`.cache/llm.sqlite`) under a SHA-256 of the full request.
- Bounded concurrency (semaphore, default 2), up to 6 retries with exponential backoff + jitter,
  honours `Retry-After` on 429/5xx.
- Tracks `calls`, `cache_hits`, `prompt_tokens`, `completion_tokens`.

## How the pipeline works (`pipeline/pipeline.py`)

1. Build prompt: M-Schema (types, keys, 3 example values/column, descriptions) + fuzzy value hints
   (+ optional few-shot).
2. 5 candidates by default: #0 greedy (T=0), #1–4 at T=0.7, run **sequentially** (so a local
   server reuses the prompt prefix).
3. Each candidate: guard → execute → on error up to 2 repair rounds with the error text fed back;
   if it ran but returned nothing/only NULLs, one extra revision (kept only if it returns rows).
4. Vote: group successful candidates by an order-insensitive fingerprint of their **result rows**;
   rank by (non-empty, group size, earliest index). `confidence = winning group size / 5`.
   This is the "agreement" number the brief wants exposed.
5. `repaired` is not a single field today, but each candidate has `repairs`, so it can be derived.

## How the sandbox works

- **Layer 1 – AST guard** (`guard/sql_guard.py`): parse with sqlglot; exactly 1 statement; must be a
  query; no forbidden node anywhere (Insert/Update/Delete/Drop/Create/Alter/Pragma/Attach/…);
  no forbidden functions (`load_extension`, `readfile`, …); only known tables; no schema-qualified
  tables. Returns a human-readable `reason` (good source for `blocked_reason`).
- **Layer 2 – executor** (`db/executor.py`): `mode=ro` URI, `PRAGMA query_only`, SQLite
  authorizer allowing only SELECT/READ/FUNCTION/RECURSIVE, progress-handler wall-clock timeout
  (default 5 s), `fetchmany(max_rows+1)` row cap (default 1000) → `truncated`.
- `tests/test_redteam.py`: 14 attacks; each must be stopped by at least one layer **and** the DB
  file's SHA-256 must be unchanged. Source of "14/14".

## How evaluation is run

- `scripts/get_bird.sh` downloads BIRD mini-dev + Arcwise corrected gold + train pool (~1.5 GB).
- `make eval-all` → presets `bare → mschema → values → full`, resumable, LLM calls cached.
- `t2sql rescore runs/<x>` re-scores against corrected gold (no LLM calls); `make report` writes
  `runs/REPORT.md`.
- Metric: execution accuracy = `set(pred rows) == set(gold rows)`, 30 s timeout.
- **CI method: bootstrap over questions, 2,000 resamples** (`eval/report.py::_bootstrap_ci`).
  Significance: exact two-sided McNemar on paired per-question correctness.

## Things to flag for the resume (number audit preview)

| Claim on resume | What the repo says | Action |
|---|---|---|
| "BIRD mini-dev (500 questions, 11 databases)" | Dataset has 500, but **498 are scored** (the ones with corrected gold); README says "498 scorable questions" | Say "BIRD mini-dev, 11 databases" or "498 questions" |
| 45.6% → 58.4%, 95% CI 53.8–62.7 | Matches README / REPORT.md | OK |
| 79.6% vs 28.0% | 5/5 agree → 79.6% (211 q); **≤ 2/5** agree → 28.0% (100 q) | OK, but in interviews say "≤ 2 of 5", not "disagree" |
| 14/14 red-team attacks | 14 entries in `ATTACKS` | OK |
| 70+ tests | 74 passing | OK |
| "CI/CD" | CI only (lint + test). No CD/deploy step exists yet | Say "CI" until Phase 1 adds deployment |
