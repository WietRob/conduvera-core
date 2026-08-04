"""Adapter boundary tests (DOD-LIVE-02, DOD-LIVE-08).

Core (FixtureRunner) must never import a concrete adapter:
- registry present + enabled        -> adapter loadable
- registry entry missing            -> CAPABILITY_UNAVAILABLE
- adapter module physically absent  -> Core still starts, structured error
- no hidden fallback
- disable vs removal are separate tests
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curaops.buildroom.fixture_runner import FixtureRunner
from curaops.harness.registry import (
    HarnessAdapterRegistry,
    HarnessCapabilityUnavailableError,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


def _runner_with(tmp_path, registry_content: str) -> FixtureRunner:
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text(registry_content, encoding="utf-8")
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    return FixtureRunner(
        fixture_dir=fixture_dir,
        route_manifest=FIXTURES / "ods" / "route-manifest.fixture.yaml",
        adapter_registry=reg,
        producer={"name": "t", "version": "1"},
        execution_mode='SIMULATION',
    )


def test_registry_present_enabled_loads_adapter(tmp_path):
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text(
        "adapters:\n  hermes:\n    enabled: true\n"
        "    module: curaops.harness.hermes_adapter\n"
        "    entry_point: HermesAdapter\n",
        encoding="utf-8",
    )
    registry = HarnessAdapterRegistry(reg)
    adapter = registry.load_adapter("hermes")
    assert adapter.name == "hermes"
    assert adapter.adapter_version == "hermes-adapter.v1"


def test_registry_entry_missing_cap_unavailable(tmp_path):
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text("adapters: {}\n", encoding="utf-8")
    registry = HarnessAdapterRegistry(reg)
    with pytest.raises(HarnessCapabilityUnavailableError) as exc:
        registry.load_adapter("hermes")
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    assert "no registry entry" in exc.value.reason


def test_registry_disabled_cap_unavailable(tmp_path):
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text(
        "adapters:\n  hermes:\n    enabled: false\n"
        "    module: curaops.harness.hermes_adapter\n"
        "    entry_point: HermesAdapter\n",
        encoding="utf-8",
    )
    registry = HarnessAdapterRegistry(reg)
    with pytest.raises(HarnessCapabilityUnavailableError) as exc:
        registry.load_adapter("hermes")
    assert "disabled" in exc.value.reason


def test_adapter_module_physically_absent_core_starts(tmp_path):
    """Module path points at a non-existent module -> Core still starts."""
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text(
        "adapters:\n  hermes:\n    enabled: true\n"
        "    module: curaops.harness.no_such_adapter_module\n"
        "    entry_point: HermesAdapter\n",
        encoding="utf-8",
    )
    runner = _runner_with(tmp_path, reg.read_text())
    result = runner.run("task")
    assert result.status == "cap_unavailable"
    assert result.error == "CAPABILITY_UNAVAILABLE"
    assert "CAPABILITY_UNAVAILABLE" in result.final_status_readable


def test_runner_without_registry_no_hidden_fallback(tmp_path):
    """No registry provided -> structured error, never a hidden fallback."""
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    runner = FixtureRunner(
        fixture_dir=fixture_dir,
        route_manifest=FIXTURES / "ods" / "route-manifest.fixture.yaml",
        producer={"name": "t", "version": "1"},
        execution_mode='SIMULATION',
    )
    result = runner.run("task")
    assert result.status == "cap_unavailable"
    assert result.error == "CAPABILITY_UNAVAILABLE"
