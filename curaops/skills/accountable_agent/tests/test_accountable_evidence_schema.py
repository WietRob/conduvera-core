"""Evidence schema conformance tests for Accountable Agent Layer."""

import json
from pathlib import Path

from curaops.skills.accountable_agent import (
    AccountableAgentService,
    AgentContext,
    ChangeIntent,
)
from curaops.skills.change_request import ChangeRequestService
from curaops.skills.change_request.models import RootCauseCategory


def _approved_cr(tmp_path: Path, *, change_type="feature", refs=None):
    refs = refs or ["SW-REQ-200"]
    service = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    )
    cr = service.create_cr(
        title="Evidence schema proof",
        requester="pytest",
        problem="Evidence schema drift",
        justification="Review-ready evidence conformance",
        change_type=change_type,
        requirement_linkage_type="existing_ref",
        impact_level=["SW"],
        requirement_refs=refs,
        safety_impact="none",
    )
    service.submit_cr(cr.id, actor="pytest")
    service.approve_cr(cr.id, reviewer="pytest", comment="approved")
    return service, cr.id


def _register(service: AccountableAgentService, cr_id: str, *, change_type="feature", refs=None):
    refs = refs or ["SW-REQ-200"]
    return service.register_accountable_change(
        agent_context=AgentContext(
            agent_id="agent-evidence-test",
            agent_name="Evidence Test Agent",
            model="test-model",
            tools_used=["pytest"],
            session_id="sess-evidence-test",
        ),
        change_intent=ChangeIntent(
            description="Evidence schema proof",
            change_type=change_type,
            files_affected=["src/example.py"],
            estimated_impact="SW",
        ),
        cr_id=cr_id,
        requirement_refs=refs,
        strict=True,
    )


def _load_evidence(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_generic_accountable_evidence_matches_contract(tmp_path):
    _, cr_id = _approved_cr(tmp_path)
    service = AccountableAgentService(project_root=tmp_path)
    ac = _register(service, cr_id)

    evidence = _load_evidence(service.generate_accountability_evidence(ac.accountable_id))

    assert evidence["schema_version"] == "AAL-1.0.0"
    assert evidence["accountable_change"]["agent_context"]["agent_id"] == "agent-evidence-test"
    assert evidence["accountable_change"]["change_intent"]["change_type"] == "feature"
    assert evidence["accountable_change"]["accountability_links"] == {
        "cr_id": cr_id,
        "requirement_refs": ["SW-REQ-200"],
    }
    assert evidence["validation"]["valid"] is True
    assert evidence["bugfix_context"] is None
    assert evidence["referenced_c_evidence"]["available"] is True
    assert evidence["referenced_c_evidence"]["integrity_verified"] is True
    assert evidence["referenced_c_evidence"]["verification"]["valid"] is True
    assert evidence["referenced_c_evidence"]["hash"].startswith("sha256:")
    assert evidence["referenced_c_evidence"]["cr_evidence_path"]
    assert evidence["evidence_chain"]["linked_cr"].endswith(f"changes/{cr_id}.md")
    assert evidence["evidence_chain"]["linked_cr_evidence"] == evidence["referenced_c_evidence"]["cr_evidence_path"]


def test_bugfix_accountable_evidence_includes_c_metadata(tmp_path):
    cr_service, cr_id = _approved_cr(tmp_path, change_type="bugfix", refs=["SW-REQ-201"])
    cr = cr_service.get_cr(cr_id)
    cr.root_cause_category = RootCauseCategory.IMPL_BUG
    cr.affected_verifications = ["TC-SVT-201"]
    cr_service.persistence.save(cr)

    service = AccountableAgentService(project_root=tmp_path)
    ac = _register(service, cr_id, change_type="bugfix", refs=["SW-REQ-201"])

    evidence = _load_evidence(service.generate_accountability_evidence(ac.accountable_id))
    bugfix = evidence["bugfix_context"]

    assert evidence["accountable_change"]["change_intent"]["change_type"] == "bugfix"
    assert bugfix["change_type"] == "bugfix"
    assert bugfix["requirement_linkage_type"] == "existing_ref"
    assert bugfix["root_cause_category"] == "impl_bug"
    assert bugfix["regression_verification_ids"] == ["TC-SVT-201"]
    assert bugfix["regression_verification_semantics"] == "linked_from_cr_affected_verifications"
    assert bugfix["escalation_triggers_met"] == []
    assert evidence["referenced_c_evidence"]["available"] is True


def test_bugfix_evidence_uses_explicit_empty_regression_list_when_none(tmp_path):
    _, cr_id = _approved_cr(tmp_path, change_type="bugfix", refs=["SW-REQ-202"])
    service = AccountableAgentService(project_root=tmp_path)
    ac = _register(service, cr_id, change_type="bugfix", refs=["SW-REQ-202"])

    evidence = _load_evidence(service.generate_accountability_evidence(ac.accountable_id))
    bugfix = evidence["bugfix_context"]

    assert bugfix["regression_verification_ids"] == []
    assert bugfix["regression_verification_semantics"] == "no_regression_verification_linked_on_cr"
    assert any("No regression VerificationCase linked" in warning for warning in bugfix["warnings"])


def test_tampered_c_evidence_is_not_marked_verified(tmp_path, monkeypatch):
    _, cr_id = _approved_cr(tmp_path)
    service = AccountableAgentService(project_root=tmp_path)
    ac = _register(service, cr_id)
    c_path = service.cr_service.generate_evidence(cr_id)
    data = json.loads(Path(c_path).read_text(encoding="utf-8"))
    data["requirement_refs"] = ["SW-REQ-TAMPERED"]
    Path(c_path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    monkeypatch.setattr(service.cr_service, "generate_evidence", lambda _cr_id: c_path)
    evidence = _load_evidence(service.generate_accountability_evidence(ac.accountable_id))

    ref = evidence["referenced_c_evidence"]
    assert ref["available"] is False
    assert ref["integrity_verified"] is False
    assert ref["verification"]["valid"] is False
    assert ref["unavailable_reason"] == "hash_mismatch"
    assert evidence["evidence_chain"]["chain_integrity"] == "incomplete"


def test_c_evidence_unavailable_is_explicit(tmp_path, monkeypatch):
    _, cr_id = _approved_cr(tmp_path)
    service = AccountableAgentService(project_root=tmp_path)
    ac = _register(service, cr_id)

    def fail_generate(_cr_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.cr_service, "generate_evidence", fail_generate)
    evidence = _load_evidence(service.generate_accountability_evidence(ac.accountable_id))

    assert evidence["referenced_c_evidence"] == {
        "available": False,
        "cr_evidence_path": None,
        "integrity_verified": False,
        "hash": None,
        "verification": None,
        "unavailable_reason": "boom",
    }
    assert evidence["cr_evidence_path"] is None
