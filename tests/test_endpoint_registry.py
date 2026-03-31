from __future__ import annotations

from server.config import VistaSettings
from server.endpoint_registry import ENDPOINTS_BY_TOOL, SCOPED_ENDPOINTS, endpoint_dependency_graph, iter_enabled_endpoints
from server.generated_models import model_for_response_schema


def test_scoped_registry_has_unique_tool_names() -> None:
    names = [endpoint.tool_name for endpoint in SCOPED_ENDPOINTS]
    assert len(names) == len(set(names))
    assert len(SCOPED_ENDPOINTS) == 45


def test_optional_endpoints_honor_settings_flags() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
        include_test_enterprise_tool=False,
        include_health_alive_tool=False,
    )
    enabled_names = {endpoint.tool_name for endpoint in iter_enabled_endpoints(settings)}
    assert "test_list_enterprises" not in enabled_names
    assert "health_alive" not in enabled_names
    assert "health_ready" in enabled_names


def test_unapproved_invoice_action_uses_action_schema() -> None:
    action_spec = ENDPOINTS_BY_TOOL["get_unapproved_invoice_action"]
    record_spec = ENDPOINTS_BY_TOOL["get_unapproved_invoice"]
    assert action_spec.response_schema_ref is not None
    assert record_spec.response_schema_ref is not None
    assert action_spec.response_schema_ref.endswith("UnapprovedInvoiceActionRecordGetItemResponse")
    assert record_spec.response_schema_ref.endswith("UnapprovedInvoiceRecordGetItemResponse")


def test_response_model_mapping_keeps_action_and_record_distinct() -> None:
    action_model = model_for_response_schema(
        "#/components/schemas/UnapprovedInvoiceActionRecordGetItemResponse"
    )
    record_model = model_for_response_schema(
        "#/components/schemas/UnapprovedInvoiceRecordGetItemResponse"
    )
    assert action_model.__name__ == "UnapprovedInvoiceActionRecordGetItemResponse"
    assert record_model.__name__ == "UnapprovedInvoiceRecordGetItemResponse"
    assert action_model is not record_model


def test_dependency_graph_contains_required_io_metadata() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
    )
    graph = endpoint_dependency_graph(settings)
    assert graph["version"] == 2
    tools = graph["tools"]
    assert isinstance(tools, list)
    vendor_node = next(node for node in tools if node["tool"] == "get_vendor")
    assert "produced_fields" in vendor_node
    assert "required_inputs" in vendor_node
    assert "requires" in vendor_node
    assert "produces" in vendor_node
    assert "prerequisites" in vendor_node
    assert "id_sources" in vendor_node
    assert "safe_to_retry" in vendor_node


def test_dependency_graph_contains_workflow_decision_rules() -> None:
    settings = VistaSettings(
        _env_file=None,
        api_base_url="https://api.example.com",
        bearer_token="token",
    )
    graph = endpoint_dependency_graph(settings)
    workflows = graph["workflows"]
    assert isinstance(workflows, list)
    create_invoice = next(item for item in workflows if item["intent"] == "create_unapproved_invoice")
    assert "tool_order" in create_invoice
    assert "decision_rules" in create_invoice

