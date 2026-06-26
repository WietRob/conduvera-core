# Compliance Change Control Rules — Authoritative

> **⚠️ LEGACY NOTICE:** This replaces the mixed COMPLIANCE_CHANGE_CONTROL_RULES_BINDING.md.
> For Accountable Agent Layer rules, see ACCOUNTABLE_AGENT_LAYER_RULES.md.

**Status:** AUTHORITATIVE  
**Version:** 2.0.0  
**Date:** 2026-04-11  
**Scope:** Compliance Change Control ONLY

---

## 1. Pragmatic ASPICE Hierarchy (Binding)

```
CR
└── SYS-REQ (only for system effect/safety/regulatory)
    └── SW-REQ (required for almost every software change)
        ├── SW-ARCH (only for structure/interfaces)
        ├── CODE (implementation — linked artifact)
        ├── VerificationCase (verification — required per level, entity per PROCESS.md B.4)
        └── Evidence (audit trail — required at VERIFIED)
```

**Verification mapping (binding):**

| Requirement Level | Verified by VerificationCase.type | ID Pattern |
|---|---|---|
| SYS-REQ | system_verification | TC-SVT-{Nr} |
| SW-REQ | software_verification | TC-SVT-{Nr} |
| SW-ARCH | software_integration or system_integration | TC-SIT-{Nr} or TC-SYSIT-{Nr} |
| CODE / unit design | unit | TC-UT-{Nr} |
| Interface / component interaction | software_integration | TC-SIT-{Nr} |
| System-level externally visible behavior | system_verification | TC-SVT-{Nr} |

**VerificationCase = specification artifact (planned test).**
**Evidence / VerificationResult = execution/result artifact (test outcome).**
These are separate concepts and MUST NOT be conflated.

**NOT Required:**
- User Stories (optional, allowed above SYS-REQ but not canonical)
- NFR as separate hierarchy (modeled as tags on SYS-REQ/SW-REQ)
- IF-SYS (optional, only for external interfaces)

---

## 2. When Each Level Is Required

### 2.1 SYS-REQ Required When:
- [ ] Externally visible behavior changes
- [ ] Safety-relevant effect exists
- [ ] Regulatory requirements touched (GDPR, ISO, etc.)
- [ ] System-wide interfaces changed
- [ ] External interfaces (APIs, hardware) affected

**When SYS-REQ Required:**
- CR must link to SYS-REQ
- SW-REQ must derive from SYS-REQ (`derived_from`)
- SYS-REQ must be verified by VerificationCase(s) of type `system_verification` (TC-SVT-*)

### 2.2 SW-REQ Required When:
- [ ] Software behavior changes
- [ ] Logic/function changes
- [ ] Data processing changes
- [ ] Bug fix — all categories per Section 10

**HARD RULE:**
> Without SW-REQ or justified exception, no functional software change.

**When SW-REQ Required:**
- CR must link to SW-REQ
- Code must link to SW-REQ (`implements`)
- SW-REQ must be verified by VerificationCase(s) of type `software_verification` (TC-SVT-*)
- Unit verification (TC-UT-*) recommended for code-level coverage

### 2.3 SW-ARCH Required When:
- [ ] Component responsibility shifts
- [ ] Interfaces change
- [ ] Data model/function interfaces change
- [ ] Security mechanisms structurally adapted
- [ ] Technical architecture decision affected

**When SW-ARCH Required:**
- CR must link to SW-ARCH
- SW-REQ must be constrained by SW-ARCH (`constrained_by`)
- SW-ARCH must be verified by VerificationCase(s) of type `software_integration` (TC-SIT-*) or `system_integration` (TC-SYSIT-*) depending on scope
- ADR should be created

### 2.4 CODE (Required Link, Not a Requirement)
- Every code change must link to SW-REQ
- No "free" code without requirement reference
- Unit verification (TC-UT-*) recommended per CODE/SW-REQ

### 2.5 VerificationCase and Evidence Required Before Close
- [ ] At least one VerificationCase per linked SW-REQ (type per mapping in Section 1)
- [ ] SYS-REQ requires at least one VerificationCase of type `system_verification`
- [ ] SW-ARCH requires at least one VerificationCase of type `software_integration` or `system_integration`
- [ ] VerificationCase result (Evidence) documented
- [ ] Evidence file generated

---

## 3. Parent/Child Rules per Level

