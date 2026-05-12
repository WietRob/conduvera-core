# Accountable Agent Layer Implementation

Status: PR C implementation contract. This document describes the implemented PR C slice only.

## Files

Implementation:

- `curaops/skills/accountable_agent/__init__.py`
- `curaops/cli/commands/accountable.py`
- `curaops/cli/main.py` command registration

Tests:

- `curaops/skills/accountable_agent/tests/test_accountable_agent.py`
- `curaops/skills/accountable_agent/tests/test_high_blockers.py`

Docs:

- `docs/ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md`
- `docs/ACCOUNTABLE_AGENT_LAYER_PROCESS.md`
- `docs/ACCOUNTABLE_AGENT_LAYER_RULES.md`
- `docs/ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md`

## Public API used from CCC

```python
from curaops.skills.change_request import (
    CRStatus,
    ChangeRequestService,
    verify_evidence_file,
)
```

No other CCC helper API is required by PR C.

## Public AAL service API

```python
service = AccountableAgentService(project_root=project_root)

service.pre_flight_check(
    cr_id="CR-001",
    requirement_refs=["SW-REQ-001"],
    change_type="feature",
    impact_level=["SW", "CODE"],
)

service.register_accountable_change(
    agent_context=AgentContext(...),
    change_intent=ChangeIntent(...),
    cr_id="CR-001",
    requirement_refs=["SW-REQ-001"],
)

service.validate_accountability("AC-XXXXXXXX")
service.generate_accountability_evidence("AC-XXXXXXXX")
```

## CLI API

```bash
matrix-cli accountable preflight --cr CR-001 --requirements SW-REQ-001 --type feature --impact SW,CODE
matrix-cli accountable register --agent-id agent-001 --name "Release Agent" --model gpt-5.5 --description "..." --type feature --cr CR-001 --requirements SW-REQ-001
matrix-cli accountable validate AC-XXXXXXXX
matrix-cli accountable evidence AC-XXXXXXXX
```

`pre-flight` is an alias for `preflight`.

There is no `matrix-cli accountable setup` command and no `matrix-cli cr link` command in PR C.

## Persistence

`register_accountable_change()` persists AccountableChange records to:

```text
changes/accountable/AC-*.json
```

`generate_accountability_evidence()` persists AAL evidence to:

```text
changes/evidence/AC-*.json
```

## Evidence safety

`generate_accountability_evidence()` calls `validate_accountability()` first. If validation is invalid, it raises `AccountabilityError` and writes no AAL evidence.

This prevents audit evidence from being generated for draft/submitted/rejected/emergency or otherwise invalid linked CRs.

## Evidence chain

AAL evidence contains a `referenced_c_evidence` object that records:

- referenced CCC evidence path
- referenced hash
- availability
- integrity verification result
- verification error, if any

Integrity verification uses CCC's public `verify_evidence_file()` export.

## Test coverage

AAL tests cover:

- preflight pass/fail
- register / validate / evidence workflow
- persistent AccountableChange storage
- missing CR block
- missing requirement refs block
- draft/pre-approval CR validation/evidence block
- bugfix SW-REQ block
- bugfix metadata and root-cause warnings
- referenced CCC evidence integrity
- no duplicate CCC `new_ref` hard block
