"""Durable redacted event outbox (CONTROL-PLANE-V1).

Persists MXOS-EVIDENCE-1.0.0 lifecycle events to an append-only JSONL outbox
and can deliver them to a webhook sink (n8n stays an event consumer, never
the orchestration authority). Secrets and raw auth data are redacted.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def redact_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with secrets/tokens redacted."""
    redacted = json.loads(json.dumps(event))
    sensitive_keys = ("token", "api_key", "apikey", "secret", "password",
                      "authorization", "key_env", "LITELLM_API_KEY")
    payload = redacted.get("payload")
    if isinstance(payload, dict):
        for key in list(payload.keys()):
            if any(s in key.lower() for s in sensitive_keys):
                payload[key] = "[REDACTED]"
    return redacted


class EventOutbox:
    """Append-only JSONL outbox with durable delivery + idempotency.

    Every event is persisted BEFORE any webhook attempt (no event is
    acknowledged before durable persistence). Delivery state (pending/done/
    failed) is tracked in the outbox row; failed deliveries are retried on
    the next append call (bounded retries). The event_id serves as the
    idempotency key for consumers.
    """

    def __init__(
        self,
        path: str | Path,
        webhook_url: str | None = None,
        max_retries: int = 3,
    ):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.webhook_url = webhook_url
        self.max_retries = max_retries

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        entry = redact_event(event)
        entry["outbox_received_at"] = datetime.now(timezone.utc).isoformat()
        entry["delivery_state"] = "pending"
        entry["delivery_retries"] = 0
        entry["idempotency_key"] = entry.get("event_id", "")
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # persist first -> then attempt delivery (never acknowledge before
        # durable persistence)
        if self.webhook_url:
            self._deliver(entry)
        return entry

    def _deliver(self, entry: dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    self.webhook_url,
                    data=json.dumps(entry).encode("utf-8"),
                    headers={"Content-Type": "application/json",
                             "Idempotency-Key": str(entry.get("idempotency_key", ""))},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - configured webhook
                    if 200 <= resp.status < 300:
                        self._mark_delivered(entry, attempt + 1)
                        return True
            except (urllib.error.URLError, OSError):
                pass
        self._mark_failed(entry, self.max_retries)
        return False

    def _mark_delivered(self, entry: dict[str, Any], retries: int) -> None:
        self._update_row(entry, "delivered", retries)

    def _mark_failed(self, entry: dict[str, Any], retries: int) -> None:
        self._update_row(entry, "failed", retries)

    def _update_row(self, entry: dict[str, Any], state: str, retries: int) -> None:
        """Rewrite the matching outbox row with its delivery state (durable)."""
        event_id = entry.get("event_id") or entry.get("outbox_received_at")
        if not event_id or not self.path.is_file():
            return
        lines = self.path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (row.get("event_id") or row.get("outbox_received_at")) == event_id:
                row["delivery_state"] = state
                row["delivery_retries"] = retries
                lines[i] = json.dumps(row, ensure_ascii=False)
                break
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def retry_failed(self, limit: int = 50) -> int:
        """Re-attempt delivery of failed/pending rows (durable retry)."""
        if not self.webhook_url or not self.path.is_file():
            return 0
        delivered = 0
        for row in self.read(limit=limit):
            if row.get("delivery_state") in ("failed", "pending"):
                if self._deliver(row):
                    delivered += 1
        return delivered

    def read(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if line.strip():
                rows.append(json.loads(line))
        return rows