### 3.1 CR → Requirements
- CR has `impacts: [Requirement-IDs]`
- Requirements have `changed_by: [CR-ID]` (auto)

### 3.2 SYS-REQ → SW-REQ
- Required: SYS-REQ has `refined_in: [SW-REQ-IDs]`
- Required: SW-REQ has `derived_from: [SYS-REQ-ID]`
- Cardinality: 1 SYS-REQ → 1-7 SW-REQs

### 3.3 SW-REQ → CODE
- Required: SW-REQ has `implemented_in: [File-Paths]`
- Required: Code has `implements: [SW-REQ-ID]` (in Docstring/Header)
- Cardinality: 1 SW-REQ → 1-n Files

### 3.4 SW-REQ → VerificationCase
- Required: SW-REQ has `validated_by: [VerificationCase-IDs]`
- Required: VerificationCase has `validates: [SW-REQ-ID]`
- Cardinality: At least 1 VerificationCase per SW-REQ
- VerificationCase.type must be `software_verification` (TC-SVT-*) for SW-REQ
- Unit verification (TC-UT-*) is additional, not a substitute

### 3.5 SW-ARCH → VerificationCase
- Required: SW-ARCH has `validated_by: [VerificationCase-IDs]`
- VerificationCase.type must be `software_integration` (TC-SIT-*) or `system_integration` (TC-SYSIT-*)
- Required when SW-ARCH exists

### 3.6 SYS-REQ → VerificationCase
- Required: SYS-REQ has `validated_by: [VerificationCase-IDs]`
- VerificationCase.type must be `system_verification` (TC-SVT-*)
- Required when SYS-REQ exists

### 3.7 SW-ARCH → SW-REQ (Constraint)
- When SW-ARCH exists: SW-ARCH has `constrains: [SW-REQ-IDs]`
- SW-REQ has `constrained_by: [SW-ARCH-ID]`

---

## 4. Minimum Required Fields per Requirement

### 4.1 SYS-REQ
```yaml
id: SYS-REQ-[Nr]                    # Required
title: String                       # Required
type: system_requirement            # Required
domain: String                      # Required
status: Enum [DRAFT, APPROVED, IMPLEMENTED, VERIFIED]  # Required
description: String (normative sentence)  # Required (MUST/SHOULD/MAY)
derived_from: ID [US-ID or CR-ID]   # Required (source)
refined_in: [SW-REQ-IDs]            # Required (child links)
validated_by: [TC-SVT-IDs]          # Required (verification links — system_verification)
acceptance_criteria: [String]       # Required (min 1)
safety_tag: Enum [SAFETY-CRITICAL, SAFETY-RELATED, NONE]  # Required
compliance_tags: [GDPR, ISO27001, etc.]  # Optional
owner: String                       # Required
```

### 4.2 SW-REQ
```yaml
id: SW-REQ-[Nr]                     # Required
title: String                       # Required
type: software_requirement          # Required
domain: String                      # Required
status: Enum [DRAFT, APPROVED, IMPLEMENTED, VERIFIED]  # Required
description: String (normative sentence)  # Required
derived_from: ID [SYS-REQ-ID]       # Required (parent)
constrained_by: [SW-ARCH-IDs]       # Required if ARCH exists
implemented_in: [File-Paths]        # Required (after implementation)
validated_by: [TC-SVT-IDs, TC-UT-IDs]  # Required (min 1 software_verification)
acceptance_criteria: [String]       # Required (min 1)
safety_tag: Enum [SAFETY-CRITICAL, SAFETY-RELATED, NONE]  # Required
compliance_tags: [GDPR, etc.]       # Optional
component: String                   # Required (module/class name)
owner: String                       # Required
```

### 4.3 SW-ARCH
```yaml
id: SW-ARCH-[Nr]                    # Required
title: String                       # Required
type: architecture                  # Required
domain: String                      # Required
status: Enum [DRAFT, APPROVED, IMPLEMENTED]  # Required
description: String                 # Required (pattern/constraint)
derived_from: ID [SYS-REQ-ID]       # Required (source)
constrains: [SW-REQ-IDs]            # Required (constrained requirements)
validated_by: [TC-SIT-IDs, TC-SYSIT-Ids]  # Required (software_integration or system_integration)
acceptance_criteria: [String]       # Required (min 1)
pattern_name: String                # Optional (e.g., "Protocol-based")
owner: String                       # Required
```

