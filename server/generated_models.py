"""Generated-like model adapters for OpenAPI schema references."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model

from .models import HealthResponse, QueryFilter


class GeneratedVistaModel(BaseModel):
    """Base class for generated response wrappers."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class GeneratedRecordItem(GeneratedVistaModel):
    """Common cross-domain record shape with extra fields allowed."""

    id: UUID | str | int | None = None
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")


class GeneratedGetItemResponse(GeneratedVistaModel):
    item: GeneratedRecordItem | None = None


class GeneratedListPagedResponse(GeneratedVistaModel):
    items: list[GeneratedRecordItem] = Field(default_factory=list)
    page_size: int | None = Field(default=None, alias="pageSize")
    current_page: int | None = Field(default=None, alias="currentPage")


class GeneratedActionResult(GeneratedVistaModel):
    status_code: str | None = Field(default=None, alias="statusCode")
    action: str | None = None
    message: str | None = None
    item: GeneratedRecordItem | None = None


class GeneratedBulkActionResponse(GeneratedVistaModel):
    items: list[GeneratedActionResult] = Field(default_factory=list)


class GeneratedFilterBody(GeneratedVistaModel):
    filters: list[QueryFilter] = Field(default_factory=list)


class GeneratedBulkActionBody(GeneratedVistaModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


_MODEL_CACHE: dict[str, type[BaseModel]] = {}
_OPENAPI_SCHEMAS: dict[str, Any] | None = None


def _workspace_openapi_path() -> Path:
    return Path(__file__).resolve().parent.parent / "viewpoint_common_api.json"


def _load_openapi_schemas() -> dict[str, Any]:
    global _OPENAPI_SCHEMAS
    if _OPENAPI_SCHEMAS is None:
        payload = json.loads(_workspace_openapi_path().read_text(encoding="utf-8"))
        _OPENAPI_SCHEMAS = payload.get("components", {}).get("schemas", {})
    return _OPENAPI_SCHEMAS


def _resolve_schema_ref(schema_ref: str) -> dict[str, Any]:
    schema_name = schema_ref.rsplit("/", 1)[-1]
    schemas = _load_openapi_schemas()
    if schema_name not in schemas:
        raise ValueError(f"Schema ref not found: {schema_ref}")
    return schemas[schema_name]


def _is_nullable(schema: dict[str, Any], required: bool) -> bool:
    return bool(schema.get("nullable")) or not required


def _python_type_for_schema(schema: dict[str, Any]) -> Any:
    ref = schema.get("$ref")
    if ref:
        name = ref.rsplit("/", 1)[-1]
        model_name = f"{name}Typed"
        if model_name not in _MODEL_CACHE:
            _MODEL_CACHE[model_name] = _create_typed_object_model(name, model_name=model_name)
        return _MODEL_CACHE[model_name]

    schema_type = schema.get("type")
    schema_format = schema.get("format")
    if schema_type == "string":
        if schema_format == "uuid":
            return UUID
        if schema_format in {"date-time", "date"}:
            return datetime
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        item_type = _python_type_for_schema(schema.get("items", {}))
        return list[item_type]  # type: ignore[valid-type]
    if schema_type == "object":
        return dict[str, Any]
    return Any


def _create_typed_object_model(schema_name: str, *, model_name: str | None = None) -> type[BaseModel]:
    schemas = _load_openapi_schemas()
    source = schemas.get(schema_name, {})
    properties = source.get("properties", {})
    required = set(source.get("required", []))
    fields: dict[str, tuple[Any, Any]] = {}

    for prop_name, prop_schema in properties.items():
        field_type = _python_type_for_schema(prop_schema)
        if _is_nullable(prop_schema, prop_name in required):
            field_type = field_type | None  # type: ignore[operator]
        default_value = ... if prop_name in required else None
        fields[prop_name] = (field_type, Field(default=default_value))

    dynamic_name = model_name or schema_name
    return create_model(dynamic_name, __base__=GeneratedVistaModel, **fields)


def _schema_name(schema_ref: str | None) -> str:
    if not schema_ref:
        return "HealthResponse"
    return schema_ref.rsplit("/", 1)[-1]


def _base_for_response_schema(schema_name: str) -> type[BaseModel]:
    if schema_name == "HealthResponse":
        return HealthResponse
    if schema_name.endswith("ListPagedResponse"):
        return GeneratedListPagedResponse
    if schema_name.endswith("BulkApiActionResponse"):
        return GeneratedBulkActionResponse
    return GeneratedGetItemResponse


def model_for_response_schema(schema_ref: str | None) -> type[BaseModel]:
    """Return a stable generated model class for an OpenAPI response schema ref."""

    schema_name = _schema_name(schema_ref)
    if schema_name in _MODEL_CACHE:
        return _MODEL_CACHE[schema_name]
    base_model = _base_for_response_schema(schema_name)
    model = create_model(schema_name, __base__=base_model)
    _MODEL_CACHE[schema_name] = model
    return model


def request_model_for_schema(schema_ref: str | None) -> type[BaseModel] | None:
    """Map OpenAPI request schema refs to request body wrappers."""

    schema_name = _schema_name(schema_ref)
    if schema_name.endswith("FilterBody"):
        if schema_name not in _MODEL_CACHE:
            _MODEL_CACHE[schema_name] = create_model(schema_name, __base__=GeneratedFilterBody)
        return _MODEL_CACHE[schema_name]
    if schema_name.endswith("BulkActionBody"):
        if schema_name not in _MODEL_CACHE:
            schema = _resolve_schema_ref(schema_ref) if schema_ref else {}
            item_schema = schema.get("properties", {}).get("items", {}).get("items", {})
            item_ref = item_schema.get("$ref")
            if item_ref:
                item_name = item_ref.rsplit("/", 1)[-1]
                item_model_name = f"{item_name}Typed"
                if item_model_name not in _MODEL_CACHE:
                    _MODEL_CACHE[item_model_name] = _create_typed_object_model(item_name, model_name=item_model_name)
                item_model = _MODEL_CACHE[item_model_name]
                _MODEL_CACHE[schema_name] = create_model(
                    schema_name,
                    __base__=GeneratedVistaModel,
                    items=(list[item_model], Field(default_factory=list)),  # type: ignore[valid-type]
                )
            else:
                _MODEL_CACHE[schema_name] = create_model(schema_name, __base__=GeneratedBulkActionBody)
        return _MODEL_CACHE[schema_name]
    return None

