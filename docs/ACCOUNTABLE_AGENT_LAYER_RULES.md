# Accountable Agent Layer Rules — Authoritative

> **⚠️ LEGACY NOTICE:** This replaces the mixed COMPLIANCE_CHANGE_CONTROL_RULES_BINDING.md sections 6-7.
> For Compliance Change Control rules, see COMPLIANCE_CHANGE_CONTROL_RULES.md.

**Status:** AUTHORITATIVE  
**Version:** 2.0.0  
**Date:** 2026-04-19  
**Scope:** Accountable Agent Layer ONLY

---

## 1. Purpose

The Accountable Agent Layer provides active intervention for AI-assisted changes:
- Captures agent attribution (who, model, tools)
- Validates accountability links (CR + requirements)
- Blocks non-compliant AI-assisted changes
- Generates accountability evidence

---

## 2. Hard Rules (Binding)

### Rule 1: CR Required for AI Changes
> **Accountable Agent Layer blocks AI changes without CR.**

- Every AI-assisted engineering change must have linked CR
- No AI code changes without CR (except emergency fix with retroactive CR)

### Rule 2: SW-REQ Reference Required
> **Accountable Agent Layer blocks when SW-REQ reference missing.**

- Every AI-assisted software change must link to SW-REQ
- Exception requires team lead approval + documentation

### Rule 3: ARCH Validation
> **Accountable Agent Layer warns when ARCH impact detected but no SW-ARCH linked.**

- Interface changes detected → warn if no SW-ARCH
- Component moves detected → warn if no SW-ARCH
- Safety mechanism changes → warn if no SW-ARCH

### Rule 4: SYS Validation
> **Accountable Agent Layer blocks when SYS impact detected but no SYS-REQ linked.**

- Externally visible behavior detected → block if no SYS-REQ
- Safety-relevant detected → block if no SYS-REQ
- Regulatory detected → block if no SYS-REQ

### Rule 5: Evidence Required
> **Accountable Agent Layer requires evidence before completing AI change.**

- Accountability evidence must be generated
- Evidence must reference CR evidence
- Evidence must include agent context

### Rule 6: Pre-Flight Block
> **Accountable Agent Layer blocks AI changes without CR + requirement linkage.**

- Pre-flight Check: CR present?
- Pre-flight Check: CR Status = APPROVED?
- Pre-flight Check: Requirement-Refs present?
- Strict Mode: No exceptions

---

## 3. When Accountable Agent Layer Blocks (Binding)

### 3.1 Hard Block (Exit 1, Work Denied)

```python
IF no CR linked to session:
    BLOCK("No CR linked. Run: curaops cr link --session <id> --cr <cr-id>")

IF CR.status != APPROVED:
    BLOCK(f"CR-{cr_id} status is {status}, must be APPROVED")

IF requirement_refs empty:
    BLOCK("No requirement refs. Minimum SW-REQ required.")

IF valid_id_pattern check fails:
    BLOCK(f"Invalid ID format: {invalid_ids}")

IF SYS-Impact detected AND no SYS-REQ in refs:
    BLOCK("System impact detected but no SYS-REQ linked")

IF ARCH-Impact detected AND no SW-ARCH in refs:
    BLOCK("Architecture impact detected but no SW-ARCH linked")

IF change_type == "bugfix" AND no SW-REQ in requirement_refs:
    BLOCK("Bugfix CR has no SW-REQ linkage (C-RULES §9.1)")

IF change_type == "bugfix" AND requirement_linkage_type == "new_ref" AND new SW-REQ not APPROVED:
    BLOCK("Bugfix references new SW-REQ that is not APPROVED (C-RULES §9.3)")

IF change_type == "bugfix" AND CR.status >= IMPLEMENTED AND affected_verifications empty:
    BLOCK("Bugfix CR at IMPLEMENTED with no VerificationCases (C-RULES §9.4)")
```

### 3.2 Warning (Allow with Status "warning")

```python
IF requirement file not found:
    WARN("Requirement file not found, expected")

IF derivation obligation detected but not addressed:
    WARN("Derivation obligation not addressed")

IF test coverage < 100% for modified SW-REQ:
    WARN("Test coverage incomplete")

IF change_type == "bugfix" AND linked SW-REQ is in DRAFT:
    WARN("Bugfix linked SW-REQ is in DRAFT status")

IF change_type == "bugfix" AND no regression VerificationCase linked (at IN_PROGRESS):
    WARN("No regression VerificationCase linked yet (required at IMPLEMENTED)")

IF change_type == "bugfix" AND root_cause_category not documented:
    WARN("Root-cause category not documented (recommended)")
```

