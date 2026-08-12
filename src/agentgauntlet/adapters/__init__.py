"""Adapter implementations and the factory that selects between them."""

from __future__ import annotations

from ..models import AdapterConfig
from .base import AdapterError, AgentAdapter
from .callable_adapter import CallableAdapter
from .mock import MockAdapter, ScriptedAdapter
from .subprocess_adapter import SubprocessAdapter

__all__ = [
    "AdapterError",
    "AgentAdapter",
    "CallableAdapter",
    "MockAdapter",
    "ScriptedAdapter",
    "SubprocessAdapter",
    "build_adapter",
    "describe_adapter",
]


def build_adapter(config: AdapterConfig, temperature: float = 0.0) -> AgentAdapter:
    """Instantiate the adapter described by *config*.

    Adapters are constructed per worker thread rather than shared, since several
    of them hold per-call state or a non-thread-safe client.
    """
    if config.type == "litellm":
        if not config.model:
            raise AdapterError("adapter.model is required for the litellm adapter")
        from .litellm_adapter import LiteLLMAdapter

        return LiteLLMAdapter(
            model=config.model,
            temperature=temperature,
            max_tokens=config.max_tokens,
            api_base=config.api_base,
        )

    if config.type == "callable":
        if not config.target:
            raise AdapterError("adapter.target is required for the callable adapter")
        return CallableAdapter(config.target)

    if config.type == "subprocess":
        if not config.target:
            raise AdapterError("adapter.target is required for the subprocess adapter")
        return SubprocessAdapter(config.target)

    if config.type == "mock":
        policy = config.model or "vulnerable"
        if policy not in ("safe", "vulnerable"):
            raise AdapterError(
                f"mock adapter policy must be 'safe' or 'vulnerable', got {policy!r}"
            )
        return MockAdapter(policy=policy)  # type: ignore[arg-type]

    raise AdapterError(f"unknown adapter type {config.type!r}")


def describe_adapter(config: AdapterConfig) -> str:
    """Human-readable label used in reports and the leaderboard."""
    if config.type == "litellm":
        return config.model or "litellm"
    if config.type == "mock":
        return f"mock:{config.model or 'vulnerable'}"
    return f"{config.type}:{config.target}"
