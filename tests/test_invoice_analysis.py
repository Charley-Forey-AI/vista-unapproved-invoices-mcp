from __future__ import annotations

from datetime import UTC, datetime

from server.services.invoice_analysis import AnalysisConfig, analyze_invoices


def test_analyze_invoices_classifies_buckets_and_top_risks() -> None:
    rows = [
        {
            "id": "inv-1",
            "vendorId": "vendor-a",
            "invoiceNumber": "A-100",
            "invoiceAmount": 1000.0,
            "invoiceDate": "2025-08-01T00:00:00Z",
        },
        {
            "id": "inv-2",
            "vendorId": "vendor-a",
            "invoiceNumber": "A-100",
            "invoiceAmount": 1000.0,
            "invoiceDate": "2025-08-02T00:00:00Z",
        },
        {
            "id": "inv-3",
            "vendorId": "vendor-b",
            "invoiceNumber": "B-200",
            "invoiceAmount": 50.0,
            "invoiceDate": "2025-08-03T00:00:00Z",
        },
        {
            "id": "inv-4",
            "vendorId": "",
            "invoiceNumber": "",
            "invoiceAmount": None,
            "invoiceDate": None,
        },
    ]

    report = analyze_invoices(
        rows,
        config=AnalysisConfig(
            window_days=365,
            stale_days=30,
            top_n=5,
            high_amount_threshold=500.0,
            duplicate_amount_delta=0.01,
        ),
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert report["totals"]["sourceCount"] == 4
    assert report["totals"]["analyzedCount"] == 4
    assert report["totals"]["approveCandidateCount"] == 1
    assert report["totals"]["needsCorrectionCount"] == 1
    assert report["totals"]["needsInvestigationCount"] == 2
    assert report["topRisks"][0]["id"] in {"inv-1", "inv-2"}
    assert report["vendorGroups"][0]["vendorId"] == "vendor-a"
    assert report["vendorGroups"][0]["invoiceCount"] == 2
    assert "riskScore" in report["topRisks"][0]
    assert report["topRisks"][0]["confidence"] in {"high", "medium", "low"}


def test_analyze_invoices_filters_outside_window() -> None:
    rows = [
        {
            "id": "inv-old",
            "vendorId": "vendor-old",
            "invoiceNumber": "OLD-1",
            "invoiceAmount": 120.0,
            "invoiceDate": "2023-01-01T00:00:00Z",
        },
        {
            "id": "inv-new",
            "vendorId": "vendor-new",
            "invoiceNumber": "NEW-1",
            "invoiceAmount": 220.0,
            "invoiceDate": "2025-12-25T00:00:00Z",
        },
    ]

    report = analyze_invoices(
        rows,
        config=AnalysisConfig(
            window_days=365,
            stale_days=60,
            top_n=5,
            high_amount_threshold=10000.0,
            duplicate_amount_delta=0.01,
        ),
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert report["totals"]["sourceCount"] == 2
    assert report["totals"]["analyzedCount"] == 1
    assert report["totals"]["excludedDeletedCount"] == 0
    assert report["totals"]["excludedOutsideWindowCount"] == 1
    assert report["approveCandidates"][0]["id"] == "inv-new"


def test_analyze_invoices_excludes_deleted_records() -> None:
    rows = [
        {
            "id": "inv-deleted-1",
            "vendorId": "vendor-a",
            "invoiceNumber": "DEL-1",
            "invoiceAmount": 100.0,
            "invoiceDate": "2025-12-25T00:00:00Z",
            "deleted": True,
        },
        {
            "id": "inv-deleted-2",
            "vendorId": "vendor-a",
            "invoiceNumber": "DEL-2",
            "invoiceAmount": 200.0,
            "invoiceDate": "2025-12-26T00:00:00Z",
            "deletedDateTime": "2025-12-27T00:00:00Z",
        },
        {
            "id": "inv-active",
            "vendorId": "vendor-b",
            "invoiceNumber": "ACT-1",
            "invoiceAmount": 300.0,
            "invoiceDate": "2025-12-28T00:00:00Z",
            "deleted": False,
        },
    ]

    report = analyze_invoices(
        rows,
        config=AnalysisConfig(
            window_days=365,
            stale_days=60,
            top_n=5,
            high_amount_threshold=10000.0,
            duplicate_amount_delta=0.01,
        ),
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert report["totals"]["sourceCount"] == 3
    assert report["totals"]["analyzedCount"] == 1
    assert report["totals"]["excludedDeletedCount"] == 2
    assert report["totals"]["excludedOutsideWindowCount"] == 0
    assert [item["id"] for item in report["approveCandidates"]] == ["inv-active"]


def test_analyze_invoices_supports_strict_policy_profile() -> None:
    rows = [
        {
            "id": "inv-1",
            "vendorId": "vendor-a",
            "invoiceNumber": "INV-1",
            "invoiceAmount": 400.0,
            "invoiceDate": "2025-12-25T00:00:00Z",
        }
    ]

    report = analyze_invoices(
        rows,
        config=AnalysisConfig(
            window_days=365,
            stale_days=60,
            top_n=5,
            high_amount_threshold=500.0,
            duplicate_amount_delta=0.01,
            policy_profile="strict",
        ),
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert report["riskModel"]["profile"] == "strict"
    assert report["topRisks"][0]["id"] == "inv-1"
    assert report["topRisks"][0]["riskScore"] >= 40
