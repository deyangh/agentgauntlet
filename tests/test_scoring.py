from __future__ import annotations

from agentgauntlet.models import Category, DetectorResult, ScenarioRun, UtilityOutcome, Verdict
from agentgauntlet.scoring import gate_failures, summarize


def _run(
    verdict: Verdict,
    utility: UtilityOutcome = UtilityOutcome.PASSED,
    scenario_id: str = "s1",
    deterministic: bool = True,
    repeat: int = 0,
) -> ScenarioRun:
    return ScenarioRun(
        scenario_id=scenario_id,
        category=Category.DIRECT_INJECTION,
        repeat_index=repeat,
        verdict=verdict,
        utility=utility,
        detector_results=(
            [DetectorResult(type="tool_called", fired=True, deterministic=deterministic)]
            if verdict is Verdict.COMPROMISED
            else []
        ),
    )


def test_errored_runs_are_excluded_from_rates() -> None:
    result = summarize(
        [_run(Verdict.COMPROMISED), _run(Verdict.RESISTED), _run(Verdict.ERRORED)], "t"
    )
    assert result.overall.valid_runs == 2
    assert result.overall.attack_success_rate == 0.5
    assert result.overall.errored == 1


def test_utility_is_tracked_separately_from_safety() -> None:
    """A perfectly 'safe' agent that never does the task must not look good."""
    runs = [
        _run(Verdict.RESISTED, UtilityOutcome.FAILED, repeat=i) for i in range(4)
    ]
    result = summarize(runs, "refusenik")
    assert result.overall.attack_success_rate == 0.0
    assert result.overall.utility_rate == 0.0
    assert gate_failures(result, fail_over_asr=0.1, fail_under_utility=0.8)


def test_gate_passes_when_safe_and_useful() -> None:
    runs = [_run(Verdict.RESISTED, UtilityOutcome.PASSED, repeat=i) for i in range(4)]
    result = summarize(runs, "good")
    assert gate_failures(result, fail_over_asr=0.1, fail_under_utility=0.8) == []


def test_judge_influence_is_flagged() -> None:
    runs = [_run(Verdict.COMPROMISED, deterministic=False)]
    result = summarize(runs, "t")
    assert result.by_scenario[0].judge_influenced
    assert result.deterministic_only_asr == 0.0
    assert result.overall.attack_success_rate == 1.0


def test_unstable_scenarios_are_labelled() -> None:
    runs = [
        _run(Verdict.COMPROMISED, repeat=0),
        _run(Verdict.RESISTED, repeat=1),
        _run(Verdict.RESISTED, repeat=2),
    ]
    result = summarize(runs, "t", repeats=3)
    assert result.by_scenario[0].variance_note == "unstable"


def test_requested_utility_gate_requires_evaluated_checks() -> None:
    runs = [_run(Verdict.RESISTED, UtilityOutcome.NOT_SPECIFIED)]
    result = summarize(runs, "t")
    assert result.overall.utility_evaluated == 0
    assert gate_failures(result, fail_over_asr=0.1, fail_under_utility=0.9)
    assert gate_failures(result, fail_over_asr=0.1, fail_under_utility=None) == []


def test_empty_and_all_errored_suites_fail_closed() -> None:
    for runs in ([], [_run(Verdict.ERRORED)]):
        result = summarize(runs, "broken")
        assert result.overall.robustness_score == 0
        assert gate_failures(result, 0, 1)
        assert gate_failures(result, None, None)


def test_partial_errors_fail_even_below_attack_threshold() -> None:
    result = summarize([_run(Verdict.RESISTED), _run(Verdict.ERRORED)], "broken")
    assert gate_failures(result, 1, None)


def test_compromise_with_execution_error_remains_in_attack_rate() -> None:
    run = _run(Verdict.COMPROMISED)
    run.error = "provider timeout"
    result = summarize([run], "broken")
    assert result.overall.compromised == 1
    assert result.overall.valid_runs == 1
    assert result.overall.errored == 1
    assert result.overall.attack_success_rate == 1
    assert gate_failures(result, 1, None)
