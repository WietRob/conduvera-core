# ASPICE Link Manager

Traceability Management for ASPICE Compliance
Extracted from CuraOps Framework (SW-REQ-094)

## Features

✅ Parse requirement documents with JSON frontmatter
✅ Update bidirectional links (forward + backward)
✅ Verify link consistency
✅ Generate traceability matrix
✅ Coverage reporting
✅ <5min SLA for link updates
✅ **No external dependencies** (uses JSON instead of YAML)

## Document Format

Requirements are Markdown files with JSON frontmatter:

```markdown
```json
{
  "id": "SW-REQ-001",
  "title": "User Authentication",
  "refined_from": ["SYS-REQ-001"],
  "refined_in": ["SW-REQ-002"],
  "validated_by": ["TEST-001"],
  "implemented_in": ["src/auth.py"]
}
```

# SW-REQ-001: User Authentication

Description here...
```

## Installation

```bash
# No external dependencies!
# Only uses Python standard library
```

## Usage

### Python API

```python
from curaops.skills.aspice_link_manager import ASPICELinkManager

# Initialize
manager = ASPICELinkManager(root_dir="./my-project")

# Parse document
doc = manager.parse_document(Path("requirements/SW-REQ-001.md"))
print(doc.id, doc.title, doc.refined_from)

# Update bidirectional links
result = manager.update_bidirectional_links(Path("requirements/SW-REQ-001.md"))
print(f"Updated {result.updated_count} links")

# Verify link consistency
errors = manager.verify_links(Path("requirements/SW-REQ-001.md"))
if errors:
    print("Consistency issues found:", errors)

# Generate traceability matrix
matrix = manager.generate_traceability_matrix()
print(f"Coverage: {matrix['coverage']['test_coverage']:.1%}")

# Save matrix to file
manager.save_traceability_matrix(output_file=Path("traceability_matrix.json"))
```

### CLI

```python
# Update links for specific document
update_links("./my-project", doc_id="SW-REQ-001")

# Update all links
update_links("./my-project")

# Verify links for specific document
verify_links("./my-project", doc_id="SW-REQ-001")

# Verify all links
verify_links("./my-project")

# Generate traceability matrix
generate_matrix("./my-project")
```

## Directory Structure

```
my-project/
├── requirements/
│   ├── SYS-REQ-001.md     # System requirements
│   └── SW-REQ-001.md      # Software requirements
├── architecture/
│   └── ARCH-001.md        # Architecture decisions
├── tests/
│   └── TEST-001.md        # Test cases
└── traceability_matrix.json  # Generated matrix
```

## Link Types

- **refined_from**: Parent requirements (e.g., SYS → SW)
- **refined_in**: Child requirements (e.g., SW → detailed SW)
- **validated_by**: Test cases that validate this requirement
- **implemented_in**: Code files that implement this requirement

## Bidirectional Link Rules

If document A has B in `refined_in`, then B should have A in `refined_from`.

Example:
```
SYS-REQ-001.md:
  refined_in: [SW-REQ-001]

SW-REQ-001.md:
  refined_from: [SYS-REQ-001]  # Auto-updated
```

## Tests

```bash
cd <matrix-os checkout>
python -m pytest curaops/skills/aspice_link_manager/tests -v
```

14 tests covering:
- Document parsing
- Document finding
- Link updates
- Link verification
- Matrix generation

## Traceability Matrix

Generated JSON structure:
```json
{
  "generated_at": "2026-04-05T13:30:00",
  "requirements": [
    {"id": "SW-REQ-001", "title": "...", "file": "..."}
  ],
  "links": {
    "SW-REQ-001": {
      "refined_from": ["SYS-REQ-001"],
      "refined_in": [],
      "validated_by": ["TEST-001"],
      "implemented_in": []
    }
  },
  "coverage": {
    "total_requirements": 10,
    "with_tests": 8,
    "with_implementation": 7,
    "test_coverage": 0.8,
    "impl_coverage": 0.7
  }
}
```

## Requirements Covered

- SW-REQ-094: ASPICE Link Auto-Updater
- SYS-REQ-025: ASPICE Integration
- <5min SLA for link updates
- Bidirectional link consistency

## Differences from CuraOps Framework

- Uses **JSON** instead of YAML (no external dependency)
- Simplified document format
- Same core functionality
- Works standalone
