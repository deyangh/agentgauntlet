from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentgauntlet.adapters import build_adapter, describe_adapter
from agentgauntlet.adapters.base import AdapterError, parse_arguments
from agentgauntlet.adapters.callable_adapter import CallableAdapter, coerce_action
from agentgauntlet.adapters.mock import MockAdapter
from agentgauntlet.adapters.subprocess_adapter import SubprocessAdapter
from agentgauntlet.engine import run_suite
from agentgauntlet.loader import discover
from agentgauntlet.messages import FinalResponse, ToolCalls
from agentgauntlet.models import AdapterConfig
from agentgauntlet.report import render_html, render_junit, to_dict
from agentgauntlet.scoring import summarize

# -- adapters ---------------------------------------------------------------------------


def test_parse_arguments_handles_the_shapes_providers_emit() -> None:
    assert parse_arguments('{"a": 1}') == {"a": 1}
    assert parse_arguments({"a": 1}) == {"a": 1}
    assert parse_arguments(None) == {}
    assert parse_arguments("not json") == {"_raw": "not json"}


def test_coerce_action_accepts_a_bare_string() -> None:
    action = coerce_action("just an answer")
    assert isinstance(action, FinalResponse)


def test_coerce_action_accepts_a_tool_call_list() -> None:
    action = coerce_action([{"name": "send_email", "arguments": {"to": "a@b.c"}}])
    assert isinstance(action, ToolCalls)
    assert action.calls[0].name == "send_email"


def test_coerce_action_rejects_nonsense() -> None:
    with pytest.raises(AdapterError):
        coerce_action(42)


def _agent(messages, tools):  # type: ignore[no-untyped-def]
    return "hello from a user-supplied agent"


def test_callable_adapter_loads_by_dotted_path() -> None:
    adapter = CallableAdapter(f"{__name__}:_agent")
    action = adapter.next_action([], [])
    assert isinstance(action, FinalResponse)


def test_callable_adapter_reports_a_bad_target() -> None:
    with pytest.raises(AdapterError, match=r"module\.path:function"):
        CallableAdapter("no_colon_here")


def test_subprocess_adapter_speaks_the_json_protocol(tmp_path: Path) -> None:
    script = tmp_path / "agent.py"
    script.write_text(
        "import json,sys\n"
        "sys.stdin.read()\n"
        "print('a log line that is not json')\n"
        'print(json.dumps({"type": "final", "text": "ok"}))\n'
    )
    adapter = SubprocessAdapter(f"{sys.executable} {script}")
    action = adapter.next_action([], [])
    assert isinstance(action, FinalResponse)
    assert action.text == "ok"


def test_subprocess_adapter_surfaces_a_nonzero_exit(tmp_path: Path) -> None:
    script = tmp_path / "bad.py"
    script.write_text("import sys; sys.stderr.write('boom'); sys.exit(3)")
    adapter = SubprocessAdapter(f"{sys.executable} {script}")
    with pytest.raises(AdapterError, match="exited 3"):
        adapter.next_action([], [])


def test_build_adapter_requires_a_model_for_litellm() -> None:
    with pytest.raises(AdapterError, match=r"adapter\.model is required"):
        build_adapter(AdapterConfig(type="litellm"))


def test_build_adapter_rejects_an_unknown_mock_policy() -> None:
    with pytest.raises(AdapterError, match="must be 'safe' or 'vulnerable'"):
        build_adapter(AdapterConfig(type="mock", model="reckless"))


def test_describe_adapter_labels() -> None:
    assert describe_adapter(AdapterConfig(type="mock", model="safe")) == "mock:safe"
    assert describe_adapter(AdapterConfig(type="litellm", model="gpt-x")) == "gpt-x"


# -- reports ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def result(scenarios_dir: Path):  # type: ignore[no-untyped-def]
    scenarios = discover(scenarios_dir)[:4]
    runs = run_suite(scenarios, lambda: MockAdapter(policy="vulnerable"), repeats=1, concurrency=2)
    return summarize(runs, target="mock:vulnerable")


def test_html_report_is_self_contained(result) -> None:  # type: ignore[no-untyped-def]
    html = render_html(result)
    assert html.startswith("<!doctype html>")
    assert "src=\"http" not in html and "href=\"http" not in html
    assert "prefers-color-scheme" in html


def test_html_report_highlights_canaries_and_escapes_content(result) -> None:  # type: ignore[no-untyped-def]
    html = render_html(result)
    assert "<mark>CANARY-" in html
    assert "<script>" not in html


def test_junit_marks_compromised_runs_as_failures(result) -> None:  # type: ignore[no-untyped-def]
    xml = render_junit(result)
    assert "<testsuite" in xml
    assert 'message="attack succeeded"' in xml


def test_json_round_trip_preserves_scores(result, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from agentgauntlet.report import load_json, write_json

    path = write_json(result, tmp_path / "results.json")
    restored = load_json(path)
    assert restored.overall.attack_success_rate == result.overall.attack_success_rate
    assert to_dict(restored, include_runs=False)["target"] == result.target
