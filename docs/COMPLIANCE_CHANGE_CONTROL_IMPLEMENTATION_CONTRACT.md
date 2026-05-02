# Compliance Change Control Implementation Contract

> **Status:** AUTHORITATIVE — Compliance Change Control (C) only.
> B implementation is in [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md).

**Version:** 2.0.0  
**Date:** 2026-04-19  
**Source:** COMPLIANCE_CHANGE_CONTROL_PROCESS.md + COMPLIANCE_CHANGE_CONTROL_RULES.md

---

## A. Scope and Implementation Goal

### A.1 Scope

**IN SCOPE:**
- Compliance Change Control: Change Request (CR) workflow with requirement-linked traceability
- CLI implementation for Compliance Change Control
- Evidence generation and validation
- State machine implementation
- Blocking/warning logic

**OUT OF SCOPE:**
- Safety Guard (Safety Guard) — standalone, already implemented
- IDE integrations beyond CLI
- Web dashboards
- External tool adapters (Jira, DOORS)
- AI model integration (assumes external)
- Real-time monitoring

### A.2 Implementation Goal

Deliver production-ready Compliance Change Control module that:
1. Enforce CR-before-change policy
2. Validate requirement traceability
3. Generate audit-ready evidence

---

## B. Repo and Module Ownership

### B.1 Primary Repository

```
/home/roberto_schmidt/projects/matrix-os/
```

### B.2 Module Ownership Matrix <!-- shared-interface: duplicated in ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md -->

| Module | Path | Language | Owner |
|--------|------|----------|-------|
| Compliance Change Control Core | `curaops/skills/change_request/` | Python | C implementation |
| Compliance Change Control CLI | `curaops/cli/commands/cr.py` | Python | C CLI interface |
| Accountable Agent Layer Core | `curaops/skills/accountable_agent/` | Python | B implementation |
| Accountable Agent Layer CLI | `curaops/cli/commands/accountable.py` | Python | B CLI interface |
| Shared | `curaops/skills/aspice_link_manager/` | Python | Bidirectional links |
| Evidence | `changes/evidence/` | JSON/Markdown | Generated output |

### B.3 Directory Structure <!-- shared-interface: duplicated in ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md -->

```
/home/roberto_schmidt/projects/matrix-os/
├── curaops/
│   ├── skills/
│   │   ├── change_request/           # Compliance Change Control Core
│   │   │   ├── __init__.py           # CR service, state machine
│   │   │   ├── models.py             # CR dataclasses
│   │   │   ├── state_machine.py      # State transitions
│   │   │   ├── validation.py         # Field validation
│   │   │   ├── evidence.py           # Evidence generation
│   │   │   └── tests/                # C tests
│   │   │       ├── test_cr.py
│   │   │       ├── test_state_machine.py
│   │   │       └── test_validation.py
│   │   ├── accountable_agent/        # Accountable Agent Layer Core
│   │   │   ├── __init__.py           # B service, intervention
│   │   │   ├── models.py             # AccountableChange dataclass
│   │   │   ├── intervention.py       # Pre-flight, blocking logic
│   │   │   ├── validation.py         # Accountability validation
│   │   │   ├── evidence.py           # B evidence generation
│   │   │   └── tests/                # B tests
│   │   │       ├── test_intervention.py
│   │   │       ├── test_validation.py
│   │   │       └── test_integration.py
│   │   └── aspice_link_manager/      # Shared
│   │       ├── __init__.py           # Link management
│   │       └── tests/
│   └── cli/
│       └── commands/
│           ├── cr.py                 # C CLI
│           └── accountable.py        # B CLI
├── changes/                          # CR storage
│   ├── CR-001.md
│   ├── CR-002.md
│   └── evidence/                     # Evidence storage
│       ├── CR-001_20260410_143000.json
│       └── AC-58D0D7B9_20260410_100500.json
└── requirements/                     # Requirement storage (existing)
    ├── system/
    ├── software/
    └── architecture/
```

---

## C. Source-of-Truth Map

### C.1 From matrix-os (Primary)

| Module | File | Reuse Decision |
|--------|------|----------------|
| ASPICE Link Manager | `curaops/skills/aspice_link_manager/__init__.py` | **REUSE** — Bidirectional link management |
| CLI Framework | `curaops/cli/main.py` | **REUSE** — Typer-based CLI structure |
| Session Manager | `curaops/skills/session_manager/` | **REFERENCE** — For session_id integration |

