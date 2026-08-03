"""Manual CLI consumes a pre-issued capability and reports run truth."""

from __future__ import annotations

from pathlib import Path

import pytest

import buildroom_loop
from buildroom_core import ProjectPack
from manual_authorization import ManualAuthorizationError
from peekxd_buildroom_loop_v20 import BuildroomRunResult


ALL_PHASES = ["RESEARCHER", "DREAMER", "BUILDER", "REVIEWER", "MERGE", "REPORTER"]


def make_pack(tmp_path: Path) -> ProjectPack:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return ProjectPack.from_mapping(
        {
            "project_name": "synthetic-cli",
            "repo_path": str(repo),
            "evidence_dir": str(tmp_path / "evidence"),
            "autopilot_enabled": False,
            "delivery_mode": "engineering_finish_line",
            "allowed_phases": ALL_PHASES,
            "profiles": {
                "researcher": "researcher",
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


def argv(*extra: str) -> list[str]:
    return ["--project", "synthetic", "--manual", "--phase", "RESEARCHER", *extra]


def record() -> dict:
    return {
        "id": "manual-auth-opaque",
        "project": "synthetic-cli",
        "repository": "/synthetic",
        "phase": "RESEARCHER",
        "request_id": "owner-request-9",
        "issuer": "owner",
        "issued_at": "2026-07-15T09:00:00+00:00",
        "expires_at": "2026-07-15T09:05:00+00:00",
        "dry_run_only": False,
        "allowed_profile": "researcher",
        "consumed_at": "2026-07-15T09:00:01+00:00",
    }


def test_cli_has_only_authorization_id_as_manual_proof():
    parsed = buildroom_loop.parse_args(argv("--authorization-id", "manual-auth-opaque", "--dry-run"))
    assert parsed.authorization_id == "manual-auth-opaque"
    assert not hasattr(parsed, "authorized_by")
    assert not hasattr(parsed, "request_id")
    with pytest.raises(SystemExit):
        buildroom_loop.parse_args(argv("--authorized-by", "owner", "--request-id", "self"))


def test_missing_capability_is_required_before_manual_dry_run(monkeypatch, tmp_path, capsys):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(buildroom_loop, "resolve_project", lambda _project: pack)
    rc = buildroom_loop.main(argv("--dry-run"))
    assert rc == 4
    assert capsys.readouterr().err.strip() == "MANUAL_AUTHORIZATION_REQUIRED"


def test_policy_gates_run_before_capability_consumption(monkeypatch, tmp_path, capsys):
    autopilot = make_pack(tmp_path / "autopilot")
    object.__setattr__(autopilot, "autopilot_enabled", True)
    phase_limited = make_pack(tmp_path / "phase")
    object.__setattr__(phase_limited, "allowed_phases", ("RESEARCHER",))
    missing_git = make_pack(tmp_path / "missing-git")
    (missing_git.repo_path / ".git").rmdir()
    cases = [
        (autopilot, "RESEARCHER", "MANUAL_MODE_NOT_ALLOWED"),
        (phase_limited, "BUILDER", "PHASE_NOT_ALLOWED"),
        (missing_git, "RESEARCHER", "PROJECTPACK_NOT_READY"),
    ]
    for pack, phase, expected in cases:
        monkeypatch.setattr(buildroom_loop, "resolve_project", lambda _project, pack=pack: pack)
        monkeypatch.setattr(
            buildroom_loop,
            "consume_manual_authorization",
            lambda *_args, **_kwargs: pytest.fail("policy blocker must precede capability consumption"),
        )
        rc = buildroom_loop.main(
            [
                "--project", "synthetic", "--manual", "--phase", phase,
                "--authorization-id", "manual-auth-opaque", "--dry-run",
            ]
        )
        assert rc == 4
        assert capsys.readouterr().err.strip() == expected


def test_unconfigured_manual_project_has_exact_readiness_code(monkeypatch, capsys):
    from buildroom_core import ProjectPackError

    monkeypatch.setattr(
        buildroom_loop,
        "resolve_project",
        lambda _project: (_ for _ in ()).throw(ProjectPackError("missing")),
    )
    rc = buildroom_loop.main(
        [
            "--project", "missing", "--manual", "--phase", "RESEARCHER",
            "--authorization-id", "manual-auth-opaque", "--dry-run",
        ]
    )
    assert rc == 4
    assert capsys.readouterr().err.strip() == "PROJECTPACK_NOT_READY"


def test_dry_run_consumes_preissued_capability_and_uses_its_issuer(monkeypatch, tmp_path, capsys):
    pack = make_pack(tmp_path)
    consumed = []
    monkeypatch.setattr(buildroom_loop, "resolve_project", lambda _project: pack)
    monkeypatch.setattr(
        buildroom_loop,
        "load_orchestrator_class",
        lambda: pytest.fail("manual dry-run must not load the orchestrator"),
    )
    monkeypatch.setattr(
        buildroom_loop,
        "consume_manual_authorization",
        lambda authorization_id, **kwargs: consumed.append((authorization_id, kwargs)) or record(),
    )
    rc = buildroom_loop.main(argv("--authorization-id", "manual-auth-opaque", "--dry-run"))
    output = capsys.readouterr()
    assert rc == 0
    assert output.err == ""
    assert "MANUAL_DRY_RUN_READY" in output.out
    assert "owner-request-9" in output.out
    assert "owner" in output.out
    assert consumed[0][0] == "manual-auth-opaque"
    assert consumed[0][1]["dry_run"] is True


@pytest.mark.parametrize(
    "code",
    [
        "MANUAL_AUTHORIZATION_NOT_FOUND",
        "MANUAL_AUTHORIZATION_EXPIRED",
        "MANUAL_AUTHORIZATION_MISMATCH",
        "MANUAL_AUTHORIZATION_ALREADY_CONSUMED",
    ],
)
def test_exact_authorization_blockers_reach_cli(monkeypatch, tmp_path, capsys, code):
    pack = make_pack(tmp_path)
    monkeypatch.setattr(buildroom_loop, "resolve_project", lambda _project: pack)
    monkeypatch.setattr(
        buildroom_loop,
        "consume_manual_authorization",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ManualAuthorizationError(code)),
    )
    rc = buildroom_loop.main(argv("--authorization-id", "manual-auth-opaque", "--dry-run"))
    assert rc == 4
    assert capsys.readouterr().err.strip() == code


@pytest.mark.parametrize(
    ("run_result", "expected_rc"),
    [
        (BuildroomRunResult.PHASE_EXECUTED, 0),
        (BuildroomRunResult.LOCK_UNAVAILABLE, 4),
        (BuildroomRunResult.DISPATCH_FAILED, 4),
        (BuildroomRunResult.DISPATCH_BLOCKED, 4),
        (BuildroomRunResult.PROJECTPACK_BLOCKED, 4),
        (BuildroomRunResult.STATE_MISMATCH, 4),
        (BuildroomRunResult.PHASE_ALREADY_TERMINAL, 4),
        (BuildroomRunResult.INTERNAL_ERROR, 4),
    ],
)
def test_non_dry_success_requires_phase_executed(monkeypatch, tmp_path, capsys, run_result, expected_rc):
    pack = make_pack(tmp_path)
    events = []

    class FakeOrchestrator:
        def __init__(self, supplied_pack):
            assert supplied_pack is pack
            self.state = {"phase": "RESEARCHER", "cycle": 1}

        def reconcile_state(self):
            events.append("reconcile")

        def run(self, *, autonomous, phase_limit, reconcile, before_phase_side_effect):
            events.append("run")
            if run_result in {BuildroomRunResult.PHASE_EXECUTED, BuildroomRunResult.DISPATCH_FAILED}:
                before_phase_side_effect()
                events.append("capability-consumed")
            return run_result

    monkeypatch.setattr(buildroom_loop, "resolve_project", lambda _project: pack)
    monkeypatch.setattr(buildroom_loop, "load_orchestrator_class", lambda: FakeOrchestrator)
    monkeypatch.setattr(
        buildroom_loop,
        "consume_manual_authorization",
        lambda *_args, **_kwargs: events.append("consume") or record(),
    )
    rc = buildroom_loop.main(argv("--authorization-id", "manual-auth-opaque"))
    output = capsys.readouterr()
    assert rc == expected_rc
    assert events[0] == "reconcile"
    if run_result not in {BuildroomRunResult.PHASE_EXECUTED, BuildroomRunResult.DISPATCH_FAILED}:
        assert "consume" not in events
    else:
        assert events.index("consume") > events.index("reconcile")
    if expected_rc == 0:
        assert output.out.strip().endswith("PHASE_EXECUTED")
    else:
        assert output.err.strip() == run_result.value


def test_reconciliation_phase_mismatch_prevents_consumption(monkeypatch, tmp_path, capsys):
    pack = make_pack(tmp_path)
    consumed = []

    class ReconcilingOrchestrator:
        def __init__(self, supplied_pack):
            assert supplied_pack is pack
            self.state = {"phase": "RESEARCHER", "cycle": 1}

        def reconcile_state(self):
            self.state["phase"] = "DREAMER"

        def run(self, **_kwargs):
            pytest.fail("phase mismatch must block before run")

    monkeypatch.setattr(buildroom_loop, "resolve_project", lambda _project: pack)
    monkeypatch.setattr(buildroom_loop, "load_orchestrator_class", lambda: ReconcilingOrchestrator)
    monkeypatch.setattr(
        buildroom_loop,
        "consume_manual_authorization",
        lambda *_args, **_kwargs: consumed.append(True) or record(),
    )
    rc = buildroom_loop.main(argv("--authorization-id", "manual-auth-opaque"))
    assert rc == 4
    assert capsys.readouterr().err.strip() == "PROJECTPACK_NOT_READY"
    assert consumed == []
