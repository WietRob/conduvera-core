# Accountable Agent Skill

Status: PR C implementation contract for the Accountable Agent Layer.

## Purpose

Capture agent identity, change intent, CCC CR linkage, requirement linkage, validation status, and audit evidence for AI-assisted changes.

## Dependencies

AAL consumes only the CCC public package exports:

```python
from curaops.skills.change_request import (
    CRStatus,
    ChangeRequestService,
    verify_evidence_file,
)
```

No ASPICE utility, UI/MCP, Safety Guard, agent-evidence-plane, CAS, failure-loop, peekxd, OpenCode plugin, or ai-router dependency belongs in PR C.

## CLI

```bash
matrix-cli accountable preflight \
  --cr CR-001 \
  --requirements SW-REQ-001 \
  --type feature \
  --impact SW,CODE

matrix-cli accountable register \
  --agent-id agent-001 \
  --name "Release Agent" \
  --model gpt-5.5 \
  --description "Implement accountable agent layer" \
  --type feature \
  --cr CR-001 \
  --requirements SW-REQ-001 \
  --tools terminal,file \
  --files curaops/skills/accountable_agent/__init__.py

matrix-cli accountable validate AC-XXXXXXXX
matrix-cli accountable evidence AC-XXXXXXXX
```

Alias: `pre-flight` maps to `preflight`.

There is no `matrix-cli accountable setup` command and no `matrix-cli cr link` command in PR C.

## Python API

```python
from pathlib import Path
from curaops.skills.accountable_agent import (
    AccountableAgentService,
    AgentContext,
    ChangeIntent,
)

service = AccountableAgentService(project_root=Path.cwd())
result = service.pre_flight_check(
    cr_id="CR-001",
    requirement_refs=["SW-REQ-001"],
    change_type="feature",
    impact_level=["SW", "CODE"],
)

ac = service.register_accountable_change(
    agent_context=AgentContext(
        agent_id="agent-001",
        agent_name="Release Agent",
        model="gpt-5.5",
        tools_used=["terminal", "file"],
    ),
    change_intent=ChangeIntent(
        description="Implement accountable agent layer",
        change_type="feature",
        files_affected=["curaops/skills/accountable_agent/__init__.py"],
    ),
    cr_id="CR-001",
    requirement_refs=["SW-REQ-001"],
)

validation = service.validate_accountability(ac.accountable_id)
evidence_path = service.generate_accountability_evidence(ac.accountable_id)
```

## Persistence

- Accountable changes: `changes/accountable/AC-*.json`
- AAL evidence: `changes/evidence/AC-*.json`

## Rules

Preflight blocks when:

- linked CR is missing
- linked CR is not `approved`
- requirement refs are missing
- bugfix accountable work refs do not include `SW-REQ-*`
- bugfix CR is implemented/verified/closed without regression VerificationCases

Validation blocks when:

- mandatory links are missing
- linked CR is missing
- linked CR is before `approved`
- CCC validation returns blocking issues
- AAL bugfix gates fail

Evidence generation first validates. If invalid, it raises `AccountabilityError` and writes no AAL evidence.

AAL does not add a separate hard block for CCC `new_ref` semantics. CCC remains authoritative.

## Evidence chain

AAL evidence includes `referenced_c_evidence` and verifies referenced CCC evidence through `verify_evidence_file()`.

## Tests

```bash
python3 -m pytest curaops/skills/accountable_agent/tests -q
```
