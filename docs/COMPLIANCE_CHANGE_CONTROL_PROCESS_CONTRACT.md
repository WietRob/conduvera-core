# Compliance Change Control / Accountable Agent Layer Process Contract — Executable Specification

> **⚠️ LEGACY WARNING:** This is a mixed-content document. Do not extend. Use authoritative docs instead:
> - For C: COMPLIANCE_CHANGE_CONTROL_*.md
> - For B: ACCOUNTABLE_AGENT_LAYER_*.md


**Status:** DEPRECATED — Do Not Extend  
**Version:** 1.0.0  
**Date:** 2026-04-10  
**Source:** COMPLIANCE_CHANGE_CONTROL_RULES_BINDING.md conversion
**Replaced by:** COMPLIANCE_CHANGE_CONTROL_PROCESS.md + ACCOUNTABLE_AGENT_LAYER_PROCESS.md

---

## A. Scope and Purpose

This document provides the executable process contract for:
- **Compliance Change Control (Compliance-CR):** Change Request workflow with ASPICE-aligned traceability
- **Accountable Agent Layer (Accountable Agent):** Active intervention layer for AI-assisted changes

**Purpose:** Enable implementation without ambiguity.

**Scope IN:**
- CR state machine with exact transitions
- Requirement state machine
- Impact classification logic
- Blocking/warning rules
- Evidence obligations
- Emergency/retro-CR flow

**Scope OUT:**
- Code implementation
- UI/UX design
- AI model integration
- External tool adapters

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

### B.3 Accountable Change (Accountable Agent Layer)

```yaml
Entity: AccountableChange
ID Pattern: AC-[0-9A-F]{8} (e.g., AC-58D0D7B9)
Storage: In-memory (per session) + evidence file
Purpose: AI-assisted change attribution and accountability
```

### B.4 Evidence

