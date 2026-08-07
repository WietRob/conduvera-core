"""
Client-Authentifizierung fuer den Pi-Harness-native AI Gateway.

Validiert X-Gateway-Client Header gegen die konfigurierten Clients.
Keine Secrets in der Config — nur Client-Namen und Policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass(frozen=True)
class ClientConfig:
    """Repraesentiert einen konfigurierten Gateway-Client."""

    name: str
    default_profile: str
    cloud_allowed: bool = False
    sensitive_classes: List[str] = field(default_factory=list)


class ClientRegistry:
    """
    Registry der autorisierten Gateway-Clients.

    Laedt Client-Definitionen aus gateway-clients.yaml.
    Auth erfolgt ueber den X-Gateway-Client Header (Name-basiert).
    """

    def __init__(self, clients_path: Optional[Path] = None) -> None:
        self._clients: Dict[str, ClientConfig] = {}
        if clients_path is not None:
            self.load(clients_path)

    @property
    def clients(self) -> Dict[str, ClientConfig]:
        return dict(self._clients)

    def load(self, path: Path) -> None:
        """Laedt Clients aus einer YAML-Datei."""
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"YAML {path} enthaelt kein gueltiges Mapping.")

        for name, cfg in data.get("clients", {}).items():
            self._clients[name] = ClientConfig(
                name=name,
                default_profile=cfg.get("default_profile", "local_deep"),
                cloud_allowed=cfg.get("cloud_allowed", False),
                sensitive_classes=cfg.get("sensitive_classes", []),
            )

    def authenticate(self, client_name: str) -> Optional[ClientConfig]:
        """
        Sucht einen Client anhand seines Namens.

        Returns:
            ClientConfig wenn gefunden, sonst None.
        """
        return self._clients.get(client_name)

    def is_known(self, client_name: str) -> bool:
        """Prueft ob ein Client bekannt ist."""
        return client_name in self._clients
