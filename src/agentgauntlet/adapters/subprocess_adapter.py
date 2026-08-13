"""Adapter for an agent that is not Python, or not importable.

Speaks a one-shot JSON protocol over stdin/stdout, so a TypeScript agent, a Go
binary, or a shell wrapper around a hosted service can all be put through the
same gauntlet::

    agentgauntlet run --adapter subprocess --target "node my-agent.js"

Request on stdin::

    {"messages": [{"role": "user", "content": "..."}, ...],
     "tools": [{"name": "...", "description": "...", "parameters": {...}}, ...]}

Response on stdout, one of::

    {"type": "final", "text": "..."}
    {"type": "tool_calls", "calls": [{"name": "...", "arguments": {...}}]}

The process is spawned per turn and receives the full conversation each time,
matching the stateless contract the rest of the harness relies on.
"""

from __future__ import annotations

import json
import shlex
import subprocess

from ..messages import AgentAction, Message, ToolSchema
from .base import AdapterError, action_from_payload


class SubprocessAdapter:
    """Run an external program as the agent under test."""

    def __init__(self, target: str, timeout: float = 120.0, cwd: str | None = None) -> None:
        self.argv = shlex.split(target) if isinstance(target, str) else list(target)
        if not self.argv:
            raise AdapterError("subprocess adapter requires a non-empty command")
        self.timeout = timeout
        self.cwd = cwd

    def next_action(self, messages: list[Message], tools: list[ToolSchema]) -> AgentAction:
        request = json.dumps(
            {
                "messages": [m.to_openai_format() for m in messages],
                "tools": [
                    {"name": t.name, "description": t.description, "parameters": t.parameters}
                    for t in tools
                ],
            }
        )

        try:
            completed = subprocess.run(
                self.argv,
                input=request,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.cwd,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AdapterError(f"agent command not found: {self.argv[0]!r}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"agent command timed out after {self.timeout}s") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()[:500]
            raise AdapterError(f"agent exited {completed.returncode}: {stderr}")

        payload = _last_json_object(completed.stdout)
        return action_from_payload(payload)


def _last_json_object(stdout: str) -> dict[str, object]:
    """Parse the final JSON object printed, tolerating log lines on stdout."""
    for line in reversed([ln for ln in stdout.splitlines() if ln.strip()]):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise AdapterError(f"agent produced no JSON object on stdout; got: {stdout[:300]!r}")
