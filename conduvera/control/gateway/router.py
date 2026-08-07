"""
Model-Routing-Modul.

Entscheidet anhand des angeforderten Profils und der Sensitive-Class,
welcher Provider/Model verwendet wird. Erzwingt die Cloud-Fallback-Policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .config import GatewayConfig, ProfileConfig


class PolicyDecision(str, Enum):
    """Moegliche Policy-Entscheidungen beim Routing."""

    ALLOWED = "allowed"
    BLOCKED_CLOUD_FORBIDDEN = "blocked_cloud_forbidden"
    BLOCKED_SENSITIVE_CLASS = "blocked_sensitive_class"
    BLOCKED_NO_FALLBACK = "blocked_no_fallback"
    BLOCKED_PROFILE_NOT_FOUND = "blocked_profile_not_found"
    FALLBACK_TO_CLOUD = "fallback_to_cloud"


@dataclass(frozen=True)
class RouteDecision:
    """Ergebnis einer Routing-Entscheidung."""

    provider: str
    model: str
    base_url: Optional[str]
    profile_name: str
    policy_decision: PolicyDecision
    sensitive_class: Optional[str] = None
    original_profile: Optional[str] = None


class GatewayRouter:
    """
    Zentraler Router fuer AI-Gateway-Anfragen.

    Wendet Policy-Regeln an:
    1. Sensitive-Daten duerfen nicht an Cloud-Provider (cloud_allowed=false).
    2. Cloud-Fallback ist standardmaessig verboten (cloud_fallback=false).
    3. Sensitive-Profile koennen kein Cloud-Fallback nutzen.
    """

    def __init__(self, config: GatewayConfig, cloud_profile_name: str = "cloud_public") -> None:
        self._config = config
        self._cloud_profile_name = cloud_profile_name

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def route(
        self,
        profile_name: str,
        sensitive_class: Optional[str] = None,
    ) -> RouteDecision:
        """
        Bestimmt die Route fuer eine Anfrage.

        Args:
            profile_name: Gewuenschtes Profil.
            sensitive_class: Name der Sensitive-Class der Anfragedaten (optional).

        Returns:
            RouteDecision mit der finalen Routing-Entscheidung.
        """
        profile = self._config.get_profile(profile_name)

        # Profil nicht gefunden
        if profile is None:
            return RouteDecision(
                provider="unknown",
                model="unknown",
                base_url=None,
                profile_name=profile_name,
                policy_decision=PolicyDecision.BLOCKED_PROFILE_NOT_FOUND,
                sensitive_class=sensitive_class,
            )

        # Pruefung: Sensitive-Class verbietet Cloud
        if sensitive_class is not None:
            cloud_allowed = self._config.is_cloud_allowed_for_class(sensitive_class)
            if not cloud_allowed and profile.provider == "openai":
                # Cloud-Provider mit sensitive Daten -> blockiert
                return RouteDecision(
                    provider=profile.provider,
                    model=profile.model,
                    base_url=profile.base_url,
                    profile_name=profile_name,
                    policy_decision=PolicyDecision.BLOCKED_CLOUD_FORBIDDEN,
                    sensitive_class=sensitive_class,
                )

        # Sensitive-Daten allgemein: niemals Cloud-Fallback
        if sensitive_class is not None:
            sc = self._config.get_sensitive_class(sensitive_class)
            if sc is not None and not sc.cloud_allowed:
                # Sensible Klasse -> direkt lokales Profil, kein Fallback
                return self._build_local_decision(profile, sensitive_class)

        # Normaler Routing: Profil ist erreichbar
        if profile.base_url is not None or profile.provider != "openai_compatible":
            return RouteDecision(
                provider=profile.provider,
                model=profile.model,
                base_url=profile.base_url,
                profile_name=profile_name,
                policy_decision=PolicyDecision.ALLOWED,
                sensitive_class=sensitive_class,
            )

        # Lokaler Provider ohne base_url -> Cloud-Fallback pruefen
        if profile.cloud_fallback:
            cloud_profile = self._config.get_profile(self._cloud_profile_name)
            if cloud_profile is not None:
                return RouteDecision(
                    provider=cloud_profile.provider,
                    model=cloud_profile.model,
                    base_url=cloud_profile.base_url,
                    profile_name=self._cloud_profile_name,
                    policy_decision=PolicyDecision.FALLBACK_TO_CLOUD,
                    sensitive_class=sensitive_class,
                    original_profile=profile_name,
                )

        # Kein Fallback moeglich
        return RouteDecision(
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            profile_name=profile_name,
            policy_decision=PolicyDecision.BLOCKED_NO_FALLBACK,
            sensitive_class=sensitive_class,
        )

    @staticmethod
    def _build_local_decision(profile: ProfileConfig, sensitive_class: str) -> RouteDecision:
        """Erstellt eine ALLOWED-Entscheidung fuer lokale Profile mit Sensitive-Daten."""
        return RouteDecision(
            provider=profile.provider,
            model=profile.model,
            base_url=profile.base_url,
            profile_name=profile.name,
            policy_decision=PolicyDecision.ALLOWED,
            sensitive_class=sensitive_class,
        )
