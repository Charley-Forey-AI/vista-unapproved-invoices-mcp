"""OpenAPI-driven helper utilities for tool descriptions and validation hints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_SCHEMA_CACHE: dict[str, Any] | None = None


def _openapi_path() -> Path:
    return Path(__file__).resolve().parent.parent / "viewpoint_common_api.json"


def _load_schemas() -> dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        payload = json.loads(_openapi_path().read_text(encoding="utf-8"))
        _SCHEMA_CACHE = payload.get("components", {}).get("schemas", {})
    return _SCHEMA_CACHE


def _schema_name(schema_ref: str | None) -> str | None:
    if not schema_ref:
        return None
    return schema_ref.rsplit("/", 1)[-1]


def _schema_by_ref(schema_ref: str | None) -> dict[str, Any] | None:
    name = _schema_name(schema_ref)
    if not name:
        return None
    return _load_schemas().get(name)


def required_fields_for_request_schema(schema_ref: str | None) -> list[str]:
    """Return request-required fields from an OpenAPI schema ref."""

    schema = _schema_by_ref(schema_ref)
    if not schema:
        return []

    if schema.get("type") == "object":
        top_required = schema.get("required", [])
    else:
        top_required = []

    name = _schema_name(schema_ref) or ""
    if name.endswith("BulkActionBody"):
        item_schema = schema.get("properties", {}).get("items", {}).get("items", {})
        item_ref = item_schema.get("$ref")
        if not item_ref:
            return [f"items[].{field}" for field in top_required]
        item = _schema_by_ref(item_ref)
        if not item:
            return [f"items[].{field}" for field in top_required]
        item_required = item.get("required", [])
        return [f"items[].{field}" for field in item_required]

    return list(top_required)

