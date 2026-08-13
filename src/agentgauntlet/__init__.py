"""AgentGauntlet: pytest for agent security.

Run an LLM agent through a suite of prompt-injection, data-exfiltration, and
tool-misuse scenarios and get a reproducible security report.

Every attack executes inside an in-process mock environment. No email is sent,
no request leaves the machine, nothing is deleted or transferred: the "malicious"
tools are instrumented stubs whose invocation is the whole measurement.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .engine import run_scenario, run_suite
from .loader import discover, load_config, load_scenario
from .models import Category, Scenario, ScenarioRun, UtilityOutcome, Verdict
from .scoring import SuiteResult, summarize

__all__ = [
    "Category",
    "Scenario",
    "ScenarioRun",
    "SuiteResult",
    "UtilityOutcome",
    "Verdict",
    "__version__",
    "discover",
    "load_config",
    "load_scenario",
    "run_scenario",
    "run_suite",
    "summarize",
]
