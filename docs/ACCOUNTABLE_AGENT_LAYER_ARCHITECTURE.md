# Accountable Agent Layer Architecture — Authoritative

> **⚠️ LEGACY NOTICE:** This replaces the mixed COMPLIANCE_ACCOUNTABILITY_ARCHITECTURE.md Sections E-G.
> For Compliance Change Control architecture, see COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md.

**Status:** AUTHORITATIVE  
**Version:** 2.0.0  
**Date:** 2026-04-19  
**Scope:** Accountable Agent Layer ONLY

---

## A)  Problem, Scope, Workflow Intervention Points

### Problem Statement

AI-assisted code changes bypass the CR process:
1. **No attribution** — Can't tell human vs AI, which model, which tools
2. **No accountability** — Changes lack CR linkage and requirement traceability
3. **No enforcement** — AI agents not blocked from non-compliant changes
4. **No audit trail** — Can't reconstruct what an AI agent did

### Scope

**IN SCOPE:**
- Actor/model/tool attribution capture
- Mandatory link validation (CR + requirements)
- **Active intervention**: Block AI-assisted changes missing compliance links
- Evidence chain generation (agent context + CR reference)
- CLI interface for accountability workflow

**OUT OF SCOPE:**
- AI model integration (assumes external)
- Tool execution (assumes external)
- Session management (handled by Session Manager skill)
- Real-time IDE interception

### Workflow Intervention Points

```
┌────────────────────────────────────────────────────────────────────────┐
│  AI AGENT initiates change intent                                      │
│  (Tool call: file_edit, terminal, etc.)                                │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ B INTERVENTION POINT 1
┌────────────────────────────────────────────────────────────────────────┐
│  B PRE-FLIGHT CHECK                                                    │
│  - Is there an APPROVED CR for this session?                           │
│  - Is the agent accountable (registered)?                              │
│  IF NOT APPROVED CR:                                                   │
│    → BLOCK with error: "No approved CR. Run: curaops accountable setup"│
└────────────────────────────────────────────────────────────────────────┘
                                    │ (if approved CR exists)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  AI AGENT executes change                                              │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ B INTERVENTION POINT 2
┌────────────────────────────────────────────────────────────────────────┐
│  B CAPTURE & LINK                                                      │
│  - Record agent context (model, tools used)                            │
│  - Record change intent (files affected, description)                  │
│  - Link to CR                                                          │
│  - Update CR implementation section                                    │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ B INTERVENTION POINT 3
┌────────────────────────────────────────────────────────────────────────┐
│  B POST-CHECK                                                          │
│  - Validate bidirectional traceability maintained                      │
│  - Generate accountability evidence                                    │
│  - Warn if derivation obligations unaddressed                          │
└────────────────────────────────────────────────────────────────────────┘
```

### What B Adds on Top of C

| Feature | C (Base) | B (Layer) |
|---------|----------|-----------|
| CR workflow | ✅ | Uses C |
| Attribution | ❌ | ✅ Agent/model/tool capture |
| Pre-flight check | ❌ | ✅ Block if no approved CR |
| Accountability enforcement | ❌ | ✅ Mandatory links validation |
| AI evidence chain | ❌ | ✅ Agent context + CR linkage |
| Active intervention | ❌ | ✅ Block/fail on non-compliance |

---

## B)  Source-of-Truth, Repo Decision, Dependency on C

### Target Repository

**Primary:** `/home/roberto_schmidt/projects/matrix-os`

**Rationale:**
- Accountable Agent Layer is a Matrix OS skill
- Extends C via imports
- CLI integration

### Source-of-Truth Modules

| Component | Location | Status |
|-----------|----------|--------|
| AccountableAgentService | `curaops/skills/accountable_agent/__init__.py` | **REVISION REQUIRED** — add active intervention |
| AgentContext dataclass | Same file | **REVISION REQUIRED** |
| ChangeIntent dataclass | Same file | **REVISION REQUIRED** |
| Pre-flight check logic | Same file | **CREATE** — new |

