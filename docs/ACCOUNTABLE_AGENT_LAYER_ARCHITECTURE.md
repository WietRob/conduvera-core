# Accountable Agent Layer Architecture

Status: PR C implementation contract. Not production-ready; focused release slice on top of Foundation and Compliance Change Control Core.

## Purpose

The Accountable Agent Layer (AAL) adds attribution and pre-flight accountability for AI-assisted changes. It is intentionally a Matrix OS layer on top of the Compliance Change Control (CCC) core, not a replacement for CCC.

## Scope

Included in PR C:

- `curaops.skills.accountable_agent.AccountableAgentService`
- `AgentContext`, `ChangeIntent`, `AccountableChange`, `ACStatus`
- CLI group: `matrix-cli accountable`
- Commands: `preflight`, `pre-flight`, `register`, `validate`, `evidence`
- AAL evidence that references CCC evidence and verifies integrity

Excluded from PR C:

- ASPICE utilities
- UI/MCP/editor scaffolding
- Safety Guard
- agent-evidence-plane
- CAS / failure-loop / peekxd / OpenCode plugin / ai-router

## Dependency direction

AAL consumes the CCC public API only:

```python
from curaops.skills.change_request import (
    CRStatus,
    ChangeRequestService,
    verify_evidence_file,
)
```

AAL must not implement a parallel CCC lifecycle. CCC remains authoritative for CR creation, submission, approval, transitions, CR validation, and CCC evidence format.

## Runtime flow

1. A CCC CR is created, submitted, and approved with `matrix-cli cr ...`.
2. `matrix-cli accountable preflight` checks that the CR exists, is approved, has requirement refs, and satisfies AAL bugfix gates.
3. `matrix-cli accountable register` stores an `AccountableChange` under `changes/accountable/AC-*.json`.
4. `matrix-cli accountable validate` verifies mandatory links and CCC traceability.
5. `matrix-cli accountable evidence` writes `changes/evidence/AC-*.json` only if the accountable change is valid.
6. AAL evidence records `referenced_c_evidence` and verifies referenced CCC evidence integrity.

## Persistence

- Accountable changes: `changes/accountable/AC-*.json`
- AAL evidence: `changes/evidence/AC-*.json`
- No session-scoped CR binding is exposed in PR C.
- `AgentContext.session_id` is optional metadata only.

## Preflight contract

CLI:

```bash
matrix-cli accountable preflight \
  --cr CR-001 \
  --requirements SW-REQ-001 \
  --type feature \
  --impact SW,CODE
```

Hard blocks:

- linked CR missing
- CR status is not `approved` for preflight
- requirement refs missing
- bugfix work has no SW-REQ linkage in the accountable work refs
- bugfix implemented/verified/closed CR has no regression VerificationCase

AAL delegates CCC lifecycle and new-reference approval semantics to `ChangeRequestService`; it does not add a separate `new_ref` hard block.

## Evidence contract

`generate_accountability_evidence()` first calls `validate_accountability()`.

If validation is invalid, evidence generation raises `AccountabilityError` and writes no AAL evidence.

If validation is valid, evidence contains:

- `accountable_change`
- `validation`
- `referenced_c_evidence`
- `evidence_chain`
- `hash`

`referenced_c_evidence.integrity_verified=true` means the referenced CCC evidence file passed `verify_evidence_file()`.

## Public CLI surface

```bash
matrix-cli accountable --help
matrix-cli accountable preflight --help
matrix-cli accountable register --help
matrix-cli accountable validate --help
matrix-cli accountable evidence --help
```

There is no `matrix-cli accountable setup` command in PR C.
