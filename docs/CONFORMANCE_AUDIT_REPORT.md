# Conformance Audit Report: C/B Code vs. Authoritative Documentation Baseline

**Baseline commit:** `0c179ed` — docs(compliance): freeze authoritative change-control and accountability baseline  
**Audit date:** 2026-04-19  
**Auditor:** Hermes Agent (strict implementation auditor)  
**Scope:** All C/B Python code in `curaops/skills/` and `curaops/cli/` vs. 9 authoritative docs at v2.0.0+

---

## A) Authoritative Source-of-Truth Used

| Doc | Version | Status |
|-----|---------|--------|
| COMPLIANCE_CHANGE_CONTROL_RULES.md | v2.0.0 | AUTHORITATIVE |
| COMPLIANCE_CHANGE_CONTROL_PROCESS.md | v2.0.0 | AUTHORITATIVE |
| COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md | v2.0.0 | AUTHORITATIVE |
| COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md | v2.0.0 | AUTHORITATIVE |
| ACCOUNTABLE_AGENT_LAYER_RULES.md | v2.0.0 | AUTHORITATIVE |
| ACCOUNTABLE_AGENT_LAYER_PROCESS.md | v2.0.0 | AUTHORITATIVE |
| ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md | v2.0.0 | AUTHORITATIVE |
| ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md | v2.0.0 | AUTHORITATIVE |
| COMPLIANCE_ACCOUNTABILITY_INDEX.md | v4.0.0 | AUTHORITATIVE |

---

## B) Exact Code Locations Found for C (Compliance Change Control)

| File | Role | Git Status | Lines |
|------|------|------------|-------|
| `curaops/skills/change-request/__init__.py` | Core service + CLI wrappers | Committed (`64afa19`) | ~695 |
| `curaops/skills/change-request/tests/test_change_request.py` | Tests (17 tests) | Committed | ~190 |
| `curaops/skills/aspice-link-manager/__init__.py` | Traceability validation (dep of C) | Committed | ~500 |
| `curaops/skills/aspice-link-manager/tests/test_aspice_link_manager.py` | Tests | Committed | exists |
| `curaops/cli/commands/skills.py` | CLI wiring (cr_app) | Committed | ~800 |
| `curaops/cli/main.py` | CLI entry point | Committed | ~72 |
| `curaops/skills/change_request` → `change-request` | Symlink | Committed (`8c4c9da`) | alias |

**No other C code exists.** No `VerificationService`, no `VerificationCase` module, no `CRStatus` enum file, no `VerificationType` enum file.

---

## C) Exact Code Locations Found for B (Accountable Agent Layer)

| File | Role | Git Status | Lines |
|------|------|------------|-------|
| `curaops/skills/accountable-agent/__init__.py` | Core service + CLI wrappers | Committed (`0feaffb`) | ~500 |
| `curaops/skills/accountable-agent/tests/test_accountable_agent.py` | Tests (15 tests) | Committed | ~280 |
| `curaops/skills/accountable_agent` → `accountable-agent` | Symlink | Committed (`8c4c9da`) | alias |
| `curaops/cli/commands/skills.py` (lines 664-786) | CLI wiring (accountable_app) | Committed | ~120 |

**No `ACEvidenceGenerator` module exists.** No `pre_flight_check` implementation.

---

## D) Conformance Table: Doc Contract vs. Actual Code

### D.1 ChangeRequest Fields (C-RULES §5, C-ARCHITECTURE §C)

