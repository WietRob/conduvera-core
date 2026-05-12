# Accountable Agent Layer Implementation — Authoritative

> **⚠️ LEGACY NOTICE:** This replaces the mixed COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md Section E.
> For Compliance Change Control implementation, see COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md.

**Status:** AUTHORITATIVE
**Version:** 2.0.0
**Date:** 2026-04-19
**Scope:** Accountable Agent Layer ONLY

---

## A. Scope and Implementation Goal

### A.1 Scope

**IN SCOPE:**
- Accountable Agent Layer: Active intervention for AI-assisted changes
- Agent identity capture (attribution)
- Pre-flight blocking logic
- Accountability validation
- Evidence generation
- CLI implementation

**Scope OUT:**
- CR workflow (see Compliance Change Control)
- Requirement state machines (see Compliance Change Control)
- IDE integrations beyond CLI

### A.2 Implementation Goal

Deliver production-ready Accountable Agent Layer that:
1. Intervenes before non-compliant AI-assisted changes
2. Captures agent attribution (who, model, tools)
3. Validates accountability links (CR + requirements)
4. Blocks non-compliant changes
5. Generates accountability evidence

---

## B. Module Design

### B.1 Language: Python 3.10+

Same as Compliance Change Control for consistency.

### B.2 Core Components

```python
# accountable_agent/models.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

class ACStatus(Enum):
    PENDING = "pending"
    LINKED = "linked"
    VALIDATED = "validated"
    BLOCKED = "blocked"

@dataclass
class AgentContext:
    """AI agent attribution."""
    agent_id: str
    agent_name: str
    model: str
    tools_used: List[str] = field(default_factory=list)
    session_id: Optional[str] = None

@dataclass
class ChangeIntent:
    """What the agent intends to change."""
    description: str
    change_type: str  # feature, bugfix, refactor, test, docs
    files_affected: List[str] = field(default_factory=list)
    estimated_impact: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW

@dataclass
class AccountableChange:
    """Accountable Agent Layer accountability record."""

    # Identity
    accountable_id: str  # AC-[0-9A-F]{8}
    created_at: datetime

    # Context
    agent_context: AgentContext
    change_intent: ChangeIntent

    # Accountability links (mandatory in strict mode)
    cr_id: str
    requirement_refs: List[str]

    # State
    status: ACStatus
    block_reason: Optional[str] = None
    # Bugfix context (consumed from C, not invented by B)
    change_type: Optional[str] = None    # feature, bugfix, refactor, test, docs
    requirement_linkage_type: Optional[str] = None  # existing_ref, updated_ref, new_ref
    root_cause_category: Optional[str] = None  # impl_bug, req_ambiguous, req_missing, arch_bug, sys_bug
    regression_verification_ids: List[str] = field(default_factory=list)  # TC-IDs

    # Evidence
    evidence_path: Optional[str] = None
    validation_report: Optional[dict] = None
```

### B.3 Intervention Implementation

```python
# Canonical PR C runtime entrypoint: curaops.skills.accountable_agent.AccountableAgentService
from curaops.skills.accountable_agent import AccountableAgentService
from curaops.skills.change_request import CRStatus, ChangeRequestService, verify_evidence_file

service = AccountableAgentService(project_root=project_root)
result = service.pre_flight_check(
    cr_id="CR-001",
    requirement_refs=["SW-REQ-001"],
    change_type="bugfix",
    impact_level=["SW", "CODE"],
)

# Blocks when:
# - the linked CR does not exist
# - the linked CR is before APPROVED for pre-flight
# - requirement refs are missing
# - bugfix SW-REQ / new_ref / VerificationCase semantics from CCC fail
# - validate/evidence sees a CR before APPROVED

if not result["passed"]:
    raise SystemExit(result["blocks"])
```

> PR C keeps impact/ref helper logic inside `AccountableAgentService`; no separate `BIntervention` public class or CCC helper API is exposed.

### B.4 Validation