### Exact Dependency Reuse from C

**B MUST import from C (verified by code review):**

```python
# B's __init__.py
from curaops.skills.change_request import (
    ChangeRequestService,
    submit_change_request,
    generate_cr_evidence,
    validate_cr_traceability,
)

# B NEVER implements:
# - CR creation logic (calls C)
# - CR template enforcement (relies on C)
# - Requirement ID validation (uses C)
# - Evidence format for CRs (references C evidence)
```

**B Evidence references C Evidence:**
```json
{
  "accountable_change": { ... },
  "cr_evidence_path": "changes/evidence/CR-001_evidence.json",
  "linked_cr_id": "CR-001"
}
```

---

## C)  Architecture, Rules, DoD, Verification

### Architecture

#### Data Model

```python
@dataclass
class AgentContext:
    agent_id: str              # e.g., "claude-code-001"
    agent_name: str            # e.g., "Claude Code"
    model: str                 # e.g., "claude-sonnet-4"
    tools_used: List[str]      # ["file_edit", "terminal", "web_search"]
    session_id: Optional[str]  # Reference to Session Manager

@dataclass
class ChangeIntent:
    description: str           # What is being changed
    change_type: str           # feature, bugfix, refactor, test, docs
    files_affected: List[str]  # ["src/auth.py"]
    estimated_impact: Optional[str]  # CRITICAL, HIGH, MEDIUM, LOW

@dataclass
class AccountableChange:
    accountable_id: str        # AC-XXXXXXXX
    agent_context: AgentContext
    change_intent: ChangeIntent
    cr_id: str                 # MUST link to C
    requirement_refs: List[str]  # MUST have at least one
    status: str                # pending, linked, validated, blocked
    created_at: datetime
    evidence_path: Optional[str]
    block_reason: Optional[str]
    # Bugfix context (consumed from C, not invented by B)
    change_type: Optional[str] = None    # feature, bugfix, refactor, test, docs
    requirement_linkage_type: Optional[str] = None  # existing_ref, updated_ref, new_ref
    root_cause_category: Optional[str] = None  # impl_bug, req_ambiguous, req_missing, arch_bug, sys_bug
    regression_verification_ids: List[str] = field(default_factory=list)  # TC-IDs for regression
```

#### Active Intervention Points

**1. Pre-Flight Check (BLOCK if fails):**
```python
def pre_flight_check(session_id: str) -> PreFlightResult:
    """
    Called before ANY AI-assisted change.
    
    BLOCK conditions:
    - No approved CR for this session
    - CR exists but not in APPROVED status
    - AccountableChange not registered
    Bugfix-specific (consumed from C-RULES §9):
    - change_type=bugfix without SW-REQ in requirement_refs
    - change_type=bugfix with requirement_linkage_type=new_ref but SW-REQ not APPROVED
    - change_type=bugfix at IMPLEMENTED with no VerificationCases
    
    PASS: Returns linked CR ID for attribution
    """
```

**2. Mandatory Links Validation (BLOCK if fails in strict mode):**
```python
def validate_accountability(accountable_id: str) -> ValidationResult:
    """
    Hard checks:
    - cr_id exists in C
    - requirement_refs non-empty
    - All refs match valid ID patterns
    - Bidirectional links verified
    
    FAIL → status = "blocked", block_reason = "..."
    """
```

**3. Evidence Generation (always runs):**
```python
def generate_accountability_evidence(accountable_id: str) -> Path:
    """
    Combines:
    - AgentContext
    - ChangeIntent
    - CR reference (from C)
    - Validation results
    
    Output: changes/evidence/AC-XXX_YYYYMMDD_HHMMSS.json
    """
```

#### Required Block/Fail Conditions

| Condition | Mode | Action |
|-----------|------|--------|
| No approved CR for session | Always | BLOCK with actionable error |
| cr_id is None | strict | BLOCK: "Missing CR link" |
| requirement_refs empty | strict | BLOCK: "Missing requirement refs" |
| Invalid requirement ID format | strict | BLOCK: "Invalid ID format: XXX" |
| Referenced CR not found | strict | BLOCK: "CR-XXX does not exist" |
| Bidirectional links broken | warning | WARN: "Link inconsistency detected" |

