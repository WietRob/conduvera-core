"""
Gateway-Tests fuer den Pi-Harness-native AI Gateway Service.

Testet: app.py, auth.py, backends.py, router.py, config.py, audit.py
Endpunkte: /health, /v1/models, /v1/chat/completions
Themen: Policy-Durchsetzung, Auth, Backend-Proxy, Audit

Alle Tests und Docstrings auf Deutsch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from curaops.control.gateway.app import create_app
from curaops.control.gateway.auth import ClientConfig, ClientRegistry
from curaops.control.gateway.backends import BackendProxy
from curaops.control.gateway.config import (
    GatewayConfig,
    ProfileConfig,
    SensitiveClass,
)
from curaops.control.gateway.router import GatewayRouter, PolicyDecision
from curaops.control.gateway.audit import AuditEntry, AuditLogger


# ---------------------------------------------------------------------------
# Hilfs-Fixtures
# ---------------------------------------------------------------------------


def _make_profiles() -> Dict[str, ProfileConfig]:
    """Erzeugt Test-Profile."""
    return {
        "local_deep": ProfileConfig(
            name="local_deep",
            provider="openai_compatible",
            model="glm-deep",
            base_url="http://localhost:8001/v1",
            cloud_fallback=False,
        ),
        "local_light": ProfileConfig(
            name="local_light",
            provider="openai_compatible",
            model="qwen-light",
            base_url="http://localhost:8002/v1",
            cloud_fallback=False,
        ),
        "local_only_sensitive": ProfileConfig(
            name="local_only_sensitive",
            provider="openai_compatible",
            model="glm-deep",
            base_url="http://localhost:8001/v1",
            sensitive=True,
        ),
        "cloud_public": ProfileConfig(
            name="cloud_public",
            provider="openai",
            model="gpt-5.5",
            cloud_fallback=False,
        ),
    }


def _make_sensitive_classes() -> Dict[str, SensitiveClass]:
    """Erzeugt Test-Sensitive-Classes."""
    return {
        "curaops": SensitiveClass(name="curaops", cloud_allowed=False),
        "private_repo": SensitiveClass(name="private_repo", cloud_allowed=False),
        "patient_data": SensitiveClass(name="patient_data", cloud_allowed=False),
        "public_docs": SensitiveClass(name="public_docs", cloud_allowed=True),
    }


def _make_config() -> GatewayConfig:
    """Erzeugt eine Standard-Test-GatewayConfig."""
    return GatewayConfig(
        profiles=_make_profiles(),
        sensitive_classes=_make_sensitive_classes(),
    )


def _make_client_registry() -> ClientRegistry:
    """Erzeugt eine Test-ClientRegistry."""
    registry = ClientRegistry()
    registry._clients = {
        "test-client": ClientConfig(
            name="test-client",
            default_profile="local_deep",
            cloud_allowed=False,
            sensitive_classes=["curaops", "private_repo"],
        ),
        "admin-client": ClientConfig(
            name="admin-client",
            default_profile="local_deep",
            cloud_allowed=True,
            sensitive_classes=[],
        ),
        "research-client": ClientConfig(
            name="research-client",
            default_profile="local_light",
            cloud_allowed=True,
            sensitive_classes=["public_docs"],
        ),
    }
    return registry


@pytest.fixture()
def config() -> GatewayConfig:
    return _make_config()


@pytest.fixture()
def client_registry() -> ClientRegistry:
    return _make_client_registry()


@pytest.fixture()
def audit_logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(log_path=tmp_path / "audit.jsonl")


@pytest.fixture()
def app_client(
    config: GatewayConfig,
    client_registry: ClientRegistry,
    audit_logger: AuditLogger,
) -> TestClient:
    """FastAPI TestClient mit allen Test-Dependencies."""
    app = create_app(
        config=config,
        client_registry=client_registry,
        audit_logger=audit_logger,
    )
    return TestClient(app)


# ===================================================================
# 1) Health-Endpunkt
# ===================================================================


class TestHealthEndpoint:
    """Tests fuer GET /health."""

    def test_health_gibt_status_healthy(self, app_client: TestClient) -> None:
        """Der Health-Endpunkt muss status=healthy zurueckgeben."""
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_health_ohne_auth_erreichbar(self, app_client: TestClient) -> None:
        """Der Health-Endpunkt muss ohne Client-Header aufrufbar sein."""
        resp = app_client.get("/health")
        assert resp.status_code == 200

    def test_health_zeigt_profile_anzahl(
        self, app_client: TestClient
    ) -> None:
        """Health muss die Anzahl geladener Profile zeigen."""
        resp = app_client.get("/health")
        data = resp.json()
        assert data["profiles_loaded"] >= 1

    def test_health_zeigt_client_anzahl(
        self, app_client: TestClient
    ) -> None:
        """Health muss die Anzahl registrierter Clients zeigen."""
        resp = app_client.get("/health")
        data = resp.json()
        assert data["clients_loaded"] >= 1


# ===================================================================
# 2) Authentifizierung (auth.py)
# ===================================================================


class TestAuth:
    """Tests fuer die Client-Authentifizierung."""

    def test_bekannter_client_wird_akzeptiert(
        self, client_registry: ClientRegistry
    ) -> None:
        """Ein bekannter Client muss authentifiziert werden."""
        result = client_registry.authenticate("test-client")
        assert result is not None
        assert result.name == "test-client"

    def test_unbekannter_client_wird_abgelehnt(
        self, client_registry: ClientRegistry
    ) -> None:
        """Ein unbekannter Client muss None liefern."""
        result = client_registry.authenticate("unknown-client")
        assert result is None

    def test_is_known(self, client_registry: ClientRegistry) -> None:
        """is_known muss korrekt pruefen."""
        assert client_registry.is_known("test-client") is True
        assert client_registry.is_known("nonexistent") is False

    def test_client_default_profile(
        self, client_registry: ClientRegistry
    ) -> None:
        """Client muss sein Default-Profil zurueckgeben."""
        client = client_registry.authenticate("test-client")
        assert client.default_profile == "local_deep"

    def test_client_cloud_allowed(
        self, client_registry: ClientRegistry
    ) -> None:
        """Cloud-Flag muss korrekt gesetzt sein."""
        test_c = client_registry.authenticate("test-client")
        assert test_c.cloud_allowed is False
        admin_c = client_registry.authenticate("admin-client")
        assert admin_c.cloud_allowed is True


class TestClientRegistryYaml:
    """Tests fuer ClientRegistry YAML-Laden."""

    def test_laden_aus_yaml(self, tmp_path: Path) -> None:
        """Clients muessen aus YAML geladen werden."""
        yaml_file = tmp_path / "clients.yaml"
        yaml_file.write_text(
            "clients:\n"
            "  my-client:\n"
            "    default_profile: local_deep\n"
            "    cloud_allowed: false\n"
            "    sensitive_classes:\n"
            "      - curaops\n"
        )
        registry = ClientRegistry(clients_path=yaml_file)
        client = registry.authenticate("my-client")
        assert client is not None
        assert client.default_profile == "local_deep"
        assert client.cloud_allowed is False
        assert "curaops" in client.sensitive_classes


# ===================================================================
# 3) Models-Endpunkt
# ===================================================================


class TestModelsEndpoint:
    """Tests fuer GET /v1/models."""

    def test_models_ohne_client_wird_401(
        self, app_client: TestClient
    ) -> None:
        """Ohne X-Gateway-Client muss 401 zurueckgegeben werden."""
        resp = app_client.get("/v1/models")
        assert resp.status_code == 401

    def test_models_unbekannter_client_wird_403(
        self, app_client: TestClient
    ) -> None:
        """Ein unbekannter Client muss 403 erhalten."""
        resp = app_client.get(
            "/v1/models", headers={"X-Gateway-Client": "bad-client"}
        )
        assert resp.status_code == 403

    @patch.object(BackendProxy, "fetch_models", new_callable=AsyncMock)
    def test_models_mit_gueltigem_client(
        self, mock_fetch: AsyncMock, app_client: TestClient
    ) -> None:
        """Ein autorisierter Client sieht die Modellliste."""
        mock_fetch.return_value = {
            "object": "list",
            "data": [
                {"id": "glm-deep", "object": "model", "owned_by": "vllm"},
            ],
        }
        resp = app_client.get(
            "/v1/models", headers={"X-Gateway-Client": "test-client"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1


# ===================================================================
# 4) Chat-Completions (normal)
# ===================================================================


class TestChatCompletions:
    """Tests fuer POST /v1/chat/completions."""

    def test_chat_ohne_auth_wird_401(
        self, app_client: TestClient
    ) -> None:
        """Ohne Client-Header muss 401 geliefert werden."""
        resp = app_client.post(
            "/v1/chat/completions",
            json={
                "model": "glm-deep",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 401

    def test_chat_unbekannter_client_wird_403(
        self, app_client: TestClient
    ) -> None:
        """Unbekannter Client muss 403 sein."""
        resp = app_client.post(
            "/v1/chat/completions",
            headers={"X-Gateway-Client": "stranger"},
            json={
                "model": "glm-deep",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 403

    @patch.object(BackendProxy, "proxy_chat", new_callable=AsyncMock)
    def test_chat_erfolgreich_mit_mock(
        self, mock_proxy: AsyncMock, app_client: TestClient
    ) -> None:
        """Eine normale Chat-Anfrage wird ans Backend weitergeleitet."""
        mock_proxy.return_value = {
            "id": "chatcmpl-123",
            "choices": [
                {"message": {"content": "Hallo!", "role": "assistant"}}
            ],
        }
        resp = app_client.post(
            "/v1/chat/completions",
            headers={"X-Gateway-Client": "test-client"},
            json={
                "model": "glm-deep",
                "messages": [{"role": "user", "content": "Hallo"}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "chatcmpl-123"
        assert body["choices"][0]["message"]["content"] == "Hallo!"

    def test_chat_sensitive_class_blocked(
        self, app_client: TestClient
    ) -> None:
        """Sensitive-Class curaops darf nicht an Cloud."""
        # cloud_public hat base_url=None, also wird es blockiert
        resp = app_client.post(
            "/v1/chat/completions",
            headers={"X-Gateway-Client": "test-client"},
            json={
                "model": "gpt-5.5",
                "messages": [{"role": "user", "content": "hi"}],
                "gateway_profile": "cloud_public",
                "sensitive_class": "curaops",
            },
        )
        # curaops hat cloud_allowed=False, cloud_public hat provider=openai
        assert resp.status_code == 403


# ===================================================================
# 5) Policy-Durchsetzung (Router)
# ===================================================================


class TestPolicyDurchsetzung:
    """Tests fuer die Policy-Entscheidungen des GatewayRouter."""

    def test_lokales_profil_erlaubt(self, config: GatewayConfig) -> None:
        """Lokales Profil muss erlaubt sein."""
        router = GatewayRouter(config)
        decision = router.route("local_deep")
        assert decision.policy_decision == PolicyDecision.ALLOWED

    def test_unbekanntes_profil_blockiert(
        self, config: GatewayConfig
    ) -> None:
        """Unbekanntes Profil muss blockiert sein."""
        router = GatewayRouter(config)
        decision = router.route("nonexistent")
        assert decision.policy_decision == PolicyDecision.BLOCKED_PROFILE_NOT_FOUND

    def test_sensitive_class_blockiert_cloud(
        self, config: GatewayConfig
    ) -> None:
        """Sensitive-Class curaops muss Cloud blockieren."""
        router = GatewayRouter(config)
        decision = router.route("cloud_public", sensitive_class="curaops")
        assert decision.policy_decision == PolicyDecision.BLOCKED_CLOUD_FORBIDDEN

    def test_sensitive_class_erlaubt_lokal(
        self, config: GatewayConfig
    ) -> None:
        """Sensitive-Class mit lokalem Profil muss erlaubt sein."""
        router = GatewayRouter(config)
        decision = router.route("local_deep", sensitive_class="curaops")
        assert decision.policy_decision == PolicyDecision.ALLOWED

    def test_cloud_public_erlaubt_ohne_sensitive(
        self, config: GatewayConfig
    ) -> None:
        """Cloud-Profil ohne Sensitive-Class muss erlaubt sein."""
        router = GatewayRouter(config)
        decision = router.route("cloud_public")
        assert decision.policy_decision == PolicyDecision.ALLOWED

    def test_public_docs_cloud_erlaubt(
        self, config: GatewayConfig
    ) -> None:
        """public_docs hat cloud_allowed=True — darf an Cloud."""
        router = GatewayRouter(config)
        decision = router.route("cloud_public", sensitive_class="public_docs")
        assert decision.policy_decision == PolicyDecision.ALLOWED


# ===================================================================
# 6) Audit-Logging
# ===================================================================


class TestAuditLog:
    """Tests fuer AuditLogger."""

    def test_audit_log_schreibt_eintrag(self, tmp_path: Path) -> None:
        """AuditLogger muss einen Eintrag in JSONL schreiben."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_path)
        entry = AuditEntry(
            client="test-client",
            profile="local_deep",
            provider="openai_compatible",
            model="glm-deep",
            policy_decision="allowed",
        )
        logger.log(entry)
        assert log_path.exists()
        entries = logger.read_entries()
        assert len(entries) == 1
        assert entries[0]["client"] == "test-client"
        assert entries[0]["policy_decision"] == "allowed"

    def test_audit_log_timestamp_automatisch(
        self, tmp_path: Path
    ) -> None:
        """AuditEntry muss automatisch einen Timestamp bekommen."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_path)
        entry = AuditEntry(
            client="test",
            profile="local_deep",
            provider="openai_compatible",
            model="glm-deep",
            policy_decision="allowed",
        )
        assert entry.timestamp != ""
        assert "T" in entry.timestamp  # ISO-8601

    def test_audit_log_clear(self, tmp_path: Path) -> None:
        """clear() muss die Log-Datei loeschen."""
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_path)
        entry = AuditEntry(
            client="test",
            profile="p",
            provider="x",
            model="m",
            policy_decision="allowed",
        )
        logger.log(entry)
        assert log_path.exists()
        logger.clear()
        assert not log_path.exists()


# ===================================================================
# 7) Config-Validierung
# ===================================================================


class TestConfigValidation:
    """Tests fuer GatewayConfig und ProfileConfig."""

    def test_sensitive_plus_cloud_fallback_verboten(self) -> None:
        """sensitive=True und cloud_fallback=True muessen ValueError werfen."""
        with pytest.raises(ValueError, match="sensitive"):
            ProfileConfig(
                name="bad",
                provider="openai_compatible",
                model="x",
                cloud_fallback=True,
                sensitive=True,
            )

    def test_lokales_profil_ist_erlaubt(self) -> None:
        """Lokales Profil ohne Cloud-Fallback muss funktionieren."""
        p = ProfileConfig(
            name="ok",
            provider="openai_compatible",
            model="x",
            base_url="http://localhost:8001/v1",
        )
        assert p.cloud_fallback is False
        assert p.sensitive is False

    def test_is_cloud_allowed_for_class(
        self, config: GatewayConfig
    ) -> None:
        """is_cloud_allowed_for_class muss korrekt pruefen."""
        assert config.is_cloud_allowed_for_class("curaops") is False
        assert config.is_cloud_allowed_for_class("public_docs") is True
        assert config.is_cloud_allowed_for_class("unknown") is False