### 4.4 VerificationCase (Canonical Entity)
```yaml
id: TC-{TYPE}-{Nr}                  # Required. TYPE ∈ {UT, SIT, SVT, SYSIT, SYST}
title: String                       # Required. e.g. "Verify null token handling"
type: Enum [unit, software_integration, software_verification, system_integration, system_verification]  # Required
status: Enum [DRAFT, APPROVED, PASSED, FAILED, DEPRECATED]  # Required
description: String                 # Required. What is being verified and how
validates: [Requirement-IDs]        # Required (min 1). Backward link to requirements
implemented_in: File-Path           # Required. Test file location
component: String                   # Required. Module under test
owner: String                       # Required
created: Date                       # Auto

# Optional
prerequisite: String                # e.g. "Requires running database"
test_data: String                   # Reference to test data
last_run: Date                      # Last execution timestamp
last_result: Enum [PASS, FAIL, SKIP]  # Last execution result
```

**ID Pattern Rules:**

| type | ID Pattern | Verifies |
|------|-----------|----------|
| unit | TC-UT-{Nr} | CODE / unit design |
| software_integration | TC-SIT-{Nr} | SW-ARCH, interface contracts |
| software_verification | TC-SVT-{Nr} | SW-REQ |
| system_integration | TC-SYSIT-{Nr} | SW-ARCH (system scope), cross-component |
| system_verification | TC-SYST-{Nr} | SYS-REQ |

**Storage:** `verification/TC-{TYPE}-{Nr}.md` (Markdown with YAML frontmatter)

**VerificationCase States:**
- DRAFT: Verification written but not reviewed
- APPROVED: Verification reviewed, ready to run
- PASSED: Verification executed and passed
- FAILED: Verification executed and failed
- DEPRECATED: Verification no longer relevant

**State Transitions:**
```
DRAFT → APPROVED → PASSED
                  → FAILED → APPROVED  (re-run after fix)
         → DEPRECATED
```

---

## 5. Minimum Required Fields per CR

```yaml
id: CR-[Nr]                         # Auto-generated
title: String                       # Required (max 80 chars)
status: Enum [DRAFT, SUBMITTED, APPROVED, IN_PROGRESS, IMPLEMENTED, VERIFIED, CLOSED, REJECTED, EMERGENCY]  # Required
created: Date                       # Auto
requester: String                   # Required

problem: String                     # Required (what is the problem?)
justification: String               # Required (why needed?)

change_type: Enum [feature, bugfix, refactor, test, docs]  # Required at SUBMITTED
requirement_linkage_type: Enum [existing_ref, updated_ref, new_ref]  # Required at SUBMITTED when change_type=bugfix

impact_level: Enum [SYS, SW-REQ, SW-ARCH, CODE]  # Required (auto-detected)
requirement_refs: [IDs]             # Required (min 1)

affected_files: [File-Paths]        # Required (at IMPLEMENTED)
affected_verifications: [TC-IDs]    # Required (at IMPLEMENTED)

parent_impact: Bool                 # Required (changes parent requirement?)
child_derivations: [IDs]            # Required if parent-impact (new children)

reviewer: String                    # Required (at APPROVED)
approval_date: Date                 # Required (at APPROVED)
approval_comment: String            # Optional

evidence_refs: [File-Paths]         # Required (at CLOSED)
commits: [SHA]                      # Required (at IMPLEMENTED)

safety_impact: Enum [NONE, LOW, MEDIUM, HIGH]  # Required
compliance_impact: [Tags]           # Required if regulatory
```

---

## 6. Hard Rules (Binding)

### Rule 1: CR Required
> **No CR, no regular change.**

- Every engineering change starts with CR
- No code changes without CR (except emergency fix with retroactive CR)

### Rule 2: SW-REQ Required
> **Without SW-REQ or justified exception, no functional software change.**

- Every software change must link to SW-REQ
- Exception requires team lead approval documented in CR.approval_comment
- Exception must include a justification string
- The exception is recorded in evidence

### Rule 3: ARCH Required for Structure
> **If architecture affected, SW-ARCH must be included.**

- Interface changes → SW-ARCH required
- Component moves → SW-ARCH required
- Safety mechanism changes → SW-ARCH required

### Rule 4: SYS Required for System Effect
> **If system effect affected, SYS-REQ must be included.**

- Externally visible behavior → SYS-REQ required
- Safety-relevant → SYS-REQ required
- Regulatory → SYS-REQ required