#### Evidence Chain Expectations

**Accountability Evidence (B):**
```json
{
  "accountable_change": {
    "accountable_id": "AC-58D0D7B9",
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
      "estimated_impact": "HIGH"
    },
    "cr_id": "CR-001",
    "requirement_refs": ["SEC-REQ-001", "SW-REQ-042"],
    "bugfix_context": {
      "change_type": "bugfix",
      "requirement_linkage_type": "existing_ref",
      "root_cause_category": "impl_bug",
      "regression_verification_ids": ["TC-SVT-012"]
    },
    "status": "validated"
  },
  "validation": {
    "valid": true,
    "issues": []
  },
  "cr_evidence_reference": "changes/evidence/CR-001_evidence.json",
  "generated_at": "2026-04-10T10:00:00",
  "service_version": "AAL-0.1.0"
}
```

### Definition of Done (DoD) for B

1. [ ] Pre-flight check blocks changes without approved CR
2. [ ] AgentContext captures all fields (agent_id, name, model, tools, session)
3. [ ] ChangeIntent captures all fields (description, type, files, impact)
4. [ ] Strict mode blocks when cr_id missing
5. [ ] Strict mode blocks when requirement_refs empty
6. [ ] Non-strict mode allows registration with status "pending"
7. [ ] Validation checks requirement ID patterns
8. [ ] Evidence generation produces JSON with full chain
9. [ ] Evidence references C evidence file
10. [ ] B imports all C services (no duplication)
11. [ ] CLI commands: register, validate, evidence, pre-flight
12. [ ] Bugfix-specific block conditions tested (3 scenarios from C-RULES §9.6)
13. [ ] Bugfix semantics consumed from C, not duplicated in B
14. [ ] Evidence includes bugfix_context when change_type=bugfix

### Verification Criteria

**Unit Tests:**
- Pre-flight check: approved CR exists / not exists
- Register: all fields captured correctly
- Register strict without cr_id → blocks
- Register strict without requirements → blocks
- Validation: valid/invalid requirement IDs
- Evidence: JSON structure matches spec
- Bugfix: block when change_type=bugfix without SW-REQ
- Bugfix: warn when root-cause not documented

**Integration Tests:**
- End-to-end valid: pre-flight → register → validate → evidence
- End-to-end blocked: pre-flight with no CR → blocks
- Evidence chain: B evidence references C evidence

**Dependency Verification:**
- Code review: B imports from C
- No CR creation logic in B
- No requirement ID validation in B (uses C)

---


---

## D. Exact Framework Assets / Convention Docs Used

| Asset | Quelle | Nutzung |
|-------|--------|---------|
| `change_request_service.py` | `src/core/` | Template, workflow (consumed by B) |
| `requirements_derivation_service.py` | `src/services/` | Derivation, constraints (reference) |
| `traceability_validation_service.py` | `src/compliance/` | Patterns, dataclass (reference) |
| `Traceability Bible v3.1 TEIL 8` | docs/guides/ | ID patterns |
| `Traceability Bible v3.1 TEIL 4` | docs/guides/ | Link semantics |
| SYS-REQ-001 | `requirements/system/` | ID conventions |
| SW-REQ-063 | `requirements/software/` | CR service requirement |

---

## E. Unresolved Decisions (Max 2)

1. **Session-CR Binding:**
   - A: Explicit `--cr` argument (Default)
   - B: Auto-binding via Session Manager
   - **Decision:** A (explicit) as default

2. **AI Quality Check:**
   - A: Rule-based only (Default)
   - B: Rule-based + LLM suggestions
   - **Decision:** A (rule-based) as default

---

**END OF AUTHORITATIVE ARCHITECTURE**

This document is the authoritative source for Accountable Agent Layer architecture.
For Compliance Change Control architecture, see COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md.
