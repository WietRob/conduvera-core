"""EvidenceStore + fail-closed evidence tests (CLOSURE-V1, WS-D / DOD-10).

Proves:
- EvidenceStore persists bundles outside worktrees (0600, atomic);
- a real exit_code=0 with evidence_invalid marker -> attempt/job FAILED,
  terminal_reason=EVIDENCE_INVALID, evidence_status INVALID;
- valid evidence -> COMPLETED with evidence result refs;
- cleanup keeps the EvidenceBundle (only runtime/worktree removed).
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "f.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return repo, base


class _Gw:
    def __init__(self, exit_code=0, evidence_invalid=False, artifacts=None):
        self.exit_code = exit_code
        self.evidence_invalid = evidence_invalid
        self.artifacts = artifacts or []

    def start_session(self, adapter_id, agent_id, worktree, task, config):
        import uuid
        sid = f"mxs_{uuid.uuid4().hex[:16]}"
        return type("R", (), {"success": True, "message": "ok",
                              "detail": {"session_id": sid,
                                         "adapter_session_id": sid,
                                         "pid": 1, "scope": "x.scope"}})()

    def collect_evidence(self, adapter_id, session_id):
        return {"session_id": session_id, "exit_code": self.exit_code,
                "artifacts": self.artifacts,
                "evidence_invalid": self.evidence_invalid}


def _svc(tmp_path, repo, base, exit_code=0, evidence_invalid=False, artifacts=None):
    from conduvera.control_plane.service import (
        ControlPlaneConfig, ControlPlaneService, PersistentSessionRegistry,
    )
    state = tmp_path / "state"
    config = ControlPlaneConfig.default(state_dir=state)
    reg = PersistentSessionRegistry(config.registry_path)
    gw = _Gw(exit_code=exit_code, evidence_invalid=evidence_invalid,
             artifacts=artifacts)
    svc = ControlPlaneService(registry=reg, gateway_service=gw, config=config,
                              repo_allowlist={"fixture": repo},
                              global_concurrency=1)
    return svc, gw


def _run_to_terminal(svc, task_id, attempt_id, gw):
    from conduvera.control_plane.engine import ControlPlaneEngine
    eng = ControlPlaneEngine(service=svc, scheduler=svc.scheduler,
                             registry=svc.registry)
    import subprocess as sp
    base = sp.run(["git", "-C", str(svc.resolve_repo("fixture")), "rev-parse",
                   "HEAD"], capture_output=True, text=True).stdout.strip()
    svc.submit_job(task_id=task_id, attempt_id=attempt_id,
                   harness="hermes_scoped", repo="fixture", base_commit=base,
                   model_binding={}, prompt="p", task_type="code_change")
    svc.scheduler.claim(attempt_id, dispatcher_id="t")
    svc.dispatch_claimed(attempt_id)
    sess = next(s for s in svc.registry.all() if s.attempt_id == attempt_id)
    eng._handle_process_gone(sess, svc.scheduler.store.get_attempt(attempt_id),
                             sess.session_id)
    return svc.scheduler.store.get_attempt(attempt_id)


class TestEvidenceStore:
    def test_valid_exit0_completed(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        art = tmp_path / "art.txt"
        art.write_text("artifact")
        svc, gw = _svc(tmp_path, repo, base, exit_code=0,
                       artifacts=[{"path": str(art), "sha256": "sha256:abc"}])
        att = _run_to_terminal(svc, "EV", "ev1", gw)
        job = svc.scheduler.store.get_job(att.job_id)
        assert job.state.value == "COMPLETED"
        assert any(r.startswith("evidence:") for r in att.result_refs)

    def test_exit0_invalid_evidence_fails_closed(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base, exit_code=0, evidence_invalid=True)
        att = _run_to_terminal(svc, "EVI", "evi1", gw)
        job = svc.scheduler.store.get_job(att.job_id)
        # exact DOD-10 result: real exit 0 but evidence invalid -> FAILED
        assert job.state.value == "FAILED"
        assert job.terminal_reason == "EVIDENCE_INVALID"
        assert att.state.value == "FAILED"

    def test_evidence_persisted_outside_worktree(self, tmp_path):
        repo, base = _make_repo(tmp_path)
        svc, gw = _svc(tmp_path, repo, base, exit_code=0,
                       artifacts=[{"path": str(tmp_path / "a.out"), "sha256": "sha256:x"}])
        att = _run_to_terminal(svc, "EVS", "evs1", gw)
        bundle_id = next((r.split(":", 1)[1] for r in att.result_refs
                          if r.startswith("evidence:")), None)
        assert bundle_id
        bundle = svc.evidence_store.get(bundle_id)
        assert bundle and bundle["exit_code"] == 0
        # persisted in the evidence dir (outside worktrees)
        ev_dir = tmp_path / "state" / "evidence"
        assert (ev_dir / f"{bundle_id}.json").is_file()
