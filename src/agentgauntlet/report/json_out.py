"""Machine-readable results.

Written for two consumers: re-rendering a report without re-running the suite,
and accumulating dated results into the public leaderboard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..scoring import SuiteResult


def to_dict(result: SuiteResult, include_runs: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target": result.target,
        "created_at": result.created_at,
        "repeats": result.repeats,
        "scenario_count": result.scenario_count,
        "overall": result.overall.to_row(),
        "deterministic_only_asr": result.deterministic_only_asr,
        "by_category": [c.to_row() for c in result.by_category],
        "by_scenario": [
            {**s.aggregate.to_row(), "category": s.category.value, "stability": s.variance_note}
            for s in result.by_scenario
        ],
    }
    if include_runs:
        payload["runs"] = [json.loads(r.model_dump_json()) for r in result.runs]
    return payload


def write_json(result: SuiteResult, path: str | Path, include_runs: bool = True) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_dict(result, include_runs), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def load_json(path: str | Path) -> SuiteResult:
    """Rehydrate a SuiteResult from a previously written results file."""
    from ..models import ScenarioRun
    from ..scoring import summarize

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    runs = [ScenarioRun.model_validate(r) for r in raw.get("runs", [])]
    if not runs:
        raise ValueError(f"{path} contains no runs; cannot rebuild a report from it")
    return summarize(runs, target=raw.get("target", "unknown"), repeats=raw.get("repeats", 1))
