# Compliance Change Control Process — Authoritative

> **⚠️ LEGACY NOTICE:** This replaces the mixed COMPLIANCE_CHANGE_CONTROL_PROCESS_CONTRACT.md.
> For Accountable Agent Layer process, see ACCOUNTABLE_AGENT_LAYER_PROCESS.md.

**Status:** AUTHORITATIVE  
**Version:** 2.0.0  
**Date:** 2026-04-11  
**Scope:** Compliance Change Control ONLY

---

## A. Scope and Purpose

This document provides the executable process contract for:
- **Compliance Change Control:** Change Request workflow with ASPICE-aligned traceability

**Scope IN:**
- CR state machine with exact transitions
- Requirement state machine
- VerificationCase entity and lifecycle
- Impact classification logic
- Evidence obligations
- Emergency/retro-CR flow

**Scope OUT:**
- Accountable Agent Layer intervention (see ACCOUNTABLE_AGENT_LAYER_PROCESS.md)
- Code implementation
- UI/UX design

---

## B. Canonical Entities

### B.1 Change Request (CR)

```yaml
Entity: CR
ID Pattern: CR-[0-9]{3,} (e.g., CR-001)
Storage: changes/CR-[ID].md
Purpose: Canonical entry point for all engineering changes
```

### B.2 Requirements

```yaml
Entity: SYS-REQ
ID Pattern: SYS-REQ-[0-9]+
Storage: requirements/system/SYS-REQ-[ID].md
Purpose: System-level requirements (externally visible behavior)

Entity: SW-REQ
ID Pattern: SW-REQ-[0-9]+
Storage: requirements/software/SW-REQ-[ID].md
Purpose: Software-level requirements (component behavior)

Entity: SW-ARCH
ID Pattern: SW-ARCH-[0-9]+
Storage: architecture/SW-ARCH-[ID].md
Purpose: Architectural constraints and patterns
```

### B.3 VerificationCase (Canonical Entity)

```yaml
Entity: VerificationCase
ID Pattern: TC-{TYPE}-{Nr} where TYPE ∈ {UT, SIT, SVT, SYSIT, SYST}
Storage: verification/TC-{TYPE}-{Nr}.md
Purpose: Planned verification artifact (specification)

Types:
  unit:                   TC-UT-{Nr}    — CODE / unit design verification
  software_integration:   TC-SIT-{Nr}   — SW-ARCH, interface contracts
  software_verification:  TC-SVT-{Nr}   — SW-REQ verification
  system_integration:     TC-SYSIT-{Nr} — SW-ARCH (system scope), cross-component
  system_verification:    TC-SYST-{Nr}  — SYS-REQ verification

States: DRAFT → APPROVED → PASSED | FAILED → APPROVED (re-run)
                                 → DEPRECATED

Minimum fields:
  id: String                    # TC-{TYPE}-{Nr}
  title: String                 # What is being verified
  type: Enum                    # unit, software_integration, software_verification, system_integration, system_verification
  status: Enum                  # DRAFT, APPROVED, PASSED, FAILED, DEPRECATED
  description: String           # Verification procedure and expected outcome
  validates: [Requirement-IDs]  # Min 1. Backward link to requirements
  implemented_in: File-Path     # Test file location
  component: String             # Module under test
  owner: String                 # Required
  created: Date                 # Auto

  # Optional
  prerequisite: String
  test_data: String
  last_run: Date
  last_result: Enum [PASS, FAIL, SKIP]
```

**Separation of Concerns:**
- VerificationCase = specification (what to verify, how)
- VerificationResult / Evidence = execution result (pass/fail, output, timestamp)
- These are separate artifacts. A VerificationCase can be re-run multiple times.
- Evidence references the VerificationCase ID, not the other way around.

### B.4 Evidence (Execution Result)

```yaml
Entity: CREvidence
File: changes/evidence/CR-[ID]_[YYYYMMDD]_[HHMMSS].json
Purpose: Machine-readable audit trail for CR (execution/result artifact)

Entity: VerificationResult
Contained-in: CREvidence.verification_results[]
Purpose: Execution result for a specific VerificationCase
Fields:
  verification_case_id: String  # TC-{TYPE}-{Nr}
  result: Enum [PASS, FAIL, SKIP]
  executed_at: DateTime
  output: String                # Summary of test execution
```

---

## C. CR State Machine

### C.1 States

