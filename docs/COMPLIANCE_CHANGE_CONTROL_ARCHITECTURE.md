# Architecture Package: Compliance Change Control — Authoritative

**Status:** AUTHORITATIVE
**Version:** 2.0.0
**Date:** 2026-04-11
**Scope:** Requirement-linked Change Request workflow for regulated development

---

## A) Compliance Change Control — Problem Statement and System Boundary

### Problem Statement

In regulated/safety-relevant development (ASPICE, ISO 26262, IEC 62304), every code change must be:
1. **Traceable** to one or more requirements
2. **Documented** with justification and impact
3. **Reviewable** before implementation
4. **Verifiable** after implementation with level-specific verification
5. **Auditable** throughout the lifecycle

Current gaps in typical development workflows:
- Changes happen without requirement linkage
- Evidence of traceability is scattered or missing
- No systematic validation that changes satisfy compliance rules
- Verification is undifferentiated (one flat "test" concept)
- Audit preparation requires manual reconstruction

### System Boundary

**IN SCOPE:**
- Change Request (CR) creation with requirement references
- CR status workflow: DRAFT → SUBMITTED → APPROVED → IN_PROGRESS → IMPLEMENTED → VERIFIED → CLOSED
- VerificationCase entity with typed verification levels
- Evidence generation for CR state and traceability
- Validation that CRs link to existing requirements
- CLI-first interface for developer workflow
- Markdown-based persistence (git-tracked)

**OUT OF SCOPE:**
- Requirement authoring/management (assumes requirements exist)
- Test execution framework (assumes external: pytest, etc.)
- Full ASPICE process implementation (only CR-focused slice)
- AI-generated requirement suggestions (RAG)
- IDE integration beyond CLI
- Dashboards/reports beyond evidence files
- Integration with external ALM tools (Jira, DOORS, etc.)

**BOUNDARY CONDITIONS:**
- CRs live in `changes/` directory
- Requirements assumed in `requirements/` directory
- VerificationCases live in `verification/` directory
- Evidence outputs to `changes/evidence/`
- All files are Markdown with YAML frontmatter

---

## B) Compliance Change Control — Source-of-Truth and Repo Decision

### Target Repository

**Primary:** `/home/roberto_schmidt/projects/matrix-os`

**Rationale:**
- C is a Matrix OS skill, not a standalone product
- Integrates with existing skill infrastructure
- Shares CLI framework with other skills

### Source-of-Truth Modules

| Component | Current Source | Decision |
|-----------|---------------|----------|
| CR Datamodel | `curaops/skills/change-request/__init__.py` | **PROVISIONAL** — needs architecture alignment |
| CR Service | `curaops/skills/change-request/__init__.py` | **PROVISIONAL** — extracted from Framework |
| Evidence Generation | `curaops/skills/change-request/__init__.py` | **PROVISIONAL** — new code |
| Traceability Validation | `curaops/skills/change-request/__init__.py` | **PROVISIONAL** — uses ASPICE Link Manager |
| ASPICE Link Manager | `curaops/skills/aspice-link-manager/__init__.py` | **REUSE** — existing skill |

### Framework Reuse Candidates

From `/home/roberto_schmidt/projects/CuraOps_Framework`:

| Framework Module | Reuse Decision | Notes |
|-----------------|----------------|-------|
| `src/core/change_request_service.py` | **REFERENCE ONLY** — DO NOT COPY | Framework version has different scope (Impact Analysis, v3.1) |
| `src/compliance/traceability_validation_service.py` | **REFERENCE ONLY** | Too complex for C scope; use simplified version |
| `Traceability Bible v3.1` | **COMPLIANCE REFERENCE** | Follow TEIL 10 for CR workflow |

**Explicitly NOT Reused:**
- Framework's Impact Analysis (out of scope)
- Framework's Workflow Engine (overkill for C)
- Framework's Notification system
- Framework's ParserFactory complexity

---

## C) Compliance Change Control — Architecture, DoD, Verification Criteria

### Architecture

#### Data Model

