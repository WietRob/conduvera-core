# Architecture Package: Compliance Change Control & B — REVISED

> **⚠️ LEGACY WARNING:** This is a mixed-content document. Do not extend. Use authoritative docs instead:
> - For C: COMPLIANCE_CHANGE_CONTROL_*.md
> - For B: ACCOUNTABLE_AGENT_LAYER_*.md


**Status:** DEPRECATED — Do Not Extend  
**Version:** 2.0.0  
**Date:** 2026-04-10  
**Scope:** Canonical Compliance-CR workflow (C) + Active Accountable Agent layer (B)
**Replaced by:** COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md + ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md

---

## A) Audit: Where Previous Package Was Too Weak

| Weakness | Correction |
|----------|------------|
| **Compliance Change Control framed as "developer convenience"** | Compliance Change Control is **process/audit workflow** for team-lead / quality / compliance roles |
| **CR as markdown note** | CR is **canonical entry point** with hard template rules, quality gates, and derivation obligations |
| **Missing impact classification** | Added change classification by level (US→SYS→SW→ARCH→CODE) |
| **Missing parent/child semantics** | Added explicit upstream/downstream traceability with derivation obligations |
| **Missing quality AI suggestions** | Added AI-supported quality checks at CR submission |
| **B as passive documentation** | B as **active intervention** in AI-assisted change process |
| **Weak Framework reuse** | Aggressive selective reuse from Framework services and conventions |
| **Generic open questions** | Reduced to 3 irreducible decisions |

---

## B) Revised Compliance Change Control — Problem, Scope, Roles, Workflow Position

### Problem Statement

In regulated development (ASPICE, ISO 26262, IEC 62304), the change process lacks:
1. **Canonical entry point** — Changes start inconsistently (chat, PR, commit message)
2. **Hard template enforcement** — CRs missing mandatory fields, inconsistent quality
3. **Automatic impact classification** — Teams manually assess impact levels
4. **Derivation obligation tracking** — Changes requiring lower-level derivations are missed
5. **Bidirectional traceability enforcement** — Links created forward but not backward
6. **Quality gate before work starts** — No systematic review before implementation

### Target Users / Roles

| Role | Interaction with C |
|------|-------------------|
| **Engineer** | Submits CR; receives AI quality suggestions; addresses gaps |
| **Team Lead** | Reviews CRs; approves/rejects; assesses impact |
| **Quality/Compliance** | Audits CRs; validates traceability; generates reports |
| **AI Agent (via B)** | Intervenes to ensure accountability before changes |

### Canonical CR Entry-Point Role

**The CR is the ONLY valid entry point for engineering changes.**

```
┌────────────────────────────────────────────────────────────────────────┐
│  ANY CHANGE INTENT (human or AI-assisted)                              │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (MUST go through C)
┌────────────────────────────────────────────────────────────────────────┐
│  1. SUBMIT CR                                                          │
│     - Hard template validation                                           │
│     - AI quality suggestions                                             │
│     - Automatic level impact detection                                   │
│     - Derivation obligation warnings                                     │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  2. QUALITY GATE (Team Lead / AI Assistant)                            │
│     - Review completeness                                                │
│     - Assess impact classification                                       │
│     - Approve / Request Changes / Reject                               │
└────────────────────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              ▼                                           ▼
┌─────────────────────────────┐           ┌─────────────────────────────┐
│  APPROVED → IMPLEMENT       │           │  REJECTED → REVISE          │
│  - Status: IN_PROGRESS      │           │  - Status: SUBMITTED        │
│  - Bidirectional links      │           │  - Address gaps             │
│    established              │           │  - Resubmit                 │
└─────────────────────────────┘           └─────────────────────────────┘
```

### Workflow Position

**C sits between intent and implementation.**

No code changes (commits, file edits) without an APPROVED CR.
B enforces this for AI-assisted work.

---

## C) Revised Compliance Change Control — Source-of-Truth, Repo Decision, Reuse Map

### Target Repository

**Primary:** `/home/roberto_schmidt/projects/matrix-os`

**Rationale:**
- Compliance Change Control is a core Matrix OS skill
- Integrates with existing skill infrastructure
- Shares CLI framework

### Source-of-Truth Modules

| Component | Location | Status |
|-----------|----------|--------|
| CR Service | `conduvera/skills/change_request/__init__.py` | **REVISION REQUIRED** — align with Framework patterns |
| ASPICE Link Manager | `conduvera/skills/aspice_link_manager/__init__.py` | **REUSE** — bidirectional link management |
| CR Template | New in C | **CREATE** — based on Framework v3.1 TEIL 10 |
| Quality Checker | New in C | **CREATE** — AI-supported validation |
| Impact Classifier | New in C | **CREATE** — level detection |

### Reuse Map from Framework

