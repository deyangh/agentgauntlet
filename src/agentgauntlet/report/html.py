"""Self-contained HTML report.

The report is the demo surface: it has to make a compromised trajectory legible
at a glance, which means showing the planted payload and the outbound call that
carried the canary, not just a score.
"""

from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..models import ScenarioRun, Verdict
from ..scoring import SuiteResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_CANARY_RE = re.compile(r"[\w-]*CANARY-[A-Z0-9]{4,}")


def _highlight(text: str) -> Markup:
    """Escape content, then mark canary tokens so leaks are visible in the transcript."""
    escaped = html.escape(text or "")
    return Markup(_CANARY_RE.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped))


def _representative(runs: list[ScenarioRun]) -> dict[str, ScenarioRun]:
    """Pick the run worth showing per scenario: the first compromised one, else the first."""
    by_scenario: dict[str, list[ScenarioRun]] = defaultdict(list)
    for run in runs:
        by_scenario[run.scenario_id].append(run)

    chosen: dict[str, ScenarioRun] = {}
    for scenario_id, scenario_runs in by_scenario.items():
        compromised = [r for r in scenario_runs if r.verdict is Verdict.COMPROMISED]
        chosen[scenario_id] = compromised[0] if compromised else scenario_runs[0]
    return chosen


def render_html(result: SuiteResult) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.j2")
    return template.render(
        result=result,
        representative=_representative(result.runs),
        highlight=_highlight,
    )


def write_html(result: SuiteResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(result), encoding="utf-8")
    return path