| Field (Doc) | Required by Doc | In Code | Status |
|-------------|----------------|---------|--------|
| `id` (CR-XXX) | ✓ | ✓ (generated) | ✅ CONFORMS |
| `title` | ✓ (10-80 chars) | ✓ (no length validation) | ⚠️ PARTIAL — no min/max enforcement |
| `status` | ✓ (9-state enum) | ✓ (6 states as strings) | ❌ CONTRADICTED — code has 6 states, docs require 9 |
| `created` | ✓ | ✓ | ✅ CONFORMS |
| `requester` | ✓ | ✗ (hardcoded "(TBD)") | ❌ MISSING |
| `problem` | ✓ (min 50 chars) | ✗ | ❌ MISSING |
| `justification` | ✓ (min 20 chars) | ✗ | ❌ MISSING |
| `change_type` | ✓ (enum, required at SUBMITTED) | ✗ | ❌ MISSING from CR model |
| `requirement_linkage_type` | ✓ (required when bugfix) | ✗ | ❌ MISSING |
| `impact_level` | ✓ (auto-detected) | ✗ | ❌ MISSING |
| `requirement_refs` | ✓ (min 1) | ✓ (optional, no min-1 enforcement) | ⚠️ PARTIAL — allows empty |
| `safety_impact` | ✓ | ✗ | ❌ MISSING |
| `reviewer` | ✓ (at APPROVED) | ✗ | ❌ MISSING |
| `approval_date` | ✓ (at APPROVED) | ✓ (auto-set) | ⚠️ PARTIAL — auto, no reviewer |
| `affected_files` | ✓ (at IMPLEMENTED) | ✗ | ❌ MISSING |
| `affected_verifications` | ✓ (at IMPLEMENTED) | ✗ | ❌ MISSING |
| `commits` | ✓ (at IMPLEMENTED) | ✗ | ❌ MISSING |
| `evidence_refs` | ✓ (at VERIFIED) | ✗ | ❌ MISSING |
| `is_emergency` | ✓ | ✗ | ❌ MISSING |
| `incident_id` | ✓ (for EMERGENCY) | ✗ | ❌ MISSING |

**Score: 4/20 fields fully conform, 3 partial, 13 missing entirely.**

### D.2 CR State Machine (C-PROCESS §C.2)

| Doc State | In Code | Status |
|-----------|---------|--------|
| DRAFT | ✗ | ❌ MISSING |
| SUBMITTED | ✓ | ✅ EXISTS |
| APPROVED | ✓ | ✅ EXISTS |
| IN_PROGRESS | ✓ | ✅ EXISTS |
| IMPLEMENTED | ✓ | ✅ EXISTS |
| VERIFIED | ✗ | ❌ MISSING |
| CLOSED | ✓ | ✅ EXISTS |
| REJECTED | ✓ | ✅ EXISTS |
| EMERGENCY | ✗ | ❌ MISSING |

**Code state machine: 6/9 states. Missing: DRAFT, VERIFIED, EMERGENCY.**

**Code transition matrix:** SUBMITTED→APPROVED→IN_PROGRESS→IMPLEMENTED→CLOSED with REJECTED as escape. This matches the old v1 model, NOT the v2.0.0 doc.

**Doc transition matrix:** DRAFT→SUBMITTED→APPROVED→IN_PROGRESS→IMPLEMENTED→VERIFIED→CLOSED with REJECTED and EMERGENCY as additional states. R→D (revise), E→S (retro_submit). **Zero of these additional transitions exist in code.**

### D.3 VerificationCase / VerificationType (C-RULES §2.3, C-ARCHITECTURE)

| Component | In Code | Status |
|-----------|---------|--------|
| `VerificationType` enum | ✗ | ❌ MISSING ENTIRELY |
| `VerificationStatus` enum | ✗ | ❌ MISSING ENTIRELY |
| `VerificationCase` dataclass | ✗ | ❌ MISSING ENTIRELY |
| `VerificationService` class | ✗ | ❌ MISSING ENTIRELY |
| TC-{TYPE}-{Nr} ID pattern | ✗ | ❌ MISSING |
| VerificationCase storage (verification/) | ✗ | ❌ MISSING |

**Score: 0/6 — entire verification layer is absent from code.**

### D.4 Bugfix Policy (C-RULES §9)

| Rule | In Code | Status |
|------|---------|--------|
| `change_type = "bugfix"` required at SUBMITTED | ✗ (no `change_type` on CR) | ❌ MISSING |
| `requirement_linkage_type` mandatory for bugfix | ✗ | ❌ MISSING |
| SW-REQ mandatory for functional bugfix | ✗ (no enforcement) | ❌ MISSING |
| Emergency CR (24h rule, incident_id) | ✗ | ❌ MISSING |
| Bugfix blocking rules (C-RULES §9.6) | ✗ | ❌ MISSING |
| Bugfix warning rules (C-RULES §9.6 WARN) | ✗ | ❌ MISSING |
| root_cause_category documentation | ✗ | ❌ MISSING |
| Bugfix decision table (C-RULES §10) | ✗ | ❌ MISSING |