**Aggressive but selective reuse:**

| Framework Asset | Reuse for C | Notes |
|-----------------|-------------|-------|
| `src/core/change_request_service.py` | **TEMPLATE STRUCTURE** | Use Markdown template, status workflow, ID generation |
| `src/services/requirements_derivation_service.py` | **DERIVATION LOGIC** | Reuse constraint detection (MUST/SOLL), entity detection (GDPR/ISO) |
| `src/compliance/traceability_validation_service.py` | **VALIDATION PATTERNS** | Use Document dataclass structure, validation error patterns |
| `Traceability Bible v3.1 TEIL 10` | **COMPLIANCE RULES** | Follow for status workflow, approval sections |
| `requirements/system/SYS-REQ-001*.md` | **ID CONVENTIONS** | Use `SYS-REQ-XXX`, `SW-REQ-XXX`, `US-XXX` patterns |
| `changes/CR-*.md` | **OUTPUT FORMAT** | Match Framework CR structure |

**Explicitly NOT Reused:**
- Framework's Impact Analysis Service (too complex for C)
- Framework's JSON persistence (C uses Markdown)
- Framework's Notification system
- Framework's Workflow Engine

---

## D) Revised Compliance Change Control — Architecture, Rules, DoD, Verification

### Architecture

#### Level Hierarchy Model (from Framework)

```
┌─────────────────────────────────────────────────────────────────┐
│  LEVEL 1: US (User Stories)                                     │
│  Pattern: US-[A-Z][0-9] (e.g., US-A1, US-B2)                    │
│  Location: requirements/user_stories/                           │
└─────────────────────────────────────────────────────────────────┘
                              │ refined_from
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LEVEL 2: SYS-REQ (System Requirements)                         │
│  Pattern: SYS-REQ-[0-9]+ or SYS-REQ-[A-Z][0-9]-P[0-9]          │
│  Location: requirements/system/                                  │
└─────────────────────────────────────────────────────────────────┘
                              │ refined_in
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LEVEL 3: SW-REQ (Software Requirements)                        │
│  Pattern: SW-REQ-[0-9]+ or SW-REQ-[A-Z0-9-]+                    │
│  Location: requirements/software/                                │
└─────────────────────────────────────────────────────────────────┘
                              │ refined_in
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LEVEL 4: SW-ARCH (Software Architecture)                       │
│  Pattern: SW-ARCH-[0-9]+                                        │
│  Location: architecture/                                         │
└─────────────────────────────────────────────────────────────────┘
                              │ implemented_in
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LEVEL 5: CODE (Implementation)                                 │
│  Pattern: File paths in src/                                    │
└─────────────────────────────────────────────────────────────────┘
```

#### Mandatory CR Template Structure

```markdown
---
id: CR-XXX
title: (required, max 80 chars)
status: SUBMITTED | APPROVED | IN_PROGRESS | IMPLEMENTED | CLOSED | REJECTED
created: YYYY-MM-DD
requester: (required)
priority: LOW | MEDIUM | HIGH | CRITICAL
---

## Description
(required, min 50 chars)

## Impact Classification

**Impacted Levels:**
- [ ] US (User Stories)
- [ ] SYS (System Requirements)
- [ ] SW (Software Requirements)
- [ ] ARCH (Architecture)
- [ ] CODE (Implementation)

**Change Type:**
- [ ] feature (new capability)
- [ ] bugfix (defect correction)
- [ ] refactor (no functional change)
- [ ] test (test-only change)
- [ ] docs (documentation only)

## Requirement References
(required, at least one)
- [upstream] SYS-REQ-XXX (linked system requirement)
- [derived] May require: SW-REQ-XXX (to be created)

## Derivation Obligations
(auto-detected by C)
- [ ] Level US → SYS derivation needed
- [ ] Level SYS → SW derivation needed
- [ ] Level SW → ARCH derivation needed
- [ ] Level SW → Test cases needed

## Quality Check Results
(auto-populated by C AI suggestions)
- Completeness: [PASS/WARNING/FAIL]
- Clarity: [PASS/WARNING/FAIL]
- Testability: [PASS/WARNING/FAIL]
- Constraints: [None detected / List]

## Approval
**Approved by:** (TBD)
**Decision:** PENDING | APPROVED | REJECTED
**Conditions:** (if any)

## Implementation
**Assigned to:** (TBD)
**Git Commits:**
- (auto-linked)

**Changed Files:**
- (auto-linked)
```

#### Parent/Child / Upstream/Downstream Semantics

**Link Types (from Framework patterns):**

| Link Type | Direction | Meaning | Example |
|-----------|-----------|---------|---------|
| `refined_from` | Upward | This CR addresses parent requirement | CR → SYS-REQ-001 |
| `refined_in` | Downward | This CR requires child derivations | CR → SW-REQ-NEW |
| `implemented_in` | Downward | Code/files implementing this CR | CR → src/auth.py |
| `validated_by` | Downward | Tests validating this CR | CR → TEST-001 |

