from __future__ import annotations

from pathlib import Path

import pytest

from agentgauntlet.loader import ScenarioLoadError, discover, load_config, load_scenario
from agentgauntlet.models import Category


def test_bundled_scenarios_all_load(scenarios_dir: Path) -> None:
    scenarios = discover(scenarios_dir)
    assert len(scenarios) >= 16
    assert {s.category for s in scenarios} == set(Category)


def test_every_scenario_has_a_utility_check(scenarios_dir: Path) -> None:
    """A scenario without a benign-task control cannot distinguish safety from uselessness."""
    missing = [s.id for s in discover(scenarios_dir) if not s.utility_check]
    assert missing == [], f"scenarios missing a utility_check: {missing}"


def test_scenario_ids_are_unique(scenarios_dir: Path) -> None:
    ids = [s.id for s in discover(scenarios_dir)]
    assert len(ids) == len(set(ids))


def test_category_filter(scenarios_dir: Path) -> None:
    only = discover(scenarios_dir, [Category.DATA_EXFILTRATION])
    assert only
    assert all(s.category is Category.DATA_EXFILTRATION for s in only)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    body = """
id: dupe-01
category: direct_injection
system_prompt: s
user_task: u
environment:
  tools: [{name: t, response: "x"}]
detectors:
  - {type: tool_called, tool: t}
"""
    (tmp_path / "a.yaml").write_text(body)
    (tmp_path / "b.yaml").write_text(body)
    with pytest.raises(ScenarioLoadError, match="duplicate scenario id"):
        discover(tmp_path)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
id: bad-01
category: direct_injection
system_prompt: s
user_task: u
typoed_field: oops
environment:
  tools: [{name: t, response: "x"}]
detectors:
  - {type: tool_called, tool: t}
"""
    )
    with pytest.raises(ScenarioLoadError, match="typoed_field"):
        load_scenario(path)


def test_unknown_detector_type_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
id: bad-02
category: direct_injection
system_prompt: s
user_task: u
environment:
  tools: [{name: t, response: "x"}]
detectors:
  - {type: telepathy, tool: t}
"""
    )
    with pytest.raises(ScenarioLoadError):
        load_scenario(path)


def test_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ScenarioLoadError, match="no such scenario path"):
        discover(tmp_path / "nope")


def test_load_config_defaults() -> None:
    cfg = load_config(None)
    assert cfg.suite.repeats == 3
    assert cfg.gate.fail_over_asr == 0.10
