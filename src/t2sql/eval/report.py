"""Turn run JSONL files into a Markdown report: ablation ladder, per-difficulty EX, error
taxonomy, confidence calibration and cost. Every number in the README comes from here."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _preset_of(run_dir: Path) -> str:
    cfg = run_dir / "config.json"
    return json.loads(cfg.read_text()).get("preset", run_dir.name) if cfg.exists() else run_dir.name


def _scored(records: list[dict]) -> list[dict]:
    return [r for r in records if "final" in r]


def _ex(records: list[dict], variant: str) -> float:
    return 100 * sum(r[variant]["correct"] for r in records) / max(1, len(records))


def _bootstrap_ci(
    records: list[dict], variant: str, n_boot: int = 2000, seed: int = 0
) -> tuple[float, float]:
    import random

    rng = random.Random(seed)
    vals = sorted(_ex([rng.choice(records) for _ in records], variant) for _ in range(n_boot))
    return vals[int(0.025 * n_boot)], vals[int(0.975 * n_boot) - 1]


def _mcnemar(a: list[dict], va: str, b: list[dict], vb: str) -> str:
    """Exact two-sided McNemar test on paired per-question correctness."""
    from math import comb

    bm = {r["qid"]: r for r in b}
    pairs = [(r[va]["correct"], bm[r["qid"]][vb]["correct"]) for r in a if r["qid"] in bm]
    n01 = sum(1 for x, y in pairs if not x and y)
    n10 = sum(1 for x, y in pairs if x and not y)
    n = n01 + n10
    if n == 0:
        return "1.000"
    k = min(n01, n10)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)
    return f"{p:.3f}" if p >= 0.001 else "<0.001"


def _pct(x: float) -> str:
    return f"{x:.1f}"


def build_report(runs_dir: Path) -> str:
    order = {"bare": 0, "mschema": 1, "values": 2, "full": 3}
    paths = sorted(
        runs_dir.glob("*/results.jsonl"), key=lambda p: order.get(_preset_of(p.parent), 9)
    )
    runs = {p.parent.name: _scored(_load(p)) for p in paths}
    if not runs:
        return "No runs found."
    configs = {
        name: json.loads((runs_dir / name / "config.json").read_text())
        for name in runs
        if (runs_dir / name / "config.json").exists()
    }

    # The ablation ladder uses one model; runs with any other model go in a "model swap" table
    # that is compared question-for-question against the main model's full run.
    main_model = next(
        (configs[n].get("model") for n in runs if configs.get(n, {}).get("preset") == "bare"),
        next((c.get("model") for c in configs.values()), "?"),
    )
    swaps = {n: r for n, r in runs.items() if configs.get(n, {}).get("model") != main_model}
    runs = {n: r for n, r in runs.items() if n not in swaps}

    # Compare ladder rows on the intersection of questions so they are like-for-like.
    common = set.intersection(*({r["qid"] for r in recs} for recs in runs.values()))
    runs = {k: [r for r in v if r["qid"] in common] for k, v in runs.items()}
    n = len(common)
    diffs = sorted({r["difficulty"] for recs in runs.values() for r in recs})

    # Same predictions re-scored against expert-corrected gold SQL, when available.
    alt: dict[str, dict[str, dict]] = {}
    for name in list(runs) + list(swaps):
        path = runs_dir / name / "results_arcwise.jsonl"
        if path.exists():
            alt[name] = {r["qid"]: r for r in _scored(_load(path))}

    ladder: list[tuple[str, str, list[dict], str]] = []
    for name, recs in runs.items():
        if name in swaps:
            continue
        preset = configs.get(name, {}).get("preset", name)
        if preset == "bare":
            ladder.append(("Baseline: plain schema, greedy", name, recs, "greedy_initial"))
        elif preset == "mschema":
            ladder.append(
                ("+ M-Schema (descriptions + example values)", name, recs, "greedy_initial")
            )
        elif preset == "values":
            ladder.append(("+ database value retrieval", name, recs, "greedy_initial"))
        elif preset == "full":
            ladder.append(("+ 3 few-shot examples (train split)", name, recs, "greedy_initial"))
            ladder.append(
                ("+ execution-feedback repair (errors, empty results)", name, recs, "greedy")
            )
            ladder.append(("+ 5-way self-consistency vote (full system)", name, recs, "final"))
        else:
            ladder.append((name, name, recs, "final"))

    model = main_model
    dataset = next((c.get("dataset") for c in configs.values()), "?")
    lines = [
        "# Evaluation report",
        "",
        f"- Dataset: `{dataset}` — {n} questions scored by every run",
        f"- Model: `{model}`",
        "- Metric: execution accuracy (EX), official BIRD definition (result sets equal)",
        "",
    ]

    head = (
        "| Configuration | EX (%) [95% CI] | Δ | p (McNemar) | "
        + " | ".join(f"{d} (n)" for d in diffs)
        + " | EX, corrected gold (%) |"
    )
    lines += ["## Ablation", "", head, "|" + "---|" * (5 + len(diffs))]
    prev: tuple[list[dict], str] | None = None
    prev_ex = None
    for label, name, recs, variant in ladder:
        ex = _ex(recs, variant)
        lo, hi = _bootstrap_ci(recs, variant)
        delta = "" if prev_ex is None else f"{ex - prev_ex:+.1f}"
        p = "" if prev is None else _mcnemar(prev[0], prev[1], recs, variant)
        cells = []
        for d in diffs:
            sub = [r for r in recs if r["difficulty"] == d]
            cells.append(f"{_pct(_ex(sub, variant))} ({len(sub)})")
        corrected = "–"
        alt_recs = [alt[name][q] for q in common if name in alt and q in alt[name]]
        if alt_recs:
            corrected = f"{_pct(_ex(alt_recs, variant))} (n={len(alt_recs)})"
        lines.append(
            f"| {label} | **{_pct(ex)}** [{_pct(lo)}–{_pct(hi)}] | {delta} | {p} | "
            + " | ".join(cells)
            + f" | {corrected} |"
        )
        prev, prev_ex = (recs, variant), ex

    main_full = next(
        (r for nm, r in runs.items() if configs.get(nm, {}).get("preset") == "full"), None
    )
    for name, recs in swaps.items():
        m = configs[name].get("model")
        base = {r["qid"]: r for r in (main_full or [])}
        qids = sorted({r["qid"] for r in recs} & set(base))
        if not qids:
            continue
        mine = {r["qid"]: r for r in recs}
        sw = [mine[q] for q in qids]
        ref = [base[q] for q in qids]
        lines += [
            "",
            f"## Same pipeline, different model: `{m}`",
            "",
            f"Compared on the {len(qids)} questions both models answered.",
            "",
            f"| Configuration | `{main_model}` EX (%) | `{m}` EX (%) [95% CI] | p (McNemar) |",
            "|---|---|---|---|",
        ]
        for label, variant in (
            ("full prompt, greedy", "greedy_initial"),
            ("+ repair", "greedy"),
            ("+ 5-way vote", "final"),
        ):
            lo, hi = _bootstrap_ci(sw, variant)
            lines.append(
                f"| {label} | {_pct(_ex(ref, variant))} | **{_pct(_ex(sw, variant))}** "
                f"[{_pct(lo)}–{_pct(hi)}] | {_mcnemar(ref, variant, sw, variant)} |"
            )

    full = main_full
    if full:
        lines += [
            "",
            "## Where the full system still fails",
            "",
            "| Error category | Count | Share of errors |",
            "|---|---|---|",
        ]
        cats = Counter(r["final"]["category"] for r in full if not r["final"]["correct"])
        total_err = sum(cats.values()) or 1
        for cat, c in cats.most_common():
            lines.append(f"| `{cat}` | {c} | {100 * c / total_err:.0f}% |")

        lines += [
            "",
            "## Is the confidence score meaningful?",
            "",
            "Confidence = share of the 5 candidates whose result matches the chosen answer.",
            "",
            "| Agreement | Questions | EX (%) |",
            "|---|---|---|",
        ]
        buckets = [
            (0.0, 0.41, "≤ 2/5"),
            (0.41, 0.61, "3/5"),
            (0.61, 0.81, "4/5"),
            (0.81, 1.01, "5/5"),
        ]
        for lo, hi, label in buckets:
            sub = [r for r in full if lo <= r["confidence"] < hi]
            if sub:
                lines.append(f"| {label} | {len(sub)} | {_pct(_ex(sub, 'final'))} |")

        lat = sorted(r["elapsed_ms"] for r in full)
        p50 = lat[len(lat) // 2] / 1000
        p90 = lat[int(len(lat) * 0.9) - 1] / 1000 if len(lat) >= 10 else lat[-1] / 1000
        calls = sum(r["llm_calls"] for r in full) / len(full)
        ptok = sum(r["prompt_tokens"] for r in full) / len(full)
        ctok = sum(r["completion_tokens"] for r in full) / len(full)
        lines += [
            "",
            "## Cost per question (full system)",
            "",
            f"- LLM calls: {calls:.1f} (5 candidates + repairs)",
            f"- Tokens: {ptok:,.0f} prompt / {ctok:,.0f} completion",
            f"- Latency: p50 {p50:.1f}s, p90 {p90:.1f}s (local model, includes all "
            "candidates; cached calls excluded from token counts)",
        ]
    return "\n".join(lines) + "\n"


def write_report(runs_dir: Path, out: Path | None = None) -> Path:
    out = out or runs_dir / "REPORT.md"
    out.write_text(build_report(runs_dir))
    return out