```yaml
Entity: CREvidence
File: changes/evidence/CR-[ID]_[YYYYMMDD]_[HHMMSS].json
Purpose: Machine-readable audit trail for CR

Entity: ACEvidence
File: changes/evidence/AC-[ID]_[YYYYMMDD]_[HHMMSS].json
Purpose: Machine-readable audit trail for AccountableChange
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
| IMPLEMENTED | I | Code changes complete | All files committed, tests written |
| VERIFIED | V | Testing complete, evidence generated | Tests passed, evidence verified |
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
| D → S | `submit()` | Author | All mandatory fields valid |
| S → A | `approve()` | Approver | Quality gates pass, no blocks |
| S → R | `reject()` | Approver | Reason provided |
| A → P | `start()` | Developer/Auto | Implementation begins |
| P → I | `complete()` | Developer | Code committed |
| I → V | `verify()` | QA/Auto | Tests pass, evidence valid |
| V → C | `close()` | Approver | Final sign-off |
| D → R | `abandon()` | Author | - |
| R → D | `revise()` | Author | Address rejection reason |
| * → E | `emergency()` | Emergency Role | Incident declared |
| E → S | `retro_submit()` | Author | Within 24h deadline |

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
| impact_level | - | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| requirement_refs | ○ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ○ |
| safety_impact | - | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| reviewer | - | - | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| approval_date | - | - | ✓ | ✓ | ✓ | ✓ | ✓ | - |
| affected_files | - | - | - | - | ✓ | ✓ | ✓ | - |
| affected_tests | - | - | - | - | ✓ | ✓ | ✓ | - |
| commits | - | - | - | - | ✓ | ✓ | ✓ | - |
| evidence_refs | - | - | - | - | - | ✓ | ✓ | - |
| rejection_reason | - | - | - | - | - | - | - | ✓ |

✓ = Required, ○ = Optional, - = Not applicable

---

## D. Requirement State Machine

### D.1 States

| State | Code | Definition |
|-------|------|------------|
| DRAFT | D | Initial creation |
| APPROVED | A | Ready for implementation |
| IMPLEMENTED | I | Code complete |
| VERIFIED | V | Tests passed |
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
| Bug fix (functionally relevant)? | - | - | ✓ | - |
| Code file modified? | - | - | - | ✓ |

### E.3 Impact Enforcement Rules

| Impact Detected | Required in CR.refs | Severity if Missing |
|-----------------|--------------------|--------------------|
| SYS | SYS-REQ | BLOCKING |
| ARCH | SW-ARCH | BLOCKING |
| SW | SW-REQ | BLOCKING |
| CODE | SW-REQ (parent) | WARNING if no test |

---

## F. Derivation and Parent/Child Rules

### F.1 Derivation Obligation Matrix

| Parent Level | Child Level | Obligation | Min | Max | Severity |
|--------------|-------------|------------|----|-----|----------|
| SYS-REQ | SW-REQ | MUST derive | 1 | 7 | BLOCKING |
| SW-ARCH | SW-REQ | MUST constrain | 1 | 10 | WARNING |
| SW-REQ | CODE | MUST implement | 1 | N | BLOCKING |
| SW-REQ | TC-* | MUST validate | 1 | N | BLOCKING |

### F.2 Parent/Child Link Rules

| Parent | Child | Forward Link | Backward Link |
|--------|-------|--------------|---------------|
| CR | Requirement | `impacts` | `changed_by` |
| SYS-REQ | SW-REQ | `refined_in` | `derived_from` |
| SW-ARCH | SW-REQ | `constrains` | `constrained_by` |
| SW-REQ | CODE | `implemented_in` | `implements` |
| SW-REQ | TC-UT | `validated_by` | `validates` |
| SW-REQ | TC-IT | `validated_by` | `validates` |

### F.3 Link Cardinality Rules

| Link Type | Min | Max |
|-----------|----|-----|
| CR → Requirement | 1 | N |
| SYS-REQ → SW-REQ | 1 | 7 |
| SW-ARCH → SW-REQ | 0 | 10 |
| SW-REQ → CODE | 1 | N |
| SW-REQ → TC-* | 1 | N |

### F.4 Derivation Validation Rules

```python
def validate_derivation(cr_refs):
    """
    Returns: (valid: bool, issues: list)
    """
    issues = []
    
    # Rule: SYS-REQ must have SW-REQ children
    sys_reqs = [r for r in cr_refs if r.startswith("SYS-REQ-")]
    for sys_req in sys_reqs:
        children = get_children(sys_req, "refined_in")
        if not children:
            issues.append({
                "severity": "BLOCKING",
                "message": f"{sys_req} has no SW-REQ children (derivation obligation)",
                "rule": "SYS-REQ must derive 1-7 SW-REQs"
            })
    
    # Rule: SW-REQ must have CODE implementation
    sw_reqs = [r for r in cr_refs if r.startswith("SW-REQ-")]
    for sw_req in sw_reqs:
        impl = get_implementation(sw_req)
        if not impl:
            issues.append({
                "severity": "WARNING",
                "message": f"{sw_req} has no CODE implementation yet",
                "rule": "SW-REQ should have implemented_in links"
            })
    
    return len(issues) == 0, issues
```

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

### G.3 Approval Checklist

Before `approve()`:
- [ ] All mandatory fields present
- [ ] Impact classification correct
- [ ] Derivation obligations addressed
- [ ] Safety impact assessed
- [ ] No BLOCKING validation issues
- [ ] Reviewer assigned

---

## H. Evidence Obligation Matrix

### H.1 Evidence Required by State

| Entity | State | Evidence Required | Format |
|--------|-------|-------------------|--------|
| CR | SUBMITTED | Validation report | JSON |
| CR | APPROVED | Approval record | JSON |
| CR | IMPLEMENTED | Implementation evidence | JSON |
| CR | VERIFIED | Test results | JSON |
| CR | CLOSED | Complete audit package | JSON + Markdown |
| SW-REQ | IMPLEMENTED | Code links | In-file |
| SW-REQ | VERIFIED | Test results | JSON |

### H.2 Evidence Content Schema

**CR Evidence (JSON):**
```json
{
  "cr_id": "CR-001",
  "timestamp": "2026-04-10T14:30:00Z",
  "status": "CLOSED",
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
    "tests": ["TC-UT-001"]
  },
  "approval": {
    "approver": "lead@example.com",
    "date": "2026-04-10T11:00:00Z"
  },
  "hash": "sha256:..."
}
```

### H.3 Evidence Verification Rules

```python
def verify_evidence(cr_id):
    evidence = load_evidence(cr_id)
    
    checks = {
        "hash_valid": verify_hash(evidence),
        "status_matches": evidence.status == cr.status,
        "links_verified": all_links_exist(evidence.traceability),
        "tests_passed": all_tests_passed(evidence.implementation.tests),
        "approval_valid": approver_has_permission(evidence.approval)
    }
    
    return all(checks.values()), checks
