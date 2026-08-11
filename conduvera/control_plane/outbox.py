"""Durable redacted event outbox (CONTROL-PLANE-V1).

Persists MXOS-EVIDENCE-1.0.0 lifecycle events to an append-only JSONL outbox
and can deliver them to a webhook sink (n8n stays an event consumer, never
the orchestration authority). Secrets and raw auth data are redacted.
"""

from __future__ import annotations

import json
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
    """Append-only JSONL outbox with optional webhook delivery."""

    def __init__(self, path: str | Path, webhook_url: str | None = None):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.webhook_url = webhook_url

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        entry = redact_event(event)
        entry["outbox_received_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if self.webhook_url:
            self._deliver(entry)
        return entry

    def _deliver(self, entry: dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(entry).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - configured webhook
                return 200 <= resp.status < 300
        except (urllib.error.URLError, OSError):
            return False

    def read(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if line.strip():
                rows.append(json.loads(line))
        return rows
