"""In-memory storage for invoice analysis runs and reviewer decisions."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def encode_offset_cursor(offset: int) -> str:
    payload = {"offset": max(0, offset)}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def decode_offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
        offset = int(payload.get("offset", 0))
        return max(0, offset)
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0


@dataclass
class AnalysisRunStore:
    """Thread-safe ephemeral run store for queueing and audit workflows."""

    ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def _prune_expired(self) -> None:
        cutoff = _utcnow() - timedelta(seconds=max(60, self.ttl_seconds))
        to_delete = [run_id for run_id, run in self._runs.items() if run.get("createdAtDt", cutoff) < cutoff]
        for run_id in to_delete:
            self._runs.pop(run_id, None)

    def create_run(self, *, analysis: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        run_id = str(uuid4())
        created_at = _utcnow()
        run_payload = {
            "runId": run_id,
            "createdAt": created_at.isoformat(),
            "createdAtDt": created_at,
            "analysis": analysis,
            "metadata": metadata,
            "decisions": [],
        }
        with self._lock:
            self._prune_expired()
            self._runs[run_id] = run_payload
        return {"runId": run_id, "createdAt": run_payload["createdAt"]}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._prune_expired()
            run = self._runs.get(run_id)
            if run is None:
                return None
            return dict(run)

    def save_decision(
        self,
        *,
        run_id: str,
        invoice_id: str,
        decision: str,
        rationale: str | None,
        actor: str | None,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._prune_expired()
            run = self._runs.get(run_id)
            if run is None:
                return None
            record = {
                "invoiceId": invoice_id,
                "decision": decision,
                "rationale": rationale,
                "actor": actor,
                "recordedAt": _utcnow().isoformat(),
            }
            run["decisions"].append(record)
            return dict(record)

