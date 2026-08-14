"""
Transportpfad-Tests für GitHubDeliveryProvider (close-conduvera-github-provider-transport-v3).

Testet den Provider-Transportpfad direkt an der `gh`-CLI-Grenze mit einer
fake-gh-argv-Senke (subprocess.run-Mock): Pagination, Schema-Validierung,
branch-protection Classification (contexts/checks/app_id/-1/case-insensitive),
legacy commit-statuses, Stale-Preservation und State-Ableitung.

Spec: docs/control-plane/DELIVERY_WORKSPACE.md (Provider/Sync-Kontrakt)

Verifizierte Properties:
- P1: Provider/Schema-Fehler sind nie leere Erfolge (GH_BAD_JSON propagiert)
- P2: Pagination über mehrere Seiten wird vollständig gelesen
- P3: branch exists + protection 404 => known-empty (PR_OPEN-fähig)
- P4: app_id-Bindung wird erzwungen; app_id == -1 = any-app
- P5: case-insensitive context-Matching
- P6: legacy commit-status erfüllt nur ungebundene Requirements
- P7: stale source preserviert durable negative facts (kein MERGE_READY)
- P8: frisch erstelltes PR ist PR_OPEN/CI_PENDING, nie sofort MERGE_READY
"""

from __future__ import annotations

import json
import subprocess

import pytest

from conduvera.control_plane.github_provider import (
    GitHubDeliveryError,
    GitHubDeliveryProvider,
)


def _gh_ok(data):
    """Payload-Value: ein dict/list wird als JSON serialisiert."""
    return data


class _FakeProc:
    def __init__(self, payload):
        if isinstance(payload, Exception):
            raise payload
        self.returncode = 0
        self.stdout = json.dumps(payload) if not isinstance(payload, str) else payload
        self.stderr = ""


def _mock_subprocess(script, monkeypatch):
    def _run(argv, **kw):
        key = " ".join(argv)
        for pattern, payload in script.items():
            if key.startswith(pattern):
                return _FakeProc(payload)
        raise GitHubDeliveryError("GH_UNMAPPED", f"no fixture for: {key}")
    monkeypatch.setattr(subprocess, "run", _run)


def _provider_with_argv(script, monkeypatch):
    _mock_subprocess(script, monkeypatch)
    return GitHubDeliveryProvider(gh_bin="gh", dry_run=False)


# ---- T01: paginated check-runs across multiple pages ----------------------
def test_t01_paginated_check_runs_multiple_pages(monkeypatch):
    p1 = {"check_runs": [{"name": "a", "status": "completed",
                          "conclusion": "success", "app": {"name": "x", "id": 1}}]}
    p2 = {"check_runs": [{"name": "b", "status": "completed",
                          "conclusion": "failure", "app": {"name": "y", "id": 2}}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [p1, p2],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [{"statuses": []}],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [{"required_status_checks": {}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    runs = [c for c in checks if c["app"] != "commit-status"]
    assert {c["name"] for c in runs} == {"a", "b"}
    assert len(runs) == 2


# ---- T02: malformed check-runs page -> GH_BAD_JSON ------------------------
def test_t02_malformed_check_page_propagates(monkeypatch):
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": ["not-an-object"],
    }, monkeypatch)
    with pytest.raises(GitHubDeliveryError) as ei:
        prov.list_checks("r", "h")
    assert ei.value.code == "GH_BAD_JSON"


# ---- T03: provider failure (gh missing) -> GH_LAUNCH ----------------------
def test_t03_launch_failure_propagates(monkeypatch):
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": OSError("no gh"),
    }, monkeypatch)
    with pytest.raises(GitHubDeliveryError) as ei:
        prov.list_checks("r", "h")
    assert ei.value.code == "GH_LAUNCH"


# ---- T04: branch exists + protection 404 => known empty -------------------
def test_t04_protection_404_known_empty(monkeypatch):
    err = GitHubDeliveryError("GH_HTTP_404", "HTTP 404: Not Found")
    prov = _provider_with_argv({
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": err,
    }, monkeypatch)
    requirements, known = prov.required_status_checks("r", "main")
    assert requirements == {}
    assert known is True