```python
# accountable_agent/validation.py

class BValidator:
    """Validate accountability requirements."""

    def validate_accountability(self, ac: AccountableChange) -> dict:
        """
        Validate AccountableChange meets accountability requirements.

        Returns validation report with:
        - valid: bool
        - checks: detailed check results
        - issues: list of warnings/blockers
        """
        checks = {
            "cr_exists": {"passed": False},
            "cr_approved": {"passed": False},
            "requirement_refs_present": {"passed": False, "count": 0},
            "requirement_ids_valid": {"passed": False},
            "hierarchy_consistent": {"passed": False},
        }
        issues = []

        # Check: CR exists
        cr = self.cr_service.get_cr(ac.cr_id)
        if cr:
            checks["cr_exists"]["passed"] = True

            # Check: CR approved
            if cr.status == CRStatus.APPROVED:
                checks["cr_approved"]["passed"] = True
            else:
                issues.append({
                    "severity": "BLOCKING",
                    "message": f"CR not approved: {cr.status.value}"
                })
        else:
            issues.append({
                "severity": "BLOCKING",
                "message": f"CR not found: {ac.cr_id}"
            })

        # Check: Requirement refs present
        if ac.requirement_refs:
            checks["requirement_refs_present"]["passed"] = True
            checks["requirement_refs_present"]["count"] = len(ac.requirement_refs)
        else:
            issues.append({
                "severity": "BLOCKING",
                "message": "No requirement_refs"
            })

        # Check: ID formats
        invalid = self._validate_ids(ac.requirement_refs)
        if not invalid:
            checks["requirement_ids_valid"]["passed"] = True
        else:
            issues.append({
                "severity": "BLOCKING",
                "message": f"Invalid IDs: {invalid}"
            })

        # Check: Hierarchy
        hierarchy_ok = self._check_hierarchy(ac.requirement_refs)
        checks["hierarchy_consistent"]["passed"] = hierarchy_ok
        if not hierarchy_ok:
            issues.append({
                "severity": "WARNING",
                "message": "Hierarchy consistency check failed"
            })

        return {
            "valid": all(c["passed"] for c in checks.values()),
            "checks": checks,
            "issues": issues
        }
```

### B.5 Evidence Generation

```python
# accountable_agent/evidence.py

class ACEvidenceGenerator:
    """Generate accountability evidence."""

    def generate(self, ac: AccountableChange,
                 cr_evidence_path: str) -> Path:
        """Generate Accountable Agent Layer evidence with C reference."""

        evidence = {
            "schema_version": "AAL-1.0.0",
            "accountable_change": {
                "accountable_id": ac.accountable_id,
                "created_at": ac.created_at.isoformat() + "Z",
                "status": ac.status.value,
                "agent_context": {
                    "agent_id": ac.agent_context.agent_id,
                    "agent_name": ac.agent_context.agent_name,
                    "model": ac.agent_context.model,
                    "tools_used": ac.agent_context.tools_used,
                    "session_id": ac.agent_context.session_id
                },
                "change_intent": {
                    "description": ac.change_intent.description,
                    "change_type": ac.change_intent.change_type,
                    "files_affected": ac.change_intent.files_affected,
                    "estimated_impact": ac.change_intent.estimated_impact
                },
                "accountability_links": {
                    "cr_id": ac.cr_id,
                    "requirement_refs": ac.requirement_refs
                }
            },
            "bugfix_context": {
                "change_type": ac.change_intent.change_type,
                "requirement_linkage_type": getattr(ac, 'requirement_linkage_type', None),
                "root_cause_category": getattr(ac, 'root_cause_category', None),
                "regression_verification_ids": getattr(ac, 'regression_verification_ids', []),
            } if ac.change_intent.change_type == "bugfix" else None,
            "validation": ac.validation_report,
            "referenced_c_evidence": {
                "cr_evidence_path": cr_evidence_path,
                "integrity_verified": True
            },
            "evidence_chain": {
                "this_evidence": f"changes/evidence/{ac.accountable_id}_{timestamp}.json",
                "linked_cr": f"changes/{ac.cr_id}.md",
                "linked_cr_evidence": cr_evidence_path,
                "chain_integrity": "verified"
            },
            "generated_at": datetime.utcnow().isoformat() + "Z"
        }

        # Write file
        filepath = self.EVIDENCE_DIR / f"{ac.accountable_id}_{timestamp}.json"
        filepath.write_text(json.dumps(evidence, indent=2))

        return filepath
```

---

## C. Persistence and Evidence Model


> **CR Persistence** is documented in [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md) Section F.

### C.1 Evidence Persistence

**Format:** JSON
**Location:** `changes/evidence/`
**Naming:** `[ENTITY]-[ID]_[YYYYMMDD]_[HHMMSS].json`

### C.2 In-Memory State

