"""Tests for ASPICE Conflict Detector.

Validated by: TC-UT-095
"""

import tempfile
from pathlib import Path

import pytest

from curaops.skills.aspice_conflict_detector import (
    Conflict,
    ConflictDetector,
    ConflictType,
    Severity,
)


class TestConflictTypes:
    """Test conflict type enum."""

    def test_conflict_type_values(self):
        """Test that all conflict types exist."""
        assert ConflictType.REQUIREMENTS_VS_CODE_DRIFT == "REQUIREMENTS_VS_CODE_DRIFT"
        assert ConflictType.MISSING_TRACEABILITY == "MISSING_TRACEABILITY"
        assert ConflictType.ORPHANED_CODE == "ORPHANED_CODE"
        assert ConflictType.TEST_COVERAGE_GAP == "TEST_COVERAGE_GAP"


class TestSeverity:
    """Test severity enum."""

    def test_severity_values(self):
        """Test that all severity levels exist."""
        assert Severity.LOW == "LOW"
        assert Severity.MEDIUM == "MEDIUM"
        assert Severity.HIGH == "HIGH"
        assert Severity.CRITICAL == "CRITICAL"


class TestConflict:
    """Test Conflict dataclass."""

    def test_conflict_creation(self):
        """Test creating a conflict."""
        conflict = Conflict(
            type=ConflictType.ORPHANED_CODE,
            severity=Severity.MEDIUM,
            location="src/test.py",
            message="Test message",
            fix_suggestions=["Fix 1", "Fix 2"],
        )
        assert conflict.type == ConflictType.ORPHANED_CODE
        assert conflict.severity == Severity.MEDIUM
        assert conflict.location == "src/test.py"
        assert conflict.message == "Test message"
        assert conflict.fix_suggestions == ["Fix 1", "Fix 2"]


class TestConflictDetectorInit:
    """Test ConflictDetector initialization."""

    def test_init_with_default_dir(self):
        """Test initialization with default directory."""
        detector = ConflictDetector()
        assert detector.root_dir == Path.cwd()

    def test_init_with_custom_dir(self):
        """Test initialization with custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = ConflictDetector(root_dir=Path(tmpdir))
            assert detector.root_dir == Path(tmpdir)

    def test_init_with_string_path(self):
        """Test initialization with string path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            detector = ConflictDetector(root_dir=tmpdir)
            assert detector.root_dir == Path(tmpdir)


class TestConflictDetectorCT3OrphanedCode:
    """Test CT3: Orphaned Code Detection."""

    def test_detect_orphaned_code_no_traceability(self):
        """Test detection of code without SW-REQ traceability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create src directory structure
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            # Create Python file without traceability
            py_file = src_dir / "orphaned.py"
            py_file.write_text("""
def hello():
    pass
""")

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(py_file)

            assert len(conflicts) == 1
            assert conflicts[0].type == ConflictType.ORPHANED_CODE
            assert conflicts[0].severity == Severity.MEDIUM
            assert "orphaned.py" in conflicts[0].message

    def test_no_orphaned_code_with_implements(self):
        """Test that code with 'Implements:' is not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            # Create Python file with traceability
            py_file = src_dir / "traced.py"
            py_file.write_text('''
"""
Implements: SW-REQ-001
"""
def hello():
    pass
''')

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(py_file)

            assert len(conflicts) == 0

    def test_no_orphaned_code_with_sw_req(self):
        """Test that code with 'SW-REQ' is not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            # Create Python file with SW-REQ mention
            py_file = src_dir / "traced.py"
            py_file.write_text('''
# Implements SW-REQ-001
def hello():
    pass
''')

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(py_file)

            assert len(conflicts) == 0


class TestConflictDetectorCT2MissingTraceability:
    """Test CT2: Missing Traceability Detection."""

    def test_detect_missing_implemented_in(self):
        """Test detection of SW-REQ without implemented_in field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create requirements directory structure
            req_dir = Path(tmpdir) / "requirements" / "software"
            req_dir.mkdir(parents=True)

            # Create requirement file without implemented_in
            req_file = req_dir / "SW-REQ-001_test.md"
            req_file.write_text("""---
id: SW-REQ-001
---

# Test Requirement

This requirement must be implemented.
""")

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(req_file)

            # Should detect missing traceability
            ct2_conflicts = [c for c in conflicts if c.type == ConflictType.MISSING_TRACEABILITY]
            assert len(ct2_conflicts) >= 1
            assert any("implemented_in" in c.message for c in ct2_conflicts)

    def test_no_missing_traceability_with_implemented_in(self):
        """Test that SW-REQ with implemented_in is not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            req_dir = Path(tmpdir) / "requirements" / "software"
            req_dir.mkdir(parents=True)

            # Create requirement file with implemented_in
            req_file = req_dir / "SW-REQ-002_test.md"
            req_file.write_text("""---
id: SW-REQ-002
implemented_in: src/core/test.py
---

# Test Requirement