### Rule 5: Verification Required Before Close
> **No verification evidence, no close.**

- Evidence file must exist
- Must contain VerificationCase results
- Must verify traceability links
- C blocks CLOSE without evidence

---

## 7. Interface to Accountable Agent Layer

Compliance Change Control provides:

```python
ChangeRequestService:
  - create_cr(fields) → CR-ID
  - get_cr(cr_id) → CR-Object
  - validate_links(cr_id) → Bool
  - generate_evidence(cr_id) → Path
  - check_status(cr_id) → Status
  - validate_id_format(id) → Bool

EvidenceService:
  - generate_cr_evidence(cr_id) → JSON
  - verify_traceability(cr_id) → Report

VerificationService:
  - create_verification(fields) → TC-ID
  - get_verification(tc_id) → VerificationCase
  - validate_verification_type(tc_id, req_id) → Bool
```

Accountable Agent Layer consumes these services.

---

## 8. Definition of Done

### 8.1 CR is "Done" (CLOSED) when:
- [ ] Status = CLOSED
- [ ] Evidence file exists
- [ ] All linked requirements exist
- [ ] Bidirectional links verified
- [ ] VerificationCase results present and PASSED
- [ ] Commits linked
- [ ] Safety/compliance tags checked
- [ ] For change_type=bugfix: root_cause_category documented

### 8.2 Requirement is "Done" (VERIFIED) when:
- [ ] Status = VERIFIED
- [ ] Implementation linked
- [ ] VerificationCase(s) linked and PASSED
- [ ] VerificationCase.type matches requirement level (per Section 1)
- [ ] Review conducted
- [ ] Acceptance criteria met

---

## 9. Bugfix Policy (Binding)

### 9.1 Principle

Every bugfix, regardless of severity or urgency, starts with a CR.
Every functional bugfix links to at least one SW-REQ.
No bugfix may close without verification evidence from VerificationCase(s) of the correct type.

### 9.2 CR Classification

Every CR MUST declare a change_type:
    change_type: Enum [feature, bugfix, refactor, test, docs]

For bugfixes, change_type MUST be "bugfix".
This classification is mandatory at SUBMITTED state.

### 9.3 Requirement Linkage Rules

A bugfix MUST link to an existing SW-REQ when:
    The SW-REQ already correctly describes the intended behavior.
    The implementation simply deviated from a clear, unambiguous requirement.
    This is a pure implementation bug.
    Action: Reference the existing SW-REQ in CR.requirement_refs.

A bugfix MUST revise the existing SW-REQ when:
    The SW-REQ exists but is ambiguous, incomplete, or contradicts the correct behavior.
    The fix requires changing the normative statement itself.
    This is an ambiguous requirement bug.
    Action: Move SW-REQ status to DRAFT. Revise description and acceptance criteria.
    Link CR to the revised SW-REQ.
    Record the revision in CR.evidence as a requirement change record.

A bugfix MUST create a new SW-REQ when:
    No existing SW-REQ covers the buggy behavior domain.
    The defect reveals a specification gap.
    This is a missing requirement bug.
    Action: Create SW-REQ in DRAFT. Set derived_from to parent SYS-REQ if one exists.
    Derive through DRAFT→APPROVED before the CR transitions past SUBMITTED.
    Link CR to new SW-REQ.

### 9.4 Escalation Triggers

SYS-REQ linkage becomes mandatory when:
    - The defect affects externally visible system behavior.
    - safety_impact >= MEDIUM.
    - The defect touches a regulatory requirement (GDPR, ISO, etc.).
    - The root cause is a system-level specification error.

SW-ARCH linkage becomes mandatory when:
    - The root cause is an interface contract error between components.
    - The fix changes component boundaries or responsibilities.
    - The fix modifies error-handling or data-flow architecture.

VerificationCase linkage becomes mandatory when:
    - CR is at IMPLEMENTED state.
    - At least one regression VerificationCase MUST exist per linked SW-REQ.
    - VerificationCase.type MUST match the requirement level per Section 1.
    - VerificationCase ID MUST appear in CR.affected_verifications and in SW-REQ.validated_by.

### 9.5 Emergency Bugfix Rule

