"""The mock tool sandbox the agent under test operates inside.

The environment serves two jobs at once. It is where adversarial payloads are
planted (inside the data a tool returns, which is the realistic threat model),
and it is where every tool invocation is observed. Because the harness owns the
loop, the agent cannot reach any tool the environment did not hand it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from . import stdlib_tools
from .messages import RecordedCall, ToolCall, ToolSchema
from .models import EnvironmentSpec, ToolSpec
from .templating import render, render_any


@dataclass
class _ResolvedTool:
    spec: ToolSpec
    schema: ToolSchema
    stdlib: stdlib_tools.StdlibTool | None

    def response_key(self) -> str | None:
        if self.spec.response_key:
            return self.spec.response_key
        required = self.schema.parameters.get("required") or []
        if required:
            return str(required[0])
        props = self.schema.parameters.get("properties") or {}
        return next(iter(props), None)


class Environment:
    """Instantiates a scenario's mock tools and records everything the agent does."""

    def __init__(self, spec: EnvironmentSpec, secrets: dict[str, str]) -> None:
        self.secrets = secrets
        self.log: list[RecordedCall] = []
        self._tools: dict[str, _ResolvedTool] = {}
        for tool_spec in spec.tools:
            resolved = self._resolve(tool_spec)
            self._tools[resolved.schema.name] = resolved

    # -- construction ------------------------------------------------------------------

    def _resolve(self, spec: ToolSpec) -> _ResolvedTool:
        stdlib: stdlib_tools.StdlibTool | None = None
        name = spec.resolved_name
        description = spec.description
        parameters = spec.parameters

        if spec.use_stdlib:
            stdlib = stdlib_tools.get(spec.use_stdlib)
            name = spec.name or stdlib.name
            description = spec.description or stdlib.description
            if parameters == {"type": "object", "properties": {}, "required": []}:
                parameters = stdlib.parameters

        schema = ToolSchema(
            name=name,
            description=render(description, self.secrets),
            parameters=render_any(parameters, self.secrets),
        )
        return _ResolvedTool(spec=spec, schema=schema, stdlib=stdlib)

    # -- interface used by the engine --------------------------------------------------

    def tool_schemas(self) -> list[ToolSchema]:
        return [t.schema for t in self._tools.values()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools)

    def execute(self, call: ToolCall, turn: int) -> str:
        """Run a mock tool, record the invocation, and return its simulated output."""
        tool = self._tools.get(call.name)
        if tool is None:
            result = (
                f"Error: no tool named {call.name!r}. "
                f"Available tools: {', '.join(self.tool_names)}."
            )
        else:
            result = self._response_for(tool, call.arguments)

        self.log.append(
            RecordedCall(turn=turn, name=call.name, arguments=dict(call.arguments), result=result)
        )
        return result

    def _response_for(self, tool: _ResolvedTool, arguments: dict[str, Any]) -> str:
        spec = tool.spec

        if spec.response_map is not None:
            key = tool.response_key()
            raw_value = arguments.get(key) if key else None
            lookup = str(raw_value).strip() if raw_value is not None else ""
            body = spec.response_map.get(lookup)
            if body is None and lookup:
                # Tolerate "3" vs 3 and minor formatting drift in model-supplied arguments.
                for candidate, value in spec.response_map.items():
                    if candidate.strip().lower() == lookup.lower():
                        body = value
                        break
            if body is None:
                body = spec.default_response or spec.response
            if body is None:
                body = f"No entry found for {lookup!r}."
            return render(body, self.secrets)

        if spec.response is not None:
            return render(spec.response, self.secrets)

        if tool.stdlib is not None:
            return render(tool.stdlib.render_response(arguments), self.secrets)

        return "OK"

    # -- evidence helpers used by detectors --------------------------------------------

    def calls_to(self, name: str) -> list[RecordedCall]:
        return [c for c in self.log if c.name == name]

    def called(self, name: str) -> bool:
        return any(c.name == name for c in self.log)


def make_environment(
    spec: EnvironmentSpec, secrets: dict[str, str], rng: random.Random | None = None
) -> Environment:
    """Convenience constructor kept for symmetry with the engine's call sites."""
    del rng  # secrets are resolved before the environment is built
    return Environment(spec, secrets)
