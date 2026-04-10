"""
Tests for Change Request Service
"""

import pytest
import shutil
from pathlib import Path
import sys
import os

# Add skill to path (use local matrix-os version)
sys.path.insert(0, str(Path(__file__).parent.parent))

from __init__ import (
    ChangeRequestService, 
    ChangeRequestError,
    generate_cr_evidence,
    validate_cr_traceability,
)


class TestChangeRequestService:
    """Test Change Request Service functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        self.test_dir = Path("/tmp/test_cr_service")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.service = ChangeRequestService(changes_path=self.test_dir / "changes")
    
    def teardown_method(self):
        """Cleanup after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_submit_cr_creates_file(self):
        """AC1: Submit CR creates Markdown file."""
        cr = self.service.submit_change_request(
            title="Test Feature",
            description="This is a test CR"
        )
        
        assert cr["cr_id"] == "CR-001"
        assert cr["title"] == "Test Feature"
        assert cr["status"] == "SUBMITTED"
        assert Path(cr["file_path"]).exists()
    
    def test_submit_cr_empty_title_raises_error(self):
        """AC2: Empty title raises error."""
        with pytest.raises(ChangeRequestError, match="Title cannot be empty"):
            self.service.submit_change_request(title="", description="Test")
    
    def test_submit_cr_empty_description_raises_error(self):
        """AC3: Empty description raises error."""
        with pytest.raises(ChangeRequestError, match="Description cannot be empty"):
            self.service.submit_change_request(title="Test", description="")
    
    def test_submit_multiple_crs_increment_ids(self):
        """AC4: Multiple CRs get incrementing IDs."""
        cr1 = self.service.submit_change_request("Feature 1", "Desc 1")
        cr2 = self.service.submit_change_request("Feature 2", "Desc 2")
        cr3 = self.service.submit_change_request("Feature 3", "Desc 3")
        
        assert cr1["cr_id"] == "CR-001"
        assert cr2["cr_id"] == "CR-002"
        assert cr3["cr_id"] == "CR-003"
    
    def test_get_pending_requests(self):
        """AC5: Get pending returns SUBMITTED CRs."""
        self.service.submit_change_request("CR1", "Desc1")
        self.service.submit_change_request("CR2", "Desc2")
        
        pending = self.service.get_pending_requests()
        
        assert len(pending) == 2
        assert all(cr["status"] == "SUBMITTED" for cr in pending)
    
    def test_process_change_request_approve(self):
        """AC6: Process CR updates status to APPROVED."""
        cr = self.service.submit_change_request("Test", "Desc")
        
        result = self.service.process_change_request(cr["cr_id"], "APPROVED")
        
        assert result["success"] == True
        assert result["status"] == "APPROVED"
        
        # Verify file was updated
        updated = self.service.get_cr_status(cr["cr_id"])
        assert updated["status"] == "APPROVED"
    
    def test_process_change_request_invalid_transition(self):
        """AC7: Invalid status transition returns error."""
        cr = self.service.submit_change_request("Test", "Desc")
        
        # Cannot go from SUBMITTED to IMPLEMENTED (must go through APPROVED and IN_PROGRESS)
        result = self.service.process_change_request(cr["cr_id"], "IMPLEMENTED")
        
        assert result["success"] == False
        assert "Invalid transition" in result["error"]
    
    def test_get_requests_by_status(self):
        """AC8: Get by status returns matching CRs."""
        cr1 = self.service.submit_change_request("CR1", "Desc1")
        cr2 = self.service.submit_change_request("CR2", "Desc2")
        
        # Approve first CR
        self.service.process_change_request(cr1["cr_id"], "APPROVED")
        
        submitted = self.service.get_requests_by_status("SUBMITTED")
        approved = self.service.get_requests_by_status("APPROVED")
        
        assert len(submitted) == 1
        assert len(approved) == 1
        assert submitted[0]["cr_id"] == cr2["cr_id"]
        assert approved[0]["cr_id"] == cr1["cr_id"]
    
    def test_get_all_requests(self):
        """AC9: Get all returns all CRs regardless of status."""
        cr1 = self.service.submit_change_request("CR1", "Desc1")
        cr2 = self.service.submit_change_request("CR2", "Desc2")
        self.service.process_change_request(cr1["cr_id"], "APPROVED")
        
        all_crs = self.service.get_all_requests()
        
        assert len(all_crs) == 2
    
    def test_get_cr_status_not_found(self):
        """AC10: Get status for non-existent CR returns error."""
        result = self.service.get_cr_status("CR-999")
        
        assert result["success"] == False
        assert "not found" in result["error"]
    
    def test_status_workflow_complete(self):
        """AC11: Complete workflow SUBMITTED → CLOSED."""
        cr = self.service.submit_change_request("Test Workflow", "Desc")
        cr_id = cr["cr_id"]
        
        # SUBMITTED → APPROVED
        result = self.service.process_change_request(cr_id, "APPROVED")
        assert result["success"] == True
        
        # APPROVED → IN_PROGRESS
        result = self.service.process_change_request(cr_id, "IN_PROGRESS")
        assert result["success"] == True
        
        # IN_PROGRESS → IMPLEMENTED
        result = self.service.process_change_request(cr_id, "IMPLEMENTED")
        assert result["success"] == True
        
        # IMPLEMENTED → CLOSED
        result = self.service.process_change_request(cr_id, "CLOSED")
        assert result["success"] == True
        
        # Verify final status
        final = self.service.get_cr_status(cr_id)
        assert final["status"] == "CLOSED"
    
    def test_reject_and_reopen(self):
        """AC12: Can reject and reopen CR."""
        cr = self.service.submit_change_request("Test", "Desc")
        cr_id = cr["cr_id"]
        
        # Reject
        result = self.service.process_change_request(cr_id, "REJECTED")
        assert result["success"] == True
        
        # Reopen
        result = self.service.process_change_request(cr_id, "SUBMITTED")
        assert result["success"] == True
        
        final = self.service.get_cr_status(cr_id)
        assert final["status"] == "SUBMITTED"


