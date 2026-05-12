# Accountable Agent Layer Process

Status: PR C implementation contract.

## Process summary

AAL is a thin accountability layer over CCC:

1. Create, submit, and approve a CCC CR with `matrix-cli cr`.
2. Run AAL preflight against the approved CR and the accountable work refs.
3. Register the accountable change.
4. Validate the accountable change.
5. Generate AAL evidence only after validation passes.

## Commands

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

Alias: `pre-flight` is kept as a CLI alias for `preflight`.

## States

`AccountableChange.status` values:

- `pending`: missing mandatory links; allowed only when registered with `strict=False`
- `linked`: CR and requirement refs are present
- `validated`: validation passed
- `blocked`: validation failed

## Blocking behavior

Preflight blocks when:

- CR does not exist
- CR is not `approved`
- requirement refs are missing
- bugfix accountable work refs do not include `SW-REQ-*`
- bugfix CR is implemented/verified/closed without regression VerificationCases

Validation blocks when:

- AccountableChange has no CR link
- AccountableChange has no requirement refs
- linked CR does not exist
- linked CR is before `approved`
- CCC validation returns blocking issues
- AAL bugfix gates fail

Evidence generation blocks when validation is invalid. It raises `AccountabilityError` and writes no AAL evidence.

## CCC consumption rule

AAL consumes these CCC public exports only:

```python
CRStatus
ChangeRequestService
verify_evidence_file
```

AAL does not invent a separate CR lifecycle and does not add a separate hard block for CCC `new_ref` semantics. CCC remains authoritative for CR state and CCC validation.

## Persistence

- Accountable changes: `changes/accountable/AC-*.json`
- AAL evidence: `changes/evidence/AC-*.json`

No PR C command creates session-scoped CR binding. `session_id` is optional metadata on `AgentContext` only.

## Evidence chain

AAL evidence includes `referenced_c_evidence` with CCC evidence path, hash, availability, and integrity verification status. A true `integrity_verified` value requires the referenced CCC evidence to pass `verify_evidence_file()`.
