"""v0.23.1 ProjectPack / repo-agnostic core tests.

Verifizierte Eigenschaften:
- ProjectPack ist die Pflichtquelle fuer generische Buildroom-Ausfuehrung.
- PeekXD-Legacy ist nur ueber explizites --legacy-peekxd erlaubt.
- Dummy-Projekt beweist, dass generischer Dry-Run ohne PeekXD-Pfade funktioniert.
- Diese Tests starten keinen Buildroom-Cycle und dispatchen keine Kanban-Tasks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from buildroom_core import ProjectPackError, resolve_project

SCRIPTS_DIR = Path.home() / ".hermes/scripts"
PROJECTS_DIR = Path.home() / ".hermes/buildroom/projects"
PEEKXD_REPO = Path.home() / "projects/peekxd-linux-computer-use"
DUMMY_REPO = Path.home() / "projects/dummy-buildroom-repo"
DUMMY_EVIDENCE = Path.home() / ".hermes/research-vault/ops/dummy-buildroom"


def run_loop(*args: str) -> subprocess.CompletedProcess[str]:
    """Run buildroom_loop.py in dry-run/test mode only."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "buildroom_loop.py"), *args],
        cwd=SCRIPTS_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


def test_01_resolve_project_peekxd_loads_yaml():
    """Test 1: resolve_project('peekxd') laedt peekxd.yaml."""
    pack = resolve_project("peekxd")
    assert pack.project_name == "peekxd"
    assert pack.repo_path == PEEKXD_REPO
    assert pack.evidence_dir.name == "peekxd-buildroom-v09"


def test_02_resolve_project_dummy_loads_yaml():
    """Test 2: resolve_project('dummy') laedt dummy.yaml."""
    pack = resolve_project("dummy")
    assert pack.project_name == "dummy"
    assert pack.repo_path == DUMMY_REPO
    assert pack.evidence_dir == DUMMY_EVIDENCE


def test_03_buildroom_loop_dry_run_project_peekxd():
    """Test 3: buildroom_loop.py --dry-run --project peekxd funktioniert."""
    result = run_loop("--dry-run", "--project", "peekxd")
    assert result.returncode == 0, result.stderr
    assert "Project: peekxd" in result.stdout
    assert "Generic mode: true" in result.stdout


def test_04_buildroom_loop_dry_run_project_dummy():
    """Test 4: buildroom_loop.py --dry-run --project dummy funktioniert."""
    result = run_loop("--dry-run", "--project", "dummy")
    assert result.returncode == 0, result.stderr
    assert "Project: dummy" in result.stdout
    assert str(DUMMY_REPO) in result.stdout
    assert "Generic mode: true" in result.stdout


def test_05_no_project_without_legacy_requires_pack():
    """Test 5: kein ProjectPack ohne --legacy-peekxd fuehrt zu PROJECT_PACK_REQUIRED."""
    result = run_loop("--dry-run")
    assert result.returncode == 2
    assert "PROJECT_PACK_REQUIRED" in result.stderr


def test_06_dummy_project_uses_no_peekxd_paths():
    """Test 6: dummy project verwendet keine PeekXD paths."""
    pack = resolve_project("dummy")
    summary = "\n".join([str(pack.repo_path), str(pack.evidence_dir), *pack.strategy_files, *pack.candidate_sources])
    assert "peekxd" not in summary.lower()


def test_07_evidence_dir_comes_from_project_pack():
    """Test 7: evidence_dir kommt aus ProjectPack."""
    pack = resolve_project("dummy")
    assert pack.evidence_dir == DUMMY_EVIDENCE


def test_08_repo_path_comes_from_project_pack():
    """Test 8: repo_path kommt aus ProjectPack."""
    pack = resolve_project("dummy")
    assert pack.repo_path == DUMMY_REPO


def test_09_state_file_comes_from_evidence_dir():
    """Test 9: state_file kommt aus evidence_dir."""
    pack = resolve_project("dummy")
    assert pack.state_file == DUMMY_EVIDENCE / "orchestrator-state.json"


def test_10_branch_prefix_comes_from_project_pack():
    """Test 10: branch_prefix kommt aus ProjectPack."""
    pack = resolve_project("dummy")
    assert pack.builder_branch_prefix == "autonomy/dummy"


def test_11_test_command_comes_from_project_pack():
    """Test 11: test_command kommt aus ProjectPack."""
    pack = resolve_project("dummy")
    assert pack.test_command == "python3 -m pytest -q"


def test_12_strategy_files_come_from_project_pack():
    """Test 12: strategy_files kommen aus ProjectPack."""
    pack = resolve_project("dummy")
    assert pack.strategy_files == ("docs/strategy.md",)


def test_13_legacy_peekxd_mode_only_with_flag():
    """Test 13: Legacy PeekXD mode funktioniert nur mit --legacy-peekxd."""
    result = run_loop("--dry-run", "--legacy-peekxd")
    assert result.returncode == 0, result.stderr
    assert "Legacy PeekXD compatibility mode" in result.stdout
    assert "ProjectPack: disabled" in result.stdout


def test_14_generic_core_has_no_hardcoded_peekxd_paths_except_legacy_block():
    """Test 14: generischer Core enthaelt keine hardcoded PeekXD Pfade."""
    core_text = (SCRIPTS_DIR / "buildroom_core.py").read_text()
    loop_text = (SCRIPTS_DIR / "buildroom_loop.py").read_text()
    combined = core_text + "\n" + loop_text
    forbidden_paths = [
        "/home/roberto_schmidt/projects/peekxd-linux-computer-use",
        "peekxd-buildroom-v09",
        "ADR-0006-v0.4.0-priorisierung-cua-driver-differenzierung.md",
        "wayland-wtype-fallback",
        "snapshot-module-scaffold",
    ]
    for forbidden in forbidden_paths:
        assert forbidden not in combined
    assert "--legacy-peekxd" in loop_text


def test_15_legacy_file_remains_compatibility_but_new_work_uses_buildroom_loop():
    """Test 15: Kompatibilitaetsdatei bleibt, neue Arbeit nutzt buildroom_loop.py."""
    assert (SCRIPTS_DIR / "peekxd_buildroom_loop_v20.py").exists()
    assert (SCRIPTS_DIR / "buildroom_loop.py").exists()
    result = run_loop("--dry-run", "--project", str(PROJECTS_DIR / "dummy.yaml"))
    assert result.returncode == 0, result.stderr
    assert "Project: dummy" in result.stdout


def test_project_argument_and_legacy_are_mutually_exclusive():
    """Zusatztest: --project und --legacy-peekxd duerfen nicht kombiniert werden."""
    result = run_loop("--dry-run", "--project", "dummy", "--legacy-peekxd")
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr


def test_unknown_project_reports_error():
    """Zusatztest: unbekanntes ProjectPack liefert klare Fehlermeldung."""
    result = run_loop("--dry-run", "--project", "does-not-exist")
    assert result.returncode == 2
    assert "not found" in result.stderr


def test_evidence_path_helper_uses_project_pack_root():
    """Zusatztest: evidence_path helper verwendet ProjectPack evidence_dir."""
    pack = resolve_project("dummy")
    assert pack.evidence_path("researcher", cycle=7, date="20260630") == (
        DUMMY_EVIDENCE / "researcher/researcher-cycle-7-20260630.md"
    )
    assert pack.evidence_path("builder", cycle=7, date="20260630", candidate="demo-candidate") == (
        DUMMY_EVIDENCE / "builder/builder-cycle-7-demo-candidate-20260630.md"
    )
    with pytest.raises(ProjectPackError):
        pack.evidence_path("builder", cycle=7, date="20260630")