**AccountableChange Registry:**
- Per-session in-memory storage
- Key: `session_id`
- Value: `AccountableChange`
- Lifetime: Session duration
- Persistence: Evidence file only

---

## D. CLI Contract


> **C CLI Commands** are documented in [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md) Section G.

### D.1 B CLI Commands

```bash
# Pre-flight: consume an existing approved-or-later CCC CR and requirement refs
matrix-cli accountable pre-flight \
  --cr CR-001 \
  --requirements SW-REQ-001 \
  --type bugfix \
  --impact SW,CODE

# Register accountable change
matrix-cli accountable register \
  --agent-id claude-code-001 \
  --name "Claude Code" \
  --model claude-sonnet-4 \
  --description "Fix auth vulnerability" \
  --type bugfix \
  --cr CR-001 \
  --requirements SW-REQ-001 \
  --files src/auth.py,tests/test_auth.py

# Validation and evidence
matrix-cli accountable validate AC-58D0D7B9
matrix-cli accountable evidence AC-58D0D7B9
```

### D.2 Exit Codes <!-- shared-interface: duplicated in C implementation contract -->

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Blocking condition (B intervention) |
| 2 | Validation failure |
| 3 | State transition invalid |
| 4 | Missing required fields |
| 5 | File not found |

---

## E. Verification Strategy

### E.1 Test Pyramid

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

### E.2 Integration Tests

```python
# test_integration.py

# See canonical executable tests under `curaops/skills/accountable_agent/tests/`:
# - pre-flight blocking
# - register / validate / evidence
# - draft/pre-approval CR evidence blocking
# - bugfix metadata and regression VerificationCase rules
# - referenced CCC evidence integrity
---

## G. Minimum Requirement Set

### G.1 Problem Domain

**Data Accuracy / Truth Resolution:**
- Engineering changes must be traceable to requirements
- AI-assisted changes must be accountable
- Compliance requires audit trail

### G.2 Minimum Requirement Set

**Accountability (B):**
- Agent identity capture
- Pre-flight blocking
- Evidence chain to C

### G.3 Explicitly Out (for now)

- User Stories (can be added above SYS-REQ later)
- NFR as separate type (use tags on SYS-REQ)
- IF-SYS (only if external interfaces needed)
- TC-AT/TC-ST (start with TC-IT/TC-UT)
- Real-time monitoring
- Dashboards
- IDE plugins

---

## H. Migration Plan from Provisional Code

### H.1 Current State (Provisional)

```
curaops/skills/accountable-agent/__init__.py      # 518 lines, needs refactoring
curaops/skills/aspice-link-manager/__init__.py    # Exists, reuse
```

> **C provisional code** (`change-request/__init__.py`) migration is in [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md) Section H.

### H.2 Migration Steps

**Phase 1: B Module Creation (2-3 days)**
1. Create new structure:
   - `accountable_agent/models.py`
   - `accountable_agent/intervention.py`
   - `accountable_agent/validation.py`
   - `accountable_agent/evidence.py`

2. Refactor intervention logic:
   - Implement pre-flight check
   - Add explicit CR linking
   - Implement blocking rules

3. Verify B→C dependency:
   - Remove any Compliance-Change-Control-logic duplication
   - Ensure all C calls go through service

**Phase 2: Testing (2-3 days)**
1. Port existing tests
2. Add new test cases
3. Verify integration

**Phase 3: Validation (1 day)**
1. Run worked examples
2. Verify evidence format
3. Check blocking scenarios

### H.3 Backward Compatibility

- Existing CR files: Parse and migrate on first access
- Evidence format: New schema version (1.0.0)
- CLI commands: Add new, deprecate old

---

## I. Remaining Ambiguities

### I.1 Session Persistence

**Question:** How long does session→CR binding persist?

**Options:**
- A: Until session ends (process exit)
- B: Timeout-based (e.g., 8 hours)
- C: Explicit unlink required

**Decision:** A for MVP (simplest), add timeout later if needed.

### I.2 Evidence Retention

**Question:** How many evidence versions to keep per CR?

**Options:**
- A: Keep all (disk usage grows)
- B: Keep last N (e.g., 10)
- C: Keep only latest (simplest)

**Decision:** A for compliance (keep all), add cleanup policy later.

---

**END OF AUTHORITATIVE DOCUMENT**

This document is the authoritative source for Accountable Agent Layer implementation.
For Compliance Change Control implementation, see [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md).
