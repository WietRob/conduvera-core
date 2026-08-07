"""
ASPICE Conflict Detector - Detect Conflicts Between ASPICE Levels

Validates: US-A3 AC3 (Conflict Detection <1min)
Implements: SW-REQ-095 (ASPICE Conflict Detector)
Derived from: SYS-REQ-032 (Architecture-Governance)

Purpose:
Detect conflicts between ASPICE-Ebenen within 1 minute after commit.

Traceability:
- Implements: SW-REQ-095
- Derived from: SYS-REQ-032
- Validated by: TC-IT-095, TC-UT-095
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ConflictType(str, Enum):
    """Conflict types."""

    REQUIREMENTS_VS_CODE_DRIFT = "REQUIREMENTS_VS_CODE_DRIFT"
    MISSING_TRACEABILITY = "MISSING_TRACEABILITY"
    ORPHANED_CODE = "ORPHANED_CODE"
    TEST_COVERAGE_GAP = "TEST_COVERAGE_GAP"


class Severity(str, Enum):
    """Conflict severity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class Conflict:
    """Conflict data model."""

    type: ConflictType
    severity: Severity
    location: str
    message: str
    fix_suggestions: list[str]


class ConflictDetectorError(Exception):
    """Base exception for conflict detector errors."""

    pass


