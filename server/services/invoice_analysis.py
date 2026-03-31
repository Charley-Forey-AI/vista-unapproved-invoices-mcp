"""Read-only analysis workflow for unapproved invoices."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class AnalysisConfig:
    window_days: int
    stale_days: int
    top_n: int
    high_amount_threshold: float
    duplicate_amount_delta: float
    policy_profile: str = "standard"


def _parse_datetime(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=UTC)
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _invoice_datetime(invoice: dict[str, Any]) -> datetime | None:
    for key in ("invoiceDate", "createdDate", "createdDateTime", "lastUpdateDateUtc", "monthYear"):
        parsed = _parse_datetime(invoice.get(key))
        if parsed is not None:
            return parsed
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _normalize_invoice_number(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value).strip().lower()
    return value.strip().lower().replace("-", "").replace(" ", "")


def _is_deleted_invoice(invoice: dict[str, Any]) -> bool:
    deleted_value = invoice.get("deleted")
    if isinstance(deleted_value, bool):
        if deleted_value:
            return True
    elif isinstance(deleted_value, str):
        if deleted_value.strip().lower() in {"true", "1", "yes"}:
            return True
    elif isinstance(deleted_value, (int, float)) and deleted_value != 0:
        return True

    deleted_date = invoice.get("deletedDateTime")
    if _parse_datetime(deleted_date) is not None:
        return True
    return False


def _bucket_from_findings(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "approve_candidate"
    severities = {finding["severity"] for finding in findings}
    if "high" in severities:
        return "needs_investigation"
    if "medium" in severities:
        return "needs_correction"
    return "approve_candidate"


def _finding(
    *,
    code: str,
    severity: str,
    message: str,
    suggestion: str,
    field: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "suggestion": suggestion,
    }
    if field is not None:
        payload["field"] = field
    return payload


def _resolve_policy_values(config: AnalysisConfig) -> tuple[int, float, float]:
    profile = config.policy_profile.strip().lower()
    if profile == "strict":
        return (max(1, int(config.stale_days * 0.8)), max(0.0, config.high_amount_threshold * 0.75), 1.15)
    if profile == "lenient":
        return (max(1, int(config.stale_days * 1.2)), max(0.0, config.high_amount_threshold * 1.25), 0.85)
    return (max(1, config.stale_days), max(0.0, config.high_amount_threshold), 1.0)


def _risk_score(findings: list[dict[str, Any]], *, multiplier: float) -> int:
    severity_weight = {"high": 40, "medium": 20, "low": 8}
    base = sum(severity_weight.get(str(item.get("severity")), 0) for item in findings)
    score = int(round(base * multiplier))
    return max(0, min(100, score))


def _confidence_level(score: int, findings: list[dict[str, Any]]) -> str:
    severities = {item.get("severity") for item in findings}
    if "high" in severities or score >= 60:
        return "low"
    if "medium" in severities or score >= 25:
        return "medium"
    return "high"


def _recommended_action(bucket: str) -> str:
    if bucket == "needs_investigation":
        return "investigate_and_hold"
    if bucket == "needs_correction":
        return "correct_and_revalidate"
    return "approve_when_policy_allows"


def _watermark(items: list[dict[str, Any]]) -> str | None:
    latest: datetime | None = None
    for item in items:
        parsed = _invoice_datetime(item)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest else None


def analyze_invoices(
    items: list[dict[str, Any]],
    *,
    config: AnalysisConfig,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Analyze invoice records and classify reviewer actions."""
    reference_time = as_of or datetime.now(tz=UTC)
    reference_time = reference_time if reference_time.tzinfo is not None else reference_time.replace(tzinfo=UTC)
    window_start = reference_time - timedelta(days=max(1, config.window_days))
    stale_days, high_amount_threshold, risk_multiplier = _resolve_policy_values(config)
    stale_cutoff = reference_time - timedelta(days=stale_days)

    filtered_items: list[dict[str, Any]] = []
    missing_window_date = 0
    excluded_outside_window = 0
    excluded_deleted = 0
    for item in items:
        if _is_deleted_invoice(item):
            excluded_deleted += 1
            continue

        invoice_dt = _invoice_datetime(item)
        if invoice_dt is None:
            filtered_items.append(item)
            missing_window_date += 1
            continue
        if invoice_dt >= window_start:
            filtered_items.append(item)
            continue
        excluded_outside_window += 1

    duplicate_index: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for item in filtered_items:
        vendor_id = str(item.get("vendorId") or "").strip()
        normalized_number = _normalize_invoice_number(item.get("invoiceNumber"))
        invoice_id = str(item.get("id") or "")
        amount = _coerce_float(item.get("invoiceAmount"))
        if vendor_id and normalized_number and invoice_id and amount is not None:
            duplicate_index[(vendor_id, normalized_number)].append((invoice_id, amount))

    duplicate_ids: set[str] = set()
    for entries in duplicate_index.values():
        if len(entries) < 2:
            continue
        for idx, (invoice_id, amount) in enumerate(entries):
            for other_id, other_amount in entries[idx + 1 :]:
                if abs(amount - other_amount) <= config.duplicate_amount_delta:
                    duplicate_ids.add(invoice_id)
                    duplicate_ids.add(other_id)

    vendor_amounts: dict[str, list[float]] = defaultdict(list)
    vendor_day_counts: dict[tuple[str, str], int] = defaultdict(int)
    for item in filtered_items:
        vendor_id = str(item.get("vendorId") or "").strip()
        amount = _coerce_float(item.get("invoiceAmount"))
        if vendor_id and amount is not None:
            vendor_amounts[vendor_id].append(amount)
        invoice_dt = _invoice_datetime(item)
        if vendor_id and invoice_dt is not None:
            vendor_day_counts[(vendor_id, invoice_dt.date().isoformat())] += 1

    analyzed_items: list[dict[str, Any]] = []
    vendor_summary: dict[str, dict[str, Any]] = {}
    bucket_counts: dict[str, int] = {
        "approve_candidate": 0,
        "needs_correction": 0,
        "needs_investigation": 0,
    }

    for item in filtered_items:
        findings: list[dict[str, Any]] = []
        invoice_id = str(item.get("id") or "")
        vendor_id = str(item.get("vendorId") or "").strip()
        vendor_key = vendor_id or "unknown-vendor"
        invoice_number = str(item.get("invoiceNumber") or "").strip()
        amount = _coerce_float(item.get("invoiceAmount"))
        invoice_dt = _invoice_datetime(item)

        if not invoice_id:
            findings.append(
                _finding(
                    code="missing_invoice_id",
                    severity="medium",
                    message="Invoice record is missing an id.",
                    suggestion="Regenerate or re-sync this invoice record before approval.",
                    field="id",
                )
            )
        if not vendor_id:
            findings.append(
                _finding(
                    code="missing_vendor_id",
                    severity="medium",
                    message="Invoice has no vendor id.",
                    suggestion="Assign a valid vendor before approval.",
                    field="vendorId",
                )
            )
        if not invoice_number:
            findings.append(
                _finding(
                    code="missing_invoice_number",
                    severity="medium",
                    message="Invoice number is missing.",
                    suggestion="Enter invoice number and validate source document.",
                    field="invoiceNumber",
                )
            )
        if amount is None:
            findings.append(
                _finding(
                    code="missing_invoice_amount",
                    severity="medium",
                    message="Invoice amount is missing or invalid.",
                    suggestion="Correct invoice amount before review.",
                    field="invoiceAmount",
                )
            )
        elif amount <= 0:
            findings.append(
                _finding(
                    code="non_positive_amount",
                    severity="medium",
                    message="Invoice amount must be greater than zero.",
                    suggestion="Correct invoice amount or route for investigation.",
                    field="invoiceAmount",
                )
            )

        if invoice_dt is None:
            findings.append(
                _finding(
                    code="missing_invoice_date",
                    severity="medium",
                    message="Invoice date is unavailable.",
                    suggestion="Populate invoice date for proper aging review.",
                )
            )
        elif invoice_dt < stale_cutoff:
            findings.append(
                _finding(
                    code="stale_invoice",
                    severity="low",
                    message=f"Invoice has been open more than {stale_days} days.",
                    suggestion="Prioritize reviewer follow-up for stale item.",
                )
            )

        if amount is not None and amount >= high_amount_threshold:
            findings.append(
                _finding(
                    code="high_amount_threshold",
                    severity="high",
                    message=(
                        f"Invoice amount {amount:.2f} exceeds configured threshold "
                        f"{high_amount_threshold:.2f}."
                    ),
                    suggestion="Require second-level review before approval.",
                    field="invoiceAmount",
                )
            )

        if invoice_id and invoice_id in duplicate_ids:
            findings.append(
                _finding(
                    code="possible_duplicate_invoice",
                    severity="high",
                    message="Possible duplicate detected for vendor/invoice number and amount.",
                    suggestion="Compare with matching records and resolve duplicate risk.",
                )
            )

        if vendor_id and amount is not None:
            history = vendor_amounts.get(vendor_id, [])
            if len(history) >= 5:
                average = sum(history) / len(history)
                if average > 0 and amount >= average * 3:
                    findings.append(
                        _finding(
                            code="vendor_amount_anomaly",
                            severity="medium",
                            message="Invoice amount is materially higher than vendor baseline in current run.",
                            suggestion="Validate supporting documents and approval authority.",
                            field="invoiceAmount",
                        )
                    )
            if invoice_dt is not None:
                day_count = vendor_day_counts.get((vendor_id, invoice_dt.date().isoformat()), 0)
                if day_count >= 10:
                    findings.append(
                        _finding(
                            code="vendor_submission_burst",
                            severity="low",
                            message="Vendor submitted an unusually high number of invoices on the same day.",
                            suggestion="Check for batching artifacts or duplicate submission behavior.",
                        )
                    )

        bucket = _bucket_from_findings(findings)
        risk_score = _risk_score(findings, multiplier=risk_multiplier)
        confidence = _confidence_level(risk_score, findings)
        evidence_fields = sorted(
            {
                str(item.get("field"))
                for item in findings
                if isinstance(item, dict) and item.get("field") is not None
            }
        )
        bucket_counts[bucket] += 1

        analyzed_record = {
            "id": invoice_id or None,
            "vendorId": vendor_id or None,
            "invoiceNumber": invoice_number or None,
            "invoiceAmount": amount,
            "invoiceDate": invoice_dt.isoformat() if invoice_dt else None,
            "bucket": bucket,
            "riskScore": risk_score,
            "confidence": confidence,
            "findings": findings,
            "whyFlagged": [item["code"] for item in findings],
            "evidenceFields": evidence_fields,
            "recommendedAction": _recommended_action(bucket),
            "requiredHumanCheck": bucket != "approve_candidate" or risk_score >= 50,
        }
        analyzed_items.append(analyzed_record)

        summary = vendor_summary.setdefault(
            vendor_key,
            {
                "vendorId": vendor_id or None,
                "invoiceCount": 0,
                "totalAmount": 0.0,
                "approveCandidateCount": 0,
                "needsCorrectionCount": 0,
                "needsInvestigationCount": 0,
            },
        )
        summary["invoiceCount"] += 1
        summary["totalAmount"] += amount or 0.0
        if bucket == "approve_candidate":
            summary["approveCandidateCount"] += 1
        elif bucket == "needs_correction":
            summary["needsCorrectionCount"] += 1
        else:
            summary["needsInvestigationCount"] += 1

    attention_candidates = [item for item in analyzed_items if item["bucket"] != "approve_candidate"]
    attention_candidates.sort(
        key=lambda item: (
            int(item.get("riskScore") or 0),
            float(item.get("invoiceAmount") or 0.0),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    top_risks = attention_candidates[: max(1, config.top_n)]

    grouped_vendors = list(vendor_summary.values())
    grouped_vendors.sort(key=lambda vendor: vendor["totalAmount"], reverse=True)

    return {
        "window": {
            "asOf": reference_time.date().isoformat(),
            "windowDays": config.window_days,
            "startDate": window_start.date().isoformat(),
            "endDate": reference_time.date().isoformat(),
        },
        "runHints": {
            "policyProfile": config.policy_profile,
            "watermark": _watermark(filtered_items),
        },
        "riskModel": {
            "scoreRange": "0-100",
            "confidenceLevels": ("high", "medium", "low"),
            "profile": config.policy_profile,
        },
        "totals": {
            "sourceCount": len(items),
            "analyzedCount": len(filtered_items),
            "excludedDeletedCount": excluded_deleted,
            "excludedOutsideWindowCount": excluded_outside_window,
            "missingWindowDateCount": missing_window_date,
            "approveCandidateCount": bucket_counts["approve_candidate"],
            "needsCorrectionCount": bucket_counts["needs_correction"],
            "needsInvestigationCount": bucket_counts["needs_investigation"],
        },
        "vendorGroups": grouped_vendors,
        "topRisks": top_risks,
        "approveCandidates": [item for item in analyzed_items if item["bucket"] == "approve_candidate"],
        "needsCorrection": [item for item in analyzed_items if item["bucket"] == "needs_correction"],
        "needsInvestigation": [item for item in analyzed_items if item["bucket"] == "needs_investigation"],
    }