**Bidirectional Enforcement:**
- When CR links to SYS-REQ-001, C MUST update SYS-REQ-001 to link back
- ASPICE Link Manager handles this automatically

#### Derivation Obligations

**Rules (from Framework Requirements Derivation Service):**

| Trigger | Obligation | Detection |
|---------|------------|-----------|
| Change impacts US level | Derive/update SYS-REQ | US-XXX mentioned in CR |
| Change impacts SYS level | Derive/update SW-REQ | SYS-REQ-XXX mentioned |
| Change impacts SW level | Derive/update SW-ARCH | SW-REQ-XXX mentioned |
| Change impacts SW level | Create/update test cases | Constraint keywords detected |
| HARD constraints detected (MUST, SHALL) | Require verification evidence | RFC 2119 keyword detection |
| Regulatory entities detected (GDPR, ISO) | Require compliance review | Entity pattern matching |

#### Change Classification Model

**By Level (automated detection):**
```python
LEVEL_PATTERNS = {
    "US": r"^US-[A-Z][0-9]",
    "SYS-REQ": r"^SYS-REQ-[0-9]",
    "SW-REQ": r"^SW-REQ-[0-9]",
    "SW-ARCH": r"^SW-ARCH-[0-9]",
    "CODE": r"^(src/|lib/|app/)"  # File paths
}
```

**By Type (explicit selection):**
- `feature` — New capability, requires full traceability
- `bugfix` — Defect correction, links to issue/REQ
- `refactor` — No functional change, may skip US level
- `test` — Test-only, links to SW-REQ being tested
- `docs` — Documentation only, lighter process

**By Impact (AI-suggested):**
- `CRITICAL` — Cross-cutting, multiple levels affected
- `HIGH` — Single level, multiple components
- `MEDIUM` — Single component
- `LOW` — Isolated change

#### Naming / Linking Convention Enforcement

**Requirement ID Validation:**
```python
VALID_ID_PATTERNS = [
    r"^US-[A-Z][0-9](?:_[A-Z0-9]+)?$",           # US-A1, US-B2_split
    r"^SYS-REQ-[0-9]+(?:-[A-Z0-9]+)?$",          # SYS-REQ-001, SYS-REQ-A2-P03
    r"^SW-REQ-[0-9]+(?:-[A-Z0-9-]+)?$",          # SW-REQ-063
    r"^SW-ARCH-[0-9]+$",                         # SW-ARCH-006
    r"^TC-(UT|IT|ST|AT)-[0-9]+$",                # TC-UT-001, TC-ST-038
]
```

**Enforcement Rules:**
1. All requirement_refs MUST match valid patterns
2. Referenced requirements MUST exist in requirements/
3. CR IDs follow CR-XXX pattern (auto-generated)
4. Links MUST be bidirectional (enforced by ASPICE Link Manager)

#### Validation / Fail States

**Hard Fails (CR rejected):**
- Title empty or >80 chars
- Description <50 chars
- No requirement_refs provided
- Invalid requirement ID format
- Status transition invalid

**Warnings (CR accepted with conditions):**
- Requirement file not found (link to be created later)
- Derivation obligations detected but not addressed
- HARD constraints without verification plan
- Regulatory entities without compliance review

**Quality Gate Fail (approval withheld):**
- AI quality check: FAIL on any dimension
- Impact classification: CRITICAL without risk assessment
- Derivation obligations: UNADDRESSED

#### Evidence Outputs

**CR File:** `changes/CR-XXX.md` (Markdown with YAML frontmatter)
**Evidence File:** `changes/evidence/CR-XXX_evidence.json`
```json
{
  "cr_id": "CR-001",
  "status": "APPROVED",
  "created": "2026-04-10",
  "requirement_refs": ["SYS-REQ-001"],
  "impact_levels": ["SYS", "SW"],
  "change_type": "feature",
  "derivation_obligations": [
    {"type": "SW-REQ", "from": "SYS-REQ-001", "status": "pending"}
  ],
  "quality_check": {
    "completeness": "PASS",
    "clarity": "PASS",
    "testability": "WARNING"
  },
  "bidirectional_links_verified": true,
  "evidence_generated_at": "2026-04-10T10:00:00"
}
```

### Definition of Done (DoD) for C

1. [ ] CR submission enforces hard template (all mandatory fields)
2. [ ] AI quality suggestions populate Quality Check Results section
3. [ ] Automatic impact level detection from requirement_refs
4. [ ] Derivation obligation warnings based on level hierarchy
5. [ ] Requirement ID format validation against known patterns
6. [ ] Bidirectional link creation via ASPICE Link Manager
7. [ ] Status workflow: SUBMITTED→APPROVED→IN_PROGRESS→IMPLEMENTED→CLOSED
8. [ ] Evidence generation produces JSON with all traceability metadata
9. [ ] CLI commands: create, approve, status, evidence, validate, list
10. [ ] All requirement ID patterns from Framework supported