```

---

## I. Blocking vs Warning Rules

### I.1 Blocking Conditions (Hard Stop)

| Condition | Block Message | Exit Code |
|-----------|---------------|-----------|
| No CR linked | "No CR linked. Run: curaops cr link --cr <id>" | 1 |
| CR.status != APPROVED | "CR-{id} status is {status}, must be APPROVED" | 1 |
| Missing requirement_refs | "Missing requirement_refs (min 1 required)" | 1 |
| Invalid ID format | "Invalid requirement ID format: {ids}" | 1 |
| SYS impact but no SYS-REQ | "SYS impact detected but no SYS-REQ linked" | 1 |
| ARCH impact but no SW-ARCH | "ARCH impact detected but no SW-ARCH linked" | 1 |
| SW impact but no SW-REQ | "SW impact detected but no SW-REQ linked" | 1 |
| CR file not found | "CR-{id} does not exist in changes/" | 1 |
| Safety-critical without approval | "Safety-critical change requires Compliance approval" | 1 |
| Emergency CR expired | "Emergency CR deadline (24h) exceeded" | 1 |

### I.2 Warning Conditions (Allow with Status)

| Condition | Warning Message | Result Status |
|-----------|-----------------|---------------|
| Requirement file not found | "Requirement {id} file not found (expected)" | warning |
| Derivation obligation pending | "Derivation obligation not yet addressed" | warning |
| Test coverage < 100% | "Test coverage incomplete ({pct}%)" | warning |
| Missing ARCH but ARCH-like change | "Possible ARCH impact - verify manually" | warning |
| No CODE links yet | "No CODE implementation linked" | pending |
| Evidence hash mismatch | "Evidence hash mismatch - regenerate" | warning |

### I.3 Info Conditions (No Effect)

| Condition | Info Message |
|-----------|--------------|
| AI suggestion available | "Similar CR found: {cr_id}" |
| Estimated effort calculated | "Estimated effort: {hours}h" |
| Related requirements detected | "Related: {req_ids}" |

### I.4 Decision Flow

```
Check BLOCKING conditions first
    └── If any BLOCK → STOP, return exit 1

Then check WARNING conditions
    └── If any WARN → ALLOW, status = "warning", log issues

Then check INFO conditions
    └── Log only, no status change

If no blocks → status = "valid", proceed
```

---

## J. Emergency / Hotfix / Retro-CR Process

### J.1 Emergency Declaration

**When:** Production incident requiring immediate fix

**Who can declare:** Emergency On-Call, Team Lead, Architect

**How:**
```bash
curaops cr create --emergency \
  --title "Hotfix: [description]" \
  --problem "[incident description]" \
  --justification "[business justification]"
```

**Result:**
- CR created with status = EMERGENCY
- ID pattern: CR-[ID]-EMG
- 24-hour countdown starts

### J.2 Emergency Workflow

```
EMERGENCY (E)
    ↓ immediate
[Fix implemented in production]
    ↓ within 24h
SUBMITTED (S) [retroactive]
    ↓ review
APPROVED (A) or REJECTED (R)
    ↓ if approved
CLOSED (C) [if evidence complete]
    ↓ if rejected
ESCALATION required
```

### J.3 Emergency Rules

| Rule | Enforcement |
|------|-------------|
| Must submit within 24h | Auto-escalate if deadline missed |
| Must have incident ticket reference | Required field: incident_id |
| Must have post-mortem commitment | Required field: post_mortem_date |
| Same validation as normal CR | After submit |
| Can be rejected | If insufficient justification |

### J.4 Retro-CR Policy

| Scenario | Action |
|----------|--------|
| Emergency fix applied | Must create retro-CR within 24h |
| Small fix (< 10 lines) | Retro-CR allowed, streamlined review |
| Documentation fix | Retro-CR optional (team discretion) |
| Test-only fix | Retro-CR required |
| Config change | Retro-CR required |

### J.5 Emergency Evidence Requirements

```yaml
Emergency CR Additional Fields:
  incident_id: String (Pflicht)
  severity: Enum [P0, P1, P2] (Pflicht)
  affected_systems: [String] (Pflicht)
  rollback_plan: String (Pflicht)
  post_mortem_date: Date (Pflicht)
  production_change_id: String (Optional)