| State | Code | Definition | Entry Criteria |
|-------|------|------------|----------------|
| DRAFT | D | Initial creation, editable by author | CR created, not submitted |
| SUBMITTED | S | Ready for review, immutable content | All mandatory fields present |
| APPROVED | A | Authorized for implementation | Review passed, approver signed |
| IN_PROGRESS | P | Implementation underway | First commit detected or dev started |
| IMPLEMENTED | I | Code changes complete | All files committed, VerificationCases written |
| VERIFIED | V | Verification complete, evidence generated | VerificationCases PASSED, evidence verified |
| CLOSED | C | Complete audit trail | Final approval, archived |
| REJECTED | R | Will not be implemented | Review failed, reason documented |
| EMERGENCY | E | Retroactive CR for hotfix | Emergency flag set, 24h deadline |

### C.2 State Transition Matrix

| From → To | D | S | A | P | I | V | C | R | E |
|-----------|---|---|---|---|---|---|---|---|---|
| **D** | - | Y | N | N | N | N | N | N | N |
| **S** | Y | - | Y | N | N | N | N | Y | N |
| **A** | N | N | - | Y | N | N | N | Y | N |
| **P** | N | N | N | - | Y | N | N | Y | N |
| **I** | N | N | N | N | - | Y | N | Y | N |
| **V** | N | N | N | N | N | - | Y | N | N |
| **C** | N | N | N | N | N | N | - | N | N |
| **R** | Y | N | N | N | N | N | N | - | N |
| **E** | N | Y | N | N | N | N | N | N | - |

**Y = Allowed, N = Blocked**

### C.3 Transition Triggers

| Transition | Trigger | Actor | Preconditions |
|------------|---------|-------|---------------|
| D → S | `submit()` | Author | All mandatory fields valid, change_type set |
| S → A | `approve()` | Approver | Quality gates pass, no blocks |
| S → R | `reject()` | Approver | Reason provided |
| A → P | `start()` | Developer/Auto | Implementation begins |
| P → I | `complete()` | Developer | Code committed, VerificationCases written |
| I → V | `verify()` | QA/Auto | VerificationCases PASSED, evidence valid |
| V → C | `close()` | Approver | Final sign-off |
| D → R | `abandon()` | Author | - |
| R → D | `revise()` | Author | Address rejection reason |
| * → E | `emergency()` | Emergency Role | Incident declared |
| E → S | `retro_submit()` | Author | Within 24h deadline, SW-REQ linked |

### C.4 Mandatory Fields by State

| Field | D | S | A | P | I | V | C | R |
|-------|---|---|---|---|---|---|---|---|
| id | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| title | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| status | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| created | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| requester | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| problem | ○ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| justification | ○ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| change_type | ○ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| requirement_linkage_type | ○ | ○* | ○* | ○* | ○* | ○* | ○* | - |
| impact_level | - | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| requirement_refs | ○ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ○ |
| safety_impact | - | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| reviewer | - | - | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| approval_date | - | - | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| affected_files | - | - | - | - | ✓ | ✓ | ✓ | - |
| affected_verifications | - | - | - | - | ✓ | ✓ | ✓ | - |
| commits | - | - | - | - | ✓ | ✓ | ✓ | - |
| evidence_refs | - | - | - | - | - | ✓ | ✓ | - |
| rejection_reason | - | - | - | - | - | - | - | ✓ |

✓ = Required, ○ = Optional, - = Not applicable
* = Required when change_type = "bugfix"

---

## D. Requirement State Machine

### D.1 States

| State | Code | Definition |
|-------|------|------------|
| DRAFT | D | Initial creation |
| APPROVED | A | Ready for implementation |
| IMPLEMENTED | I | Code complete |
| VERIFIED | V | VerificationCases passed |
| DEPRECATED | X | No longer valid |

### D.2 Transitions

| From → To | D | A | I | V | X |
|-----------|---|---|---|---|---|
| **D** | - | Y | N | N | N |
| **A** | N | - | Y | N | Y |
| **I** | N | N | - | Y | Y |
| **V** | N | N | N | - | Y |
| **X** | N | N | N | N | - |

### D.3 Mandatory Fields by State

| Field | D | A | I | V | X |
|-------|---|---|---|---|---|
| id | ✓ | ✓ | ✓ | ✓ | ✓ |
| title | ✓ | ✓ | ✓ | ✓ | ✓ |
| type | ✓ | ✓ | ✓ | ✓ | ✓ |
| status | ✓ | ✓ | ✓ | ✓ | ✓ |
| description | ✓ | ✓ | ✓ | ✓ | ✓ |
| derived_from | ○ | ✓ | ✓ | ✓ | ✓ |
| refined_in | - | ○ | ○ | ○ | - |
| constrains | - | ○ | ○ | ○ | - |
| implemented_in | - | - | ✓ | ✓ | - |
| validated_by | - | - | ○ | ✓ | - |
| acceptance_criteria | ✓ | ✓ | ✓ | ✓ | - |
| safety_tag | ✓ | ✓ | ✓ | ✓ | ✓ |
| component | - | - | ✓ | ✓ | - |
| owner | ✓ | ✓ | ✓ | ✓ | ✓ |

