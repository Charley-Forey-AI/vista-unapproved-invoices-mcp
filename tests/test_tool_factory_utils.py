from __future__ import annotations

import pytest

from server.tool_factory import normalize_bulk_items


def test_normalize_bulk_items_enforces_max_size() -> None:
    with pytest.raises(ValueError, match="max_items=1"):
        normalize_bulk_items([{"a": 1}, {"a": 2}], max_items=1)


def test_normalize_bulk_items_accepts_single_item_dict() -> None:
    normalized = normalize_bulk_items({"a": 1}, max_items=5)
    assert normalized == [{"a": 1}]