```

---

## K. Machine-Readable Schema Contract

### K.1 CR Schema

```yaml
CR:
  type: object
  required: [id, title, status, created, requester, problem, justification, impact_level, requirement_refs, safety_impact]
  properties:
    id:
      type: string
      pattern: "^CR-[0-9]{3,}$"
    title:
      type: string
      minLength: 10
      maxLength: 80
    status:
      type: string
      enum: [DRAFT, SUBMITTED, APPROVED, IN_PROGRESS, IMPLEMENTED, VERIFIED, CLOSED, REJECTED, EMERGENCY]
    created:
      type: string
      format: date-time
    requester:
      type: string
    problem:
      type: string
      minLength: 50
    justification:
      type: string
      minLength: 20
    impact_level:
      type: array
      items:
        enum: [SYS, ARCH, SW, CODE]
    requirement_refs:
      type: array
      minItems: 1
      items:
        pattern: "^(SYS-REQ|SW-REQ|SW-ARCH)-[0-9]+$"
    safety_impact:
      type: string
      enum: [NONE, LOW, MEDIUM, HIGH, CRITICAL]
    reviewer:
      type: string
    approval_date:
      type: string
      format: date-time
    affected_files:
      type: array
      items:
        type: string
    affected_tests:
      type: array
      items:
        pattern: "^TC-(UT|IT|ST)-[0-9]+$"
    commits:
      type: array
      items:
        pattern: "^[a-f0-9]{7,40}$"
    evidence_refs:
      type: array
      items:
        type: string
```

### K.2 SW-REQ Schema

```yaml
SW_REQ:
  type: object
  required: [id, title, type, status, description, derived_from, acceptance_criteria, safety_tag, owner]
  properties:
    id:
      type: string
      pattern: "^SW-REQ-[0-9]+$"
    title:
      type: string
    type:
      const: software_requirement
    status:
      enum: [DRAFT, APPROVED, IMPLEMENTED, VERIFIED, DEPRECATED]
    description:
      type: string
      minLength: 50
    derived_from:
      type: string
      pattern: "^(SYS-REQ|SW-ARCH)-[0-9]+$"
    constrained_by:
      type: array
      items:
        pattern: "^SW-ARCH-[0-9]+$"
    implemented_in:
      type: array
      items:
        type: string
    validated_by:
      type: array
      minItems: 1
      items:
        pattern: "^TC-(UT|IT)-[0-9]+$"
    acceptance_criteria:
      type: array
      minItems: 1
      items:
        type: string
    safety_tag:
      enum: [SAFETY-CRITICAL, SAFETY-RELATED, NONE]
    component:
      type: string
    owner:
      type: string
```

### K.3 AccountableChange Schema (Accountable Agent Layer)

```yaml
AccountableChange:
  type: object
  required: [accountable_id, agent_context, change_intent, cr_id, requirement_refs, status, created_at]
  properties:
    accountable_id:
      type: string
      pattern: "^AC-[0-9A-F]{8}$"
    agent_context:
      type: object
      required: [agent_id, agent_name, model, tools_used]
      properties:
        agent_id:
          type: string
        agent_name:
          type: string
        model:
          type: string
        tools_used:
          type: array
          items:
            type: string
        session_id:
          type: string
    change_intent:
      type: object
      required: [description, change_type, files_affected]
      properties:
        description:
          type: string
        change_type:
          enum: [feature, bugfix, refactor, test, docs]
        files_affected:
          type: array
          items:
            type: string
        estimated_impact:
          enum: [CRITICAL, HIGH, MEDIUM, LOW]
    cr_id:
      type: string
      pattern: "^CR-[0-9]{3,}$"
    requirement_refs:
      type: array
      minItems: 1
      items:
        pattern: "^(SYS-REQ|SW-REQ|SW-ARCH)-[0-9]+$"
    status:
      enum: [pending, linked, validated, blocked]
    created_at:
      type: string
      format: date-time
    evidence_path:
      type: string
    block_reason:
      type: string
```

---

## L. Worked Examples

### Example 1: Simple Bug Fix

**Scenario:** Fix null pointer exception in auth module

```yaml
CR:
  id: CR-042
  title: "Fix NPE in auth validation"
  status: CLOSED
  problem: "NullPointerException thrown when user token is expired"
  justification: "Prevents users from accessing dashboard"
  impact_level: [SW, CODE]
  requirement_refs: [SW-REQ-003]
  safety_impact: NONE
  
  # Links
  # SW-REQ-003: Token validation must handle null tokens
  #   → implemented_in: [src/auth/validator.py]
  #   → validated_by: [TC-UT-012]