```python
@dataclass
class ChangeRequest:
    """Canonical Change Request entity."""

    # Identity
    id: str                           # CR-[0-9]{3,}

    # Metadata
    title: str                        # 10-80 chars
    status: CRStatus
    created: datetime
    requester: str

    # Content
    problem: str                      # min 50 chars
    justification: str                # min 20 chars

    # Classification
    change_type: str = "feature"      # feature, bugfix, refactor, test, docs
    requirement_linkage_type: Optional[str] = None  # existing_ref, updated_ref, new_ref

    # Impact
    impact_level: List[ImpactLevel] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    safety_impact: SafetyImpact = SafetyImpact.NONE
    compliance_impact: Optional[List[str]] = None

    # Lifecycle
    reviewer: Optional[str] = None
    approval_date: Optional[datetime] = None
    approval_comment: Optional[str] = None

    # Implementation
    affected_files: List[str] = field(default_factory=list)
    affected_verifications: List[str] = field(default_factory=list)  # TC-{TYPE}-{Nr} IDs
    commits: List[str] = field(default_factory=list)

    # Evidence
    evidence_refs: List[str] = field(default_factory=list)

    # Emergency
    is_emergency: bool = False
    incident_id: Optional[str] = None
    severity: Optional[str] = None
    rollback_plan: Optional[str] = None
    post_mortem_date: Optional[datetime] = None

    # Storage
    file_path: Optional[Path] = None

class CRStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    CLOSED = "closed"
    REJECTED = "rejected"
    EMERGENCY = "emergency"
```

#### Verification Type Model

```python
class VerificationType(Enum):
    UNIT = "unit"                           # TC-UT-{Nr}
    SOFTWARE_INTEGRATION = "software_integration"   # TC-SIT-{Nr}
    SOFTWARE_VERIFICATION = "software_verification" # TC-SVT-{Nr}
    SYSTEM_INTEGRATION = "system_integration"       # TC-SYSIT-{Nr}
    SYSTEM_VERIFICATION = "system_verification"     # TC-SYST-{Nr}

@dataclass
class VerificationCase:
    """Planned verification artifact (specification)."""
    id: str                           # TC-{TYPE}-{Nr}
    title: str
    type: VerificationType
    status: VerificationStatus        # DRAFT, APPROVED, PASSED, FAILED, DEPRECATED
    description: str
    validates: List[str]              # Requirement IDs
    implemented_in: str               # Test file path
    component: str
    owner: str
    created: datetime

class VerificationStatus(Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PASSED = "passed"
    FAILED = "failed"
    DEPRECATED = "deprecated"
```

#### Process Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  DEVELOPER initiates change                                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. CREATE CR                                                       │
│     Input: title, problem, justification, requirement_refs           │
│     Input: change_type, requirement_linkage_type (if bugfix)        │
│     Output: CR-XXX.md in changes/                                   │
│     Status: SUBMITTED                                               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. VALIDATE TRACEABILITY (optional, can be deferred)               │
│     Check: requirement_refs exist in requirements/                  │
│     Check: change_type=bugfix → SW-REQ linkage valid               │
│     Output: validation report                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. APPROVE CR                                                      │
│     Transition: SUBMITTED → APPROVED                                │
│     Authority: tech lead, architect, or automated criteria          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. IMPLEMENT                                                       │
│     Transition: APPROVED → IN_PROGRESS → IMPLEMENTED                │
│     Developer makes code changes                                    │
│     VerificationCases written (type per requirement level)          │
│     Files and VerificationCase IDs linked to CR                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  5. VERIFY                                                          │
│     Transition: IMPLEMENTED → VERIFIED                              │
│     VerificationCases executed (PASSED)                             │
│     VerificationResults recorded in evidence                        │
│     Output: changes/evidence/CR-XXX_evidence.json                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  6. CLOSE                                                           │
│     Transition: VERIFIED → CLOSED                                   │
│     Final audit state                                               │
└─────────────────────────────────────────────────────────────────────┘
```

#### System Boundaries

| Boundary | Inside C | Outside C |
|----------|----------|-----------|
| **Data** | CR files, evidence files, VerificationCase files | Requirement source files (read-only) |
| **Logic** | CR lifecycle, validation rules, evidence generation, verification type mapping | Requirement parsing, test execution |
| **Interface** | CLI commands | IDE plugins, web dashboards |
| **Storage** | `changes/`, `verification/` directories | `requirements/` directory (external) |

#### Interfaces

**CLI Interface:**
```bash
curaops cr create --title "..." --problem "..." --justification "..." --requirements "REQ-001,REQ-002" --change-type bugfix --requirement-linkage-type existing_ref
curaops cr submit CR-001
curaops cr validate CR-001
curaops cr approve CR-001 --reviewer "lead@example.com"
curaops cr status CR-001
curaops cr evidence CR-001
curaops cr list --status approved --impact-level SW

