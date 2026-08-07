"""
CuraOps-Control AI Gateway Control Plane.

Pi-Harness-native Policy Proxy fuer lokale AI-Backends.
Kein LiteLLM. Keine Cloud-Fallbacks im MVP.
"""

from .config import GatewayConfig, ProfileConfig, SensitiveClass, load_gateway_config
from .router import RouteDecision, GatewayRouter, PolicyDecision
from .audit import AuditEntry, AuditLogger
from .smoke import SmokeResult, smoke_check_profile, smoke_check_all
from .auth import ClientConfig, ClientRegistry
from .backends import BackendProxy
from .app import create_app

__all__ = [
    # Config
    "GatewayConfig",
    "ProfileConfig",
    "SensitiveClass",
    "load_gateway_config",
    # Router
    "RouteDecision",
    "GatewayRouter",
    "PolicyDecision",
    # Audit
    "AuditEntry",
    "AuditLogger",
    # Smoke
    "SmokeResult",
    "smoke_check_profile",
    "smoke_check_all",
    # Auth
    "ClientConfig",
    "ClientRegistry",
    # Backend Proxy
    "BackendProxy",
    # FastAPI App
    "create_app",
]