# ---- T05: other protection failure propagates (stale) ---------------------
def test_t05_protection_other_failure_propagates(monkeypatch):
    err = GitHubDeliveryError("GH_HTTP_403", "HTTP 403: Forbidden")
    prov = _provider_with_argv({
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": err,
    }, monkeypatch)
    with pytest.raises(GitHubDeliveryError):
        prov.required_status_checks("r", "main")


# ---- T06: app-bound required check ----------------------------------------
def test_t06_app_bound_required_check(monkeypatch):
    p = {"check_runs": [{"name": "build", "status": "completed",
                         "conclusion": "success", "app": {"name": "wrong", "id": 999}}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [p],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [{"statuses": []}],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [
            {"required_status_checks": {"checks": [{"context": "build", "app_id": 123}]}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    build = next(c for c in checks if c["name"] == "build")
    assert build["required"] is False  # wrong app must NOT satisfy
    assert build["required_missing"] == ["build"]


# ---- T07: app_id == -1 means any app --------------------------------------
def test_t07_app_id_neg1_any_app(monkeypatch):
    p = {"check_runs": [{"name": "build", "status": "completed",
                         "conclusion": "success", "app": {"name": "real", "id": 7}}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [p],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [{"statuses": []}],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [
            {"required_status_checks": {"checks": [{"context": "build", "app_id": -1}]}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    build = next(c for c in checks if c["name"] == "build")
    assert build["required"] is True
    assert build["required_missing"] == []


# ---- T08: case-insensitive context matching -------------------------------
def test_t08_case_insensitive_context(monkeypatch):
    p = {"check_runs": [{"name": "ci/build", "status": "completed",
                         "conclusion": "success", "app": {"name": "a", "id": 1}}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [p],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [{"statuses": []}],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [
            {"required_status_checks": {"contexts": ["CI/Build"]}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    build = next(c for c in checks if c["name"] == "ci/build")
    assert build["required"] is True
    assert build["required_missing"] == []


# ---- T09: legacy commit-status satisfies only unbound requirement ---------
def test_t09_legacy_status_unbound_only(monkeypatch):
    p = {"statuses": [{"context": "ci/legacy", "state": "success",
                       "updated_at": "2026-01-01T00:00:00Z"}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [{"check_runs": []}],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [p],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [
            {"required_status_checks": {"contexts": ["ci/legacy"]}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    status = next(c for c in checks if c["app"] == "commit-status")
    assert status["required"] is True
    assert status["required_missing"] == []


# ---- T10: app-bound requirement not satisfied by legacy status ------------
def test_t10_legacy_status_not_app_bound(monkeypatch):
    p = {"statuses": [{"context": "build", "state": "success",
                       "updated_at": "2026-01-01T00:00:00Z"}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [{"check_runs": []}],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [p],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [
            {"required_status_checks": {"checks": [{"context": "build", "app_id": 123}]}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    status = next(c for c in checks if c["app"] == "commit-status")
    assert status["required"] is False
    assert "build" in status["required_missing"]


# ---- T11: unknown status state never defaults to success ------------------
def test_t11_unknown_status_non_green(monkeypatch):
    p = {"statuses": [{"context": "ci/x", "state": "weird", "updated_at": "2026-01-01"}]}
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/check-runs?per_page=100": [{"check_runs": []}],
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": [p],
        "gh api repos/r/branches/main --jq .name": "main",
        "gh api --paginate --slurp repos/r/branches/main/protection": [{"required_status_checks": {}}],
    }, monkeypatch)
    checks = prov.list_checks("r", "h", base_branch="main")
    status = next(c for c in checks if c["app"] == "commit-status")
    assert status["conclusion"] == "pending"  # non-green, not success


# ---- T12: malformed review row propagates --------------------------------
def test_t12_malformed_review_row(monkeypatch):
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/pulls/1/reviews?per_page=100": [[None]],
    }, monkeypatch)
    with pytest.raises(GitHubDeliveryError) as ei:
        prov.list_reviews("r", 1)
    assert ei.value.code == "GH_BAD_JSON"


# ---- T13: malformed commit-status page propagates -------------------------
def test_t13_malformed_commit_status_page(monkeypatch):
    prov = _provider_with_argv({
        "gh api --paginate --slurp repos/r/commits/h/status?per_page=100": ["not-obj"],
    }, monkeypatch)
    with pytest.raises(GitHubDeliveryError) as ei:
        prov._commit_statuses("r", "h")
    assert ei.value.code == "GH_BAD_JSON"


# ---- T14: stale preservation (service-level) ------------------------------
def test_t14_stale_preserves_durable_negative(tmp_path):
    from conduvera.control_plane.delivery_store import DeliveryStore
    from conduvera.control_plane.evidence_store import EvidenceStore
    from conduvera.control_plane.delivery_service import DeliveryService
    store = DeliveryStore(tmp_path / "d")
    ev = EvidenceStore(tmp_path / "e")
    dlv = DeliveryService(store=store, evidence_store=ev,
                          provider=GitHubDeliveryProvider(dry_run=True))
    rec = dlv._new_record("job_1", "a1")
    rec["github_repository"] = "r"
    rec["pull_request_number"] = 1
    rec["checks_summary"] = {"required_failed": True}
    rec["delivery_state"] = "CI_FAILED"
    store.save(rec)
    def _fail(*a, **k):
        raise GitHubDeliveryError("GH_ERROR", "boom")
    dlv.provider.pr_view = lambda repo, num: {"state": "OPEN", "headRefOid": "h" * 40,
                                              "baseRefOid": "b" * 40}
    dlv.provider.list_checks = _fail
    dlv.provider.list_reviews = lambda repo, num, **k: []
    synced = dlv._sync_record(rec)
    assert synced["availability"]["checks"] == "stale"
    assert synced["checks_summary"]["required_failed"] is True  # preserved
    assert dlv._state_from_sync(synced) == "CI_FAILED"


# ---- T15: stale never yields MERGE_READY ----------------------------------
def test_t15_stale_not_merge_ready(tmp_path):
    from conduvera.control_plane.delivery_store import DeliveryStore
    from conduvera.control_plane.evidence_store import EvidenceStore
    from conduvera.control_plane.delivery_service import DeliveryService
    store = DeliveryStore(tmp_path / "d")
    ev = EvidenceStore(tmp_path / "e")
    dlv = DeliveryService(store=store, evidence_store=ev,
                          provider=GitHubDeliveryProvider(dry_run=True))
    rec = dlv._new_record("job_1", "a1")
    rec["github_repository"] = "r"
    rec["pull_request_number"] = 1
    store.save(rec)
    def _fail(*a, **k):
        raise GitHubDeliveryError("GH_ERROR", "boom")
    dlv.provider.pr_view = lambda repo, num: {"state": "OPEN", "headRefOid": "h" * 40,
                                              "baseRefOid": "b" * 40}
    dlv.provider.list_checks = _fail
    dlv.provider.list_reviews = _fail
    synced = dlv._sync_record(rec)
    assert synced["availability"]["checks"] == "stale"
    assert dlv._state_from_sync(synced) != "MERGE_READY"


# ---- T16: freshly created PR never immediately MERGE_READY ----------------
def test_t16_fresh_pr_not_immediately_merge_ready(tmp_path):
    from conduvera.control_plane.delivery_store import DeliveryStore
    from conduvera.control_plane.evidence_store import EvidenceStore
    from conduvera.control_plane.delivery_service import DeliveryService
    store = DeliveryStore(tmp_path / "d")
    ev = EvidenceStore(tmp_path / "e")
    dlv = DeliveryService(store=store, evidence_store=ev,
                          provider=GitHubDeliveryProvider(dry_run=True))
    rec = dlv._new_record("job_1", "a1")
    rec["github_repository"] = "r"
    rec["pull_request_number"] = 1
    store.save(rec)
    dlv.provider.pr_view = lambda repo, num: {"state": "OPEN", "headRefOid": "h" * 40,
                                              "baseRefOid": "b" * 40,
                                              "mergeStateStatus": "CLEAN",
                                              "mergeable": "MERGEABLE"}
    dlv.provider.list_checks = lambda repo, sha, **k: []
    dlv.provider.list_reviews = lambda repo, num, **k: []
    synced = dlv._sync_record(rec)
    assert dlv._state_from_sync(synced) == "PR_OPEN"


# ---- T17: real gh CLI smoke (live, guarded) -------------------------------
def test_t17_real_gh_cli_smoke():
    """Live smoke: gh api --paginate --slurp on a real endpoint."""
    r = subprocess.run(
        ["gh", "api", "--paginate", "--slurp",
         "repos/WietRob/conduvera-core/pulls?per_page=100&state=all"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert isinstance(data, list)  # --paginate --slurp returns a list


# ---- T18: missing/UNKNOWN merge metadata never yields MERGE_READY ----------
def test_t18_unknown_merge_metadata_not_merge_ready(tmp_path):
    from conduvera.control_plane.delivery_store import DeliveryStore
    from conduvera.control_plane.evidence_store import EvidenceStore
    from conduvera.control_plane.delivery_service import DeliveryService
    store = DeliveryStore(tmp_path / "d")
    ev = EvidenceStore(tmp_path / "e")
    dlv = DeliveryService(store=store, evidence_store=ev,
                          provider=GitHubDeliveryProvider(dry_run=True))
    rec = dlv._new_record("job_1", "a1")
    rec["github_repository"] = "r"
    rec["pull_request_number"] = 1
    store.save(rec)
    # green required check but UNKNOWN merge metadata
    dlv.provider.pr_view = lambda repo, num: {"state": "OPEN",
                                              "headRefOid": "h" * 40,
                                              "baseRefOid": "b" * 40,
                                              "mergeStateStatus": "UNKNOWN",
                                              "mergeable": "UNKNOWN"}
    dlv.provider.list_checks = lambda repo, sha, **k: [
        {"name": "build", "status": "completed", "conclusion": "success",
         "required": True, "required_known": True, "app": "a", "app_id": 1}]
    dlv.provider.list_reviews = lambda repo, num, **k: []
    synced = dlv._sync_record(rec)
    assert synced["checks_summary"]["required_by_status"]["success"] >= 1
    assert dlv._state_from_sync(synced) == "CI_PENDING"  # fail-closed


# ---- T19: fresh PR with pre-attached green check is NOT MERGE_READY --------
def test_t19_fresh_pr_green_check_not_merge_ready(tmp_path):
    from conduvera.control_plane.delivery_store import DeliveryStore
    from conduvera.control_plane.evidence_store import EvidenceStore
    from conduvera.control_plane.delivery_service import DeliveryService
    store = DeliveryStore(tmp_path / "d")
    ev = EvidenceStore(tmp_path / "e")
    dlv = DeliveryService(store=store, evidence_store=ev,
                          provider=GitHubDeliveryProvider(dry_run=True))
    rec = dlv._new_record("job_1", "a1")
    rec["github_repository"] = "r"
    rec["branch_name"] = "conduvera/job_1/a1"
    store.save(rec)
    pr = {"number": 1, "url": "http://x/pull/1", "headRefOid": "h" * 40,
          "baseRefOid": "b" * 40, "state": "OPEN", "mergeable": "MERGEABLE",
          "mergeStateStatus": "CLEAN"}
    # a green required check already exists on the head SHA
    dlv.provider.pr_view = lambda repo, num: pr
    dlv.provider.list_checks = lambda repo, sha, **k: [
        {"name": "build", "status": "completed", "conclusion": "success",
         "required": True, "required_known": True, "app": "a", "app_id": 1}]
    dlv.provider.list_reviews = lambda repo, num, **k: []
    wt = tmp_path / "wt"
    wt.mkdir()
    res = dlv._record_pr(rec, pr, "job_1", "a1", wt)
    assert res["record"]["delivery_state"] == "PR_OPEN"  # never MERGE_READY
