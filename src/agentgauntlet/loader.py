"""Discovery and validation of YAML scenario files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import Category, RunConfig, Scenario

SCENARIO_SUFFIXES = (".yaml", ".yml")


class ScenarioLoadError(ValueError):
    """Raised when a scenario file is missing, malformed, or fails validation."""


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"invalid scenario {path}:"]
    for error in exc.errors():
        location = ".".join(str(p) for p in error["loc"]) or "<root>"
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)


def load_scenario(path: str | Path) -> Scenario:
    """Parse and validate a single scenario file."""
    path = Path(path)
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScenarioLoadError(f"scenario file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ScenarioLoadError(f"could not parse YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ScenarioLoadError(f"{path} must contain a YAML mapping at the top level")

    try:
        scenario = Scenario.model_validate(raw)
    except ValidationError as exc:
        raise ScenarioLoadError(_format_validation_error(path, exc)) from exc

    scenario.source_path = str(path)
    return scenario


def discover(
    root: str | Path,
    categories: list[Category] | None = None,
    ids: list[str] | None = None,
) -> list[Scenario]:
    """Load every scenario under *root*, optionally filtered by category or id.

    Accepts a single file as well as a directory so that ``--scenarios path/to/one.yaml``
    works for iterating on a new attack.
    """
    root = Path(root)
    if root.is_file():
        paths = [root]
    elif root.is_dir():
        paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in SCENARIO_SUFFIXES)
    else:
        raise ScenarioLoadError(f"no such scenario path: {root}")

    scenarios: list[Scenario] = []
    seen: dict[str, str] = {}
    for path in paths:
        scenario = load_scenario(path)
        if scenario.id in seen:
            raise ScenarioLoadError(
                f"duplicate scenario id {scenario.id!r} in {path} "
                f"(already defined in {seen[scenario.id]})"
            )
        seen[scenario.id] = str(path)
        scenarios.append(scenario)

    if categories:
        wanted = set(categories)
        scenarios = [s for s in scenarios if s.category in wanted]
    if ids:
        wanted_ids = set(ids)
        scenarios = [s for s in scenarios if s.id in wanted_ids]

    return scenarios


def load_config(path: str | Path | None) -> RunConfig:
    """Load an ``agentgauntlet.yaml`` config, falling back to defaults when absent."""
    if path is None:
        return RunConfig()
    path = Path(path)
    if not path.exists():
        raise ScenarioLoadError(f"config file not found: {path}")
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ScenarioLoadError(f"could not parse YAML in {path}: {exc}") from exc
    try:
        return RunConfig.model_validate(raw)
    except ValidationError as exc:
        raise ScenarioLoadError(_format_validation_error(path, exc)) from exc


def default_scenarios_dir() -> Path:
    """Scenarios bundled beside the repository checkout, if present."""
    candidate = Path(__file__).resolve().parents[2] / "scenarios"
    return candidate if candidate.is_dir() else Path("scenarios")
