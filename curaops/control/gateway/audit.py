"""
Audit-Logging-Modul fuer das AI Gateway.

Schreibt Audit-Eintraege als JSONL (JSON Lines) fuer jeden
Routing-Entscheidungsprozess. Append-Only fuer Nachvollziehbarkeit.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parents[3] / "logs" / "gateway_audit.jsonl"


@dataclass(frozen=True)
class AuditEntry:
    """
    Ein einzelner Audit-Log-Eintrag.

    Felder:
        client: Identifikation des aufrufenden Clients.
        profile: Verwendetes Gateway-Profil.
        provider: Ziel-Provider (z.B. openai, openai_compatible).
        model: Verwendetes Modell.
        policy_decision: Ergebnis der Policy-Pruefung.
        timestamp: ISO-8601 UTC Zeitstempel.
        sensitive_class: Optional: Name der Sensitive-Class.
        original_profile: Optional: Urspruengliches Profil bei Fallback.
        extra: Optional: Zusaetzliche Metadaten.
    """

    client: str
    profile: str
    provider: str
    model: str
    policy_decision: str
    timestamp: str = ""
    sensitive_class: Optional[str] = None
    original_profile: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            # frozen=True workaround: nur wenn leer setzen
            object.__setattr__(
                self,
                "timestamp",
                datetime.now(timezone.utc).isoformat(),
            )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert den Eintrag in ein Dict (ohne None-Werte)."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    def to_json(self) -> str:
        """Serialisiert den Eintrag als JSON-Zeile."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AuditLogger:
    """
    Append-Only JSONL Audit-Logger.

    Schreibt jeden AuditEntry als eine Zeile in die Log-Datei.
    Thread-safe durch append-Modus.
    """

    def __init__(self, log_path: Optional[Path] = None) -> None:
        self._log_path = log_path or DEFAULT_AUDIT_LOG_PATH

    @property
    def log_path(self) -> Path:
        return self._log_path

    def log(self, entry: AuditEntry) -> Path:
        """
        Schreibt einen AuditEntry in die JSONL-Datei.

        Erstellt das Elternverzeichnis automatisch falls noetig.

        Args:
            entry: Der zu protokollierende AuditEntry.

        Returns:
            Pfad zur Log-Datei.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")
        return self._log_path

    def read_entries(self) -> list[Dict[str, Any]]:
        """
        Liest alle vorhandenen Audit-Eintraege.

        Returns:
            Liste von Dicts, einen pro Zeile.
        """
        if not self._log_path.exists():
            return []
        entries: list[Dict[str, Any]] = []
        with open(self._log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def clear(self) -> None:
        """Loescht die Audit-Log-Datei."""
        if self._log_path.exists():
            self._log_path.unlink()
