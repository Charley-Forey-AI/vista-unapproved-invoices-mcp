"""Normalization helpers for tool payloads."""

from __future__ import annotations

import re
from typing import Any

_FIRST_CAP_RE = re.compile("(.)([A-Z][a-z]+)")
_ALL_CAP_RE = re.compile("([a-z0-9])([A-Z])")


def _to_snake_case(value: str) -> str:
    with_underscores = _FIRST_CAP_RE.sub(r"\1_\2", value)
    return _ALL_CAP_RE.sub(r"\1_\2", with_underscores).lower()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_to_snake_case(key): _normalize_value(sub_value) for key, sub_value in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def normalize_payload(
    payload: dict[str, Any],
    *,
    tool_name: str,
    schema_ref: str | None,
) -> dict[str, Any]:
    """Return canonical snake_case output with metadata for agent planning."""

    normalized = _normalize_value(payload)
    return {
        "tool_name": tool_name,
        "schema_ref": schema_ref,
        "data": normalized,
    }