# VerificationCase management
curaops verification create --title "..." --type software_verification --validates SW-REQ-001 --implemented-in tests/test_auth.py
curaops verification list --validates SW-REQ-001
curaops verification run TC-SVT-001
```

**Python API:**
```python
class ChangeRequestService:
    def submit_change_request(title, problem, justification, requirement_refs,
                             change_type="feature", requirement_linkage_type=None) -> dict
    def get_cr_status(cr_id) -> dict
    def process_change_request(cr_id, new_status) -> dict
    def generate_cr_evidence(cr_id, format) -> Path
    def validate_cr_traceability(cr_id) -> ValidationResult

class VerificationService:
    def create_verification(title, type, validates, implemented_in) -> str
    def get_verification(tc_id) -> VerificationCase
    def validate_verification_type(tc_id, req_id) -> bool
    def list_verifications(validates=None, type=None) -> list
```

#### Storage/Evidence Outputs

**CR Storage:**
- Location: `changes/CR-XXX.md`
- Format: Markdown with YAML frontmatter

**VerificationCase Storage:**
- Location: `verification/TC-{TYPE}-{Nr}.md`
- Format: Markdown with YAML frontmatter

**Evidence Storage:**
- Location: `changes/evidence/CR-XXX_evidence.json`
- Format: JSON
- Content: CR metadata + verification results + timestamp + hash

#### Validation Rules

1. **Mandatory Fields:** title, problem, justification cannot be empty at SUBMITTED
2. **Requirement References:** If provided, must be non-empty list
3. **change_type:** Required at SUBMITTED. If "bugfix", requirement_linkage_type also required
4. **Status Transitions:** Only valid transitions allowed per state machine
5. **Traceability Check:** (Optional) Verify requirement files exist in requirements/
6. **Verification Type Check:** VerificationCase.type must match requirement level per mapping
7. **Uniqueness:** CR IDs and VerificationCase IDs are auto-generated and unique

### Definition of Done (DoD)

**PR #3 hardening note:** This checklist is a merge-gate checklist for the Compliance Change Control slice, not proof that PR #3 is complete. Leave unchecked items open until backed by tests, CLI proof, or linked evidence.

**For C to be considered complete:**

1. [ ] CR creation with requirement_refs works via CLI
2. [ ] CR status workflow implemented (all 9 states, all transitions)
3. [ ] Evidence generation produces valid JSON/Markdown
4. [ ] Traceability validation checks requirement existence
5. [ ] VerificationCase entity with 5 types implemented
6. [ ] Verification type mapping enforced per requirement level
7. [ ] Bugfix-specific validation (change_type, linkage_type) working
8. [ ] All functions have unit tests (minimum 80% coverage)
9. [ ] CLI commands documented in help text
10. [ ] At least one end-to-end workflow verified manually
11. [ ] No dependency on external ALM tools
12. [ ] Markdown format documented
13. [ ] Error messages are actionable

### Verification Criteria

**Unit Tests:**
- CR creation with/without requirement_refs
- Status transitions (valid and invalid)
- Evidence generation format validation
- Traceability validation (found/not found)
- VerificationCase type matching per requirement level
- Bugfix-specific validation (change_type=bugfix without SW-REQ → BLOCKING)

**Integration Tests:**
- End-to-end: create → validate → implement → verify → evidence → close
- CR with linked requirements that exist
- CR with linked requirements that don't exist
- VerificationCase PASSED → evidence contains result

**Manual Verification:**
- Run CLI commands and inspect outputs
- Verify Markdown files are human-readable
- Verify evidence JSON is machine-parseable

---

> **Accountable Agent Layer** architecture (sections previously D-H) is now in [ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md](./ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md).

**END OF AUTHORITATIVE DOCUMENT**
