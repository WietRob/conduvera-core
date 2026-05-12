"""
Tests for ASPICE Link Manager
"""

import pytest
import shutil
import json
from pathlib import Path

from curaops.skills.aspice_link_manager import ASPICELinkManager


class TestASPICELinkManager:
    """Test ASPICE Link Manager functionality."""

    def setup_method(self):
        """Setup for each test."""
        self.test_dir = Path("/tmp/test_aspice_manager")
        self.test_dir.mkdir(parents=True, exist_ok=True)

        # Create directory structure
        (self.test_dir / "requirements").mkdir(exist_ok=True)
        (self.test_dir / "tests").mkdir(exist_ok=True)

        self.manager = ASPICELinkManager(root_dir=self.test_dir)

    def teardown_method(self):
        """Cleanup after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_doc(self, path: Path, doc_id: str, title: str, **kwargs):
        """Helper to create a requirement document."""
        data = {
            "id": doc_id,
            "title": title,
            **kwargs
        }
        content = f"""```json
{json.dumps(data, indent=2)}
```

# {title}

Description of {doc_id}.
"""
        path.write_text(content, encoding="utf-8")

    def test_parse_document_valid(self):
        """AC1: Parse valid document with JSON frontmatter."""
        doc_file = self.test_dir / "requirements" / "SW-REQ-001.md"
        self._create_doc(
            doc_file,
            "SW-REQ-001",
            "User Authentication",
            refined_from=["SYS-REQ-001"],
            refined_in=["SW-REQ-002"],
        )

        doc = self.manager.parse_document(doc_file)

        assert doc is not None
        assert doc.id == "SW-REQ-001"
        assert doc.title == "User Authentication"
        assert doc.refined_from == ["SYS-REQ-001"]
        assert doc.refined_in == ["SW-REQ-002"]

    def test_parse_document_no_frontmatter(self):
        """AC2: Document without frontmatter returns None."""
        doc_file = self.test_dir / "requirements" / "no_frontmatter.md"
        doc_file.write_text("# Just a title\n\nNo JSON frontmatter here.")

        doc = self.manager.parse_document(doc_file)

        assert doc is None

    def test_find_document(self):
        """AC3: Find document by ID."""
        doc_file = self.test_dir / "requirements" / "SW-REQ-001.md"
        self._create_doc(doc_file, "SW-REQ-001", "Test Requirement")

        found = self.manager.find_document("SW-REQ-001")

        assert found == doc_file

    def test_find_document_not_found(self):
        """AC4: Find non-existent document returns None."""
        found = self.manager.find_document("NON-EXISTENT")

        assert found is None

    def test_update_bidirectional_links(self):
        """AC5: Update bidirectional links."""
        # Create parent document
        parent_file = self.test_dir / "requirements" / "SYS-REQ-001.md"
        self._create_doc(parent_file, "SYS-REQ-001", "System Requirement")

        # Create child document with link to parent
        child_file = self.test_dir / "requirements" / "SW-REQ-001.md"
        self._create_doc(
            child_file,
            "SW-REQ-001",
            "Software Requirement",
            refined_from=["SYS-REQ-001"]
        )

        # Update links
        result = self.manager.update_bidirectional_links(child_file)

        assert result.success
        assert result.updated_count >= 1

        # Verify parent now has child in refined_in
        parent_doc = self.manager.parse_document(parent_file)
        assert "SW-REQ-001" in parent_doc.refined_in

    def test_verify_links_consistent(self):
        """AC6: Verify consistent links returns no errors."""
        # Create properly linked documents
        parent_file = self.test_dir / "requirements" / "SYS-REQ-001.md"
        self._create_doc(
            parent_file,
            "SYS-REQ-001",
            "Parent",
            refined_in=["SW-REQ-001"]
        )

        child_file = self.test_dir / "requirements" / "SW-REQ-001.md"
        self._create_doc(
            child_file,
            "SW-REQ-001",
            "Child",
            refined_from=["SYS-REQ-001"]
        )

        errors = self.manager.verify_links(child_file)

        assert len(errors) == 0

    def test_verify_links_inconsistent(self):
        """AC7: Verify inconsistent links returns errors."""
        # Create documents with non-reciprocal links
        parent_file = self.test_dir / "requirements" / "SYS-REQ-001.md"
        self._create_doc(parent_file, "SYS-REQ-001", "Parent")  # No refined_in

        child_file = self.test_dir / "requirements" / "SW-REQ-001.md"
        self._create_doc(
            child_file,
            "SW-REQ-001",
            "Child",
            refined_from=["SYS-REQ-001"]  # Claims parent, but parent doesn't acknowledge
        )

        errors = self.manager.verify_links(child_file)

        assert len(errors) > 0
        assert any("not reciprocal" in e for e in errors)

    def test_generate_traceability_matrix(self):
        """AC8: Generate traceability matrix."""
        # Create some documents
        self._create_doc(
            self.test_dir / "requirements" / "SYS-REQ-001.md",
            "SYS-REQ-001",
            "System Req",
            refined_in=["SW-REQ-001"]
        )

        self._create_doc(
            self.test_dir / "requirements" / "SW-REQ-001.md",
            "SW-REQ-001",
            "Software Req",
            refined_from=["SYS-REQ-001"],
            validated_by=["TEST-001"],
        )

        self._create_doc(
            self.test_dir / "tests" / "TEST-001.md",
            "TEST-001",
            "Test Case",
        )

        matrix = self.manager.generate_traceability_matrix()

        assert matrix["coverage"]["total_requirements"] == 3
        assert matrix["coverage"]["with_tests"] == 1
        assert "SYS-REQ-001" in matrix["links"]
        assert "SW-REQ-001" in matrix["links"]

    def test_save_traceability_matrix(self):
        """AC9: Save traceability matrix to file."""
        self._create_doc(
            self.test_dir / "requirements" / "REQ-001.md",
            "REQ-001",
            "Requirement",
        )

        output_file = self.manager.save_traceability_matrix()

        assert output_file.exists()

        # Verify content
        data = json.loads(output_file.read_text())
        assert "generated_at" in data
        assert "requirements" in data
        assert "coverage" in data

    def test_update_links_missing_target(self):
        """AC10: Update links with missing target returns error."""
        doc_file = self.test_dir / "requirements" / "SW-REQ-001.md"
        self._create_doc(
            doc_file,
            "SW-REQ-001",
            "Requirement",
            refined_from=["NON-EXISTENT"]
        )

        result = self.manager.update_bidirectional_links(doc_file)

        assert not result.success
        assert any("NON-EXISTENT" in e for e in result.errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
