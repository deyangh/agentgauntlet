#!/usr/bin/env python3
"""Run the full suite against every model in models.yaml and write dated results.

    python benchmark/run_benchmark.py                  # everything in models.yaml
    python benchmark/run_benchmark.py --only ollama/llama3.1

Results land in ``benchmark/results/<date>/<model>.json`` and the leaderboard is
regenerated from whatever is on disk, so a partial run is still publishable and a
failed model does not lose the others.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentgauntlet.adapters import build_adapter
from agentgauntlet.engine import run_suite
from agentgauntlet.loader import discover
from agentgauntlet.models import AdapterConfig
from agentgauntlet.report import write_json
from agentgauntlet.scoring import summarize

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parent
RESULTS_DIR = BENCH_DIR / "results"


def _slug(model_id: str) -> str:
    return model_id.replace("/", "_").replace(":", "_")


def run_one(model: dict[str, Any], config: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    model_id = model["id"]
    label = model.get("label", model_id)
    print(f"\n=== {label} ({model_id}) ===", flush=True)

    scenarios = discover(REPO_ROOT / "scenarios")
    adapter_config = AdapterConfig(type="litellm", model=model_id)

    try:
        runs = run_suite(
            scenarios,
            lambda: build_adapter(adapter_config, temperature=config.get("temperature", 0.0)),
            repeats=config.get("repeats", 3),
            concurrency=config.get("concurrency", 4),
        )
    except Exception:
        print(f"  FAILED to run {model_id}:\n{traceback.format_exc()}", file=sys.stderr)
        return None

    result = summarize(runs, target=label, repeats=config.get("repeats", 3))
    write_json(result, out_dir / f"{_slug(model_id)}.json")

    print(f"  {result.gate_summary}")
    if result.overall.errored:
        print(f"  {result.overall.errored} errored runs")
    if result.overall.utility_evaluated and result.overall.utility_rate < 0.5:
        print("  WARNING: very low utility — this model may not support tool calling well.")

    return {
        "model_id": model_id,
        "label": label,
        "notes": model.get("notes", ""),
        "asr": result.overall.attack_success_rate,
        "robustness": result.overall.robustness_score,
        "utility": result.overall.utility_rate,
        "errored": result.overall.errored,
        "valid_runs": result.overall.valid_runs,
        "by_category": {c.label: c.attack_success_rate for c in result.by_category},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=BENCH_DIR / "models.yaml")
    parser.add_argument("--only", action="append", help="Run only this model id (repeatable).")
    parser.add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    args = parser.parse_args()

    config = yaml.safe_load(args.models.read_text())
    models = config.get("models", [])
    if args.only:
        models = [m for m in models if m["id"] in set(args.only)]
    if not models:
        print("no models selected", file=sys.stderr)
        return 2

    out_dir = RESULTS_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [row for model in models if (row := run_one(model, config, out_dir)) is not None]
    if not rows:
        print("every model failed", file=sys.stderr)
        return 1

    summary = {
        "date": args.date,
        "repeats": config.get("repeats", 3),
        "scenario_count": len(discover(REPO_ROOT / "scenarios")),
        "rows": sorted(rows, key=lambda r: (-r["robustness"], -r["utility"])),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {out_dir}/summary.json")
    print("Regenerate the leaderboard with: python benchmark/build_leaderboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
