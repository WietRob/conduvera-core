"""Legacy state migration tests (goal converge..., Arbeit 5 / DOD-04)."""

from __future__ import annotations

from pathlib import Path

from conduvera.cli.legacy_state import (
    plan_migration,
    rollback,
    run_migration,
)

SUBDIRS = ["sessions", "locks", "patterns", "control"]


def _make_legacy(home: Path) -> Path:
    legacy = home / ".curaops"
    for sub in SUBDIRS:
        d = legacy / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "fixture.txt").write_text(f"state-{sub}", encoding="utf-8")
    return legacy


def test_dry_run_reports_actions_without_writing(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    legacy = _make_legacy(home)
    plan = plan_migration(home, SUBDIRS, dry_run=True)
    result = run_migration(plan)

    assert result["dry_run"] is True
    assert result["action_count"] == 4
    assert all(a["action"] == "WOULD_COPY" for a in result["actions"])
    # Nothing written to canonical
    assert not (home / ".conduvera").exists()


def test_apply_copies_and_backs_up(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _make_legacy(home)
    plan = plan_migration(home, SUBDIRS, dry_run=False)
    result = run_migration(plan)

    assert result["action_count"] == 4
    assert all(a["action"] == "COPIED" for a in result["actions"])
    assert "backup_manifest" in result
    canonical = home / ".conduvera"
    assert canonical.exists()
    for sub in SUBDIRS:
        assert (canonical / sub / "fixture.txt").read_text() == f"state-{sub}"


def test_idempotent_rerun_produces_no_second_result(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _make_legacy(home)
    plan = plan_migration(home, SUBDIRS, dry_run=False)
    run_migration(plan)

    # Second run: no COPIED actions (no second copy result), only markers
    plan2 = plan_migration(home, SUBDIRS, dry_run=False)
    result2 = run_migration(plan2)
    copied2 = [a for a in result2["actions"] if a["action"] == "COPIED"]
    assert len(copied2) == 0
    assert all(a["action"] == "ALREADY_MIGRATED" for a in result2["actions"])


def test_never_parallel_write_when_canonical_has_content(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    legacy = _make_legacy(home)
    # Canonical already has content (newer state must win)
    canonical_sessions = home / ".conduvera" / "sessions"
    canonical_sessions.mkdir(parents=True)
    (canonical_sessions / "new.txt").write_text("newer", encoding="utf-8")

    plan = plan_migration(home, SUBDIRS, dry_run=False)
    result = run_migration(plan)

    # sessions already migrated (canonical has newer content -> no write),
    # other 3 copied
    actions = result["actions"]
    migrated = [a for a in actions if a["action"] == "ALREADY_MIGRATED"]
    assert any("sessions" in a["src"] for a in migrated)
    copied = [a for a in actions if a["action"] == "COPIED"]
    assert len(copied) == 3
    # Canonical session content untouched
    assert (canonical_sessions / "new.txt").read_text() == "newer"


def test_rollback_restores_from_backup(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _make_legacy(home)
    plan = plan_migration(home, SUBDIRS, dry_run=False)
    result = run_migration(plan)
    assert "backup_manifest" in result

    backup_dir = Path(result["backup_manifest"]).parent
    canonical = home / ".conduvera"
    # Mutate canonical, then rollback
    (canonical / "sessions" / "fixture.txt").write_text("mutated", encoding="utf-8")
    restored = rollback(backup_dir, canonical)
    assert set(restored) == set(SUBDIRS)
    assert (canonical / "sessions" / "fixture.txt").read_text() == "state-sessions"


def test_missing_legacy_is_noop(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    plan = plan_migration(home, SUBDIRS, dry_run=False)
    result = run_migration(plan)
    assert result["action_count"] == 0
    assert not (home / ".conduvera").exists()
