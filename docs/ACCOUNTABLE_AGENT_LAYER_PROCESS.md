# Accountable Agent Layer Process — Authoritative

> **⚠️ LEGACY NOTICE:** This replaces the mixed COMPLIANCE_CHANGE_CONTROL_PROCESS_CONTRACT.md sections on AccountableChange.
> For Compliance Change Control process, see COMPLIANCE_CHANGE_CONTROL_PROCESS.md.

**Status:** AUTHORITATIVE
**Version:** 2.0.0
**Date:** 2026-04-19
**Scope:** Accountable Agent Layer ONLY

---

## A. Scope and Purpose

This document provides the executable process contract for:
- **Accountable Agent Layer:** Active intervention layer for AI-assisted changes

**Scope IN:**
- AccountableChange entity and lifecycle
- Intervention points in AI workflow
- Blocking/warning logic
- Accountability evidence

**Scope OUT:**
- CR state machine (see COMPLIANCE_CHANGE_CONTROL_PROCESS.md)
- Requirement state machine (see COMPLIANCE_CHANGE_CONTROL_PROCESS.md)
- Code implementation

---

## B. Canonical Entities

### B.1 Accountable Change

```yaml
Entity: AccountableChange
ID Pattern: AC-[0-9A-F]{8} (e.g., AC-58D0D7B9)
Storage: In-memory (per session) + evidence file
Purpose: AI-assisted change attribution and accountability
```

### B.2 Agent Context

```yaml
Entity: AgentContext
Fields:
  agent_id: String        # e.g., "claude-code-001"
  agent_name: String      # e.g., "Claude Code"
  model: String           # e.g., "claude-sonnet-4"
  tools_used: [String]    # e.g., ["file_edit", "terminal"]
  session_id: String      # Reference to Session Manager
Purpose: Attribution of AI agent
```

### B.3 Change Intent

```yaml
Entity: ChangeIntent
Fields:
  description: String     # What is being changed
  change_type: String     # feature, bugfix, refactor, test, docs
  files_affected: [String] # Files being modified
  estimated_impact: String # CRITICAL, HIGH, MEDIUM, LOW
Purpose: Intent capture for AI change
```

### B.4 Evidence

```yaml
Entity: ACEvidence
File: changes/evidence/AC-[ID]_[YYYYMMDD]_[HHMMSS].json
Purpose: Machine-readable audit trail for AccountableChange
```

---

## C. AccountableChange State Machine

### C.1 States

| State | Code | Definition | Entry Criteria |
|-------|------|------------|----------------|
| PENDING | P | Created, awaiting validation | AccountableChange registered |
| LINKED | L | CR linked, requirements present | CR exists, refs provided |
| VALIDATED | V | Validation passed | All checks passed |
| BLOCKED | B | Validation failed, work stopped | Blocking condition met |

### C.2 State Transition Matrix

| From → To | P | L | V | B |
|-----------|---|---|---|---|
| **P** | - | Y | N | Y |
| **L** | N | - | Y | Y |
| **V** | N | N | - | N |
| **B** | Y | N | N | - |

**Y = Allowed, N = Blocked**

### C.3 Transition Triggers

| Transition | Trigger | Actor | Preconditions |
|------------|---------|-------|---------------|
| P → L | `link()` | Agent | CR linked, requirement_refs provided |
| L → V | `validate()` | System | All validation checks pass |
| L → B | `block()` | System | Blocking condition detected |
| P → B | `block()` | System | Pre-flight check fails |
| B → P | `reset()` | Developer | Address blocking issue |

---

## D. Intervention Points

### D.1 Intervention Point 1: Pre-Flight (Before ANY Work)

```
AI AGENT initiates change intent
        ↓
┌─────────────────────────┐
│  PRE-FLIGHT CHECK       │
│  - CR linked?           │
│  - CR APPROVED?         │
│  → BLOCK if no          │
└─────────────────────────┘
```

