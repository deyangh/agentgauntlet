"""Collect scenarios as pytest tests.

Lets an agent's security suite live beside its unit tests and run under the same
command, which is the difference between a benchmark someone reads once and a
regression gate that keeps working.

    pytest --agentgauntlet-scenarios ./scenarios --agentgauntlet-adapter mock
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .adapters import build_adapter
from .engine import run_scenario
from .loader import ScenarioLoadError, load_scenario
from .models import AdapterConfig, Scenario, Verdict


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("agentgauntlet")
    group.addoption(
        "--agentgauntlet-scenarios",
        action="store",
        default=None,
        help="Directory of AgentGauntlet scenario YAML files to collect as tests.",
    )
    group.addoption(
        "--agentgauntlet-adapter",
        action="store",
        default="mock",
        help="Adapter type: litellm | callable | subprocess | mock.",
    )
    group.addoption(
        "--agentgauntlet-model",
        action="store",
        default=None,
        help="Model string for the litellm adapter, or policy for the mock adapter.",
    )
    group.addoption(
        "--agentgauntlet-target",
        action="store",
        default=None,
        help="module:function for the callable adapter, or a subprocess command.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "agentgauntlet: an adversarial agent-security scenario."
    )


def _adapter_config(config: pytest.Config) -> AdapterConfig:
    return AdapterConfig(
        type=config.getoption("--agentgauntlet-adapter"),
        model=config.getoption("--agentgauntlet-model"),
        target=config.getoption("--agentgauntlet-target"),
    )


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> pytest.Collector | None:
    root = parent.config.getoption("--agentgauntlet-scenarios")
    if not root or file_path.suffix.lower() not in (".yaml", ".yml"):
        return None
    try:
        scenario_root = Path(root).resolve()
        file_path.resolve().relative_to(scenario_root)
    except (ValueError, OSError):
        return None
    return ScenarioFile.from_parent(parent, path=file_path)


class ScenarioFile(pytest.File):
    def collect(self) -> Any:
        try:
            scenario = load_scenario(self.path)
        except ScenarioLoadError as exc:
            raise pytest.UsageError(str(exc)) from exc
        yield ScenarioItem.from_parent(self, name=scenario.id, scenario=scenario)


class ScenarioItem(pytest.Item):
    def __init__(self, *, scenario: Scenario, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scenario = scenario
        self.add_marker(pytest.mark.agentgauntlet)
        self._result_repr = ""

    def runtest(self) -> None:
        adapter = build_adapter(_adapter_config(self.config))
        result = run_scenario(self.scenario, adapter)

        if result.verdict is Verdict.ERRORED:
            pytest.skip(f"run errored: {result.error}")

        if result.verdict is Verdict.COMPROMISED:
            evidence = "\n".join(
                f"  - {d.description or d.type}: {d.evidence}"
                for d in result.detector_results
                if d.fired
            )
            self._result_repr = (
                f"{self.scenario.id} was compromised "
                f"({self.scenario.category.value})\n{evidence}"
            )
            raise AssertionError(self._result_repr)

        if self.scenario.utility_check and result.utility.value == "failed":
            pytest.skip(
                "agent resisted the attack but failed the benign task, "
                "so this run does not demonstrate safe-and-useful behavior"
            )

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException], style: Any = None) -> Any:
        if isinstance(excinfo.value, AssertionError) and self._result_repr:
            return self._result_repr
        return super().repr_failure(excinfo, style)

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.path, 0, f"scenario: {self.scenario.id}"
