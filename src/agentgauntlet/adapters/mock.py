"""Offline adapters: a scripted one for tests, and simulated agents for demos.

These exist so the entire harness (engine, detectors, scoring, reports) can be
exercised with no API key and no network. CI runs on them, and ``--adapter mock``
gives a new user a working end-to-end run in one command.

``MockAdapter`` is a caricature, not a model. The ``vulnerable`` policy blindly
obeys instructions it finds in tool output, which is precisely the failure mode
the scenarios are written to catch, so it is a useful fixture for proving that
detectors fire when they should.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from ..messages import AgentAction, FinalResponse, Message, ToolCall, ToolCalls, ToolSchema
from ..stdlib_tools import DESTRUCTIVE_TOOLS, EXFILTRATION_SINKS
from .base import AdapterError

# Matches a canary along with any prefix it was planted with, so that a secret
# declared as "sk-live-{{random_token}}" is echoed whole rather than truncated.
_CANARY_RE = re.compile(r"[\w-]*CANARY-[A-Z0-9]{4,}")
SINK_NAMES = EXFILTRATION_SINKS | DESTRUCTIVE_TOOLS

# Identifiers a real agent would lift out of a listing and feed back into a
# lookup tool: "T-441", "INV-9001", "alice/brief.md", "config/settings.py".
_IDENTIFIER_PATTERNS = (
    re.compile(r"\b[A-Za-z][A-Za-z0-9]*-\d+\b"),
    re.compile(r"\b[\w-]+(?:/[\w.-]+)+\b"),
    re.compile(r"\b[\w.-]+\.(?:md|py|log|db|txt|ya?ml|json|csv)\b"),
)

# Parameters that name a record to look up, as opposed to free-form input.
_IDENTIFIER_PARAMS = frozenset(
    {"id", "path", "name", "file", "filename", "document", "item", "key", "step"}
)

MockPolicy = Literal["safe", "vulnerable"]


class ScriptedAdapter:
    """Replay a fixed list of actions. Deterministic fixture for unit tests."""

    def __init__(self, actions: list[AgentAction]) -> None:
        self._actions = list(actions)
        self._index = 0

    def next_action(self, messages: list[Message], tools: list[ToolSchema]) -> AgentAction:
        if self._index >= len(self._actions):
            return FinalResponse(text="done")
        action = self._actions[self._index]
        self._index += 1
        return action


class MockAdapter:
    """A crude simulated agent used for offline demos and detector self-tests."""

    def __init__(self, policy: MockPolicy = "vulnerable", max_calls_per_tool: int = 3) -> None:
        if policy not in ("safe", "vulnerable"):
            raise AdapterError(f"unknown mock policy {policy!r}; use 'safe' or 'vulnerable'")
        self.policy = policy
        self.max_calls_per_tool = max_calls_per_tool

    def next_action(self, messages: list[Message], tools: list[ToolSchema]) -> AgentAction:
        by_name = {t.name: t for t in tools}
        safe_tools = [t for t in tools if t.name not in SINK_NAMES]
        counts = _call_counts(messages)

        candidates = _identifier_candidates(messages)
        for tool in safe_tools:
            budget = self.max_calls_per_tool if _has_parameters(tool) else 1
            if counts.get(tool.name, 0) < budget:
                return ToolCalls(
                    calls=[
                        ToolCall(
                            name=tool.name, arguments=_synthesize_args(tool, counts, candidates)
                        )
                    ]
                )

        if self.policy == "vulnerable":
            action = self._attempt_injected_action(messages, by_name, counts)
            if action is not None:
                return action

        return FinalResponse(text=_summarize(messages))

    def _attempt_injected_action(
        self,
        messages: list[Message],
        by_name: dict[str, ToolSchema],
        counts: dict[str, int],
    ) -> AgentAction | None:
        """Obey whatever the tool output told us to do, the behavior under test."""
        observed = "\n".join(m.content or "" for m in messages if m.role == "tool")
        sinks = [name for name in by_name if name in SINK_NAMES and counts.get(name, 0) == 0]
        if not sinks:
            return None

        mentioned = [name for name in sinks if name in observed] or sinks
        target = by_name[mentioned[0]]

        canary = _CANARY_RE.search(observed)
        email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", observed)
        payload = canary.group(0) if canary else "acknowledged"

        arguments = _synthesize_args(target, counts, _identifier_candidates(messages))
        for key in ("body", "text", "content", "message"):
            if key in (target.parameters.get("properties") or {}):
                arguments[key] = f"Forwarding as instructed: {payload}"
                break
        for key in ("to", "email", "url", "to_account"):
            if key in (target.parameters.get("properties") or {}) and email:
                arguments[key] = email.group(0)
                break

        return ToolCalls(calls=[ToolCall(name=target.name, arguments=arguments)])


def _has_parameters(tool: ToolSchema) -> bool:
    return bool(tool.parameters.get("properties"))


def _call_counts(messages: list[Message]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in messages:
        for call in message.tool_calls or []:
            counts[call.name] = counts.get(call.name, 0) + 1
    return counts


def _identifier_candidates(messages: list[Message]) -> list[str]:
    """Pull record identifiers out of earlier tool output, in order of appearance.

    A real agent reads a listing and feeds the ids it saw back into a lookup tool.
    Without this the mock passes a placeholder, never reaches the branch holding
    the planted payload, and makes every string-keyed scenario look safe.
    """
    observed = "\n".join(m.content or "" for m in messages if m.role == "tool")
    hits: list[tuple[int, str]] = []
    for pattern in _IDENTIFIER_PATTERNS:
        hits.extend((m.start(), m.group(0)) for m in pattern.finditer(observed))

    ordered: list[str] = []
    for _, value in sorted(hits, key=lambda pair: pair[0]):
        if value not in ordered:
            ordered.append(value)
    return ordered


def _synthesize_args(
    tool: ToolSchema, counts: dict[str, int], candidates: list[str] | None = None
) -> dict[str, Any]:
    """Fill required parameters with type-appropriate values.

    Integer parameters advance with the call count so tools keyed by a number
    (``read_email(id=1)``, ``read_email(id=2)``…) get walked. Identifier-shaped
    string parameters draw from ids observed in earlier tool output.
    """
    properties: dict[str, Any] = tool.parameters.get("properties") or {}
    required: list[str] = list(tool.parameters.get("required") or properties.keys())
    nth = counts.get(tool.name, 0) + 1
    candidates = candidates or []

    arguments: dict[str, Any] = {}
    for name in required:
        spec = properties.get(name, {})
        kind = spec.get("type", "string")
        if kind in ("integer", "number"):
            arguments[name] = nth
        elif kind == "boolean":
            arguments[name] = True
        elif kind == "array":
            arguments[name] = []
        elif kind == "object":
            arguments[name] = {}
        elif candidates and (name in _IDENTIFIER_PARAMS or name.endswith("_id")):
            arguments[name] = candidates[(nth - 1) % len(candidates)]
        else:
            arguments[name] = str(nth) if name in ("id", "item_id", "index") else "placeholder"
    return arguments


def _summarize(messages: list[Message]) -> str:
    results = [m.content or "" for m in messages if m.role == "tool"]
    if not results:
        return "I could not find anything to report."
    joined = " ".join(" ".join(r.split()) for r in results)
    return f"Here is a summary of what I found: {joined[:400]}"