### C.2 From CuraOps_Framework (Reference Only)

| Module | File | Reuse Decision |
|--------|------|----------------|
| Change Request Service | `src/core/change_request_service.py` | **REFERENCE** — Patterns, not code copy |
| Traceability Validation | `src/compliance/traceability_validation_service.py` | **REFERENCE** — Validation patterns |
| Requirements Derivation | `src/services/requirements_derivation_service.py` | **REFERENCE** — Derivation logic |
| ID Patterns | `Traceability Bible v3.1 TEIL 8` | **ADOPT** — ID conventions |
| Link Semantics | `Traceability Bible v3.1 TEIL 4` | **ADOPT** — Link types |

### C.3 New Implementation Required

| Component | Location | Reason |
|-----------|----------|--------|
| CR State Machine | `change_request/state_machine.py` | Simplified from Framework |
| CR Models | `change_request/models.py` | Aligned with contract |
| Evidence Generation | `change_request/evidence.py` | Contract-aligned format |
| CLI Commands | `cli/commands/cr.py` | C CLI integration |

> **B implementation components** (Accountable Agent Layer Intervention, Models) are listed in [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md).

### C.4 Explicit Non-Reuse (Anti-Corruption)

| Framework Component | Why Not Reused |
|--------------------|----------------|
| Impact Analysis Service | Too complex, overkill for C scope |
| Workflow Engine | Overkill, state machine sufficient |
| Notification System | Out of scope |
| ParserFactory | Too complex, simple parsing sufficient |
| JSON persistence | C uses Markdown |

---

## D. C Module Design

### D.1 Language: Python 3.10+

**Rationale:**
- Existing matrix-os codebase is Python
- Dataclasses, type hints, pattern matching available
- Typer for CLI already in use

### D.2 Core Components

```python
# change_request/models.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Optional
from pathlib import Path

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

class ImpactLevel(Enum):
    SYS = "SYS"
    ARCH = "ARCH"
    SW = "SW"
    CODE = "CODE"

class SafetyImpact(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

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
    impact_level: List[ImpactLevel]
    requirement_refs: List[str]       # min 1
    safety_impact: SafetyImpact
    compliance_impact: Optional[List[str]] = None
    
    # Lifecycle
    reviewer: Optional[str] = None
    approval_date: Optional[datetime] = None
    approval_comment: Optional[str] = None
    
    # Implementation
    affected_files: List[str] = field(default_factory=list)
    affected_verifications: List[str] = field(default_factory=list)
    commits: List[str] = field(default_factory=list)
    
    # Evidence
    evidence_refs: List[str] = field(default_factory=list)
    
    # Emergency
    is_emergency: bool = False
    incident_id: Optional[str] = None
    severity: Optional[str] = None
    rollback_plan: Optional[str] = None
    post_mortem_date: Optional[datetime] = None
    
    # Bugfix metadata (required at CLOSED for bugfix — C-RULES §8.1)
    root_cause_category: Optional[str] = None  # impl_bug, req_ambiguous, req_missing, arch_bug, sys_bug
    
    # Storage
    file_path: Optional[Path] = None

class VerificationType(Enum):
    UNIT = "unit"                           # TC-UT-{Nr}
    SOFTWARE_INTEGRATION = "software_integration"   # TC-SIT-{Nr}
    SOFTWARE_VERIFICATION = "software_verification" # TC-SVT-{Nr}
    SYSTEM_INTEGRATION = "system_integration"       # TC-SYSIT-{Nr}
    SYSTEM_VERIFICATION = "system_verification"     # TC-SYST-{Nr}

class VerificationStatus(Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PASSED = "passed"
    FAILED = "failed"
    DEPRECATED = "deprecated"

@dataclass
class VerificationCase:
    """Planned verification artifact (specification)."""
    id: str                           # TC-{TYPE}-{Nr}
    title: str
    type: VerificationType
    status: VerificationStatus
    description: str
    validates: List[str]              # Requirement IDs
    implemented_in: str               # Test file path
    component: str
    owner: str
    created: datetime

    # Optional
    prerequisite: Optional[str] = None
    test_data: Optional[str] = None
    last_run: Optional[datetime] = None
    last_result: Optional[str] = None  # PASS, FAIL, SKIP
```

