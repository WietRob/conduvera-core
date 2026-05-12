# Accountable Agent Layer Rules

Status: PR C implementation contract.

## Rule 1 — CCC is authoritative

AAL consumes CCC. It does not replace CCC and must not duplicate CCC lifecycle semantics.

Allowed CCC public imports:

```python
from curaops.skills.change_request import (
    CRStatus,
    ChangeRequestService,
    verify_evidence_file,
)
```

## Rule 2 — Mandatory links

An accountable change must link to:

- one CCC CR ID
- at least one requirement reference

Strict registration blocks missing links. Non-strict registration may create `pending` records for tests or recovery flows, but validation/evidence must still block until links are valid.

## Rule 3 — Preflight gate

`matrix-cli accountable preflight` blocks when:

- linked CR is missing
- linked CR is not `approved`
- requirement refs are missing
- bugfix accountable work refs do not include `SW-REQ-*`
- bugfix CR is implemented/verified/closed without regression VerificationCases

## Rule 4 — Validation gate

`validate_accountability()` blocks when:

- CR link is missing
- requirement refs are missing
- linked CR does not exist
- linked CR is before `approved`
- CCC validation returns blocking issues
- AAL bugfix gates fail

Approved-or-later CR states are valid for post-preflight validation: `approved`, `in_progress`, `implemented`, `verified`, `closed`.

## Rule 5 — Evidence gate

`generate_accountability_evidence()` must not write evidence for invalid accountable changes. It first runs validation and raises `AccountabilityError` when validation fails.

## Rule 6 — Evidence integrity

AAL evidence must reference CCC evidence and verify its integrity with CCC's public `verify_evidence_file()` helper.

## Rule 7 — Bugfix semantics

AAL enforces only accountability-specific bugfix gates:

- the accountable work refs must include `SW-REQ-*`
- implemented-or-later bugfix CRs must have regression VerificationCases
- root-cause metadata may produce warning context

AAL does not add a hard block for CCC `new_ref` semantics. CCC remains authoritative for that validation.

## Rule 8 — PR C scope boundary

PR C must not include ASPICE utilities, UI/MCP/editor scaffolding, Safety Guard, agent-evidence-plane, CAS, failure-loop, peekxd, OpenCode plugin, ai-router, or broad architecture synthesis.
