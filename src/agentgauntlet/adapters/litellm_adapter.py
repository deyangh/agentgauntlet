"""Adapter for any model reachable through LiteLLM (Anthropic, OpenAI, Gemini, Ollama…).

This is the path used for the published benchmark. It tests a *model plus system
prompt*, which is the right unit for cross-model comparison; to test an assembled
agent stack instead, use the callable or subprocess adapters.
"""

from __future__ import annotations

import time
from typing import Any

from ..messages import AgentAction, FinalResponse, Message, ToolCall, ToolCalls, ToolSchema
from .base import AdapterError, parse_arguments

_RETRY_DELAYS = (1.0, 3.0, 8.0)


class LiteLLMAdapter:
    """Drive a hosted or local model through LiteLLM's unified completion API."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        api_base: str | None = None,
    ) -> None:
        try:
            import litellm
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise AdapterError(
                "the litellm adapter requires the 'llm' extra: pip install 'agentgauntlet[llm]'"
            ) from exc

        self._litellm = litellm
        self._litellm.drop_params = True  # tolerate providers lacking a given knob
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_base = api_base

    def next_action(self, messages: list[Message], tools: list[ToolSchema]) -> AgentAction:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_openai_format() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = [t.to_openai_format() for t in tools]
            kwargs["tool_choice"] = "auto"
        if self.api_base:
            kwargs["api_base"] = self.api_base

        response = self._complete_with_retries(kwargs)
        return self._to_action(response)

    def _complete_with_retries(self, kwargs: dict[str, Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                return self._litellm.completion(**kwargs)
            except Exception as exc:
                last_error = exc
                if attempt >= len(_RETRY_DELAYS) or not _is_retryable(exc):
                    break
                time.sleep(_RETRY_DELAYS[attempt])
        raise AdapterError(f"{self.model} call failed: {last_error}") from last_error

    def _to_action(self, response: Any) -> AgentAction:
        try:
            message = response.choices[0].message
        except (AttributeError, IndexError, KeyError) as exc:
            raise AdapterError(f"unexpected completion shape from {self.model}: {exc}") from exc

        raw_calls = getattr(message, "tool_calls", None) or []
        if raw_calls:
            calls: list[ToolCall] = []
            for raw in raw_calls:
                function = getattr(raw, "function", None)
                if function is None:
                    continue
                calls.append(
                    ToolCall(
                        name=str(function.name),
                        arguments=parse_arguments(getattr(function, "arguments", None)),
                        id=str(getattr(raw, "id", None) or f"call_{len(calls)}"),
                    )
                )
            if calls:
                return ToolCalls(calls=calls)

        return FinalResponse(text=str(getattr(message, "content", "") or ""))


def _is_retryable(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(
        marker in text
        for marker in ("ratelimit", "rate limit", "429", "overloaded", "timeout", "503", "502")
    )
