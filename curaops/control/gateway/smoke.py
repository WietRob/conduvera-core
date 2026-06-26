"""
Smoke-Test-Modul fuer Gateway-Profile.

Prueft die Erreichbarkeit eines Profils durch einen HTTP GET
auf den /v1/models Endpunkt des konfigurierten Providers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .config import GatewayConfig, ProfileConfig


DEFAULT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class SmokeResult:
    """Ergebnis eines Smoke Tests."""

    profile_name: str
    reachable: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    model_count: Optional[int] = None
    url_tested: Optional[str] = None


def smoke_check_profile(
    profile: ProfileConfig,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SmokeResult:
    """
    Prueft ob ein einzelnes Profil erreichbar ist.

    Sendet HTTP GET an {base_url}/models (oder /v1/models fuer cloud)
    und wertet die Antwort aus.

    Args:
        profile: Das zu pruefende Profil.
        timeout: Timeout in Sekunden.

    Returns:
        SmokeResult mit dem Test-Ergebnis.
    """
    if profile.base_url is None:
        return SmokeResult(
            profile_name=profile.name,
            reachable=False,
            error="Profil hat keine base_url (Cloud-Provider ohne lokalen Endpunkt).",
        )

    # /models Endpunkt: base_url endet bereits auf /v1
    url = f"{profile.base_url.rstrip('/')}/models"

    try:
        req = Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            model_count = None
            if isinstance(data, dict) and "data" in data:
                model_count = len(data["data"])
            return SmokeResult(
                profile_name=profile.name,
                reachable=True,
                status_code=status_code,
                model_count=model_count,
                url_tested=url,
            )
    except HTTPError as exc:
        return SmokeResult(
            profile_name=profile.name,
            reachable=False,
            status_code=exc.code,
            error=f"HTTP {exc.code}: {exc.reason}",
            url_tested=url,
        )
    except URLError as exc:
        return SmokeResult(
            profile_name=profile.name,
            reachable=False,
            error=f"Verbindungsfehler: {exc.reason}",
            url_tested=url,
        )
    except Exception as exc:  # noqa: BLE001
        return SmokeResult(
            profile_name=profile.name,
            reachable=False,
            error=f"Unerwarteter Fehler: {exc}",
            url_tested=url,
        )


def smoke_check_all(
    config: GatewayConfig,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    only_local: bool = True,
) -> Dict[str, SmokeResult]:
    """
    Prueft alle (oder nur lokale) Profile auf Erreichbarkeit.

    Args:
        config: Die Gateway-Konfiguration.
        timeout: Timeout pro Request in Sekunden.
        only_local: Wenn True, werden nur Profile mit base_url getestet.

    Returns:
        Dict von Profilnamen auf SmokeResult.
    """
    results: Dict[str, SmokeResult] = {}
    for name, profile in config.profiles.items():
        if only_local and profile.base_url is None:
            results[name] = SmokeResult(
                profile_name=name,
                reachable=False,
                error="Cloud-Profil uebersprungen (only_local=True).",
            )
            continue
        results[name] = smoke_check_profile(profile, timeout=timeout)
    return results
