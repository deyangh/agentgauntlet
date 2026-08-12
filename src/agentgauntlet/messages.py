"""Conversation and action primitives exchanged between the harness and an adapter.

These types are deliberately provider-agnostic. Adapters translate between them
and whatever wire format a given backend speaks, which keeps the engine — and
therefore the scoring — identical across every agent under test.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

Role: TypeAlias = Literal["system", "user", "assistant", "tool"]


def _new_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation requested by the agent."""

    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=_new_id)


@dataclass(frozen=True)
class ToolSchema:
    """A tool offered to the agent, described with JSON Schema parameters."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_format(self) -> dict[str, Any]:
        """Render as an OpenAI-style function tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class Message:
    """One turn of conversation state."""

    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    @staticmethod
    def system(content: str) -> Message:
        return Message(role="system", content=content)

    @staticmethod
    def user(content: str) -> Message:
        return Message(role="user", content=content)

    @staticmethod
    def assistant(content: str) -> Message:
        return Message(role="assistant", content=content)

    @staticmethod
    def assistant_tool_calls(calls: list[ToolCall]) -> Message:
        return Message(role="assistant", content=None, tool_calls=list(calls))

    @staticmethod
    def tool_result(call: ToolCall, result: str) -> Message:
        return Message(role="tool", content=result, tool_call_id=call.id, name=call.name)

    def to_openai_format(self) -> dict[str, Any]:
        """Render as an OpenAI-style chat message."""
        if self.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": self.tool_call_id,
                "content": self.content or "",
            }
        payload: dict[str, Any] = {"role": self.role, "content": self.content or ""}
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": _json_dumps(c.arguments)},
                }
                for c in self.tool_calls
            ]
        return payload


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


@dataclass(frozen=True)
class FinalResponse:
    """The agent is done and produced prose."""

    text: str


@dataclass(frozen=True)
class ToolCalls:
    """The agent wants to invoke one or more tools."""

    calls: list[ToolCall]


AgentAction: TypeAlias = FinalResponse | ToolCalls


@dataclass
class RecordedCall:
    """A tool call as observed by the environment — the primary evidence for detectors."""

    turn: int
    name: str
    arguments: dict[str, Any]
    result: str

    def argument_text(self, arg: str | None = None) -> str:
        """Flatten one argument (or all of them) to searchable text."""
        if arg is not None:
            value = self.arguments.get(arg)
            return "" if value is None else str(value)
        return " ".join(str(v) for v in self.arguments.values())
