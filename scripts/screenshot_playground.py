"""Capture a README screenshot of the playground answering a real BIRD question.

Needs Playwright (`pip install playwright && playwright install chromium`) and a running API:
    T2SQL_DATABASES_DIR=data/bird/dev_databases .venv/bin/t2sql serve --port 8000
    python scripts/screenshot_playground.py --db california_schools \
        --question "Which county has the most schools with a free meal rate above 50% for K-12?"
"""

from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/")
    ap.add_argument("--db", default="university")
    ap.add_argument("--question", required=True)
    ap.add_argument("--evidence", default="")
    ap.add_argument("--out", default="docs/playground.png")
    ap.add_argument("--dark", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900}, device_scale_factor=2,
                                color_scheme="dark" if args.dark else "light")
        page.goto(args.url)
        page.select_option("#db", args.db)
        page.fill("#q", args.question)
        if args.evidence:
            page.fill("#ev", args.evidence)
        page.click("#go")
        page.wait_for_selector("text=agreement", timeout=300_000)
        page.screenshot(path=args.out, full_page=True)
        browser.close()
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