Emergency bugfixes (CR status = EMERGENCY):
    - A CR MUST be created within 24h of the fix deploy.
    - The CR MUST have change_type = "bugfix".
    - SW-REQ linkage MUST be established before E→S transition
      (retro-CR submit). The 24h clock defers documentation, not the linkage requirement.
    - incident_id is a mandatory field for EMERGENCY CRs.
    - Post-mortem date MUST be committed at E→S.

### 9.6 Blocking

The system blocks a bugfix when:
    - No CR exists.
    - CR has no SW-REQ in requirement_refs.
    - change_type = "bugfix" and requirement_linkage_type = "new_ref" but the new SW-REQ is not APPROVED.
    - CR is at IMPLEMENTED and affected_verifications is empty.

The system warns (does not block) when:
    - change_type = "bugfix" and the linked SW-REQ is in DRAFT.
    - No regression VerificationCase linked yet (at IN_PROGRESS, allowed; blocked at IMPLEMENTED).
    - Root-cause category not documented in CR (recommended, not mandatory for non-safety bugs).

### 9.7 requirement_linkage_type

For change_type = "bugfix", the CR MUST declare how it links:
    requirement_linkage_type: Enum [existing_ref, updated_ref, new_ref]

    existing_ref: CR references an existing, unchanged SW-REQ.
    updated_ref: CR references an SW-REQ that was revised for this fix.
    new_ref: CR references a newly created SW-REQ.

---

## 10. Bugfix Decision Table

| Bugfix Category | Trigger / Indicator | Mandatory Artifacts | Optional Artifacts | Block Condition | Warning Condition |
|---|---|---|---|---|---|
| Pure implementation bug | Code deviates from clear SW-REQ. SW-REQ is correct and unambiguous | CR, existing SW-REQ ref, VerificationCase (TC-SVT-*), Evidence | Root-cause note in CR | No SW-REQ in refs; no VerificationCase at IMPLEMENTED | SW-REQ in DRAFT; root-cause not documented |
| Ambiguous requirement bug | SW-REQ exists but is unclear, incomplete, or contradicts correct behavior | CR, revised SW-REQ (DRAFT→APPROVED), VerificationCase (TC-SVT-*), Evidence | ADR if interpretation is non-obvious | SW-REQ not moved to DRAFT; no VerificationCase at IMPLEMENTED; revised SW-REQ not APPROVED | Acceptance criteria still incomplete on revised SW-REQ |
| Missing requirement bug | No SW-REQ covers the buggy behavior domain | CR, new SW-REQ (DRAFT→APPROVED), VerificationCase (TC-SVT-*), Evidence | Parent SYS-REQ if domain has system scope | New SW-REQ not created; new SW-REQ not APPROVED before CR past SUBMITTED; no VerificationCase at IMPLEMENTED | No parent SYS-REQ for the domain |
| Architecture-affecting bug | Root cause is interface contract or component responsibility error | CR, SW-ARCH ref or new SW-ARCH, SW-REQ, VerificationCase (TC-SIT-* or TC-SYSIT-*), Evidence | ADR, interface contract update, component diagram update | No SW-ARCH linked; interface change without SW-ARCH review; no VerificationCase at IMPLEMENTED | ADR not created; component diagram unchanged |
| System/safety/regulatory bug | Defect affects externally visible behavior or is safety/regulatory relevant | CR, SYS-REQ (create if missing), SW-REQ, VerificationCase (TC-SYST-*), Evidence | Post-mortem, rollback plan, regulatory review record | No SYS-REQ linked; safety_impact not set; <2 approvers for SYS; no post-mortem committed for safety >= MEDIUM; no VerificationCase at IMPLEMENTED | safety_impact=NONE but SYS-REQ present (possible misclassification) |
| Emergency/hotfix bug | Production incident requiring immediate fix | CR (EMERGENCY state), SW-REQ linked before E→S, VerificationCase (correct type), Evidence | Incident ticket link, post-mortem date, rollback plan | Retro-CR not within 24h; SW-REQ not linked before E→S; no incident_id; no VerificationCase at IMPLEMENTED | SW-REQ in DRAFT; post-mortem not yet scheduled |

---

## 11. Open Points

### OP-1: Emergency Changes
- **Decision:** Emergency CR retroactive with 24h deadline. SW-REQ linkage before E→S. Per Section 9.5.

---

**END OF AUTHORITATIVE RULES**

This document is the authoritative source for Compliance Change Control rules.
For blocking/intervention rules, see ACCOUNTABLE_AGENT_LAYER_RULES.md.