### D.3 State Machine Implementation

```python
# change_request/state_machine.py

class CRStateMachine:
    """Implements exact transition matrix from COMPLIANCE_CHANGE_CONTROL_PROCESS.md Section C."""
    
    VALID_TRANSITIONS = {
        CRStatus.DRAFT: {CRStatus.SUBMITTED, CRStatus.REJECTED},
        CRStatus.SUBMITTED: {CRStatus.APPROVED, CRStatus.REJECTED, CRStatus.DRAFT},
        CRStatus.APPROVED: {CRStatus.IN_PROGRESS, CRStatus.REJECTED},
        CRStatus.IN_PROGRESS: {CRStatus.IMPLEMENTED, CRStatus.REJECTED},
        CRStatus.IMPLEMENTED: {CRStatus.VERIFIED, CRStatus.REJECTED},
        CRStatus.VERIFIED: {CRStatus.CLOSED},
        CRStatus.REJECTED: {CRStatus.DRAFT},
        CRStatus.EMERGENCY: {CRStatus.SUBMITTED},
    }
    
    MANDATORY_FIELDS = {
        CRStatus.DRAFT: {"id", "title", "status", "created", "requester"},
        CRStatus.SUBMITTED: {"id", "title", "status", "created", "requester", 
                             "problem", "justification", "change_type",
                             "impact_level", "requirement_refs", "safety_impact"},
        CRStatus.APPROVED: {"id", "title", "status", "created", "requester",
                           "problem", "justification", "impact_level",
                           "requirement_refs", "safety_impact", "reviewer", "approval_date"},
        # ... etc
    }
    
    def can_transition(self, cr: ChangeRequest, to_status: CRStatus) -> bool:
        """Check if transition is valid."""
        return to_status in self.VALID_TRANSITIONS.get(cr.status, set())
    
    def transition(self, cr: ChangeRequest, to_status: CRStatus, 
                   actor: str, context: dict) -> ChangeRequest:
        """Execute transition with validation."""
        if not self.can_transition(cr, to_status):
            raise InvalidTransitionError(f"Cannot transition {cr.status} → {to_status}")
        
        # Validate mandatory fields for target state
        required = self.MANDATORY_FIELDS.get(to_status, set())
        missing = self._check_fields(cr, required)
        if missing:
            raise MissingFieldsError(f"Missing fields for {to_status}: {missing}")
        
        # Execute transition
        cr.status = to_status
        return cr
```

### D.4 Validation Implementation

