#!/usr/bin/env python3
"""Regenerate the published example report at docs/example-report.html.

This is the sample report linked from the site, so it is built with the site
navigation bar (`site_nav=True`) — unlike a user's own `agentgauntlet run`
report, which has no site chrome. Runs the offline `safe` mock, so it needs no
API key.

    python docs/build_example_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentgauntlet.adapters import MockAdapter  # noqa: E402
from agentgauntlet.engine import run_suite  # noqa: E402
from agentgauntlet.loader import discover  # noqa: E402
from agentgauntlet.report import render_html  # noqa: E402
from agentgauntlet.scoring import summarize  # noqa: E402

OUT = REPO_ROOT / "docs" / "example-report.html"


def main() -> int:
    scenarios = discover(REPO_ROOT / "scenarios")
    runs = run_suite(scenarios, lambda: MockAdapter(policy="safe"), repeats=3, concurrency=4)
    result = summarize(runs, target="mock:safe", repeats=3)
    OUT.write_text(render_html(result, site_nav=True), encoding="utf-8")
    print(f"Wrote {OUT}  ({result.gate_summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