This requirement is implemented.
""")

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(req_file)

            # Should not have MISSING_TRACEABILITY conflict
            ct2_conflicts = [c for c in conflicts if c.type == ConflictType.MISSING_TRACEABILITY]
            assert len(ct2_conflicts) == 0
    def test_no_missing_traceability_with_json_implemented_in(self):
        """JSON frontmatter from link manager is accepted by conflict detector."""
        with tempfile.TemporaryDirectory() as tmpdir:
            req_dir = Path(tmpdir) / "requirements" / "software"
            req_dir.mkdir(parents=True)
            req_file = req_dir / "SW-REQ-020_test.md"
            req_file.write_text('''```json
{"id":"SW-REQ-020","title":"JSON Req","implemented_in":["src/impl.py"]}
```
# JSON Requirement
''')

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(req_file)

            ct2_conflicts = [c for c in conflicts if c.type == ConflictType.MISSING_TRACEABILITY]
            assert ct2_conflicts == []


class TestConflictDetectorCT4TestCoverageGap:
    """Test CT4: Test Coverage Gap Detection."""

    def test_detect_missing_test_coverage(self):
        """Test detection of SW-REQ without test coverage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create requirements directory
            req_dir = Path(tmpdir) / "requirements" / "software"
            req_dir.mkdir(parents=True)

            # Create requirement file without tests
            req_file = req_dir / "SW-REQ-003_test.md"
            req_file.write_text("""---
id: SW-REQ-003
---

# Test Requirement

This requirement needs tests.
""")

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(req_file)

            # Should detect test coverage gap
            ct4_conflicts = [c for c in conflicts if c.type == ConflictType.TEST_COVERAGE_GAP]
            assert len(ct4_conflicts) == 1
            assert "SW-REQ-003" in ct4_conflicts[0].message

    def test_no_test_gap_when_test_exists(self):
        """Test that SW-REQ with tests is not flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create requirements directory
            req_dir = Path(tmpdir) / "requirements" / "software"
            req_dir.mkdir(parents=True)

            # Create tests directory with test file
            test_dir = Path(tmpdir) / "tests" / "unit"
            test_dir.mkdir(parents=True)
            test_file = test_dir / "test_sw_req_004.py"
            test_file.write_text("""
# Tests for SW-REQ-004
def test_feature():
    pass
""")

            # Create requirement file
            req_file = req_dir / "SW-REQ-004_test.md"
            req_file.write_text("""---
id: SW-REQ-004
---

# Test Requirement

This requirement has tests.
""")

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts_for_file(req_file)

            # Should not have TEST_COVERAGE_GAP conflict
            ct4_conflicts = [c for c in conflicts if c.type == ConflictType.TEST_COVERAGE_GAP]
            assert len(ct4_conflicts) == 0


class TestConflictReport:
    """Test conflict report generation."""

    def test_empty_report(self):
        """Test report with no conflicts."""
        detector = ConflictDetector()
        report = detector.generate_conflict_report([])

        assert report["total_conflicts"] == 0
        assert report["by_type"] == {}
        assert report["by_severity"] == {}
        assert report["conflicts"] == []

    def test_report_grouping(self):
        """Test that conflicts are grouped correctly."""
        detector = ConflictDetector()

        conflicts = [
            Conflict(
                type=ConflictType.ORPHANED_CODE,
                severity=Severity.MEDIUM,
                location="src/a.py",
                message="Orphaned A",
                fix_suggestions=["Fix A"],
            ),
            Conflict(
                type=ConflictType.ORPHANED_CODE,
                severity=Severity.HIGH,
                location="src/module_b.py",
                message="Orphaned B",
                fix_suggestions=["Fix B"],
            ),
            Conflict(
                type=ConflictType.MISSING_TRACEABILITY,
                severity=Severity.MEDIUM,
                location="req/c.md",
                message="Missing C",
                fix_suggestions=["Fix C"],
            ),
        ]

        report = detector.generate_conflict_report(conflicts)

        assert report["total_conflicts"] == 3
        assert report["by_type"]["ORPHANED_CODE"] == 2
        assert report["by_type"]["MISSING_TRACEABILITY"] == 1
        assert report["by_severity"]["MEDIUM"] == 2
        assert report["by_severity"]["HIGH"] == 1

    def test_report_conflict_structure(self):
        """Test that report contains full conflict details."""
        detector = ConflictDetector()

        conflicts = [
            Conflict(
                type=ConflictType.TEST_COVERAGE_GAP,
                severity=Severity.HIGH,
                location="req/test.md",
                message="Test gap",
                fix_suggestions=["Add tests"],
            ),
        ]

        report = detector.generate_conflict_report(conflicts)

        assert len(report["conflicts"]) == 1
        c = report["conflicts"][0]
        assert c["type"] == "TEST_COVERAGE_GAP"
        assert c["severity"] == "HIGH"
        assert c["location"] == "req/test.md"
        assert c["message"] == "Test gap"
        assert c["fix_suggestions"] == ["Add tests"]


class TestFullScan:
    """Test full project scan."""

    def test_full_scan_finds_all_issues(self):
        """Test scanning entire project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create full project structure
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            req_dir = Path(tmpdir) / "requirements" / "software"
            req_dir.mkdir(parents=True)

            # Create orphaned code file
            (src_dir / "orphaned.py").write_text("def foo(): pass")

            # Create requirement without implementation
            (req_dir / "SW-REQ-010_orphan_req.md").write_text("""---
id: SW-REQ-010
---
# Orphan Req
""")

            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts()

            # Should find issues
            assert len(conflicts) >= 2

            # Check for orphaned code
            orphaned = [c for c in conflicts if c.type == ConflictType.ORPHANED_CODE]
            assert len(orphaned) >= 1

            # Check for test coverage gap
            gaps = [c for c in conflicts if c.type == ConflictType.TEST_COVERAGE_GAP]
            assert len(gaps) >= 1


class TestPerformance:
    """Test performance requirements."""

    def test_detection_under_1_minute(self):
        """Test that conflict detection completes in under 1 minute."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            for i in range(10):
                (src_dir / f"file_{i}.py").write_text(f"def func_{i}(): pass")

            detector = ConflictDetector(root_dir=tmpdir)

            start = time.time()
            detector.detect_conflicts()
            elapsed = time.time() - start

            assert elapsed < 60.0, f"Detection took {elapsed:.2f}s, expected <60s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