class ConflictDetector:
    """
    Detect conflicts between ASPICE-Ebenen within 1 minute after commit.

    Validates: US-A3 AC3 (Conflict Detection <1min)
    Implements: SW-REQ-095

    Conflict Types:
    - CT1: Requirements vs Code Drift (SW-REQ says X, Code does Y)
    - CT2: Missing Traceability (SW-REQ without CODE)
    - CT3: Orphaned Code (CODE without SW-REQ)
    - CT4: Test Coverage Gaps (SW-REQ without TEST)

    Performance:
    - Conflict detection: <1 min (AC3 SLA)
    - Report generation: <10s (PR2)
    """

    def __init__(self, root_dir: Path | None = None):
        """
        Initialize conflict detector.

        Args:
            root_dir: Root directory for analysis (default: current directory)
        """
        if root_dir is None:
            root_dir = Path.cwd()
        self.root_dir = Path(root_dir)

        logger.info(f"ConflictDetector initialized: {self.root_dir}")

    def detect_conflicts(self, commit_sha: str | None = None) -> list[Conflict]:
        """
        Detect conflicts in traceability chain.

        Args:
            commit_sha: Optional Git commit SHA to analyze (if None, analyze current state)

        Returns:
            List of detected conflicts

        Tests: SW-REQ-095 FR1, FR2, FR3
        Performance: <1 min (AC3 SLA)
        """
        conflicts = []

        try:
            # Get changed files (if commit_sha provided)
            if commit_sha:
                changed_files = self._get_changed_files(commit_sha)
            else:
                # Analyze all files (Python files in src/ and requirement files)
                changed_files = list(self.root_dir.rglob("*.py"))
                changed_files.extend(self.root_dir.rglob("requirements/**/*.md"))

            # Detect conflicts for each file
            for file_path in changed_files:
                file_conflicts = self._detect_file_conflicts(file_path)
                conflicts.extend(file_conflicts)

            logger.info(f"Detected {len(conflicts)} conflicts")
            return conflicts

        except Exception as e:
            logger.error(f"Error detecting conflicts: {e}")
            return [
                Conflict(
                    type=ConflictType.MISSING_TRACEABILITY,
                    severity=Severity.HIGH,
                    location="unknown",
                    message=f"Conflict detection failed: {e}",
                    fix_suggestions=[],
                )
            ]

    def generate_conflict_report(self, conflicts: list[Conflict]) -> dict:
        """
        Generate conflict report.

        Args:
            conflicts: List of conflicts to report

        Returns:
            Report dictionary

        Tests: SW-REQ-095 FR4
        Performance: <10s (PR2)
        """
        by_type = {}
        by_severity = {}

        for conflict in conflicts:
            # Group by type
            if conflict.type.value not in by_type:
                by_type[conflict.type.value] = []
            by_type[conflict.type.value].append(conflict)

            # Group by severity
            if conflict.severity.value not in by_severity:
                by_severity[conflict.severity.value] = []
            by_severity[conflict.severity.value].append(conflict)

        return {
            "total_conflicts": len(conflicts),
            "by_type": {k: len(v) for k, v in by_type.items()},
            "by_severity": {k: len(v) for k, v in by_severity.items()},
            "conflicts": [
                {
                    "type": c.type.value,
                    "severity": c.severity.value,
                    "location": c.location,
                    "message": c.message,
                    "fix_suggestions": c.fix_suggestions,
                }
                for c in conflicts
            ],
        }

    def detect_conflicts_for_file(self, file_path: Path) -> list[Conflict]:
        """
        Detect conflicts for a specific file.

        Args:
            file_path: Path to file to analyze

        Returns:
            List of conflicts for this file
        """
        return self._detect_file_conflicts(Path(file_path))

    def _get_changed_files(self, commit_sha: str) -> list[Path]:
        """Get changed files from Git commit."""
        try:
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha],
                capture_output=True,
                text=True,
                cwd=self.root_dir,
            )
            if result.returncode != 0:
                logger.warning(f"Git command failed: {result.stderr}")
                return []

            changed_files = []
            for line in result.stdout.strip().split("\n"):
                if line and (line.endswith(".py") or line.endswith(".md")):
                    changed_files.append(self.root_dir / line)

            return changed_files
        except Exception as e:
            logger.error(f"Error getting changed files: {e}")
            return []

    def _detect_file_conflicts(self, file_path: Path) -> list[Conflict]:
        """Detect conflicts for a specific file."""
        conflicts = []

        # CT1: Requirements-Code Drift - Check semantic mismatch between SW-REQ and Code
        if "requirements/software" in str(file_path) and file_path.suffix == ".md":
            req_drift_conflicts = self._detect_requirements_code_drift(file_path)
            conflicts.extend(req_drift_conflicts)

        # CT2: Missing Traceability - Check if SW-REQ has implementation
        if "requirements/software" in str(file_path) and file_path.suffix == ".md":
            missing_trace_conflicts = self._detect_missing_traceability(file_path)
            conflicts.extend(missing_trace_conflicts)

        # CT3: Orphaned Code - Check if Python file has SW-REQ
        if file_path.suffix == ".py" and "src/" in str(file_path):
            # Check for traceability in docstring
            try:
                content = file_path.read_text(encoding="utf-8")
                if "Implements:" not in content and "SW-REQ" not in content:
                    conflicts.append(
                        Conflict(
                            type=ConflictType.ORPHANED_CODE,
                            severity=Severity.MEDIUM,
                            location=str(file_path),
                            message=f"Code file {file_path.name} has no SW-REQ traceability",
                            fix_suggestions=[
                                "Add 'Implements: SW-REQ-XXX' to module docstring",
                                "Add traceability comment linking to requirement",
                            ],
                        )
                    )
            except Exception:
                pass

        # CT4: Test Coverage Gaps - Check if SW-REQ file has tests
        if "requirements/software" in str(file_path):
            # Extract SW-REQ ID from filename (e.g., "SW-REQ-093_iteration_tracker.md" -> "SW-REQ-093")
            filename = file_path.name
            if filename.startswith("SW-REQ-"):
                # Extract ID (e.g., "SW-REQ-093")
                req_id = filename.split("_")[0] if "_" in filename else filename.replace(".md", "")

                # Check if test file exists
                test_file = self._find_test_file(req_id)
                if not test_file:
                    conflicts.append(
                        Conflict(
                            type=ConflictType.TEST_COVERAGE_GAP,
                            severity=Severity.HIGH,
                            location=str(file_path),
                            message=f"SW-REQ {req_id} has no associated test file",
                            fix_suggestions=[
                                f"Create test file tests/unit/TC-UT-XXX_{req_id.lower()}.py",
                                f"Add '{req_id}' to test file validated_by field",
                            ],
                        )
                    )

        return conflicts

    def _find_test_file(self, req_id: str) -> Path | None:
        """Find test file for requirement ID."""
        # Search in tests/ directory
        test_dirs = [
            self.root_dir / "tests" / "unit",
            self.root_dir / "tests" / "integration",
            self.root_dir / "tests" / "acceptance",
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for test_file in test_dir.rglob("*.py"):
                try:
                    content = test_file.read_text(encoding="utf-8")
                    if req_id in content or f"SW-REQ-{req_id.split('-')[-1]}" in content:
                        return test_file
                except Exception:
                    continue

        return None

    def _detect_requirements_code_drift(self, req_file: Path) -> list[Conflict]:
        """
        CT1: Detect Requirements-Code Drift.

        Checks if SW-REQ requirements match the actual code implementation.
        Uses simple keyword matching (v1) - can be enhanced with NLP later.

        Args:
            req_file: Path to SW-REQ markdown file

        Returns:
            List of conflicts detected
        """
        conflicts = []
        try:
            content = req_file.read_text(encoding="utf-8")
            req_id = req_file.stem.split("_")[0] if "_" in req_file.stem else req_file.stem

            # Extract key requirements from SW-REQ (simple keyword extraction)
            # Look for MUST/SHALL/SHOULD statements
            must_statements = re.findall(r"(?:MUST|SHALL|SHOULD)[^.]*\.", content, re.IGNORECASE)
            key_requirements = []
            for stmt in must_statements[:5]:  # Limit to first 5 for performance
                # Extract keywords (simple approach)
                keywords = re.findall(r"\b[a-z]{4,}\b", stmt.lower())
                key_requirements.extend(keywords)

            if not key_requirements:
                return conflicts  # No requirements found, skip

            # Find implementation file(s) for this requirement
            impl_files = self._find_implementation_files(req_id)
            if not impl_files:
                return conflicts  # No implementation found (handled by CT2)

            # Check if code matches requirements (simple keyword matching)
            for impl_file in impl_files:
                try:
                    code_content = impl_file.read_text(encoding="utf-8").lower()
                    # Count matching keywords
                    matches = sum(1 for kw in key_requirements if kw in code_content)
                    match_ratio = matches / len(key_requirements) if key_requirements else 0

                    # If match ratio < 60%, potential drift
                    if match_ratio < 0.6:
                        conflicts.append(
                            Conflict(
                                type=ConflictType.REQUIREMENTS_VS_CODE_DRIFT,
                                severity=Severity.HIGH,
                                location=str(impl_file),
                                message=f"Code in {impl_file.name} may not match requirements in {req_id} (match: {match_ratio:.0%})",
                                fix_suggestions=[
                                    f"Review {req_id} requirements and update code implementation",
                                    "Add comments linking code sections to specific requirements",
                                    "Verify semantic alignment between requirements and code",
                                ],
                            )
                        )
                except Exception as e:
                    logger.debug(f"Error checking drift for {impl_file}: {e}")

        except Exception as e:
            logger.debug(f"Error detecting requirements-code drift for {req_file}: {e}")

        return conflicts

    def _detect_missing_traceability(self, req_file: Path) -> list[Conflict]:
        """
        CT2: Detect Missing Traceability.

        Checks if SW-REQ has implementation files (check implemented_in field).

        Args:
            req_file: Path to SW-REQ markdown file

        Returns:
            List of conflicts detected
        """
        conflicts = []
        try:
            content = req_file.read_text(encoding="utf-8")
            req_id = req_file.stem.split("_")[0] if "_" in req_file.stem else req_file.stem

            # Check if implemented_in field exists in YAML or JSON frontmatter.
            yaml_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            json_match = re.search(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
            has_implemented_in = False
            if yaml_match:
                has_implemented_in = "implemented_in:" in yaml_match.group(1).lower()
            elif json_match:
                import json

                data = json.loads(json_match.group(1).strip())
                has_implemented_in = bool(data.get("implemented_in"))

            if yaml_match or json_match:
                if not has_implemented_in:
                    conflicts.append(
                        Conflict(
                            type=ConflictType.MISSING_TRACEABILITY,
                            severity=Severity.MEDIUM,
                            location=str(req_file),
                            message=f"SW-REQ {req_id} has no implemented_in traceability",
                            fix_suggestions=[
                                f"Add implemented_in link to {req_id} frontmatter",
                                "Link requirement to implementation file(s)",
                            ],
                        )
                    )
            else:
                # No frontmatter - check if implementation exists via code search
                impl_files = self._find_implementation_files(req_id)
                if not impl_files:
                    conflicts.append(
                        Conflict(
                            type=ConflictType.MISSING_TRACEABILITY,
                            severity=Severity.MEDIUM,
                            location=str(req_file),
                            message=f"SW-REQ {req_id} has no implemented_in traceability",
                            fix_suggestions=[
                                f"Create implementation file for {req_id}",
                                f"Add 'Implements: {req_id}' to code docstring",
                            ],
                        )
                    )

        except Exception as e:
            logger.debug(f"Error detecting missing traceability for {req_file}: {e}")

        return conflicts

    def _find_implementation_files(self, req_id: str) -> list[Path]:
        """
        Find implementation files for a requirement ID.

        Args:
            req_id: Requirement ID (e.g., "SW-REQ-093")

        Returns:
            List of implementation file paths
        """
        impl_files = []
        src_dir = self.root_dir / "src"

        if not src_dir.exists():
            return impl_files

        # Search for req_id in Python files
        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                # Check if requirement is mentioned in docstring or comments
                if req_id in content or f"Implements: {req_id}" in content:
                    impl_files.append(py_file)
            except Exception:
                pass

        return impl_files
