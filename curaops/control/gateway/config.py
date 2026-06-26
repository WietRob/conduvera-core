"""
Gateway-Konfigurationslademodul.

Laedt Profile und Sensitive Classes aus YAML-Dateien und stellt
typisierte Dataclass-Objekte zur Verfuegung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_PROFILES_PATH = Path(__file__).resolve().parents[3] / "config" / "gateway-profiles.yaml"
DEFAULT_SENSITIVE_PATH = Path(__file__).resolve().parents[3] / "config" / "sensitive-classes.yaml"


@dataclass(frozen=True)
class ProfileConfig:
    """Repraesentiert ein einzelnes Gateway-Profil."""

    name: str
    provider: str
    model: str
    base_url: Optional[str] = None
    cloud_fallback: bool = False
    max_daily_cost_eur: Optional[float] = None
    sensitive: bool = False

    def __post_init__(self) -> None:
        # cloud_fallback ist standardmaessig verboten – explizite Sicherheit
        if self.cloud_fallback and self.sensitive:
            raise ValueError(
                f"Profil '{self.name}': sensitive=True und cloud_fallback=True sind unzulaessig."
            )


@dataclass(frozen=True)
class SensitiveClass:
    """Repraesentiert eine Sensitive-Daten-Klasse."""

    name: str
    cloud_allowed: bool = False


@dataclass
class GatewayConfig:
    """Gesamte Gateway-Konfiguration (Profile + Sensitive Classes)."""

    profiles: Dict[str, ProfileConfig] = field(default_factory=dict)
    sensitive_classes: Dict[str, SensitiveClass] = field(default_factory=dict)

    def get_profile(self, name: str) -> Optional[ProfileConfig]:
        return self.profiles.get(name)

    def get_sensitive_class(self, name: str) -> Optional[SensitiveClass]:
        return self.sensitive_classes.get(name)

    def is_cloud_allowed_for_class(self, sensitive_class: str) -> bool:
        sc = self.sensitive_classes.get(sensitive_class)
        if sc is None:
            # Unbekannte Klasse: sicherheitshalber cloud verboten
            return False
        return sc.cloud_allowed


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Laedt eine YAML-Datei und gibt das top-level Dict zurueck."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"YAML-Datei {path} enthaelt kein gueltiges Mapping.")
    return data


def load_gateway_config(
    profiles_path: Optional[Path] = None,
    sensitive_path: Optional[Path] = None,
) -> GatewayConfig:
    """
    Laedt die Gateway-Konfiguration aus den YAML-Dateien.

    Args:
        profiles_path: Pfad zu gateway-profiles.yaml (Default: projekteigener Standard).
        sensitive_path: Pfad zu sensitive-classes.yaml (Default: projekteigener Standard).

    Returns:
        GatewayConfig mit allen Profilen und Sensitive Classes.
    """
    profiles_path = profiles_path or DEFAULT_PROFILES_PATH
    sensitive_path = sensitive_path or DEFAULT_SENSITIVE_PATH

    raw_profiles = _load_yaml(profiles_path)
    raw_sensitive = _load_yaml(sensitive_path)

    profiles: Dict[str, ProfileConfig] = {}
    for name, cfg in raw_profiles.get("profiles", {}).items():
        profiles[name] = ProfileConfig(
            name=name,
            provider=cfg["provider"],
            model=cfg["model"],
            base_url=cfg.get("base_url"),
            cloud_fallback=cfg.get("cloud_fallback", False),
            max_daily_cost_eur=cfg.get("max_daily_cost_eur"),
            sensitive=cfg.get("sensitive", False),
        )

    sensitive_classes: Dict[str, SensitiveClass] = {}
    for name, cfg in raw_sensitive.get("sensitive_classes", {}).items():
        sensitive_classes[name] = SensitiveClass(
            name=name,
            cloud_allowed=cfg.get("cloud_allowed", False),
        )

    return GatewayConfig(
        profiles=profiles,
        sensitive_classes=sensitive_classes,
    )
