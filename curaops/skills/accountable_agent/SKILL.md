# Accountable Agent Skill

**Accountable Agent Layer Implementation** — Thin accountability layer on top of Compliance Change Control

## Purpose

Captures agent identity, context, and intent for AI-assisted changes. Ensures mandatory accountability links (CR + requirements) are present before allowing changes. Generates evidence packets for audit trail.

## Dependencies

- **change-request** (Compliance Change Control): CR creation, requirement linking, evidence generation
- **aspice-link-manager**: Traceability validation

## Core Concepts

### AgentContext
Captures who/what is making the change:
- `agent_id`: Unique identifier
- `agent_name`: Human-readable name
- `model`: AI model used
- `tools_used`: List of tools invoked
- `session_id`: Optional session reference
- `platform`: Optional platform identifier

### ChangeIntent
Captures what is being changed:
- `description`: Change description
- `change_type`: feature, bugfix, refactor, test
- `files_affected`: List of files modified
- `estimated_impact`: Optional impact assessment
- `justification`: Optional business justification

### AccountableChange
Complete accountability record:
- Links `AgentContext` + `ChangeIntent` to CR + requirements
- Status: pending → linked → validated → blocked
- Evidence path for audit trail

## CLI Usage

```bash
# Register an accountable change (strict mode - requires CR + requirements)
python -m curaops.cli.main accountable register \
  --agent-id "claude-001" \
  --name "Claude Code" \
  --model "claude-sonnet-4" \
  --description "Fix authentication bug" \
  --type bugfix \
  --cr "CR-001" \
  --requirements "SW-REQ-001,SEC-REQ-005" \
  --tools "file_edit,terminal" \
  --files "src/auth.py,tests/test_auth.py"

# Register without mandatory links (non-strict)
python -m curaops.cli.main accountable register \
  --agent-id "agent-001" \
  --name "Test Agent" \
  --model "gpt-4" \
  --description "Refactor utils" \
  --type refactor \
  --no-strict

# Validate an accountable change
python -m curaops.cli.main accountable validate AC-XXXXXXXX

# Generate evidence report
python -m curaops.cli.main accountable evidence AC-XXXXXXXX --format json
python -m curaops.cli.main accountable evidence AC-XXXXXXXX --format markdown
```

## Python API

```python
from accountable_agent import (
    AccountableAgentService,
    AgentContext,
    ChangeIntent,
    MissingMandatoryLinkError,
)

# Initialize service
service = AccountableAgentService(project_root=Path.cwd())

# Create agent context
agent_context = AgentContext(
    agent_id="claude-001",
    agent_name="Claude Code",
    model="claude-sonnet-4",
    tools_used=["file_edit", "terminal"],
)

# Create change intent
change_intent = ChangeIntent(
    description="Fix authentication bug",
    change_type="bugfix",
    files_affected=["src/auth.py"],
)

# Register (strict mode - blocks if missing links)
try:
    ac = service.register_accountable_change(
        agent_context=agent_context,
        change_intent=change_intent,
        cr_id="CR-001",
        requirement_refs=["SW-REQ-001"],
        strict=True,
    )
    print(f"Registered: {ac.accountable_id}")
except MissingMandatoryLinkError as e:
    print(f"Blocked: {e}")

# Validate
result = service.validate_accountability(ac.accountable_id)
print(f"Valid: {result['valid']}")

# Generate evidence
evidence_path = service.generate_accountability_evidence(
    ac.accountable_id, output_format="json"
)
```

## Accountability Rules

### Mandatory Links (Strict Mode)
- `cr_id`: Must link to existing Change Request
- `requirement_refs`: Must reference at least one requirement

### Validation Checks
1. CR exists in changes/ directory
2. Requirements are non-empty
3. Traceability via ASPICE Link Manager (optional)

### Block Conditions
- Missing CR link → BLOCKED
- Missing requirement refs → BLOCKED
- Non-existent CR → BLOCKED
- Any validation issue → BLOCKED

## Evidence Format

### JSON Evidence
```json
{
  "accountable_change": {
    "accountable_id": "AC-XXXXXXXX",
    "agent_context": { ... },
    "change_intent": { ... },
    "cr_id": "CR-001",
    "requirement_refs": ["SW-REQ-001"],
    "status": "validated"
  },
  "validation": {
    "valid": true,
    "issues": []
  },
  "cr_evidence_path": "changes/evidence/CR-001_evidence.json",
  "generated_at": "2025-01-15T10:30:00",
  "service_version": "B-0.1.0"
}
```

### Markdown Evidence
Human-readable report with:
- Agent identity and model
- Change description and type
- Accountability links (CR + requirements)
- Validation results
- Evidence chain references

## Testing

```bash
cd /home/roberto_schmidt/projects/matrix-os/curaops/skills/accountable_agent/tests
python3 -m pytest test_accountable_agent.py -v
```

## Integration with C Core

Accountable Agent Layer reuses Compliance Change Control services:
- `ChangeRequestService`: CR creation and management
- `generate_cr_evidence()`: CR evidence generation
- `validate_cr_traceability()`: Requirement traceability

No duplication of CR/traceability logic.
