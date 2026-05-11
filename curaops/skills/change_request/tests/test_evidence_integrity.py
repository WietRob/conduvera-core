"""Compliance Change Control evidence schema and hash-integrity tests."""

import json
from datetime import datetime, timezone
from pathlib import Path

from curaops.skills.change_request import ChangeRequestService
from curaops.skills.change_request.evidence import verify_evidence_file
from curaops.skills.change_request.models import RootCauseCategory, VerificationResult


def _approved_cr(tmp_path: Path, *, change_type="feature", refs=None):
    refs = refs or ["SW-REQ-500"]
    service = ChangeRequestService(
        changes_dir=tmp_path / "changes",
        evidence_dir=tmp_path / "changes" / "evidence",
    )
    cr = service.create_cr(
        title="CCC evidence integrity proof",
        requester="pytest",
        problem="Evidence must be structurally correct and hash-verifiable",
        justification="Review readiness requires deterministic evidence integrity",
        change_type=change_type,
        requirement_linkage_type="existing_ref",
        impact_level=["SW"],
        requirement_refs=refs,
        safety_impact="none",
    )
    service.submit_cr(cr.id, actor="pytest")
    service.approve_cr(cr.id, reviewer="pytest", comment="approved")
    return service, cr.id


def test_generic_c_evidence_contains_required_schema_fields(tmp_path):
    service, cr_id = _approved_cr(tmp_path)

    path = service.generate_evidence(cr_id)
    evidence = json.loads(path.read_text(encoding="utf-8"))

    assert evidence["schema_version"] == "CCC-1.1.0"
    assert evidence["cr_id"] == cr_id
    assert evidence["status"] == "approved"
    assert evidence["change_type"] == "feature"
    assert evidence["requirement_linkage_type"] == "existing_ref"
    assert evidence["requirement_refs"] == ["SW-REQ-500"]
    assert evidence["impact_level"] == ["SW"]
    assert evidence["safety_impact"] == "none"
    assert evidence["affected_files"] == []
    assert evidence["affected_verifications"] == []
    assert evidence["generated_at"]
    assert evidence["generated_at"].endswith("Z")
    assert "+00:00Z" not in evidence["generated_at"]
    assert evidence["timestamp"] == evidence["generated_at"]
    assert evidence["integrity"]["algorithm"] == "sha256"
    assert evidence["integrity"]["hash_excludes"] == ["hash", "integrity.hash"]
    assert evidence["integrity"]["hash"].startswith("sha256:")


def test_verification_result_timestamp_is_canonical_utc(tmp_path):
    service, cr_id = _approved_cr(tmp_path)
    cr = service.get_cr(cr_id)
    result = VerificationResult(
        verification_case_id="TC-UT-500",
        result="PASS",
        executed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        output="ok",
        validates=["SW-REQ-500"],
    )

    evidence = service.evidence_gen.generate_to_dict(cr, [result])

    assert evidence["verification_results"][0]["executed_at"] == "2026-01-02T03:04:05Z"


def test_bugfix_c_evidence_contains_root_cause_and_verifications(tmp_path):
    service, cr_id = _approved_cr(tmp_path, change_type="bugfix", refs=["SW-REQ-501"])
    cr = service.get_cr(cr_id)
    cr.root_cause_category = RootCauseCategory.IMPL_BUG
    cr.affected_files = ["src/fix.py"]
    cr.affected_verifications = ["TC-SVT-501"]
    service.persistence.save(cr)

    evidence = json.loads(service.generate_evidence(cr_id).read_text(encoding="utf-8"))

    assert evidence["change_type"] == "bugfix"
    assert evidence["root_cause_category"] == "impl_bug"
    assert evidence["affected_files"] == ["src/fix.py"]
    assert evidence["affected_verifications"] == ["TC-SVT-501"]
    assert evidence["regression_verification_ids"] == ["TC-SVT-501"]


def test_c_evidence_hash_verification_matches_generated_payload(tmp_path):
    service, cr_id = _approved_cr(tmp_path)
    path = service.generate_evidence(cr_id)

    result = verify_evidence_file(path)

    assert result["valid"] is True
    assert result["stored_hash"] == result["computed_hash"]
    assert result["reason"] is None


def test_c_evidence_hash_verification_detects_tampering(tmp_path):
    service, cr_id = _approved_cr(tmp_path)
    path = service.generate_evidence(cr_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["requirement_refs"] = ["SW-REQ-TAMPERED"]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = verify_evidence_file(path)

    assert result["valid"] is False
    assert result["stored_hash"] != result["computed_hash"]
    assert result["reason"] == "hash_mismatch"


def test_c_evidence_hash_verification_reports_missing_and_invalid(tmp_path):
    missing = verify_evidence_file(tmp_path / "missing.json")
    assert missing["valid"] is False
    assert missing["reason"] == "missing_file"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not-json", encoding="utf-8")
    invalid = verify_evidence_file(invalid_path)
    assert invalid["valid"] is False
    assert invalid["reason"] == "invalid_json"
