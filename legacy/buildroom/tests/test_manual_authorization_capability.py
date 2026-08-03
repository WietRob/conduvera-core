"""One-shot manual Buildroom authorization capability tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

import manual_authorization as auth
from buildroom_core import ProjectPack


ALL_PHASES = ["RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"]


def make_pack(
    tmp_path: Path,
    *,
    researcher_profile: str = "researcher",
    project_name: str = "synthetic-manual",
) -> ProjectPack:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    return ProjectPack.from_mapping(
        {
            "project_name": project_name,
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ALL_PHASES,
            "profiles": {
                "researcher": researcher_profile,
                "dreamer": "dreamer",
                "builder": "builder",
                "reviewer": "reviewer",
                "reporter": "orchestrator",
            },
            "execution": {
                "builder_backend": "native",
                "reviewer_backend": "native",
                "builder_model": "openai-codex/gpt-5.6-sol",
                "reviewer_model": "openai-codex/gpt-5.6-sol",
                "reviewer_independence_exception": {
                    "approved": True,
                    "approved_by": "owner",
                    "approved_at": "2026-07-15",
                },
            },
        }
    )


def store(tmp_path: Path) -> auth.ManualAuthorizationStore:
    return auth.ManualAuthorizationStore(tmp_path / "manual-authorizations.jsonl")


def issue(monkeypatch, tmp_path, pack, *, now=None, ttl_seconds=300, dry_run_only=True):
    monkeypatch.setattr(auth, "trusted_issuer_identity", lambda: "owner")
    return auth.issue_manual_authorization(
        pack,
        phase="RESEARCHER",
        request_id="owner-request-1",
        dry_run_only=dry_run_only,
        ttl_seconds=ttl_seconds,
        store=store(tmp_path),
        now=now,
    )


def test_issue_returns_opaque_id_and_records_complete_binding(monkeypatch, tmp_path):
    pack = make_pack(tmp_path)
    now = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)
    authorization_id = issue(monkeypatch, tmp_path, pack, now=now)

    assert authorization_id.startswith("manual-auth-")
    assert "owner-request-1" not in authorization_id
    record = store(tmp_path).authorization(authorization_id)
    assert record == {
        "id": authorization_id,
        "project": "synthetic-manual",
        "repository": str(pack.repo_path.resolve()),
        "phase": "RESEARCHER",
        "request_id": "owner-request-1",
        "issuer": "owner",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=300)).isoformat(),
        "dry_run_only": True,
        "allowed_profile": "researcher",
        "consumed_at": None,
    }


def test_allowed_profile_cannot_issue_its_own_capability(monkeypatch, tmp_path):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(auth, "trusted_issuer_identity", lambda: "researcher")
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.issue_manual_authorization(
            pack,
            phase="RESEARCHER",
            request_id="self-auth",
            dry_run_only=True,
            store=store(tmp_path),
        )


def test_consume_is_one_shot_and_replay_fails_closed(monkeypatch, tmp_path):
    pack = make_pack(tmp_path)
    now = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)
    authorization_id = issue(monkeypatch, tmp_path, pack, now=now)
    first = auth.consume_manual_authorization(
        authorization_id,
        pack=pack,
        phase="RESEARCHER",
        dry_run=True,
        store=store(tmp_path),
        now=now + timedelta(seconds=1),
    )
    assert first["consumed_at"] == (now + timedelta(seconds=1)).isoformat()
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_ALREADY_CONSUMED"):
        auth.consume_manual_authorization(
            authorization_id,
            pack=pack,
            phase="RESEARCHER",
            dry_run=True,
            store=store(tmp_path),
            now=now + timedelta(seconds=2),
        )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("project", "MANUAL_AUTHORIZATION_MISMATCH"),
        ("phase", "MANUAL_AUTHORIZATION_MISMATCH"),
        ("repository", "MANUAL_AUTHORIZATION_MISMATCH"),
        ("dry_run", "MANUAL_AUTHORIZATION_MISMATCH"),
    ],
)
def test_binding_mismatch_does_not_consume(monkeypatch, tmp_path, change, code):
    pack = make_pack(tmp_path)
    now = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)
    authorization_id = issue(monkeypatch, tmp_path, pack, now=now, dry_run_only=True)
    supplied_pack = pack
    supplied_phase = "RESEARCHER"
    supplied_dry_run = True
    if change == "project":
        supplied_pack = make_pack(tmp_path / "other", project_name="other-project")
    elif change == "phase":
        supplied_phase = "DREAMER"
    elif change == "repository":
        supplied_pack = make_pack(tmp_path / "other")
    elif change == "dry_run":
        supplied_dry_run = False
    with pytest.raises(auth.ManualAuthorizationError, match=code):
        auth.consume_manual_authorization(
            authorization_id,
            pack=supplied_pack,
            phase=supplied_phase,
            dry_run=supplied_dry_run,
            store=store(tmp_path),
            now=now + timedelta(seconds=1),
        )
    assert store(tmp_path).authorization(authorization_id)["consumed_at"] is None


def test_expired_and_missing_authorizations_have_exact_codes(monkeypatch, tmp_path):
    pack = make_pack(tmp_path)
    now = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)
    authorization_id = issue(monkeypatch, tmp_path, pack, now=now, ttl_seconds=5)
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_EXPIRED"):
        auth.consume_manual_authorization(
            authorization_id,
            pack=pack,
            phase="RESEARCHER",
            dry_run=True,
            store=store(tmp_path),
            now=now + timedelta(seconds=6),
        )
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_NOT_FOUND"):
        auth.consume_manual_authorization(
            "manual-auth-not-found",
            pack=pack,
            phase="RESEARCHER",
            dry_run=True,
            store=store(tmp_path),
            now=now,
        )


def test_issue_requires_orchestrator_or_owner_identity(monkeypatch, tmp_path):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(auth, "trusted_issuer_identity", lambda: "builder")
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.issue_manual_authorization(
            pack,
            phase="RESEARCHER",
            request_id="unauthorized-issuer",
            dry_run_only=True,
            store=store(tmp_path),
        )


def test_issue_refuses_autonomous_or_non_finish_line_pack(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "trusted_issuer_identity", lambda: "owner")
    base = make_pack(tmp_path)
    for autopilot, delivery_mode in [(True, "engineering_finish_line"), (False, "full")]:
        data = {
            "project_name": base.project_name,
            "repo_path": str(base.repo_path),
            "evidence_dir": str(base.evidence_dir),
            "autopilot_enabled": autopilot,
            "delivery_mode": delivery_mode,
            "allowed_phases": ALL_PHASES,
            "profiles": {
                "researcher": "researcher",
                "dreamer": "dreamer",
                "builder": "builder",
                "reviewer": "reviewer",
                "reporter": "orchestrator",
            },
            "execution": {"builder_backend": "native", "reviewer_backend": "native"},
        }
        with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_MISMATCH"):
            auth.issue_manual_authorization(
                ProjectPack.from_mapping(data),
                phase="RESEARCHER",
                request_id="wrong-mode",
                dry_run_only=True,
                store=store(tmp_path),
            )


def test_default_authorization_path_has_no_environment_override(monkeypatch, tmp_path):
    original = auth.DEFAULT_AUTHORIZATION_STORE
    monkeypatch.setenv("HERMES_MANUAL_BUILDROOM_AUDIT_PATH", str(tmp_path / "redirect.jsonl"))
    monkeypatch.setenv("HERMES_MANUAL_AUTHORIZATION_PATH", str(tmp_path / "redirect-2.jsonl"))
    assert auth.DEFAULT_AUTHORIZATION_STORE == original


def test_authorization_store_rejects_file_and_parent_symlinks(tmp_path):
    target = tmp_path / "target.jsonl"
    target.write_text("")
    file_link = tmp_path / "authorization-link.jsonl"
    file_link.symlink_to(target)
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.ManualAuthorizationStore(file_link).issue({"id": "manual-auth-test"})

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    parent_link = tmp_path / "linked-parent"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.ManualAuthorizationStore(parent_link / "authorizations.jsonl").issue(
            {"id": "manual-auth-test"}
        )


def test_malformed_or_unwritable_authorization_store_fails_closed(monkeypatch, tmp_path):
    ledger = tmp_path / "authorizations.jsonl"
    ledger.write_text("not-json\n")
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.ManualAuthorizationStore(ledger).issue({"id": "manual-auth-test"})

    safe_store = auth.ManualAuthorizationStore(tmp_path / "safe" / "authorizations.jsonl")
    monkeypatch.setattr(os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        safe_store.issue({"id": "manual-auth-test"})


@pytest.mark.parametrize("agent_name", ["hermes", "codex", "claude", "opencode", "orchestrator"])
def test_environment_spoof_cannot_create_trusted_issuer(monkeypatch, agent_name):
    class Tty:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setenv("HERMES_PROFILE", "owner")
    monkeypatch.setenv("HERMES_HOME", str(Path.home() / ".hermes/profiles/orchestrator"))
    monkeypatch.setattr(auth.sys, "stdin", Tty())
    monkeypatch.setattr(auth.sys, "stdout", Tty())
    monkeypatch.setattr(
        auth,
        "_process_ancestry",
        lambda: (
            auth.ProcessIdentity(str(Path(auth.sys.executable).resolve()).lower(), "python buildroom_authorization.py"),
            auth.ProcessIdentity("/usr/bin/bash", "bash"),
            auth.ProcessIdentity(f"/opt/{agent_name}", agent_name),
            auth.ProcessIdentity("/usr/bin/zsh", "zsh"),
            auth.ProcessIdentity("/usr/bin/ghostty", "ghostty"),
        ),
    )
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.trusted_issuer_identity()


def test_direct_owner_tty_uses_kernel_process_ancestry(monkeypatch):
    class Tty:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setattr(auth.sys, "stdin", Tty())
    monkeypatch.setattr(auth.sys, "stdout", Tty())
    monkeypatch.setattr(
        auth,
        "_process_ancestry",
        lambda: (
            auth.ProcessIdentity(str(Path(auth.sys.executable).resolve()).lower(), "python buildroom_authorization.py issue"),
            auth.ProcessIdentity("/usr/bin/zsh", "zsh"),
            auth.ProcessIdentity("/usr/bin/ghostty", "ghostty"),
            auth.ProcessIdentity("/usr/lib/systemd/systemd", "systemd --user"),
        ),
    )
    assert auth.trusted_issuer_identity() == "owner"


def test_unlisted_automation_between_python_and_owner_shell_is_rejected(monkeypatch):
    class Tty:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setattr(auth.sys, "stdin", Tty())
    monkeypatch.setattr(auth.sys, "stdout", Tty())
    monkeypatch.setattr(
        auth,
        "_process_ancestry",
        lambda: (
            auth.ProcessIdentity(str(Path(auth.sys.executable).resolve()).lower(), "python buildroom_authorization.py issue"),
            auth.ProcessIdentity("/opt/agent-runner", "agent-runner"),
            auth.ProcessIdentity("/usr/bin/bash", "bash"),
            auth.ProcessIdentity("/usr/bin/ghostty", "ghostty"),
            auth.ProcessIdentity("/usr/lib/systemd/systemd", "systemd --user"),
        ),
    )
    with pytest.raises(auth.ManualAuthorizationError, match="MANUAL_AUTHORIZATION_REQUIRED"):
        auth.trusted_issuer_identity()
