# Evaluation methodology

This document explains exactly how the numbers in the README were produced, so they can be
checked and reproduced.

## What v1 got wrong (and why the old 72% is withdrawn)

v1 reported "72% execution accuracy" on 30 hand-written questions. That number measured
memorisation, not generalisation:

| Problem in v1 | Consequence | Fix in v2 |
|---|---|---|
| The 30 test questions also appeared in the few-shot pool (`retrieval.py`) | The model was shown the answers | Few-shot examples come only from BIRD **train** (69 databases, disjoint from the test databases); the eval excludes any example whose database is being evaluated |
| `cot_layer.py` contained ~550 lines of regex rules written for those 30 questions | A rule-based "fallback" answered the test set directly | Removed. Nothing in the prompts or code is specific to any evaluation question |
| A 10-table toy database with ~60 rows | Most wrong queries still return the right (tiny) result | Evaluated on BIRD mini-dev: 11 real databases, up to ~600 MB each |
| No confidence intervals, no ablations | Impossible to tell which component helped | Cumulative ablation ladder with bootstrap CIs and paired McNemar tests |

## Benchmark

**BIRD mini-dev, SQLite** — 500 questions over 11 databases, difficulty mix 30% simple / 50% moderate
/ 20% challenging, with the official `evidence` hints (the standard BIRD setting).
Questions: `huggingface.co/datasets/birdsql/bird_mini_dev`; databases: the official mini-dev
package. License CC BY-SA 4.0.

**Second answer key.** An independent 2026 audit found annotation errors in 52.8% of mini-dev
problems. Arcwise-Plat-SQL (UIUC Kang lab) re-annotated 498 of them; **179 of the 498 gold SQL
queries differ** from the original. We score the *same predictions* against both keys
(`t2sql rescore`), so the second number costs no extra model calls. Neither is "the" truth; the
gap between them is a useful error bar in itself.

## Metric

Execution accuracy (EX), identical to the official BIRD evaluator:
a prediction is correct iff `set(rows(pred)) == set(rows(gold))` — row order and duplicates are
ignored, column order is not; both queries run with a 30 s timeout and any error scores 0.

## Ablation design

Each preset adds one idea to the previous one. The `full` run also records its first
(temperature-0) candidate before and after repair, so three rows come from one run:

| Row | Source | What changes |
|---|---|---|
| Baseline | `bare` run | schema as plain column lists, no hints, 1 greedy sample |
| + M-Schema | `mschema` run | column descriptions (from BIRD's description CSVs) + 3 example values per column |
| + value retrieval | `values` run | fuzzy-matched DB values injected as `table.column = 'Value'` hints |
| + few-shot | `full` run, greedy candidate before repair | 3 train-split examples picked by masked-question BM25 |
| + repair | `full` run, greedy candidate after repair | up to 2 rounds of execution-error feedback, plus one revision when a query returns no rows or only NULLs (kept only if the revision returns rows) |
| + self-consistency | `full` run, final answer | 5 candidates (1 greedy + 4 at T=0.7), vote on execution results |

Statistics: 95% CIs by bootstrap over questions (2,000 resamples); consecutive rows compared
with an exact two-sided McNemar test on paired per-question correctness.

## What was (and wasn't) tuned on the test set

Prompts, rules and hyper-parameters (5 candidates, T = 0.7, 2 repair rounds, 3 few-shot
examples, 3 example values per column) were set from the literature before the benchmark run.
A 30-question pilot on mini-dev was used only to check the pipeline end to end (speed, parsing,
accounting). One change followed it: the one-shot revision of empty/all-NULL results, a standard
technique (CHESS) that the pilot showed was missing. No prompt text or rule was edited in response
to individual mini-dev failures after that. The full 500-question runs include the 30 pilot
questions; excluding them is possible from the per-question JSONL files.

## A bug found after the benchmark (and re-run)

After the first full benchmark, a demo query ("Which 5 counties have the most schools?") showed
value retrieval matching the quantity "5" to a stored text value (`frpm.Low Grade = '5'`), and the
model then added a filter nobody asked for. Short bare numbers in questions are quantities or date
parts, never category labels, so value retrieval now ignores values that are 1–3 digit numbers
(`retrieval/value_index.py`, with a regression test). 106 of 500 questions had carried such hints.

This was found on a question outside the benchmark and fixes a class of false positives rather
than any individual benchmark question. The affected runs (`values`, `full`, OmniSQL) were re-run;
the pre-fix runs are kept unchanged in `runs_before_hint_fix/` so both can be inspected.

| Run (same 498 questions) | Before fix | After fix | Questions fixed / newly wrong |
|---|---|---|---|
| `values` (greedy) | 49.6 | 48.8 | 2 / 6 |
| `full` (5-way vote) | 58.0 | 58.4 | 10 / 8 |

The benchmark effect is within noise — BIRD's evidence hints already pin down most literals — but
the fix removes a failure users would actually see. All numbers in the README are after the fix.

## Model

`qwen2.5-coder:7b` (Q4_K_M, 4.7 GB) via Ollama on an 18 GB Apple-silicon laptop — a *generic*
code model, chosen so the ablation shows what the pipeline adds. Published reference points for
calibration (same benchmark family, different prompts): Qwen2.5-Coder-7B ≈ 50.9 on BIRD dev with
OmniSQL's prompt; zero-shot GPT-4 ≈ 46–48; SQL-specialised 7B models (OmniSQL, Arctic-R1) 64–69;
top of the BIRD leaderboard ≈ 82. These are context, not like-for-like comparisons.

## Reproduce

```bash
make install
# data: see scripts/get_bird.sh (mini-dev questions + SQLite DBs, corrected gold, train pool)
make eval-all          # 4 runs, resumable; LLM responses cached in .cache/llm.sqlite
for r in runs/*/; do .venv/bin/t2sql rescore $r; done
make report            # -> runs/REPORT.md
```