**Score: 0/8 — no bugfix-specific logic exists in code.**

**Note:** `change_type` exists on B's `ChangeIntent` dataclass as a free-text field, but NOT on C's `ChangeRequest`. The doc contract requires it on the CR at SUBMITTED state.

### D.5 Evidence Schema (C-IMPLEMENTATION_CONTRACT, C-ARCHITECTURE)

| Aspect | Doc Contract | Code Reality | Status |
|--------|-------------|--------------|--------|
| Schema version | `CCC-1.1.0` | `compliance-cr-v1.0` | ❌ WRONG VERSION |
| Schema structure | See C-IMPLEMENTATION_CONTRACT §4 | Flat dict with 8 keys | ⚠️ PARTIAL |
| `change_type` in evidence | Required | ✗ | ❌ MISSING |
| `requirement_linkage_type` in evidence | Required (when bugfix) | ✗ | ❌ MISSING |
| `affected_verifications` in evidence | Required | ✗ | ❌ MISSING |
| `root_cause_category` in evidence | Required (when bugfix) | ✗ | ❌ MISSING |
| Evidence file location | `changes/evidence/CR-XXX_evidence.json` | Same | ✅ CONFORMS |
| Evidence format | JSON + Markdown | JSON + Markdown | ✅ CONFORMS |

### D.6 Blocking Rules (B-RULES §3.1)

| Blocking Condition (Doc) | In Code | Status |
|--------------------------|---------|--------|
| No CR linked → BLOCK | ✓ (strict mode raises MissingMandatoryLinkError) | ✅ EXISTS |
| CR.status != APPROVED → BLOCK | ✗ (no status check in register) | ❌ MISSING |
| No requirement_refs → BLOCK | ✓ (strict mode) | ✅ EXISTS |
| Invalid ID pattern → BLOCK | ✗ | ❌ MISSING |
| SYS-impact without SYS-REQ → BLOCK | ✗ | ❌ MISSING |
| ARCH-impact without SW-ARCH → BLOCK | ✗ | ❌ MISSING |
| Bugfix without SW-REQ → BLOCK | ✗ | ❌ MISSING |
| Bugfix with unapproved new_ref → BLOCK | ✗ | ❌ MISSING |
| Bugfix at IMPLEMENTED without verifications → BLOCK | ✗ | ❌ MISSING |

**Score: 2/9 blocking rules implemented.** Only basic "missing CR/refs" blocking exists. No doc-specified condition-based blocking.

### D.7 AccountableChange Fields (B-ARCHITECTURE §C)

| Field (Doc) | In Code | Status |
|-------------|---------|--------|
| `accountable_id` (AC-XXXXXXXX) | ✓ | ✅ CONFORMS |
| `agent_context` (AgentContext) | ✓ | ✅ CONFORMS |
| `change_intent` (ChangeIntent) | ✓ | ✅ CONFORMS |
| `cr_id` (str, MUST link to C) | ✓ (Optional — allows None) | ⚠️ PARTIAL — doc says `str`, code says `Optional[str]` |
| `requirement_refs` (min 1) | ✓ | ✅ CONFORMS |
| `status` (pending/linked/validated/blocked) | ✓ | ✅ CONFORMS |
| `created_at` | ✓ | ✅ CONFORMS |
| `evidence_path` | ✓ | ✅ CONFORMS |
| `block_reason` | ✓ | ✅ CONFORMS |
| `change_type` | ✗ | ❌ MISSING — doc requires, code omits |
| `requirement_linkage_type` | ✗ | ❌ MISSING — doc requires, code omits |
| `root_cause_category` | ✗ | ❌ MISSING — doc requires, code omits |
| `regression_verification_ids` | ✗ | ❌ MISSING — doc requires, code omits |

**Score: 8/13 — basic B dataclass conforms, but 4 bugfix-context fields from doc are absent.**

