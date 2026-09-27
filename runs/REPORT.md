# Evaluation report

- Dataset: `data/bird/mini_dev_sqlite.json` — 498 questions scored by every run
- Model: `qwen2.5-coder:7b`
- Metric: execution accuracy (EX), official BIRD definition (result sets equal)

## Ablation

| Configuration | EX (%) [95% CI] | Δ | p (McNemar) | challenging (n) | moderate (n) | simple (n) | EX, corrected gold (%) |
|---|---|---|---|---|---|---|---|
| Baseline: plain schema, greedy | **45.6** [41.4–49.8] |  |  | 34.7 (101) | 40.2 (249) | 62.2 (148) | 42.3 (n=496) |
| + M-Schema (descriptions + example values) | **49.2** [44.8–53.6] | +3.6 | 0.018 | 39.6 (101) | 41.4 (249) | 68.9 (148) | 46.4 (n=496) |
| + database value retrieval | **48.8** [44.4–52.8] | -0.4 | 0.875 | 38.6 (101) | 42.2 (249) | 66.9 (148) | 46.0 (n=496) |
| + 3 few-shot examples (train split) | **50.4** [45.8–54.6] | +1.6 | 0.403 | 41.6 (101) | 43.8 (249) | 67.6 (148) | 46.2 (n=496) |
| + execution-feedback repair (errors, empty results) | **53.8** [49.2–58.0] | +3.4 | <0.001 | 43.6 (101) | 48.6 (249) | 69.6 (148) | 49.6 (n=496) |
| + 5-way self-consistency vote (full system) | **58.4** [53.8–62.7] | +4.6 | <0.001 | 50.5 (101) | 52.2 (249) | 74.3 (148) | 54.2 (n=496) |

## Same pipeline, different model: `hf.co/mradermacher/OmniSQL-7B-GGUF:Q4_K_M`

Compared on the 150 questions both models answered.

| Configuration | `qwen2.5-coder:7b` EX (%) | `hf.co/mradermacher/OmniSQL-7B-GGUF:Q4_K_M` EX (%) [95% CI] | p (McNemar) |
|---|---|---|---|
| full prompt, greedy | 52.0 | **54.7** [46.7–62.7] | 0.636 |
| + repair | 56.0 | **56.0** [48.0–64.0] | 1.000 |
| + 5-way vote | 62.0 | **58.7** [50.7–66.7] | 0.424 |

## Where the full system still fails

| Error category | Count | Share of errors |
|---|---|---|
| `wrong:values` | 110 | 53% |
| `wrong:row_count` | 45 | 22% |
| `wrong:extra_columns` | 16 | 8% |
| `wrong:missing_columns` | 16 | 8% |
| `wrong:empty_result` | 12 | 6% |
| `exec:no_such_column` | 8 | 4% |

## Is the confidence score meaningful?

Confidence = share of the 5 candidates whose result matches the chosen answer.

| Agreement | Questions | EX (%) |
|---|---|---|
| ≤ 2/5 | 100 | 28.0 |
| 3/5 | 93 | 46.2 |
| 4/5 | 94 | 55.3 |
| 5/5 | 211 | 79.6 |

## Cost per question (full system)

- LLM calls: 6.7 (5 candidates + repairs)
- Tokens: 9,271 prompt / 179 completion
- Latency: p50 0.1s, p90 119.5s (local model, includes all candidates; cached calls excluded from token counts)