### D.4 VerificationCase Type Must Match Requirement Level

At VERIFIED state, the VerificationCase type in validated_by must match:

| Requirement Type | Required VerificationCase.type | ID Pattern |
|-----------------|-------------------------------|-----------|
| SYS-REQ | system_verification | TC-SYST-* |
| SW-REQ | software_verification | TC-SVT-* |
| SW-ARCH | software_integration or system_integration | TC-SIT-* or TC-SYSIT-* |

---

## E. Impact Classification Decision Table

### E.1 Impact Detection from Requirement Refs

| If requirement_refs contains | Then impact_level includes |
|------------------------------|---------------------------|
| SYS-REQ-* | SYS |
| SW-ARCH-* | ARCH |
| SW-REQ-* | SW |
| File paths (src/, lib/, app/) | CODE |

### E.2 Impact Classification Decision Table

| Condition | SYS | ARCH | SW | CODE |
|-----------|-----|------|----|------|
| Externally visible behavior changed? | ✓ | - | - | - |
| Safety-relevant effect? | ✓ | - | - | - |
| Regulatory requirement touched? | ✓ | - | - | - |
| External API changed? | ✓ | - | - | - |
| Component responsibility shifted? | - | ✓ | - | - |
| Interface changed? | - | ✓ | - | - |
| Data model changed? | - | ✓ | - | - |
| Security mechanism structural? | - | ✓ | - | - |
| Software behavior changed? | - | - | ✓ | - |
| Logic/function changed? | - | - | ✓ | - |
| Data processing changed? | - | - | ✓ | - |
| Bug fix — code deviates from clear SW-REQ (pure impl bug)? | - | - | ✓ | - |
| Bug fix — SW-REQ ambiguous/incomplete (req bug)? | - | ○* | ✓ | - |
| Bug fix — no SW-REQ covers behavior (missing req bug)? | ○** | - | ✓ | - |
| Bug fix — interface/component root cause (arch bug)? | - | ✓ | ✓ | - |
| Bug fix — safety/regulatory relevant (system bug)? | ✓ | - | ✓ | - |
| Code file modified? | - | - | - | ✓ |

○* = possible ARCH impact if ambiguity affects architecture constraints
○** = possible SYS impact if specification gap has system-level consequences

---

## F. Derivation and Verification Rules

### F.1 Derivation Obligation Matrix

| Parent Level | Child Level | Obligation | Min | Max | Severity |
|--------------|-------------|------------|----|-----|----------|
| SYS-REQ | SW-REQ | MUST derive | 1 | 7 | BLOCKING |
| SW-ARCH | SW-REQ | MUST constrain | 1 | 10 | WARNING |
| SW-REQ | CODE | MUST implement | 1 | N | BLOCKING |
| SW-REQ | VerificationCase (software_verification) | MUST verify | 1 | N | BLOCKING at IMPLEMENTED |
| SYS-REQ | VerificationCase (system_verification) | MUST verify | 1 | N | BLOCKING at IMPLEMENTED |
| SW-ARCH | VerificationCase (software_integration or system_integration) | MUST verify | 1 | N | BLOCKING at IMPLEMENTED |

### F.2 Parent/Child Link Rules

| Parent | Child | Forward Link | Backward Link |
|--------|-------|--------------|---------------|
| CR | Requirement | `impacts` | `changed_by` |
| SYS-REQ | SW-REQ | `refined_in` | `derived_from` |
| SW-ARCH | SW-REQ | `constrains` | `constrained_by` |
| SW-REQ | CODE | `implemented_in` | `implements` |
| SW-REQ | VerificationCase (TC-SVT-*) | `validated_by` | `validates` |
| SW-REQ | VerificationCase (TC-UT-*) | `validated_by` | `validates` |
| SYS-REQ | VerificationCase (TC-SYST-*) | `validated_by` | `validates` |
| SW-ARCH | VerificationCase (TC-SIT-*) | `validated_by` | `validates` |
| SW-ARCH | VerificationCase (TC-SYSIT-*) | `validated_by` | `validates` |

### F.3 VerificationCase Type Mapping (Binding)

| VerificationCase.type | ID Pattern | Verifies Requirement Level | Required for |
|----------------------|-----------|---------------------------|-------------|
| unit | TC-UT-{Nr} | CODE / unit design | Recommended for all SW-REQ |
| software_integration | TC-SIT-{Nr} | SW-ARCH | Mandatory when SW-ARCH exists |
| software_verification | TC-SVT-{Nr} | SW-REQ | Mandatory for all SW-REQ |
| system_integration | TC-SYSIT-{Nr} | SW-ARCH (system scope), cross-component | Mandatory for system-scope SW-ARCH |
| system_verification | TC-SYST-{Nr} | SYS-REQ | Mandatory for all SYS-REQ |