### D.8 B-on-C Dependency (B-RULES §7)

| Aspect | Doc Contract | Code Reality | Status |
|--------|-------------|--------------|--------|
| Import ChangeRequestService from C | ✓ (via importlib hack) | ⚠️ WORKS but fragile |
| Import generate_cr_evidence from C | ✓ | ✅ CONFORMS |
| Import validate_cr_traceability from C | ✓ | ✅ CONFORMS |
| B consumes change_type from C CR | ✗ (reads from ChangeIntent, not CR) | ❌ WRONG SOURCE |
| B enforces C bugfix rules at pre-flight | ✗ (no pre_flight_check exists) | ❌ MISSING |
| B does NOT invent separate bugfix semantics | ✗ (ChangeIntent.change_type is free-text) | ⚠️ PARTIAL — B has its own change_type on ChangeIntent, doc says it should come from C's CR |

### D.9 `pre_flight_check` (B-RULES §7, B-ARCHITECTURE)

| Method | Doc Contract | In Code | Status |
|--------|-------------|---------|--------|
| `pre_flight_check(session_id) → Bool` | Required | ✗ | ❌ MISSING ENTIRELY |

### D.10 ACEvidenceGenerator (B-IMPLEMENTATION)

| Component | Doc Contract | In Code | Status |
|-----------|-------------|---------|--------|
| `ACEvidenceGenerator` class | Required | ✗ | ❌ MISSING — evidence generation is inline in service |

---

## E) Repo Hygiene Findings

### E.1 Symlink-Based Import Workaround
- `curaops/skills/change_request` → `change-request` (symlink)
- `curaops/skills/accountable_agent` → `accountable-agent` (symlink)
- `curaops/skills/aspice_link_manager` → `aspice-link-manager` (symlink)
- **Risk:** Symlinks are OS-dependent, may break on Windows or in Docker. Works on Linux/macOS.

### E.2 `importlib.util` Hack in B Code
- B imports C code via `importlib.util.spec_from_file_location()` with hardcoded relative paths
- This bypasses Python package resolution entirely
- **Risk:** Fragile to directory restructuring, no IDE support, no mypy/pyright analysis

### E.3 `__pycache__` Directories Committed
- `curaops/skills/change-request/__pycache__/` present in working tree
- Should be in `.gitignore`

### E.4 In-Memory-Only Storage
- B's `AccountableAgentService._accountable_changes` is an in-memory dict
- No persistence for accountable changes across sessions
- Doc does not specify persistence mechanism but implies audit trail durability

### E.5 Test Infrastructure
- Tests pass (17 C + 15 B = 32/32 pass)
- Tests use `/tmp` directly (not isolated via tmp_path fixture)
- C tests import via `sys.path.insert(0, ...)` — non-standard
- B tests use `importlib.util` — mirrors the hack in production code

### E.6 Git History
- C code: committed in `64afa19` (feat context-c)
- B code: committed in `0feaffb` (feat context-b)
- CLI wiring fix: `8c4c9da` (symlinks for hyphenated dirs)
- Docs baseline: `0c179ed` (freeze)
- **Code predates docs by several commits** — code was written before doc contracts were finalized

---

## F) Top Contradictions/Blockers Before Serious Implementation

### F.1 HARD BLOCKERS (must fix before any implementation)

| # | Blocker | Impact |
|---|---------|--------|
| F.1.1 | **CR state machine: 6 vs 9 states.** Missing DRAFT, VERIFIED, EMERGENCY. The entire VERIFIED gate (I→V→C) is absent. Without VERIFIED, the doc's evidence-before-close requirement is unenforceable. | Critical |
| F.1.2 | **VerificationCase system: 0% exists.** No VerificationType, VerificationCase, VerificationService, TC-* ID pattern, or verification storage. This is the core of the doc's quality gate model. | Critical |
| F.1.3 | **change_type field absent from CR.** The doc requires `change_type` as a mandatory field at SUBMITTED on the ChangeRequest entity. Code has no such field. B has it on ChangeIntent, but C doesn't. | Critical |
| F.1.4 | **Bugfix policy: 0% implemented.** None of the 6 bugfix categories, blocking rules, warning rules, linkage types, or emergency procedures exist in code. | Critical |
| F.1.5 | **Evidence schema version mismatch.** Code emits `compliance-cr-v1.0`, docs require `CCC-1.1.0`. Structure is also wrong (missing 4+ mandatory fields). | High |
| F.1.6 | **pre_flight_check: not implemented.** B-RULES §3 specifies this as the primary blocking gate. Code has no equivalent. | High |

