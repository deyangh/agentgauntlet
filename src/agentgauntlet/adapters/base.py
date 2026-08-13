"""The single interface every agent under test must satisfy.

The harness owns the conversation loop and passes the full message list on every
call, so adapters are stateless translators. That is what lets a bare model, a
hand-rolled agent, and a subprocess be scored by identical machinery.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from ..messages import AgentAction, FinalResponse, Message, ToolCall, ToolCalls, ToolSchema


class AdapterError(RuntimeError):
    """Raised when an agent backend fails in a way the engine should record as ERRORED."""


@runtime_checkable
class AgentAdapter(Protocol):
    """Produces the next agent action given conversation state and available tools."""

    def next_action(self, messages: list[Message], tools: list[ToolSchema]) -> AgentAction: ...


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Coerce a provider's argument payload into a dictionary.

    Models return arguments as a JSON string, as a dict, or occasionally as
    malformed JSON. A malformed payload is still evidence of an attempted call,
    so it is preserved under a ``_raw`` key rather than discarded.
    """
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    return {"_raw": str(raw)}


def action_from_payload(payload: dict[str, Any]) -> AgentAction:
    """Build an :class:`AgentAction` from the JSON protocol shared by several adapters."""
    kind = payload.get("type")
    if kind == "tool_calls":
        calls = [
            ToolCall(name=str(c["name"]), arguments=parse_arguments(c.get("arguments")))
            for c in payload.get("calls", [])
        ]
        if not calls:
            raise AdapterError("agent returned type='tool_calls' with an empty calls list")
        return ToolCalls(calls=calls)
    if kind == "final":
        return FinalResponse(text=str(payload.get("text", "")))
    raise AdapterError(f"agent returned unrecognized payload type {kind!r}")