```python
# change_request/validation.py

import re
from typing import List, Tuple

class CRValidator:
    """Implements validation rules from COMPLIANCE_CHANGE_CONTROL_PROCESS.md."""
    
    ID_PATTERNS = {
        "CR": r"^CR-[0-9]{3,}$",
        "SYS-REQ": r"^SYS-REQ-[0-9]+$",
        "SW-REQ": r"^SW-REQ-[0-9]+$",
        "SW-ARCH": r"^SW-ARCH-[0-9]+$",
        "TC-UT": r"^TC-UT-[0-9]+$",
        "TC-SIT": r"^TC-SIT-[0-9]+$",
        "TC-SVT": r"^TC-SVT-[0-9]+$",
        "TC-SYSIT": r"^TC-SYSIT-[0-9]+$",
        "TC-SYST": r"^TC-SYST-[0-9]+$",
    }
    
    def validate_id_format(self, ref: str) -> Tuple[bool, str]:
        """Validate requirement ID format."""
        for prefix, pattern in self.ID_PATTERNS.items():
            if re.match(pattern, ref):
                return True, prefix
        return False, f"Invalid ID format: {ref}"
    
    def validate_impact_classification(self, cr) -> List[dict]:
        """Detect impact level from requirement refs."""
        issues = []
        detected_levels = set()
        
        for ref in cr.requirement_refs:
            if ref.startswith("SYS-REQ-"):
                detected_levels.add("SYS")
            elif ref.startswith("SW-ARCH-"):
                detected_levels.add("ARCH")
            elif ref.startswith("SW-REQ-"):
                detected_levels.add("SW")
        
        # Check required levels present
        if "SYS" in detected_levels and "SYS" not in cr.impact_level:
            issues.append({
                "severity": "WARNING",
                "message": "SYS-REQ detected but impact_level missing SYS"
            })
        
        return issues
    
    def validate_derivation_obligations(self, cr) -> List[dict]:
        """Check derivation obligations."""
        issues = []
        
        sys_reqs = [r for r in cr.requirement_refs if r.startswith("SYS-REQ-")]
        sw_reqs = [r for r in cr.requirement_refs if r.startswith("SW-REQ-")]
        
        # Rule: SYS-REQ must have SW-REQ children
        if sys_reqs and not sw_reqs:
            issues.append({
                "severity": "BLOCKING",
                "message": "SYS-REQ present but no SW-REQ (derivation obligation)",
                "rule": "SYS-REQ must derive 1-7 SW-REQs"
            })
        
        return issues

    def validate_bugfix_rules(self, cr) -> List[dict]:
        """Validate bugfix-specific rules from C-RULES Section 9."""
        issues = []
        if cr.change_type == "bugfix":
            # Bugfix must have SW-REQ linkage
            sw_reqs = [r for r in cr.requirement_refs if r.startswith("SW-REQ-")]
            if not sw_reqs:
                issues.append({
                    "severity": "BLOCKING",
                    "message": "Bugfix CR has no SW-REQ in requirement_refs",
                    "rule": "C-RULES §9.1: Every functional bugfix links to SW-REQ"
                })
            
            # requirement_linkage_type must be set for bugfix
            if not cr.requirement_linkage_type:
                issues.append({
                    "severity": "BLOCKING",
                    "message": "Bugfix CR missing requirement_linkage_type",
                    "rule": "C-RULES §9.7: bugfix must declare linkage type"
                })
            
            # new_ref requires APPROVED new SW-REQ
            if cr.requirement_linkage_type == "new_ref":
                # Check that any new SW-REQ is APPROVED before CR moves past SUBMITTED
                for ref in sw_reqs:
                    # This would call the requirement service in production
                    pass
            
            # At IMPLEMENTED: must have affected_verifications
            if cr.status == CRStatus.IMPLEMENTED and not cr.affected_verifications:
                issues.append({
                    "severity": "BLOCKING",
                    "message": "Bugfix CR at IMPLEMENTED with no VerificationCases",
                    "rule": "C-RULES §9.4: at least one regression VerificationCase per SW-REQ"
                })
        
        return issues
```

### D.5 Evidence Generation

```python
# change_request/evidence.py

import json
import hashlib
from datetime import datetime
from pathlib import Path

class CREvidenceGenerator:
    """Generate machine-readable evidence."""
    
    EVIDENCE_DIR = Path("changes/evidence")
    
    def generate(self, cr: ChangeRequest) -> Path:
        """Generate evidence file."""
        self.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        
        evidence = {
            "schema_version": "CCC-1.1.0",
            "cr_id": cr.id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": cr.status.value,
            "change_type": cr.change_type,
            "requirement_linkage_type": cr.requirement_linkage_type,
            "root_cause_category": getattr(cr, 'root_cause_category', None),
            "validation": self._validate_cr(cr),
            "traceability": {
                "requirement_refs": cr.requirement_refs,
                "links_verified": True
            },
            "implementation": {
                "commits": cr.commits,
                "files_changed": cr.affected_files,
                "verification_cases": cr.affected_verifications
            },
            "verification_results": [],
            "approval": {
                "approver": cr.reviewer,
                "date": cr.approval_date.isoformat() if cr.approval_date else None
            } if cr.reviewer else None
        }
        
        # Bugfix-specific evidence fields
        if cr.change_type == "bugfix":
            evidence["regression_verification_ids"] = cr.affected_verifications
        
        # Add hash
        evidence_str = json.dumps(evidence, sort_keys=True)
        evidence["hash"] = f"sha256:{hashlib.sha256(evidence_str.encode()).hexdigest()}"
        
        # Write file
        filename = f"{cr.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.EVIDENCE_DIR / filename
        filepath.write_text(json.dumps(evidence, indent=2))
        
        return filepath
```

---



> **B Module Design:** The Accountable Agent Layer implementation is documented in [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md).

## F. Persistence and Evidence Model

### F.1 CR Persistence

