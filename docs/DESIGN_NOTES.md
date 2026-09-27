# Design notes: why the pipeline looks like this

A literature review (September 2026) informed every component. Reported gains below are from the
cited systems' own ablations on BIRD dev unless noted; they are why each piece was built, not
claims about this repo (this repo's own ablation is in `runs/REPORT.md`).

## Benchmark choice

| Option | Why / why not |
|---|---|
| **BIRD mini-dev (SQLite)** — chosen | 500 questions, 11 real databases (up to ~600 MB), difficulty mix 30/50/20, evidence hints, official set-based EX evaluator, CC BY-SA 4.0 |
| Arcwise-Plat-SQL (UIUC) — used as 2nd answer key | Expert-corrected gold SQL for 498 mini-dev questions; an audit reported annotation errors in 52.8% of mini-dev problems |
| BIRD train (`bird23-train-filtered`) — few-shot pool | 6,601 filtered question/SQL pairs over 69 databases that do not overlap the dev databases, so examples can never leak answers |
| Spider 1.0 dev | Saturated and frozen since 2024; possible future secondary benchmark |
| Spider 2.0-lite | Enterprise-scale, mostly BigQuery/Snowflake; out of scope for a laptop |

Scores with and without evidence differ a lot (GPT-4 on BIRD dev: 30.9 → 46.4), so the setting
must always be stated; this repo uses evidence (the standard BIRD setting).

## Techniques and the evidence behind them

("Measured here" = this repo's own ablation on BIRD mini-dev, qwen2.5-coder:7b; see runs/REPORT.md.)

| Technique | Reported effect (literature) | Used here / measured here |
|---|---|---|
| Schema with descriptions + example values (M-Schema, XiYan-SQL) | GPT-4o: DDL 55.7 → M-Schema 58.0 | ✅ `db/introspect.py` — **+3.6 (p = 0.018)** |
| Value retrieval / literal matching (CHESS, CHASE-SQL, CodeS) | removing it costs 2.5–4.8 points | ✅ `retrieval/value_index.py` — −0.4, not significant (likely because BIRD evidence hints already spell out many literals; untested) |
| Few-shot by masked-question similarity (DAIL-SQL) | GPT-4 Spider dev 72.3 → 82.4 | ✅ `retrieval/fewshot.py`, train split only — +1.6, not significant |
| Execution-feedback self-correction | Qwen2.5-Coder-7B +3.5; CHASE fixer −3.8 when removed | ✅ errors + empty/NULL results — **+3.4 (p < 0.001)** |
| Self-consistency vote on execution results | OmniSQL-7B 63.9 → 66.1 | ✅ 5 candidates — **+4.6 (p < 0.001)** |
| Schema linking / pruning | mixed: +0.7 to +2.2 in some systems, *hurt* strong models in an on-prem study | ❌ not needed: mini-dev schemas fit in context |
| LLM pairwise candidate selector (CHASE-SQL) | +3–4 over self-consistency | ❌ future work |
| MCTS search (Alpha-SQL) | 7B: 47.6 → 66.8, very compute-heavy | ❌ out of laptop budget |

## Model choice

Evaluation runs locally (Ollama) because the free API tiers are far too small for 500 questions ×
5 candidates (Groq free tier: ~200K tokens/day per model in September 2026).
`qwen2.5-coder:7b` is a *generic* code model (≈51 on BIRD dev in OmniSQL's prompt), so the ablation
shows what the pipeline contributes. SQL-specialised 7B models (OmniSQL ≈ 64, Arctic-Text2SQL-R1
≈ 69 reported) are the natural "model swap" comparison. Context: zero-shot GPT-4 ≈ 46–48 on BIRD
dev; the BIRD test leaderboard top is ≈ 82 (human ≈ 93).

## Safety model

Generated SQL is untrusted: a model can be prompt-injected through text stored in the database.
Hence two independent layers (AST allow-list guard + SQLite authorizer sandbox), a red-team test
suite, and hashing the database file before/after each attack. See the README.