### F.2 STRUCTURAL MISMATCHES (must realign)

| # | Mismatch | Impact |
|---|----------|--------|
| F.2.1 | **CR is flat Markdown, not a dataclass.** Doc specifies `ChangeRequest` as a typed dataclass with enums (`CRStatus`, `ImpactLevel`, `SafetyImpact`). Code uses regex-parsed Markdown strings. | High |
| F.2.2 | **B's AccountableChange missing 4 bugfix-context fields.** Doc specifies `change_type`, `requirement_linkage_type`, `root_cause_category`, `regression_verification_ids`. Code has none. | High |
| F.2.3 | **No requirement validation on submit.** Doc requires min-1 requirement_refs and specific impact checks. Code accepts empty refs. | Medium |
| F.2.4 | **No role-based gating.** Doc specifies Architect, QA Lead, Compliance Officer roles for certain transitions. Code has no role concept. | Medium |

### F.3 Earlier Overstated Claims

| Claim | Reality |
|-------|---------|
| "Implemented bugfix blocking" (commit `0feaffb`) | No bugfix-specific logic exists. B blocks on missing CR/refs generically, not on bugfix conditions. |
| "Evidence generation" (commit `64afa19`) | Basic evidence file exists but misses 5+ mandatory fields, wrong schema version, no verification data. |
| "Traceability validation" (commit `64afa19`) | Only checks if requirement ID exists in ASPICE docs — does not validate VerificationCase linkage, type matching, or bidirectional consistency per doc spec. |
| "CR driven development" | CR exists but as a flat Markdown file, not a typed dataclass. No status-dependent field validation. No mandatory fields enforcement. |
| "Compliance ready" | 13/20 CR fields missing, 0/9 VerificationCase components, 0/8 bugfix rules, wrong evidence schema. |

---

## G) Verdict

### **No usable implementation exists against the v2.0.0 baseline.**

**Rationale:**

The existing code is a v0.x prototype that predates the authoritative documentation. It demonstrates basic CRUD for Change Requests (Markdown-based) and a thin Accountable Agent wrapper with in-memory storage. However:

1. **Zero VerificationCase infrastructure** — the core of the v2.0.0 quality gate model
2. **6/9 CR states** — missing DRAFT, VERIFIED, EMERGENCY
3. **13/20 CR fields missing** — no `change_type`, no `requirement_linkage_type`, no `impact_level`, no `affected_verifications`
4. **0/8 bugfix rules** — the entire §9 policy is unimplemented
5. **Evidence schema wrong** — version `compliance-cr-v1.0` vs `CCC-1.1.0`, missing fields
6. **0/9 doc-specified blocking conditions** in B (only 2 generic ones exist)
7. **`pre_flight_check` absent** — the primary intervention point does not exist
8. **`ACEvidenceGenerator` absent** — evidence generation is inline, not structured per B-IMPLEMENTATION

The code is **not partially conformant** — it is **architecturally incompatible** with the doc baseline. The docs define a typed dataclass model with enums and a 9-state machine; the code uses regex-parsed Markdown with a 6-state string model. These cannot be reconciled by patching — a rewrite of both C and B core services is required.

**The correct path is:**
1. Implement C core first (ChangeRequest dataclass, CRStatus enum, 9-state machine, VerificationCase system, bugfix rules)
2. Implement B on top of new C (blocking rules from doc, pre_flight_check, ACEvidenceGenerator, bugfix-context fields)
3. Update CLI wiring to expose new states and fields
4. Write tests against doc contracts, not against current code behavior

**Existing tests (32/32 passing) test the old prototype, NOT the doc contracts. They must be replaced.**

---

*END OF CONFORMANCE AUDIT REPORT*