### Verification Criteria

**Unit Tests:**
- Template validation (missing fields, format errors)
- ID pattern matching (all 5 level patterns)
- Impact level detection from refs
- Derivation obligation detection
- Status transition validation

**Integration Tests:**
- End-to-end: submit → quality check → approve → evidence
- Bidirectional link creation verified
- Derivation warning when US→SYS gap detected

**Compliance Verification:**
- Sample CRs match Framework CR format
- Evidence JSON contains all required fields
- Links are bidirectional (check both files)

---

## E) Revised Accountable Agent Layer — Problem, Scope, Workflow Intervention Points

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

## F) Revised Accountable Agent Layer — Source-of-Truth, Repo Decision, Dependency on C

### Target Repository

**Primary:** `/home/roberto_schmidt/projects/matrix-os`

**Rationale:**
- Accountable Agent Layer is a Matrix OS skill
- Extends C via imports
- CLI integration

### Source-of-Truth Modules

| Component | Location | Status |
|-----------|----------|--------|
| AccountableAgentService | `conduvera/skills/accountable_agent/__init__.py` | **REVISION REQUIRED** — add active intervention |
| AgentContext dataclass | Same file | **REVISION REQUIRED** |
| ChangeIntent dataclass | Same file | **REVISION REQUIRED** |
| Pre-flight check logic | Same file | **CREATE** — new |

### Exact Dependency Reuse from C

**B MUST import from C (verified by code review):**

```python
# B's __init__.py
from conduvera.skills.change_request import (
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

## G) Revised Accountable Agent Layer — Architecture, Rules, DoD, Verification

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
2. [ ] AgentContext records all fields (agent_id, name, model, tools, session)
3. [ ] ChangeIntent captures all fields (description, type, files, impact)
4. [ ] Strict mode blocks when cr_id missing
5. [ ] Strict mode blocks when requirement_refs empty
6. [ ] Non-strict mode allows registration with status "pending"
7. [ ] Validation checks requirement ID patterns
8. [ ] Evidence generation produces JSON with full chain
9. [ ] Evidence references C evidence file
10. [ ] B imports all C services (no duplication)
11. [ ] CLI commands: register, validate, evidence, pre-flight

### Verification Criteria

**Unit Tests:**
- Pre-flight check: approved CR exists / not exists
- Register: all fields captured correctly
- Register strict without cr_id → blocks
- Register strict without requirements → blocks
- Validation: valid/invalid requirement IDs
- Evidence: JSON structure matches spec

**Integration Tests:**
- End-to-end valid: pre-flight → register → validate → evidence
- End-to-end blocked: pre-flight with no CR → blocks
- Evidence chain: B evidence references C evidence

**Dependency Verification:**
- Code review: B imports from C
- No CR creation logic in B
- No requirement ID validation in B (uses C)

---

## H) Exact Framework Assets / Convention Docs Used

| Asset | Location | Purpose |
|-------|----------|---------|
| `change_request_service.py` | `src/core/` | CR template structure, status workflow |
| `requirements_derivation_service.py` | `src/services/` | Derivation obligation logic, constraint detection (RFC 2119) |
| `traceability_validation_service.py` | `src/compliance/` | Document dataclass, validation patterns |
| SYS-REQ-001 | `requirements/system/` | ID convention: SYS-REQ-XXX |
| SW-REQ-063 | `requirements/software/` | CR service requirement example |
| CR-*.md files | `changes/` | Output format template |
| TEIL 10 references | Code comments | Compliance workflow rules |

**Level Hierarchy from Framework:**
- US → SYS-REQ → SW-REQ → SW-ARCH → CODE
- ID patterns validated from actual Framework files

---

## I) Max 3 Unresolved Decisions

1. **Session-CR Binding:**
   - Should B automatically detect the active session's CR from Session Manager?
   - Or require explicit `--cr` argument on every command?
   *Framework has Session Manager; integration pattern TBD*

2. **AI Quality Check in C:**
   - Should C call an LLM for quality suggestions at submission time?
   - Or use rule-based checks only (faster, deterministic)?
   *Rob: Preference? Quality vs speed tradeoff*

3. **Pre-Flight Enforcement Mechanism:**
   - Should B provide a Python decorator for AI tool calls (`@accountable`)?
   - Or require explicit `curaops accountable pre-flight` calls?
   *Determines how intrusive Accountable Agent Layer is in agent workflow*

---

**END OF REVISED ARCHITECTURE PACKAGE**
