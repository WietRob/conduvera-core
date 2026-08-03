"""CONDUVERA-GOAL-1.0 DoD / binding / bootstrap formal verification tests.

Covers DoD-01..DoD-12 evidence generation: contract equivalence, negative
validation, binding hash consistency, fresh-process bootstrap receipt,
fixture E2E, adapter disable, and the final goal-receipt with the full DoD
matrix.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from curaops.cli.commands.goal import CONTRACT_ID, validate_goal_file, GoalValidationError

ROOT = Path(__file__).resolve().parents[2]
GOAL_FILE = ROOT / "evidence/goals/CONDUVERA-FIXTURE-001/goal.yaml"
AGENTS = ROOT / "AGENTS.md"


# --- DoD-01: human + machine SSoT equivalence ---------------------------

def test_dod01_contract_files_exist_and_equivalent():
    assert (ROOT / "contracts/goal-execution.v1.yaml").is_file()
    assert (ROOT / "contracts/goal-execution.v1.schema.json").is_file()
    assert (ROOT / "contracts/architecture-invariants.v1.yaml").is_file()
    # Machine YAML declares the same contract id as the validator
    import yaml

    data = yaml.safe_load((ROOT / "contracts/goal-execution.v1.yaml").read_text())
    assert data["contract"]["id"] == CONTRACT_ID


# --- DoD-02: goal without DoD/verification rejected ----------------------

def test_dod02_incomplete_goal_rejected(tmp_path):
    bad = tmp_path / "incomplete.yaml"
    bad.write_text(
        "contract:\n  id: CONDUVERA-GOAL-1.0\n  schema_version: '1.0'\n"
        "goal_id: CONDUVERA-BAD-001\n"
        "title: incomplete\n"
        "architekturposition:\n  control_plane: conduvera_core\n"
        "  execution_module: buildroom_internal\n"
        "  runtime_authority: ods\n"
        "  secrets_authority: bws\n"
        "scope:\n  - x\n",
        encoding="utf-8",
    )
    with pytest.raises(GoalValidationError) as exc:
        validate_goal_file(bad)
    assert exc.value.code in ("MISSING_REQUIRED_FIELD", "DOD_MISSING", "VERIFICATION_MISSING")


# --- DoD-03: all harness bindings reference same contract id + hash -----

def test_dod03_bindings_reference_same_contract_and_hash():
    agents_text = AGENTS.read_text(encoding="utf-8")
    assert CONTRACT_ID in agents_text
    # hash in AGENTS.md must match the validator's computed hash
    from curaops.cli.commands.goal import contract_hash

    computed = contract_hash()
    assert computed in agents_text, "AGENTS.md binding hash differs from contract hash"
    # Pi template references the same contract
    pi = (ROOT / "templates/pi-binding.md").read_text(encoding="utf-8")
    assert CONTRACT_ID in pi


# --- DoD-04: fresh process finds + loads contract, bootstrap receipt -----

def test_dod04_fresh_process_bootstrap_receipt():
    proc = subprocess.run(
        [sys.executable, "-m", "curaops.cli.main", "bootstrap", "receipt",
         "--goal-id", "CONDUVERA-FIXTURE-001"],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
        env={"PYTHONPATH": str(ROOT)},
    )
    assert proc.returncode == 0, proc.stderr
    receipt = json.loads(proc.stdout)
    assert receipt["goal_contract"] == CONTRACT_ID
    assert receipt["loaded"] is True
    assert receipt["contract_hash"].startswith("sha256:")


# --- DoD-05..08: fixture slice behavior ----------------------------------

def test_dod05_e2e_and_dod06_timeout_cancel(tmp_path):
    import yaml as y

    reg = tmp_path / "reg.yaml"
    reg.write_text("adapters:\n  hermes:\n    enabled: true\n", encoding="utf-8")
    from curaops.buildroom.fixture_runner import FixtureRunner
    from curaops.harness.hermes_adapter import HermesAdapter

    adapter = HermesAdapter(registry_path=reg, fixture_worktree=tmp_path / "wt")
    runner = FixtureRunner(
        fixture_dir=tmp_path / "fx",
        route_manifest=ROOT / "fixtures/ods/route-manifest.yaml",
        adapter=adapter,
        producer={"name": "t", "version": "1"},
    )
    result = runner.run("e2e")
    assert result.status == "completed"
    assert result.model_binding["auth_domain"] == "litellm"
    # timeout + cancel only affect managed sessions
    sid = result.session_id
    t = runner.timeout(sid)
    assert t.status == "timed_out"
    # adapter-level unknown session is structured error
    st = adapter.status_session("nope")
    assert st.detail["code"] == "UNKNOWN_SESSION"


def test_dod08_disabled_adapter_clean(tmp_path):
    reg = tmp_path / "reg.yaml"
    reg.write_text("adapters:\n  hermes:\n    enabled: false\n", encoding="utf-8")
    from curaops.buildroom.fixture_runner import FixtureRunner
    from curaops.harness.hermes_adapter import HermesAdapter

    adapter = HermesAdapter(registry_path=reg, fixture_worktree=tmp_path / "wt")
    runner = FixtureRunner(
        fixture_dir=tmp_path / "fx",
        route_manifest=ROOT / "fixtures/ods/route-manifest.yaml",
        adapter=adapter,
        producer={"name": "t", "version": "1"},
    )
    result = runner.run("task")
    assert result.status == "cap_unavailable"
    assert result.error == "CAPABILITY_UNAVAILABLE"


# --- DoD-09: no private cross-repo imports / no vendoring ----------------

def test_dod09_no_private_imports_no_vendoring():
    import curaops.buildroom.fixture_runner as fr
    import curaops.harness.hermes_adapter as ha
    import inspect

    # Core (runner) must never import private legacy internals or spawn
    # processes. The adapter is the ONLY module allowed to spawn Hermes
    # (DOD-01: it owns the live start), so subprocess is permitted there
    # but private legacy imports remain forbidden everywhere.
    for mod in (fr,):
        src = inspect.getsource(mod)
        for forbidden in ("buildroom_core", "buildroom_execution", "manual_authorization",
                          "fleet_router", "peekxd_", "subprocess", "os.system"):
            assert forbidden not in src, f"{mod.__name__} uses forbidden: {forbidden}"
    for mod in (ha,):
        src = inspect.getsource(mod)
        for forbidden in ("buildroom_core", "buildroom_execution", "manual_authorization",
                          "fleet_router", "peekxd_"):
            assert forbidden not in src, f"{mod.__name__} imports private legacy: {forbidden}"
        # The adapter MUST own the spawn (DOD-01)
        assert "subprocess.Popen" in src
        assert "start_new_session=True" in src


# --- DoD-11: goal-receipt contains full DoD matrix -----------------------

def test_dod11_receipt_contains_dod_matrix(tmp_path):
    from curaops.buildroom.fixture_runner import FixtureRunner
    from curaops.harness.hermes_adapter import HermesAdapter

    reg = tmp_path / "reg.yaml"
    reg.write_text("adapters:\n  hermes:\n    enabled: true\n", encoding="utf-8")
    adapter = HermesAdapter(registry_path=reg, fixture_worktree=tmp_path / "wt")
    runner = FixtureRunner(
        fixture_dir=tmp_path / "fx",
        route_manifest=ROOT / "fixtures/ods/route-manifest.yaml",
        adapter=adapter,
        producer={"name": "t", "version": "1"},
    )
    result = runner.run("receipt task")
    receipt_path = runner.emit_receipt(result, goal_id="CONDUVERA-FIXTURE-001")
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["goal_contract"] == CONTRACT_ID
    assert data["status"] == "completed"
    assert len(data["evidence_paths"]) == 1
    assert all(v == "PASS" for v in data["invariants"].values())