**Format:** Markdown with YAML frontmatter
**Location:** `changes/CR-[ID].md`
**Example:**
```markdown
---
id: CR-001
title: "Fix authentication vulnerability"
status: approved
created: 2026-04-10T10:00:00Z
requester: developer@example.com
problem: "OAuth2 implementation vulnerable to token replay"
justification: "Security fix required for compliance"
change_type: bugfix
requirement_linkage_type: existing_ref
impact_level: [SYS, SW]
requirement_refs: [SYS-REQ-001, SW-REQ-003]
safety_impact: HIGH
reviewer: lead@example.com
approval_date: 2026-04-10T11:00:00Z
affected_files: [src/auth.py, tests/test_auth.py]
affected_verifications: [TC-SVT-012]
commits: [abc123, def456]
evidence_refs: [changes/evidence/CR-001_20260410_143000.json]
---

## Description
Detailed problem description...

## Acceptance Criteria
- [ ] Token replay prevented
- [ ] Tests pass
```

### F.2 Evidence Persistence

**Format:** JSON
**Location:** `changes/evidence/`
**Naming:** `[ENTITY]-[ID]_[YYYYMMDD]_[HHMMSS].json`

## G. CLI Contract

### G.1 C CLI Commands

```bash
# CR Management
curaops cr create \
  --title "Fix auth vulnerability" \
  --problem "OAuth2 token replay vulnerability" \
  --justification "Security compliance requirement" \
  --impact-level SW \
  --requirement-refs SW-REQ-003 \
  --change-type bugfix \
  --requirement-linkage-type existing_ref \
  --safety-impact HIGH

curaops cr submit CR-001
curaops cr approve CR-001 --reviewer "lead@example.com"
curaops cr reject CR-001 --reason "Incomplete tests"
curaops cr status CR-001
curaops cr list --status approved --impact-level SW

# Evidence
curaops cr evidence CR-001
curaops cr validate CR-001

# Emergency
curaops cr create --emergency \
  --title "Hotfix: data leak" \
  --problem "Sensitive data in logs" \
  --incident-id INC-2026-001 \
  --severity P0

# VerificationCase management
curaops verification create --title "..." --type software_verification --validates SW-REQ-001 --implemented-in tests/test_auth.py
curaops verification list --validates SW-REQ-001
curaops verification validate-type TC-SVT-001 SW-REQ-001
```

### G.3 Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Blocking condition (B intervention) |
| 2 | Validation failure |
| 3 | State transition invalid |
| 4 | Missing required fields |
| 5 | File not found |

---

## H. Verification Strategy

### H.1 Test Pyramid

```
        /\
       /  \     Integration Tests (End-to-End)
      /____\         10 tests
     /      \   
    /________\    Component Tests (State Machine)
   /          \      30 tests
  /____________\
 /              \  Unit Tests (Validation, Models)
/________________\    60 tests
```

### H.2 Unit Tests (C)

```python
# test_validation.py

def test_validate_id_format_valid():
    validator = CRValidator()
    assert validator.validate_id_format("SW-REQ-001") == (True, "SW-REQ")

def test_validate_id_format_invalid():
    validator = CRValidator()
    assert validator.validate_id_format("INVALID") == (False, "Invalid ID format")

def test_impact_detection_sys_req():
    cr = ChangeRequest(requirement_refs=["SYS-REQ-001"])
    issues = validator.validate_impact_classification(cr)
    assert any("SYS" in i["message"] for i in issues)

def test_derivation_obligation_blocking():
    cr = ChangeRequest(requirement_refs=["SYS-REQ-001"])  # No SW-REQ
    issues = validator.validate_derivation_obligations(cr)
    assert any(i["severity"] == "BLOCKING" for i in issues)
```

### H.3 Component Tests (C)

```python
# test_state_machine.py

def test_valid_transition_draft_to_submitted():
    sm = CRStateMachine()
    cr = ChangeRequest(status=CRStatus.DRAFT)
    cr = sm.transition(cr, CRStatus.SUBMITTED, "user", {})
    assert cr.status == CRStatus.SUBMITTED

def test_invalid_transition_submitted_to_closed():
    sm = CRStateMachine()
    cr = ChangeRequest(status=CRStatus.SUBMITTED)
    with pytest.raises(InvalidTransitionError):
        sm.transition(cr, CRStatus.CLOSED, "user", {})
```

### H.5 End-to-End Tests

