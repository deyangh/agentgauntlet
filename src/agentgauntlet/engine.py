"""The agent loop, owned by the harness.

This is the central design choice. Because the harness, not the agent, executes
tool calls, it controls where adversarial payloads appear and it sees every action
the agent takes, so detection is observation rather than inference.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .adapters.base import AdapterError, AgentAdapter
from .detectors import Judge, combine, evaluate_all
from .environment import Environment
from .messages import FinalResponse, Message, ToolCalls
from .models import (
    Scenario,
    ScenarioRun,
    UtilityOutcome,
    Verdict,
)
from .templating import render, resolve_secrets

AdapterFactory = Callable[[], AgentAdapter]


@dataclass
class _Trajectory:
    messages: list[Message]
    final_response: str | None
    turns_used: int


def _serialize_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        entry: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            entry["tool_calls"] = [
                {"name": c.name, "arguments": c.arguments} for c in message.tool_calls
            ]
        if message.name:
            entry["tool_name"] = message.name
        out.append(entry)
    return out


def _transcript_text(messages: Sequence[Message]) -> str:
    parts: list[str] = []
    for message in messages:
        if message.role == "system":
            continue
        if message.tool_calls:
            calls = ", ".join(f"{c.name}({c.arguments})" for c in message.tool_calls)
            parts.append(f"[assistant tool calls] {calls}")
        elif message.role == "tool":
            parts.append(f"[tool result: {message.name}] {message.content}")
        elif message.content:
            parts.append(f"[{message.role}] {message.content}")
    return "\n".join(parts)


def _drive(
    scenario: Scenario,
    adapter: AgentAdapter,
    env: Environment,
    secrets: dict[str, str],
    max_turns: int,
) -> _Trajectory:
    messages: list[Message] = [
        Message.system(render(scenario.system_prompt, secrets)),
        Message.user(render(scenario.user_task, secrets)),
    ]
    final_response: str | None = None
    turns_used = 0

    for turn in range(1, max_turns + 1):
        turns_used = turn
        action = adapter.next_action(messages, env.tool_schemas())

        if isinstance(action, FinalResponse):
            final_response = action.text
            messages.append(Message.assistant(action.text))
            break

        if isinstance(action, ToolCalls):
            messages.append(Message.assistant_tool_calls(action.calls))
            for call in action.calls:
                result = env.execute(call, turn)
                messages.append(Message.tool_result(call, result))
            continue

        raise AdapterError(f"adapter returned unsupported action type {type(action)!r}")

    return _Trajectory(messages=messages, final_response=final_response, turns_used=turns_used)


def run_scenario(
    scenario: Scenario,
    adapter: AgentAdapter,
    *,
    repeat_index: int = 0,
    max_turns: int | None = None,
    judge: Judge | None = None,
    seed: int = 0,
) -> ScenarioRun:
    """Execute one scenario once and score the resulting trajectory."""
    started = time.perf_counter()
    rng = random.Random(f"{seed}:{scenario.id}:{repeat_index}")
    secrets = resolve_secrets(scenario.secrets, rng)
    env = Environment(scenario.environment, secrets)
    turn_budget = max_turns or scenario.max_turns

    try:
        trajectory = _drive(scenario, adapter, env, secrets, turn_budget)
    except Exception as exc:
        return ScenarioRun(
            scenario_id=scenario.id,
            category=scenario.category,
            repeat_index=repeat_index,
            verdict=Verdict.ERRORED,
            error=f"{type(exc).__name__}: {exc}",
            calls=[{"name": c.name, "arguments": c.arguments} for c in env.log],
            duration_s=time.perf_counter() - started,
        )

    transcript_text = _transcript_text(trajectory.messages)
    attack_results = evaluate_all(
        scenario.detectors, env, trajectory.final_response, transcript_text, judge
    )
    compromised = combine(attack_results, scenario.detector_mode)

    utility_results = evaluate_all(
        scenario.utility_check, env, trajectory.final_response, transcript_text, judge
    )
    if not scenario.utility_check:
        utility = UtilityOutcome.NOT_SPECIFIED
    else:
        utility = (
            UtilityOutcome.PASSED
            if combine(utility_results, "all")
            else UtilityOutcome.FAILED
        )

    return ScenarioRun(
        scenario_id=scenario.id,
        category=scenario.category,
        repeat_index=repeat_index,
        verdict=Verdict.COMPROMISED if compromised else Verdict.RESISTED,
        utility=utility,
        detector_results=attack_results,
        utility_results=utility_results,
        turns_used=trajectory.turns_used,
        calls=[
            {"turn": c.turn, "name": c.name, "arguments": c.arguments, "result": c.result}
            for c in env.log
        ],
        transcript=_serialize_messages(trajectory.messages),
        final_response=trajectory.final_response,
        duration_s=time.perf_counter() - started,
    )


def run_suite(
    scenarios: Iterable[Scenario],
    adapter_factory: AdapterFactory,
    *,
    repeats: int = 1,
    max_turns: int | None = None,
    judge: Judge | None = None,
    concurrency: int = 4,
    seed: int = 0,
    on_result: Callable[[ScenarioRun], None] | None = None,
) -> list[ScenarioRun]:
    """Run every scenario *repeats* times, optionally in parallel.

    A fresh adapter is built per unit of work rather than shared, because several
    backends hold per-call state or a client that is not thread-safe.
    """
    jobs = [(s, i) for s in scenarios for i in range(repeats)]
    if not jobs:
        return []

    def execute(job: tuple[Scenario, int]) -> ScenarioRun:
        scenario, repeat_index = job
        try:
            adapter = adapter_factory()
        except Exception as exc:
            return ScenarioRun(
                scenario_id=scenario.id,
                category=scenario.category,
                repeat_index=repeat_index,
                verdict=Verdict.ERRORED,
                error=f"adapter construction failed: {exc}",
            )
        return run_scenario(
            scenario,
            adapter,
            repeat_index=repeat_index,
            max_turns=max_turns,
            judge=judge,
            seed=seed,
        )

    results: list[ScenarioRun] = []
    if concurrency <= 1:
        for job in jobs:
            result = execute(job)
            results.append(result)
            if on_result:
                on_result(result)
        return results

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for result in pool.map(execute, jobs):
            results.append(result)
            if on_result:
                on_result(result)
    return results
