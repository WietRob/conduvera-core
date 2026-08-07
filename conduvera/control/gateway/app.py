"""
Pi-Harness-native AI Gateway Service.

Minimaler FastAPI-Service der als Policy-Proxy vor lokalen
OpenAI-compatible Backends (vLLM) sitzt.

MVP-Endpunkte:
    GET  /health
    GET  /v1/models
    POST /v1/chat/completions

Kein LiteLLM. Keine Cloud-Fallbacks im MVP.
Cloud nur explizit policy-gated.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .auth import ClientConfig, ClientRegistry
from .backends import BackendProxy
from .config import GatewayConfig, load_gateway_config
from .router import GatewayRouter, PolicyDecision
from .audit import AuditEntry, AuditLogger


def create_app(
    config: Optional[GatewayConfig] = None,
    client_registry: Optional[ClientRegistry] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> FastAPI:
    """
    Factory fuer die Gateway FastAPI-App.

    Args:
        config: Gateway-Konfiguration (Profile + Sensitive Classes).
        client_registry: Registry der autorisierten Clients.
        audit_logger: Audit-Logger fuer Routing-Entscheidungen.

    Returns:
        Konfigurierte FastAPI-Instanz.
    """
    app = FastAPI(
        title="CuraOps AI Gateway",
        description="Pi-Harness-native Policy Proxy fuer lokale AI-Backends",
        version="0.1.0",
    )

    # Dependencies injizieren oder Defaults laden
    app.state.config = config
    app.state.client_registry = client_registry or ClientRegistry()
    app.state.audit_logger = audit_logger or AuditLogger()
    app.state.router = GatewayRouter(config) if config else None
    app.state.backend_proxy = BackendProxy()
    app.state.start_time = time.time()

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        """Gateway-Gesundheitscheck."""
        uptime = time.time() - app.state.start_time
        profiles_loaded = len(app.state.config.profiles) if app.state.config else 0
        clients_loaded = len(app.state.client_registry.clients)
        return {
            "status": "healthy",
            "uptime_seconds": round(uptime, 1),
            "profiles_loaded": profiles_loaded,
            "clients_loaded": clients_loaded,
        }

    @app.get("/v1/models")
    async def list_models(
        x_gateway_client: Optional[str] = Header(None),
    ) -> JSONResponse:
        """
        Listet verfuegbare Modelle.

        Nutzt den Client-Namen um das Default-Profil zu bestimmen
        und ruft /v1/models vom entsprechenden Backend ab.
        """
        if not x_gateway_client:
            raise HTTPException(status_code=401, detail="X-Gateway-Client Header fehlt")

        client = app.state.client_registry.authenticate(x_gateway_client)
        if client is None:
            raise HTTPException(status_code=403, detail=f"Unbekannter Client: {x_gateway_client}")

        config = app.state.config
        if config is None:
            raise HTTPException(status_code=503, detail="Gateway nicht konfiguriert")

        profile = config.get_profile(client.default_profile)
        if profile is None:
            raise HTTPException(
                status_code=503,
                detail=f"Profil '{client.default_profile}' nicht gefunden",
            )

        if profile.base_url is None:
            # Cloud-Profil ohne lokalen Endpunkt — Model-Liste aus Config
            return JSONResponse(content={
                "object": "list",
                "data": [{"id": profile.model, "object": "model", "owned_by": profile.provider}],
            })

        try:
            proxy: BackendProxy = app.state.backend_proxy
            result = await proxy.fetch_models(profile.base_url)
            return JSONResponse(content=result)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Backend-Fehler: {exc}") from exc

    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(
        request: Request,
        x_gateway_client: Optional[str] = Header(None),
    ) -> JSONResponse | StreamingResponse:
        """
        Proxyt Chat-Completion-Requests an das Backend.

        Policy-Enforcement:
        1. Client authentifizieren
        2. Profil bestimmen (Client-Default oder Request-Parameter)
        3. Sensitive-Class pruefen
        4. Routing-Entscheidung durchfuehren
        5. Audit-Log schreiben
        6. Request an Backend weiterleiten
        """
        if not x_gateway_client:
            raise HTTPException(status_code=401, detail="X-Gateway-Client Header fehlt")

        client = app.state.client_registry.authenticate(x_gateway_client)
        if client is None:
            raise HTTPException(status_code=403, detail=f"Unbekannter Client: {x_gateway_client}")

        config = app.state.config
        router: Optional[GatewayRouter] = app.state.router
        if config is None or router is None:
            raise HTTPException(status_code=503, detail="Gateway nicht konfiguriert")

        # Request-Body lesen
        body = await request.json()

        # Profil und Sensitive-Class aus Request oder Client-Default
        profile_name = body.pop("gateway_profile", client.default_profile)
        sensitive_class = body.pop("sensitive_class", None)
        stream = body.get("stream", False)

        # Routing-Entscheidung
        decision = router.route(profile_name, sensitive_class)

        # Audit-Log schreiben
        audit_entry = AuditEntry(
            client=x_gateway_client,
            profile=profile_name,
            provider=decision.provider,
            model=decision.model,
            policy_decision=decision.policy_decision.value,
            sensitive_class=sensitive_class,
            original_profile=decision.original_profile,
        )
        app.state.audit_logger.log(audit_entry)

        # Policy-Durchsetzung
        if decision.policy_decision == PolicyDecision.BLOCKED_CLOUD_FORBIDDEN:
            raise HTTPException(
                status_code=403,
                detail=f"Cloud-Zugriff fuer sensitive Klasse '{sensitive_class}' verboten",
            )
        if decision.policy_decision == PolicyDecision.BLOCKED_SENSITIVE_CLASS:
            raise HTTPException(
                status_code=403,
                detail=f"Sensible Daten duerfen nicht an Cloud gesendet werden",
            )
        if decision.policy_decision == PolicyDecision.BLOCKED_PROFILE_NOT_FOUND:
            raise HTTPException(
                status_code=404,
                detail=f"Profil '{profile_name}' nicht gefunden",
            )
        if decision.policy_decision == PolicyDecision.BLOCKED_NO_FALLBACK:
            raise HTTPException(
                status_code=503,
                detail=f"Backend nicht erreichbar, kein Fallback konfiguriert",
            )

        # Backend hat keine base_url (Cloud ohne lokalen Endpunkt)
        if decision.base_url is None:
            raise HTTPException(
                status_code=503,
                detail=f"Profil '{decision.profile_name}' hat keinen lokalen Endpunkt",
            )

        # Request an Backend weiterleiten
        proxy: BackendProxy = app.state.backend_proxy
        messages = body.get("messages", [])

        # Modell im Body auf das geroutete Modell setzen
        body["model"] = decision.model

        try:
            if stream:
                chunks = await proxy.proxy_chat(
                    base_url=decision.base_url,
                    model=decision.model,
                    messages=messages,
                    stream=True,
                    **{k: v for k, v in body.items() if k not in ("messages", "model", "stream")},
                )
                return StreamingResponse(
                    chunks,
                    media_type="text/event-stream",
                    headers={"X-Accel-Buffering": "no"},
                )
            else:
                result = await proxy.proxy_chat(
                    base_url=decision.base_url,
                    model=decision.model,
                    messages=messages,
                    stream=False,
                    **{k: v for k, v in body.items() if k not in ("messages", "model", "stream")},
                )
                return JSONResponse(content=result)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Backend-Fehler: {exc}") from exc

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(app_instance: FastAPI):
        yield
        proxy: BackendProxy = app_instance.state.backend_proxy
        await proxy.close()

    # shutdown via lifespan ersetzt on_event("shutdown")
    app.router.lifespan_context = _lifespan  # type: ignore[attr-defined]

    return app
