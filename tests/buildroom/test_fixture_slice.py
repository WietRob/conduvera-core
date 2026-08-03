"""Managed fixture slice tests (CONDUVERA-GOAL-1.0, Scope B).

Covers: real E2E run, timeout, cancel, disabled adapter (fail-closed),
restart/reconcile idempotence, duplicate-event protection, evidence
hash/schema, dependency scan (no private cross-repo imports), state
single-writer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curaops.buildroom.fixture_runner import FixtureRunner
from curaops.evidence.contract import SCHEMA_VERSION
from curaops.harness.hermes_adapter import HarnessCapabilityUnavailable, HermesAdapter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def adapter(tmp_path) -> HermesAdapter:
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text(
        "adapters:\n  hermes:\n    enabled: true\n    version: hermes-adapter.v1\n",
        encoding="utf-8",
    )
    return HermesAdapter(registry_path=reg, fixture_worktree=tmp_path / "wt")


@pytest.fixture
def disabled_adapter(tmp_path) -> HermesAdapter:
    reg = tmp_path / "harness-registry.yaml"
    reg.write_text(
        "adapters:\n  hermes:\n    enabled: false\n",
        encoding="utf-8",
    )
    return HermesAdapter(registry_path=reg, fixture_worktree=tmp_path / "wt")


@pytest.fixture
def runner(tmp_path, adapter) -> FixtureRunner:
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    return FixtureRunner(
        fixture_dir=fixture_dir,
        route_manifest=FIXTURES / "ods" / "route-manifest.yaml",
        adapter=adapter,
        producer={"name": "test-runner", "version": "0.0.0"},
    )


def _assert_evidence_schema(events: list[dict]):
    for ev in events:
        assert ev["schema_version"] == SCHEMA_VERSION
        assert ev["event_hash"].startswith("sha256:")
        assert ev["integrity"]["algorithm"] == "sha256"


def test_e2e_managed_fixture_run(runner):
    result = runner.run("fixture task: write harmless text")
    assert result.status == "completed"
    assert result.task_id.startswith("TASK-")
    assert result.attempt_id.startswith("ATT-")
    assert result.session_id.startswith("mxfix_")  # harness session id (managed)
    assert result.model_binding["kind"] == "gateway_alias"
    assert result.model_binding["auth_domain"] == "litellm"
    assert len(result.evidence_paths) == 1
    _assert_evidence_schema(result.events)
    types = {e["event_type"] for e in result.events}
    assert "fixture.run.started" in types
    assert "fixture.run.completed" in types
    assert result.final_status_readable.startswith("COMPLETED")


def test_timeout_only_managed_session(adapter, tmp_path):
    adapter._require_enabled()
    start = adapter.start_session("a", str(tmp_path / "wt"), "t", {"model_binding": {}})
    assert start.success
    sid = start.detail["session_id"]
    adapter.timeout_session(sid)
    st = adapter.status_session(sid)
    assert st.detail["status"] == "timed_out"


def test_cancel_only_managed_session(adapter, tmp_path):
    start = adapter.start_session("a", str(tmp_path / "wt"), "t", {"model_binding": {}})
    sid = start.detail["session_id"]
    adapter.cancel_session(sid)
    st = adapter.status_session(sid)
    assert st.detail["status"] == "cancelled"
    # unknown session is a structured error, not an exception
    unknown = adapter.status_session("does-not-exist")
    assert unknown.success is False
    assert unknown.detail["code"] == "UNKNOWN_SESSION"


def test_disabled_adapter_fail_closed(disabled_adapter, tmp_path):
    # Import never fails; every call returns CAPABILITY_UNAVAILABLE
    assert disabled_adapter.is_enabled() is False
    with pytest.raises(HarnessCapabilityUnavailable) as exc:
        disabled_adapter._require_enabled()
    assert exc.value.code == "CAPABILITY_UNAVAILABLE"
    hc = disabled_adapter.health_check()
    assert hc.success is False
    assert hc.detail["code"] == "CAPABILITY_UNAVAILABLE"
    start = disabled_adapter.start_session("a", str(tmp_path / "wt"), "t", {})
    assert start.success is False
    assert start.detail["code"] == "CAPABILITY_UNAVAILABLE"


def test_disabled_adapter_runner_ends_cleanly(disabled_adapter, tmp_path):
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    runner = FixtureRunner(
        fixture_dir=fixture_dir,
        route_manifest=FIXTURES / "ods" / "route-manifest.yaml",
        adapter=disabled_adapter,
        producer={"name": "t", "version": "1"},
    )
    result = runner.run("task")
    assert result.status == "cap_unavailable"
    assert result.error == "CAPABILITY_UNAVAILABLE"
    assert "CAPABILITY_UNAVAILABLE" in result.final_status_readable


def test_reconcile_idempotent_no_duplicate_events(runner):
    first = runner.reconcile()
    assert first["duplicate"] is False
    second = runner.reconcile()
    assert second["duplicate"] is True
    # Event count must not grow on duplicate reconcile
    assert len(runner._events) == 1  # only the initial reconciled event


def test_feature_flag_disables_fixture(tmp_path, adapter):
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    runner = FixtureRunner(
        fixture_dir=fixture_dir,
        route_manifest=FIXTURES / "ods" / "route-manifest.yaml",
        adapter=adapter,
        producer={"name": "t", "version": "1"},
        feature_flag=False,
    )
    result = runner.run("task")
    assert result.status == "disabled"
    assert "FIXTURE_DISABLED" in result.final_status_readable


def test_evidence_receipt_written(runner):
    result = runner.run("task with receipt")
    receipt = runner.emit_receipt(result, goal_id="CONDUVERA-FIXTURE-001")
    assert receipt.is_file()
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["goal_contract"] == "CONDUVERA-GOAL-1.0"
    assert data["goal_id"] == "CONDUVERA-FIXTURE-001"
    assert data["status"] == "completed"
    assert data["invariants"]["exactly_one_control_plane"] == "PASS"
    assert all(v == "PASS" for v in data["invariants"].values())


def test_no_private_cross_repo_imports():
    """Static scan: fixture runner + adapter must not import private internals."""
    import inspect

    from curaops.buildroom import fixture_runner as fr
    from curaops.harness import hermes_adapter as ha

    for mod in (fr, ha):
        src = inspect.getsource(mod)
        for forbidden in ("buildroom_core", "buildroom_execution", "peekxd_",
                          "manual_authorization", "fleet_router"):
            assert forbidden not in src, f"{mod.__name__} imports private legacy: {forbidden}"
        assert "subprocess" not in src, f"{mod.__name__} must not spawn subprocesses"
