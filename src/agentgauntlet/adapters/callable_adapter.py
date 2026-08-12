"""Adapter for an agent you wrote yourself, imported straight from your codebase.

This is the "test *my* stack, not a bare model" path. Point the harness at any
Python callable and your own routing, system prompt, guardrails, and retry logic
sit inside the loop being attacked::

    agentgauntlet run --adapter callable --target myapp.agent:decide

The callable receives the conversation and the tool schemas the scenario offers,
and returns the next action. Returning a plain string is treated as a final
answer, so the smallest possible integration is a one-line wrapper.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any, cast

from ..messages import AgentAction, FinalResponse, Message, ToolCall, ToolCalls, ToolSchema
from .base import AdapterError, action_from_payload, parse_arguments

AgentCallable = Callable[[list[Message], list[ToolSchema]], Any]


def load_callable(target: str) -> AgentCallable:
    """Import ``module.path:attribute`` and return it."""
    if ":" not in target:
        raise AdapterError(
            f"callable target {target!r} must be of the form 'module.path:function'"
        )
    module_name, _, attribute = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise AdapterError(f"could not import {module_name!r}: {exc}") from exc
    try:
        func = getattr(module, attribute)
    except AttributeError as exc:
        raise AdapterError(f"{module_name!r} has no attribute {attribute!r}") from exc
    if not callable(func):
        raise AdapterError(f"{target!r} is not callable")
    return cast(AgentCallable, func)


class CallableAdapter:
    """Wrap a user-supplied Python callable as an agent under test."""

    def __init__(self, target: str | AgentCallable) -> None:
        self._func: AgentCallable = load_callable(target) if isinstance(target, str) else target
        self.target = target if isinstance(target, str) else getattr(target, "__name__", "callable")

    def next_action(self, messages: list[Message], tools: list[ToolSchema]) -> AgentAction:
        try:
            result = self._func(messages, tools)
        except Exception as exc:
            raise AdapterError(f"agent callable {self.target!r} raised: {exc}") from exc
        return coerce_action(result)


def coerce_action(result: Any) -> AgentAction:
    """Accept the several natural shapes a user's agent might return."""
    if isinstance(result, FinalResponse | ToolCalls):
        return result
    if isinstance(result, str):
        return FinalResponse(text=result)
    if isinstance(result, dict):
        return action_from_payload(result)
    if isinstance(result, list):
        calls = [
            ToolCall(name=str(c["name"]), arguments=parse_arguments(c.get("arguments")))
            for c in result
            if isinstance(c, dict) and "name" in c
        ]
        if calls:
            return ToolCalls(calls=calls)
    raise AdapterError(
        "agent must return a string, an AgentAction, a {'type': ...} dict, "
        f"or a list of tool calls; got {type(result).__name__}"
    )