**Trigger:** Agent attempts first tool call in session
**Check:** Is there an APPROVED CR linked to this session?
**Checks:**
- CR exists in changes/
- CR.status = APPROVED
- Requirement refs present
- ID formats valid
- Impact classification consistent

**Pass:** Continue to work
**Fail:** BLOCK with actionable error message

### D.2 Intervention Point 2: Capture (During Work)

```
        ↓ (if pass)
┌─────────────────────────┐
│  CAPTURE                │
│  - Tools used           │
│  - Files affected       │
└─────────────────────────┘
```

**Trigger:** Each tool call (file_edit, terminal, etc.)
**Action:** Record tool in AgentContext.tools_used
**Action:** Record affected files in ChangeIntent.files_affected
**Storage:** In-memory AccountableChange registry

### D.3 Intervention Point 3: Validation (Before Review)

```
        ↓
┌─────────────────────────┐
│  VALIDATE               │
│  - Mandatory links      │
│  - Hierarchy check      │
│  → BLOCK if fail        │
└─────────────────────────┘
```

**Trigger:** Developer runs `curaops accountable validate`
**Check:** All mandatory links present (cr_id, requirement_refs)
**Check:** CR exists and is APPROVED
**Check:** Requirement IDs valid
**Pass:** Status → "validated"
**Fail:** Status → "blocked" with specific reason

### D.4 Intervention Point 4: Evidence (At Completion)

```
        ↓
┌─────────────────────────┐
│  EVIDENCE               │
│  - Generate AC-evidence │
│  - Reference CR-ev      │
└─────────────────────────┘
```

**Trigger:** Developer runs `curaops accountable evidence`
**Action:** Generate accountability evidence JSON
**Content:** AgentContext + ChangeIntent + CR reference + validation
**Output:** changes/evidence/AC-XXX_YYYYMMDD_HHMMSS.json

---

## E. Blocking vs Warning Decision Table

### E.1 Blocking Conditions (Hard Stop)

| Condition | Block Message | Exit Code |
|-----------|---------------|-----------|
| No CR linked | "No CR linked. Run: curaops cr link --cr <id>" | 1 |
| CR.status != APPROVED | "CR-{id} status is {status}, must be APPROVED" | 1 |
| Missing requirement_refs | "Missing requirement_refs (min 1 required)" | 1 |
| Invalid ID format | "Invalid requirement ID format: {ids}" | 1 |
| SYS impact but no SYS-REQ | "SYS impact detected but no SYS-REQ linked" | 1 |
| ARCH impact but no SW-ARCH | "ARCH impact detected but no SW-ARCH linked" | 1 |
| CR file not found | "CR-{id} does not exist in changes/" | 1 |
| Safety-critical without approval | "Safety-critical change requires Compliance approval" | 1 |
| Emergency CR expired | "Emergency CR deadline (24h) exceeded" | 1 |
| Bugfix CR without SW-REQ linkage | "Bugfix CR has no SW-REQ linkage (C-RULES §9.1)" | 1 |
| Bugfix new_ref SW-REQ not APPROVED | "Bugfix new SW-REQ not APPROVED (C-RULES §9.3)" | 1 |
| Bugfix CR IMPLEMENTED without VerificationCases | "Bugfix at IMPLEMENTED with no VerificationCases (C-RULES §9.4)" | 1 |

### E.2 Warning Conditions (Allow with Status)

| Condition | Warning Message | Result Status |
|-----------|-----------------|---------------|
| Requirement file not found | "Requirement {id} file not found (expected)" | warning |
| Derivation obligation pending | "Derivation obligation not yet addressed" | warning |
| Test coverage < 100% | "Test coverage incomplete ({pct}%)" | warning |
| Missing ARCH but ARCH-like change | "Possible ARCH impact - verify manually" | warning |
| No CODE links yet | "No CODE implementation linked" | pending |
| Evidence hash mismatch | "Evidence hash mismatch - regenerate" | warning |
| Bugfix linked SW-REQ in DRAFT | "Bugfix SW-REQ {id} is in DRAFT status" | warning |
| Bugfix no regression VerificationCase at IN_PROGRESS | "No regression VerificationCase linked (required at IMPLEMENTED)" | warning |
| Bugfix root-cause not documented | "Root-cause category not documented (recommended for non-safety)" | warning |

