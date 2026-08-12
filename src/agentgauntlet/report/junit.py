"""JUnit XML output so CI systems render each scenario as a test case."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from ..models import Verdict
from ..scoring import SuiteResult


def render_junit(result: SuiteResult) -> str:
    failures = sum(1 for r in result.runs if r.verdict is Verdict.COMPROMISED)
    errors = sum(1 for r in result.runs if r.verdict is Verdict.ERRORED)

    suite = ET.Element(
        "testsuite",
        {
            "name": f"agentgauntlet::{result.target}",
            "tests": str(len(result.runs)),
            "failures": str(failures),
            "errors": str(errors),
            "timestamp": result.created_at,
        },
    )

    for run in result.runs:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": f"agentgauntlet.{run.category.value}",
                "name": f"{run.scenario_id}[run{run.repeat_index + 1}]",
                "time": f"{run.duration_s:.3f}",
            },
        )
        if run.verdict is Verdict.COMPROMISED:
            evidence = "; ".join(
                f"{d.description or d.type}: {d.evidence}" for d in run.detector_results if d.fired
            )
            failure = ET.SubElement(
                case, "failure", {"message": "attack succeeded", "type": "Compromised"}
            )
            failure.text = evidence
        elif run.verdict is Verdict.ERRORED:
            error = ET.SubElement(case, "error", {"message": run.error or "run errored"})
            error.text = run.error or ""

    return ET.tostring(suite, encoding="unicode")


def write_junit(result: SuiteResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + render_junit(result), "utf-8")
    return path
