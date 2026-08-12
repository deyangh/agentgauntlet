"""Per-run substitution of secrets and canary tokens.

Canary tokens are regenerated for every run so that a token observed in an
outbound tool call can only have come from that run's planted secret. This is
what makes the exfiltration detectors airtight rather than suggestive.
"""

from __future__ import annotations

import random
import re
import string
from typing import Any

_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
_ALPHABET = string.ascii_uppercase + string.digits


def new_canary(rng: random.Random, length: int = 10) -> str:
    """Generate a canary token that is unlikely to appear by chance in model output."""
    body = "".join(rng.choice(_ALPHABET) for _ in range(length))
    return f"CANARY-{body}"


def resolve_secrets(raw: dict[str, str], rng: random.Random) -> dict[str, str]:
    """Expand ``{{random_token}}`` inside a scenario's declared secrets."""
    resolved: dict[str, str] = {}
    for key, value in raw.items():
        resolved[key] = _TOKEN_RE.sub(
            lambda m: new_canary(rng) if m.group(1) == "random_token" else m.group(0),
            value,
        )
    return resolved


def render(text: str, secrets: dict[str, str], rng: random.Random | None = None) -> str:
    """Substitute ``{{secrets.NAME}}`` and any stray ``{{random_token}}`` in *text*."""

    def _replace(match: re.Match[str]) -> str:
        ref = match.group(1)
        if ref == "random_token":
            return new_canary(rng) if rng is not None else match.group(0)
        if ref.startswith("secrets."):
            return secrets.get(ref.removeprefix("secrets."), match.group(0))
        return match.group(0)

    return _TOKEN_RE.sub(_replace, text)


def render_any(value: Any, secrets: dict[str, str]) -> Any:
    """Recursively render strings inside dicts, lists, and scalars."""
    if isinstance(value, str):
        return render(value, secrets)
    if isinstance(value, dict):
        return {k: render_any(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [render_any(v, secrets) for v in value]
    return value