class TestComplianceCRFeatures:
    """Test Compliance-CR specific features (C Context)."""
    
    def setup_method(self):
        """Setup for each test."""
        self.test_dir = Path("/tmp/test_compliance_cr")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.service = ChangeRequestService(changes_path=self.test_dir / "changes")
    
    def teardown_method(self):
        """Cleanup after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_submit_cr_with_requirement_refs(self):
        """C-AC1: Submit CR with requirement references."""
        cr = self.service.submit_change_request(
            title="Test Feature with Requirements",
            description="This CR links to requirements",
            requirement_refs=["SW-REQ-001", "SYS-REQ-042", "ARCH-003"]
        )
        
        assert cr["cr_id"] == "CR-001"
        assert "requirement_refs" in cr
        assert cr["requirement_refs"] == ["SW-REQ-001", "SYS-REQ-042", "ARCH-003"]
        
        # Verify requirements are in the Markdown file
        md_file = Path(cr["file_path"])
        content = md_file.read_text()
        assert "## Requirement References" in content
        assert "- SW-REQ-001" in content
        assert "- SYS-REQ-042" in content
        assert "- ARCH-003" in content
    
    def test_submit_cr_without_requirement_refs(self):
        """C-AC2: Submit CR without requirements (backward compatible)."""
        cr = self.service.submit_change_request(
            title="Test Feature",
            description="This CR has no requirements yet"
        )
        
        assert cr["requirement_refs"] == []
        
        # Verify placeholder in Markdown
        md_file = Path(cr["file_path"])
        content = md_file.read_text()
        assert "## Requirement References" in content
        assert "- (TBD)" in content
    
    def test_generate_cr_evidence_json(self):
        """C-AC3: Generate JSON evidence for CR."""
        # generate_cr_evidence already imported at top
        
        # Create a CR with requirements
        cr = self.service.submit_change_request(
            title="Feature with Evidence",
            description="Test description",
            requirement_refs=["SW-REQ-001"]
        )
        
        # Generate evidence
        result = generate_cr_evidence(
            project_path=str(self.test_dir),
            cr_id=cr["cr_id"],
            output_format="json"
        )
        
        assert "✅ Evidence generated" in result
        assert "CR-001_evidence.json" in result
        
        # Verify evidence file exists
        evidence_file = self.test_dir / "changes" / "evidence" / "CR-001_evidence.json"
        assert evidence_file.exists()
        
        # Verify content
        import json
        evidence = json.loads(evidence_file.read_text())
        assert evidence["cr_id"] == "CR-001"
        assert evidence["title"] == "Feature with Evidence"
        assert evidence["status"] == "SUBMITTED"
        assert evidence["requirement_references"] == ["SW-REQ-001"]
        assert evidence["evidence_format"] == "compliance-cr-v1.0"
    
    def test_validate_cr_traceability_no_refs(self):
        """C-AC4: Validate CR without requirement refs shows warning."""
        # validate_cr_traceability already imported at top
        
        # Create a CR without requirements
        cr = self.service.submit_change_request(
            title="Feature without Requirements",
            description="Test description"
        )
        
        # Validate
        result = validate_cr_traceability(
            project_path=str(self.test_dir),
            cr_id=cr["cr_id"]
        )
        
        assert "No requirement references found" in result
    
    def test_validate_cr_traceability_with_refs_no_aspice(self):
        """C-AC5: Validate CR with refs when ASPICE Link Manager not available."""
        # validate_cr_traceability already imported at top
        
        # Create a CR with requirements
        cr = self.service.submit_change_request(
            title="Feature with Requirements",
            description="Test description",
            requirement_refs=["SW-REQ-001", "SYS-REQ-042"]
        )
        
        # Validate (ASPICE Link Manager may not be available in test)
        result = validate_cr_traceability(
            project_path=str(self.test_dir),
            cr_id=cr["cr_id"]
        )
        
        # Should show requirements but warn about ASPICE
        assert "SW-REQ-001" in result or "ASPICE Link Manager not available" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