---

## G. Approval Authority Matrix

### G.1 Roles and Permissions

| Role | Can Approve | Can Reject | Can Emergency |
|------|-------------|------------|---------------|
| Developer | - | - | Own changes only |
| Team Lead | CR, SW-REQ | Any | Any |
| Architect | SW-ARCH, CR | ARCH-related | Any |
| QA Lead | VERIFIED state | Quality gates | - |
| Compliance Officer | Regulatory CRs | Non-compliant | Safety-critical |
| Emergency On-Call | Emergency CRs | - | Any |

### G.2 Approval Requirements by Impact

| Impact Level | Approver Count | Required Roles |
|--------------|----------------|----------------|
| CODE only | 1 | Team Lead |
| SW | 1 | Team Lead |
| ARCH | 2 | Team Lead + Architect |
| SYS | 2 | Team Lead + (Architect or Compliance) |
| Safety-Critical | 3 | Team Lead + Architect + Compliance |

---

## H. Evidence Obligation Matrix

### H.1 Evidence Required by State

| Entity | State | Evidence Required | Format |
|--------|-------|-------------------|--------|
| CR | SUBMITTED | Validation report | JSON |
| CR | APPROVED | Approval record | JSON |
| CR | IMPLEMENTED | Implementation evidence + VerificationCase list | JSON |
| CR | VERIFIED | VerificationCase results (pass/fail) | JSON |
| CR | CLOSED | Complete audit package | JSON + Markdown |
| SW-REQ | IMPLEMENTED | Code links | In-file |
| SW-REQ | VERIFIED | VerificationCase results | JSON |
| VerificationCase | PASSED | Execution result | In Evidence |
| VerificationCase | FAILED | Execution result + failure details | In Evidence |

### H.2 Evidence Content Schema

```json
{
  "schema_version": "CCC-1.1.0",
  "cr_id": "CR-001",
  "timestamp": "2026-04-11T14:30:00Z",
  "status": "CLOSED",
  "change_type": "bugfix",
  "requirement_linkage_type": "existing_ref",
  "root_cause_category": "impl_bug",
  "validation": {
    "mandatory_fields": {"passed": true},
    "impact_classification": {"passed": true, "levels": ["SW"]},
    "derivation_obligations": {"passed": true, "issues": []},
    "bidirectional_links": {"passed": true}
  },
  "traceability": {
    "requirement_refs": ["SW-REQ-001"],
    "links_verified": true
  },
  "implementation": {
    "commits": ["abc123"],
    "files_changed": ["src/auth.py"],
    "verification_cases": ["TC-SVT-012"]
  },
  "verification_results": [
    {
      "verification_case_id": "TC-SVT-012",
      "type": "software_verification",
      "result": "PASS",
      "executed_at": "2026-04-11T14:25:00Z",
      "validates": ["SW-REQ-001"]
    }
  ],
  "approval": {
    "approver": "lead@example.com",
    "date": "2026-04-11T11:00:00Z"
  },
  "hash": "sha256:..."
}
```

### H.3 Bugfix-Specific Evidence Fields

When change_type = "bugfix", evidence MUST include:

```json
{
  "change_type": "bugfix",
  "requirement_linkage_type": "existing_ref",
  "root_cause_category": "impl_bug",
  "regression_verification_ids": ["TC-SVT-012"]
}
```

root_cause_category values: `impl_bug`, `req_ambiguous`, `req_missing`, `arch_bug`, `sys_bug`

---

## I. Emergency / Hotfix / Retro-CR Process

### I.1 Emergency Declaration

**When:** Production incident requiring immediate fix
**Who can declare:** Emergency On-Call, Team Lead, Architect

**Result:**
- CR created with status = EMERGENCY
- ID pattern: CR-[ID]-EMG
- 24-hour countdown starts

### I.2 Emergency Rules

| Rule | Enforcement |
|------|-------------|
| Must submit within 24h | Auto-escalate if deadline missed |
| Must have incident ticket reference | Required field: incident_id |
| Must have post-mortem commitment | Required field: post_mortem_date |
| SW-REQ linkage must be established before E→S transition | The 24h clock defers documentation, not linkage |
| Same validation as normal CR | After submit |
| Can be rejected | If insufficient justification |

---

## J. Open Points

### OP-1: Emergency Changes
- **Decision:** Emergency CR retroactive with 24h deadline. SW-REQ linkage before E→S. Per Section I.2.

---

**END OF AUTHORITATIVE PROCESS CONTRACT**

This document is the authoritative source for Compliance Change Control process.
For intervention/blocking process, see ACCOUNTABLE_AGENT_LAYER_PROCESS.md.