```

**Validation:**
- ✓ SW-REQ present
- ✓ CODE links present
- ✓ Test passed
- ✓ Evidence generated

---

### Example 2: Architecture Change

**Scenario:** Add plugin system for detectors

```yaml
CR:
  id: CR-087
  title: "Add protocol-based plugin architecture"
  status: CLOSED
  problem: "Hard to add new detection types"
  justification: "Enable extensibility without core changes"
  impact_level: [ARCH, SW, CODE]
  requirement_refs: [SYS-REQ-005, SW-ARCH-002, SW-REQ-017]
  safety_impact: MEDIUM
  
  # Links
  # SYS-REQ-005: System must support pluggable detectors
  # SW-ARCH-002: Protocol-based plugin architecture
  #   → constrains: [SW-REQ-017, SW-REQ-018]
  # SW-REQ-017: DetectorProtocol interface
```

**Validation:**
- ✓ SYS-REQ present (system impact)
- ✓ SW-ARCH present (architecture change)
- ✓ SW-REQs derived from SW-ARCH
- ✓ Architect approval obtained
- ✓ Evidence generated

---

### Example 3: Emergency Hotfix

**Scenario:** Production data leak fix

```yaml
CR:
  id: CR-099-EMG
  title: "Hotfix: Prevent data leak in export"
  status: CLOSED
  problem: "Sensitive data visible in exports"
  justification: "GDPR violation, immediate fix required"
  impact_level: [SYS, SW, CODE]
  requirement_refs: [SYS-REQ-012, SW-REQ-045]
  safety_impact: HIGH
  
  # Emergency fields
  incident_id: INC-2026-042
  severity: P0
  affected_systems: ["export-service", "data-api"]
  rollback_plan: "Revert commit abc123"
  post_mortem_date: "2026-04-15"
  
  # Timeline
  # T+0: Emergency declared
  # T+2h: Fix deployed
  # T+4h: Retro-CR submitted
  # T+24h: CR approved, post-mortem scheduled
```

**Validation:**
- ✓ Emergency declared properly
- ✓ Submitted within 24h
- ✓ Post-mortem committed
- ✓ Evidence generated

---

### Example 4: B Block (No CR)

**Scenario:** AI agent attempts file edit without CR

```
$ curaops agent edit --file src/auth.py

[INTERVENTION POINT: PRE-FLIGHT]

ERROR: No CR linked to session sess-abc-123
ACTION REQUIRED: 
  1. Create CR: curaops cr create --title "..." --problem "..."
  2. Link to session: curaops cr link --session sess-abc-123 --cr CR-XXX
  3. Obtain approval: curaops cr approve CR-XXX

EXIT CODE: 1
WORK BLOCKED: Yes
```

---

### Example 5: B Block (Missing SW-REQ)

**Scenario:** AI agent has CR but no SW-REQ linkage

```
$ curaops agent edit --file src/auth.py --cr CR-042

[INTERVENTION POINT: PRE-FLIGHT]

ERROR: SW impact detected but no SW-REQ in requirement_refs
CURRENT REFS: [TC-UT-001]  # Only test, no requirement
ACTION REQUIRED:
  1. Identify affected SW-REQ
  2. Update CR: curaops cr update --cr CR-042 --add-ref SW-REQ-003
  3. Or justify exception with Team Lead approval

EXIT CODE: 1
WORK BLOCKED: Yes
```

---

## M. Open Decisions

### OD-1: Session-CR Default Binding

**Question:** Should session have a default CR or explicit per-change?

**Options:**
- A: Session has default CR, changes auto-link (convenient)
- B: Each change explicitly declares CR (explicit)

**Recommendation:** Start with B (explicit), add A later as optimization.

### OD-2: Auto-Detection Thresholds

**Question:** What confidence threshold for auto-detecting ARCH impact?

**Options:**
- A: Conservative (high confidence only, many manual checks)
- B: Liberal (flag potential ARCH, manual confirm)

**Recommendation:** A for safety, with clear override mechanism.

---

**END OF CONTRACT**
