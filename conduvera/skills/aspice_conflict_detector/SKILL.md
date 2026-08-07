# ASPICE Conflict Detector

Detect conflicts between ASPICE levels (Requirements, Code, Tests) within 1 minute after commit.

## Usage

```python
from conduvera.skills.aspice_conflict_detector import ConflictDetector, ConflictType, Severity

# Initialize detector
detector = ConflictDetector(root_dir=Path("/path/to/project"))

# Detect all conflicts
conflicts = detector.detect_conflicts()

# Or detect for specific commit
conflicts = detector.detect_conflicts(commit_sha="abc123")

# Generate report
report = detector.generate_conflict_report(conflicts)
print(f"Total conflicts: {report['total_conflicts']}")
print(f"By type: {report['by_type']}")
print(f"By severity: {report['by_severity']}")
```

## Conflict Types

| Type | Description | Severity |
|------|-------------|----------|
| REQUIREMENTS_VS_CODE_DRIFT | SW-REQ says X, Code does Y | HIGH |
| MISSING_TRACEABILITY | SW-REQ without CODE implementation | MEDIUM |
| ORPHANED_CODE | CODE without SW-REQ traceability | MEDIUM |
| TEST_COVERAGE_GAP | SW-REQ without TEST coverage | HIGH |

## API

### Classes

- `ConflictDetector(root_dir)` - Main detector class
- `Conflict(type, severity, location, message, fix_suggestions)` - Conflict dataclass
- `ConflictType` - Enum of conflict types
- `Severity` - Enum of severity levels (LOW, MEDIUM, HIGH, CRITICAL)

### Methods

- `detect_conflicts(commit_sha=None)` - Detect all conflicts
- `generate_conflict_report(conflicts)` - Generate structured report
- `detect_conflicts_for_file(file_path)` - Check single file

## Performance

- Conflict detection: <1 min (AC3 SLA)
- Report generation: <10s

## Traceability

- Implements: SW-REQ-095
- Derived from: SYS-REQ-032
- Validated by: TC-IT-095, TC-UT-095