### E.3 Decision Flow

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

## F. Evidence Schema

### F.1 Accountability Evidence (JSON)

```json
{
  "schema_version": "AAL-1.0.0",
  "accountable_change": {
    "accountable_id": "AC-58D0D7B9",
    "created_at": "2026-04-10T10:05:00Z",
    "status": "validated",
    "agent_context": {
      "agent_id": "claude-code-001",
      "agent_name": "Claude Code",
      "model": "claude-sonnet-4",
      "tools_used": ["file_edit", "terminal"],
      "session_id": "sess-abc-123"
    },
    "change_intent": {
      "description": "Fix OAuth2 vulnerability",
      "change_type": "bugfix",
      "files_affected": ["src/auth.py", "tests/test_auth.py"],
      "estimated_impact": "HIGH",
      "requirement_linkage_type": "existing_ref",
      "root_cause_category": "impl_bug",
      "regression_verification_ids": ["TC-SVT-012"]
    },
    "accountability_links": {
      "cr_id": "CR-001",
      "requirement_refs": ["SW-REQ-001"]
    },
    "bugfix_context": {
      "change_type": "bugfix",
      "requirement_linkage_type": "existing_ref",
      "root_cause_category": "impl_bug",
      "escalation_triggers_met": [],
      "regression_verification_ids": ["TC-SVT-012"]
    },
  },
  "validation": {
    "valid": true,
    "checks": {
      "cr_exists": {"passed": true, "cr_status": "APPROVED"},
      "requirement_refs_present": {"passed": true, "count": 1},
      "requirement_ids_valid": {"passed": true},
      "hierarchy_consistent": {"passed": true}
    },
    "issues": [],
    "block_reason": null
  },
  "referenced_c_evidence": {
    "cr_evidence_path": "changes/evidence/CR-001_20260410_143000.json",
    "integrity_verified": true
  },
  "evidence_chain": {
    "this_evidence": "changes/evidence/AC-58D0D7B9_20260410_100500.json",
    "linked_cr": "changes/CR-001.md",
    "linked_cr_evidence": "changes/evidence/CR-001_20260410_143000.json",
    "chain_integrity": "verified"
  },
  "generated_at": "2026-04-10T10:05:00Z"
}
```

---

## G. CLI Contract

### G.1 Commands

```bash
# Pre-flight check
curaops accountable pre-flight \
  --session-id sess-abc-123 \
  --files src/auth.py

# Link CR to session (explicit per decision)
curaops cr link \
  --session-id sess-abc-123 \
  --cr CR-001

# Register accountable change
curaops accountable register \
  --session-id sess-abc-123 \
  --agent-id claude-code-001 \
  --agent-name "Claude Code" \
  --model claude-sonnet-4 \
  --description "Fix auth vulnerability" \
  --change-type bugfix \
  --files src/auth.py,tests/test_auth.py

# Validate
curaops accountable validate AC-58D0D7B9

# Generate evidence
curaops accountable evidence AC-58D0D7B9
```

### G.2 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Blocking condition (intervention) |
| 2 | Validation failure |
| 3 | Invalid transition |
| 4 | Missing required fields |
| 5 | File not found |

---

## H. Open Points

### OP-1: Session Persistence
- How long does session→CR binding persist?
- Decision: Until process exit (simplest)

### OP-2: Evidence Retention
- How many evidence versions to keep per AccountableChange?
- Decision: Keep all (compliance first)

---

**END OF AUTHORITATIVE PROCESS CONTRACT**

This document is the authoritative source for Accountable Agent Layer process.
For CR/requirement process, see COMPLIANCE_CHANGE_CONTROL_PROCESS.md.
