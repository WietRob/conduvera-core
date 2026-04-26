# Change Request Service

CR Driven Development - Change-Request-First Workflow
Extracted from CuraOps Framework (SW-REQ-063)

## Features

✅ Submit Change Requests (Markdown)  
✅ Status Workflow: SUBMITTED → APPROVED → IN_PROGRESS → IMPLEMENTED → CLOSED  
✅ Git-tracked changes/ directory  
✅ Traceability Bible v3.1 compliant  
✅ Status transition validation  

## Installation

```bash
# No external dependencies!
# Only uses Python standard library
```

## Usage

### Python API

```python
from change_request import ChangeRequestService

# Initialize
service = ChangeRequestService(changes_path="./changes")

# Submit CR
cr = service.submit_change_request(
    title="Add Excel Export",
    description="Implement Excel export with charts"
)
print(cr["cr_id"])  # CR-001

# List pending
pending = service.get_pending_requests()

# Update status
service.process_change_request("CR-001", "APPROVED")
service.process_change_request("CR-001", "IN_PROGRESS")
service.process_change_request("CR-001", "IMPLEMENTED")
service.process_change_request("CR-001", "CLOSED")

# Get CR details
cr_data = service.get_cr_status("CR-001")
```

### CLI

```python
# Submit CR
submit_cr("./my-project", "Add Feature", "Description...")

# List all CRs
list_crs("./my-project")

# List by status
list_crs("./my-project", status="APPROVED")

# Update status
update_cr("./my-project", "CR-001", "APPROVED")

# Show CR details
show_cr("./my-project", "CR-001")
```

## Directory Structure

```
changes/
├── CR-001.md  (Status: SUBMITTED)
├── CR-002.md  (Status: APPROVED)
└── CR-003.md  (Status: IMPLEMENTED)
```

## Status Workflow

```
SUBMITTED → APPROVED → IN_PROGRESS → IMPLEMENTED → CLOSED
        ↘ REJECTED ↗
```

Valid transitions:
- SUBMITTED → APPROVED, REJECTED
- APPROVED → IN_PROGRESS, REJECTED
- IN_PROGRESS → IMPLEMENTED, REJECTED
- IMPLEMENTED → CLOSED, IN_PROGRESS
- REJECTED → SUBMITTED (reopen)
- CLOSED → (terminal state)

## Markdown Template

Each CR is a Markdown file with sections:
- Description
- Impact Analysis (levels, requirements, files)
- Approval (approver, date, decision)
- Implementation (commits, changed files)
- Verification (tests, results)
- Traceability (related requirements, ADRs)

## Tests

```bash
cd ~/.hermes/skills/change-request
python -m pytest tests/ -v
```

12 tests covering:
- CR submission
- Status transitions
- Validation
- Error handling

## Requirements Covered

- SW-REQ-063: Change Request Creation Service
- SYS-REQ-001: Change Request Submission
- ASPICE: SWE.4 (Software Unit Construction)
- Compliance: Traceability Bible v3.1 TEIL 10
