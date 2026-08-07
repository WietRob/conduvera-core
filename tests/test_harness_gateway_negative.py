"""Harness gateway / registry negative tests (goal make-the-harness-gateway-
canonical-in-conduvera-core, DOD-07).

Covers fail-closed behaviour for:
- unknown adapter (no registry entry)
- disabled adapter
- missing module
- incompatible contract (protocol mismatch)
- invalid execution mode
- missing registry (resolution fails closed)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conduvera.harness.registry import (
    HarnessAdapterRegistry,
    HarnessCapabilityUnavailableError,
    ExecutionMode,
)
from conduvera.harness.gateway import HarnessGatewayService

# A minimal valid registry for positive control cases.
VALID_REGISTRY = """\
adapters:
  hermes:
    enabled: true
    module: conduvera.harness.hermes_adapter
    entry_point: HermesAdapter
    version: hermes-adapter.v1
    contract: CONDUVERA-GOAL-1.0
  opencode_cli:
    enabled: false
    status: disabled_by_owner
  codex_cli:
    enabled: false
    status: disabled_by_owner
"""


def _write_registry(tmp_path, content: str) -> Path:
    p = tmp_path / "harness-registry.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def _service(tmp_path, registry_content: str = VALID_REGISTRY):
    reg = _write_registry(tmp_path, registry_content)
    return HarnessGatewayService(
        registry_path=reg, execution_mode=ExecutionMode.SIMULATION
    )


class TestGatewayNegative:
    def test_unknown_adapter_fails_closed(self, tmp_path):
        service = _service(tmp_path)
        result = service.start_session(adapter_id="pi", task="x")
        assert result.success is False
        assert "CAPABILITY_UNAVAILABLE" in str(result.detail.get("code", ""))

    def test_disabled_adapter_fails_closed(self, tmp_path):
        service = _service(tmp_path)
        result = service.start_session(adapter_id="opencode_cli", task="x")
        assert result.success is False
        assert "disabled" in str(result.message).lower()

    def test_missing_module_fails_closed(self, tmp_path):
        content = VALID_REGISTRY.replace(
            "module: conduvera.harness.hermes_adapter",
            "module: conduvera.harness.no_such_module",
        )
        service = _service(tmp_path, content)
        result = service.start_session(adapter_id="hermes", task="x")
        assert result.success is False

    def test_incompatible_contract_fails_closed(self, tmp_path):
        # Adapter entry pointing at a module that does NOT implement the
        # HarnessAdapterProtocol surface.
        content = VALID_REGISTRY.replace(
            "module: conduvera.harness.hermes_adapter\n    entry_point: HermesAdapter",
            "module: conduvera.harness.registry\n    entry_point: HarnessAdapterRegistry",
        )
        service = _service(tmp_path, content)
        result = service.start_session(adapter_id="hermes", task="x")
        assert result.success is False

    def test_invalid_execution_mode_rejected(self):
        # ExecutionMode has no silent default: unknown value must not exist.
        with pytest.raises(ValueError):
            ExecutionMode("SIMULATE")  # not a defined member

    def test_missing_registry_falls_back_to_package_resource(self, tmp_path, monkeypatch):
        # No explicit path, no env var -> the canonical package resource is
        # used (never cwd); a non-existent explicit path also falls back to
        # the package resource (fail-closed resolution, never cwd).
        monkeypatch.delenv("CONDUVERA_HARNESS_REGISTRY", raising=False)
        reg = HarnessAdapterRegistry("/nonexistent/registry.yaml")
        assert reg.registry_path.is_file()
        assert "conduvera" in str(reg.registry_path)

    def test_execution_mode_required_no_default(self, tmp_path):
        # The service MUST NOT boot without an explicit execution mode.
        reg = _write_registry(tmp_path, VALID_REGISTRY)
        with pytest.raises(ValueError, match="EXECUTION_MODE_REQUIRED"):
            HarnessGatewayService(registry_path=reg)

    def test_registry_resolution_priority_explicit_over_env(self, tmp_path, monkeypatch):
        # Explicit path wins over env var (never cwd).
        explicit = _write_registry(tmp_path, VALID_REGISTRY)
        env_reg = tmp_path / "env-registry.yaml"
        env_reg.write_text("adapters: {}\n", encoding="utf-8")
        monkeypatch.setenv("CONDUVERA_HARNESS_REGISTRY", str(env_reg))
        reg = HarnessAdapterRegistry(str(explicit))
        assert reg.registry_path == explicit.resolve()


class TestGatewayPositive:
    def test_valid_registry_resolves_package_resource(self, tmp_path, monkeypatch):
        # The canonical registry ships as a package resource; resolution
        # falls back to it when no explicit path / env var is given.
        monkeypatch.delenv("CONDUVERA_HARNESS_REGISTRY", raising=False)
        reg = HarnessAdapterRegistry()
        assert reg.registry_path.is_file()

    def test_gateway_service_constructed_from_explicit_path(self, tmp_path):
        service = _service(tmp_path)
        assert service is not None