### 3.3 Info (Documentation Only)

```python
IF AI suggestion available:
    INFO("Suggestion: Similar change in CR-XXX")
```

---

## 4. Accountability Data Model

### 4.1 Agent Context (Required)

```yaml
agent_id: String        # e.g., "claude-code-001"
agent_name: String      # e.g., "Claude Code"
model: String           # e.g., "claude-sonnet-4"
tools_used: [String]    # e.g., ["file_edit", "terminal"]
session_id: String      # Reference to Session Manager
```

### 4.2 Change Intent (Required)

```yaml
description: String     # What is being changed?
change_type: Enum       # feature, bugfix, refactor, test, docs
files_affected: [String] # Auto-captured
estimated_impact: Enum  # CRITICAL, HIGH, MEDIUM, LOW
```

### 4.3 Accountability Links (Strict Mode Required)

```yaml
cr_id: String           # MUST exist, status APPROVED
requirement_refs: [String]  # Min 1, valid IDs
```

---

## 5. Intervention Points

### 5.1 Pre-Flight Check (Before ANY Work)

**Trigger:** Agent attempts first tool call in session
**Check:** Is there an APPROVED CR linked to this session?
**Pass:** Continue to work
**Fail:** BLOCK with actionable error message

### 5.2 Capture (During Work)

**Trigger:** Each tool call (file_edit, terminal, etc.)
**Action:** Record tool in AgentContext.tools_used
**Action:** Record affected files in ChangeIntent.files_affected
**Storage:** In-memory AccountableChange registry

### 5.3 Validation (Before Review)

**Trigger:** Developer runs `curaops accountable validate`
**Check:** All mandatory links present (cr_id, requirement_refs)
**Check:** CR exists and is APPROVED
**Check:** Requirement IDs valid
**Pass:** Status → "validated"
**Fail:** Status → "blocked" with specific reason

### 5.4 Evidence (At Completion)

**Trigger:** Developer runs `curaops accountable evidence`
**Action:** Generate accountability evidence JSON
**Content:** AgentContext + ChangeIntent + CR reference + validation
**Output:** changes/evidence/AC-XXX_YYYYMMDD_HHMMSS.json

---

## 6. Definition of Done

### 6.1 AI Change is "Done" when:
- [ ] Accountable Agent Layer change created
- [ ] Validation = passed
- [ ] Evidence generated
- [ ] CR on IMPLEMENTED or CLOSED
- [ ] Agent context captured
- [ ] Change intent documented
- [ ] Accountability links verified
- [ ] Bugfix-specific block conditions tested (3 scenarios)
- [ ] Bugfix-specific warning conditions tested (3 scenarios)
- [ ] B consumes bugfix semantics from C, not from separate definition

---

## 7. Interface from Compliance Change Control

Accountable Agent Layer consumes:

```python
from curaops.skills.change_request import (
    ChangeRequestService,
    generate_cr_evidence,
    validate_cr_traceability,
)

# Accountable Agent Layer blocks when Compliance Change Control says:
# - CR does not exist
# - Status not APPROVED
# - Links invalid
```

Accountable Agent Layer adds:

```python
AccountableAgentService:
  - pre_flight_check(session_id) → Bool
  - register_accountable_change(agent_ctx, intent, cr_id, refs) → AC-ID
  - validate_accountability(ac_id) → Report
  - generate_accountability_evidence(ac_id) → Path
```

### 7.1 Bugfix Semantics from C

Accountable Agent Layer consumes bugfix semantics from Compliance Change Control:
- `change_type` field on CR (C-RULES §9.2)
- `requirement_linkage_type` field on CR (C-RULES §9.7)
- Bugfix blocking rules (C-RULES §9.6)
- Bugfix decision table categories (C-RULES §10)

B does NOT invent separate bugfix semantics. All bugfix classification and linkage rules originate in C.
B enforces these rules at pre-flight and validation intervention points.

---

## 8. Open Points

### OP-1: CR-Scope vs Session-Scope
- Does Accountable Agent Layer bind to session or individual changes?
- Proposal: Explicit per-change binding (already decided)

---

**END OF AUTHORITATIVE RULES**

This document is the authoritative source for Accountable Agent Layer rules.
For compliance/CR rules, see COMPLIANCE_CHANGE_CONTROL_RULES.md.