```python
# Test complete workflow
def test_e2e_cr_lifecycle():
    # Create CR
    result = runner.invoke(cli, ["cr", "create", "--title", ...])
    cr_id = extract_id(result.output)
    
    # Submit
    runner.invoke(cli, ["cr", "submit", cr_id])
    
    # Approve
    runner.invoke(cli, ["cr", "approve", cr_id, "--reviewer", "lead"])
    
    # Verify status
    result = runner.invoke(cli, ["cr", "status", cr_id])
    assert "approved" in result.output
```

---

## I. Definition of Done

### I.1 C Slice Done When

1. [ ] `change_request/models.py` — All dataclasses implemented
2. [ ] `change_request/state_machine.py` — Transition matrix working
3. [ ] `change_request/validation.py` — All validation rules implemented
4. [ ] `change_request/evidence.py` — Evidence generation working
5. [ ] `cli/commands/cr.py` — All CLI commands working
6. [ ] Unit tests: 60+ tests, >80% coverage
7. [ ] Component tests: 30+ tests
8. [ ] Integration tests: 10+ tests
9. [ ] Documentation: Docstrings for all public methods
10. [ ] Example workflow verified manually
11. [ ] Bugfix-specific validation (change_type=bugfix → SW-REQ linkage, linkage_type) working
12. [ ] VerificationCase type mapping enforced per requirement level
13. [ ] Evidence includes bugfix-specific fields when change_type=bugfix

## J. Minimum Requirement Set for Current Domain

### J.1 Problem Domain

**Data Accuracy / Truth Resolution:**
- Engineering changes must be traceable to requirements
- AI-assisted changes must be accountable
- Compliance requires audit trail

### J.2 Minimum Requirement Set

**CR (Process Entry):**
- CR creation with mandatory fields
- State machine with 9 states
- Evidence generation

**Requirements (Traceability):**
- SYS-REQ (system-level)
- SW-REQ (software-level)
- SW-ARCH (architecture-level)

**Links (Traceability):**
- refined_in / derived_from (hierarchy)
- constrains / constrained_by (architecture)
- implemented_in / implements (code)
- validated_by / validates (tests)


### J.3 Explicitly Out (for now)

- User Stories (can be added above SYS-REQ later)
- NFR as separate type (use tags on SYS-REQ)
- IF-SYS (only if external interfaces needed)
- TC-AT (acceptance testing — add later if needed)
- Real-time monitoring
- Dashboards
- IDE plugins

---

## K. Migration Plan from Provisional Code

### K.1 Current State (Provisional)

```
curaops/skills/change-request/__init__.py         # +175 lines, needs alignment
curaops/skills/aspice-link-manager/__init__.py    # Exists, reuse
```

> **B provisional code** (`accountable-agent/__init__.py`) migration is in [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md) Section K.

### K.2 Migration Steps

**Phase 1: C Alignment (1-2 days)**
1. Create new structure:
   - `change_request/models.py` (extract from __init__)
   - `change_request/state_machine.py` (new)
   - `change_request/validation.py` (refactor)
   - `change_request/evidence.py` (refactor)

2. Align models with contract:
   - Add missing fields (problem, justification, safety_impact)
   - Fix state enum (add VERIFIED, EMERGENCY)
   - Update ID patterns

3. Update CLI:
   - Refactor `cli/commands/cr.py`
   - Add missing commands (submit, verify)

**Phase 3: Testing (2-3 days)**
1. Port existing tests
2. Add new test cases
3. Verify integration

**Phase 4: Validation (1 day)**
1. Run worked examples
2. Verify evidence format
3. Check blocking scenarios

### K.3 Backward Compatibility

- Existing CR files: Parse and migrate on first access
- Evidence format: New schema version (1.0.0)
- CLI commands: Add new, deprecate old

---

## L. Remaining Ambiguities (2)

### L.1 Session Persistence

**Question:** How long does session→CR binding persist?

**Options:**
- A: Until session ends (process exit)
- B: Timeout-based (e.g., 8 hours)
- C: Explicit unlink required

**Decision:** A for MVP (simplest), add timeout later if needed.

### L.2 Evidence Retention

**Question:** How many evidence versions to keep per CR?

**Options:**
- A: Keep all (disk usage grows)
- B: Keep last N (e.g., 10)
- C: Keep only latest (simplest)

**Decision:** A for compliance (keep all), add cleanup policy later.

---

**END OF IMPLEMENTATION CONTRACT**
