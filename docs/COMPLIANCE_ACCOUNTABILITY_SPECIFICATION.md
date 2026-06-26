# Operational Specification: Compliance Change Control & B — CORRECTED

> **⚠️ LEGACY WARNING:** This is a mixed-content document. Do not extend. Use authoritative docs instead:
> - For C: COMPLIANCE_CHANGE_CONTROL_*.md
> - For B: ACCOUNTABLE_AGENT_LAYER_*.md


**Status:** DEPRECATED — Do Not Extend  
**Version:** 2.0.0  
**Date:** 2026-04-10  
**Scope:** Compliance-CR Workflow (C) + Accountable Agent Layer (B)
**Replaced by:** COMPLIANCE_CHANGE_CONTROL_PROCESS.md + ACCOUNTABLE_AGENT_LAYER_PROCESS.md

---

## A) Korrektur zur vorherigen Version

**Fehler in vorheriger Version:**
- Verwendete vereinfachte Hierarchie aus Python-Code
- Missed kritische Elemente: NFR, IF-SYS, ADR
- Falscher Link-Typ zwischen SW-ARCH und SW-REQ ("refined_in" statt "constrains")
- Unvollständige Pflichtfelder pro Dokumenttyp

**Korrektur:**
- Vollständige Hierarchie aus Traceability Bible v3.1 TEIL 8 übernommen
- Korrekte Link-Semantik aus TEIL 4
- Vollständige Pflichtfelder pro Artefakttyp

---

## B) Compliance Change Control — Problem, Scope, Workflow Position

### Problem Statement

In regulated development fehlt:
1. **Kanonsicher Einstiegspunkt** — Changes starten inkonsistent
2. **Template Enforcement** — CRs haben unvollständige Pflichtfelder
3. **Automatische Impact-Erfassung** — Manuelle Klassifizierung fehleranfällig
4. **Bidirektionale Traceability** — Links werden nur in eine Richtung gepflegt
5. **Change-Management-Integration** — Keine Verbindung zwischen CR und Git-Commits

### Target Users / Roles

| Role | Permissions |
|------|-------------|
| **Engineer** | Create CR, Edit DRAFT, View all |
| **Team Lead** | Review, Approve, Reject CRs |
| **Quality/Compliance** | Audit, Validate traceability |
| **AI Agent** | Submit CRs (via B), Link implementations |

### Canonical Entry Point

**Der CR ist der EINZIGE gültige Einstieg für Engineering Changes.**

```
Intent (Human or AI)
        ↓
┌─────────────────────┐
│ 1. CREATE CR        │
│    - Hard template  │
│    - Impact auto    │
│    - Quality check  │
└─────────────────────┘
        ↓
┌─────────────────────┐
│ 2. QUALITY GATE     │
│    - Pflichtfelder  │
│    - Link validation│
└─────────────────────┘
        ↓
   APPROVED → IMPLEMENT → CLOSE
```

---

## C) Compliance Change Control — Vollständige Hierarchie & Naming Conventions

### C.1 Artefakt-Hierarchie (aus Traceability Bible v3.1 TEIL 8)

**LINKS (Development) → RECHTS (Verification)**

```
┌─────────────────────┐     ┌─────────────────────┐
│ USER STORIES        │◄════┤ ACCEPTANCE TESTS    │
│ US-[Kategorie][Nr]  │     │ TC-AT-[US-ID]       │
│ z.B. US-B1, US-T1   │     │                     │
└──────────┬──────────┘     └─────────────────────┘
           │ refined_in (1:2-5)
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ SYSTEM REQUIREMENTS │◄════┤ SYSTEM TESTS        │
│ SYS-REQ-[Nr]        │     │ TC-ST-[SYS-REQ-ID]  │
│ z.B. SYS-REQ-001    │     │                     │
└──────────┬──────────┘     └─────────────────────┘
           │ refined_in (1:0-2 SW-ARCH oder 1:1-7 SW-REQ)
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ SOFTWARE ARCHITECT  │◄════┤ INTEGRATION TESTS   │
│ SW-ARCH-[Nr]        │     │ TC-IT-[ARCH/REQ-ID] │
│ z.B. SW-ARCH-002    │     │                     │
└──────────┬──────────┘     └─────────────────────┘
           │ constrains (1:5-10 SW-REQ)
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ SOFTWARE REQUIREMENTS│◄═══┤ INTEGRATION + UNIT  │
│ SW-REQ-[Nr]         │     │ TC-IT + TC-UT       │
│ z.B. SW-REQ-048     │     │                     │
└──────────┬──────────┘     └─────────────────────┘
           │ implemented_in
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ CODE                │◄════┤ UNIT TESTS          │
│ *.py                │     │ TC-UT-[REQ-ID]      │
│                     │     │                     │
└─────────────────────┘     └─────────────────────┘
```

### C.2 Vollständige Artefakt-Liste (TEIL 8)

| Artefakt | Pattern | Location | Pflicht-Links |
|----------|---------|----------|---------------|
| **US** | `US-[Kategorie][Nr]` | `requirements/user_stories/` | `refined_in` → SYS-REQ/NFR |
| **NFR** | `NFR-[Kategorie]-[Nr]` | `requirements/nfr/` | `derived_from` → US |
| **SYS-REQ** | `SYS-REQ-[Nr]` | `requirements/system/` | `derived_from` → US, `refined_in` → SW-ARCH/SW-REQ |
| **IF-SYS** | `IF-SYS-[Nr]` | `requirements/system/` | `derived_from` → SYS-REQ |
| **SW-ARCH** | `SW-ARCH-[Nr]` | `architecture/` | `derived_from` → SYS-REQ, `constrains` → SW-REQ |
| **IF-SW** | `IF-SW-[Nr]` | `requirements/software/` | `derived_from` → SW-ARCH/SW-REQ/IF-SYS |
| **SW-REQ** | `SW-REQ-[Nr]` | `requirements/software/` | `derived_from` → SYS-REQ/SW-ARCH, `implemented_in` → Code |
| **ADR** | `ADR-[Nr]` | `architecture/decisions/` | `triggered_by` → CR (optional) |
| **CR** | `CR-[Nr]` | `changes/` | `impacts` → Requirements |

### C.3 Korrekte Link-Semantik (TEIL 4)

**Bidirektionale Links (Framework-enforced):**

| Forward | Backward | Semantik |
|---------|----------|----------|
| `refined_in` | `derived_from` | Verfeinerung (US→SYS, SYS→SW) |
| `constrains` | `constrained_by` | Architektur-Constraint (SW-ARCH→SW-REQ) |
| `defines` / `requires` | `defined_by` / `required_by` | Interface-Definition |
| `implemented_in` | `implements` | Code-Implementierung |
| `validated_by` | `validates` | Test-Validierung |
| `impacts` | `changed_by` | Change-Impact |

**KRITISCH:** SW-ARCH → SW-REQ nutzt `constrains` NICHT `refined_in`!

### C.4 Change Request (CR) Pflichtfelder (TEIL 8)

```yaml
PFLICHT (Frontmatter):
  id: CR-XXX
  title: String
  status: Enum [SUBMITTED, APPROVED, IN_PROGRESS, IMPLEMENTED, CLOSED, REJECTED]
  created: Date
  
PFLICHT (Content):
  description: String (Was und Warum?)
  impacts:
    level: Liste [US, SYS, ARCH, SW, CODE]  ← AUTO-ERKANNT
    requirements: Liste (IDs)               ← MANUELL oder AUS REFS
    code: Liste (File-Paths)                ← AUTO bei Implementation
    tests: Liste (Test-IDs)                 ← AUTO bei Implementation

OPTIONAL:
  requester: String
  priority: Enum [CRITICAL, HIGH, MEDIUM, LOW]
  approval: Object (Wer, Wann, Kommentar)
  commits: Liste (Git-Commit-SHAs)
  related_adr: ID
```

### C.5 CR-Status-Workflow (TEIL 8)

```
DRAFT (optional)
    ↓ submit
SUBMITTED
    ↓ review
APPROVED ←──→ REJECTED
    ↓ start
IN_PROGRESS
    ↓ complete
IMPLEMENTED
    ↓ verify
CLOSED
```

**Status-Transitionen (harte Regeln):**
- SUBMITTED → APPROVED: Alle Pflichtfelder vorhanden, Quality-Gate bestanden
- SUBMITTED → REJECTED: Jederzeit möglich
- APPROVED → IN_PROGRESS: Implizit bei erstem Commit
- IN_PROGRESS → IMPLEMENTED: Alle Files committed, Tests grün
- IMPLEMENTED → CLOSED: Evidence generated, Traceability verified

### C.6 Impact-Erkennung (aus CR-impacts.level)

**Automatische Level-Erkennung aus requirement_refs:**

| Wenn requirement_refs enthält | Dann impacts.level enthält |
|------------------------------|---------------------------|
| US-XXX | US |
| SYS-REQ-XXX, NFR-XXX | SYS |
| SW-ARCH-XXX | ARCH |
| SW-REQ-XXX, IF-SW-XXX | SW |
| File-Paths (src/, lib/) | CODE |

**Obligatorische Abdeckung:**
- US-Change → Muss SYS-REQ haben (BLOCKING)
- SYS-REQ-Change → Muss SW-REQ haben (BLOCKING)
- SW-REQ-Change → Muss TC-UT haben (WARNING)
- SW-ARCH-Change → Muss SW-REQ haben (WARNING)

---

## D) Compliance Change Control — DoD & Verification

### Definition of Done

1. [ ] CR-Erstellung mit Template-Enforcement
2. [ ] Automatische impacts.level Erkennung
3. [ ] Pflichtfeld-Validierung (harte Regeln)
4. [ ] Bidirektionale Link-Erstellung
5. [ ] Status-Workflow implementiert
6. [ ] Evidence-Generation (JSON + Markdown)
7. [ ] CLI: create, approve, status, evidence, validate
8. [ ] Alle Artefakt-Typen aus TEIL 8 unterstützt

### Verification Criteria

**Unit Tests:**
- Template-Validierung (Pflichtfelder)
- Level-Erkennung (US, SYS, ARCH, SW, CODE)
- Link-Semantik (refined_in↔derived_from, constrains↔constrained_by)
- Status-Transitionen (gültig/ungültig)

**Integration:**
- End-to-End: Create → Submit → Approve → Implement → Evidence
- Bidirektionale Links verifiziert

---

## E) Accountable Agent Layer — Intervention, Accountability, Fail Conditions

### Was B auf C aufbaut

| Feature | C (Base) | B (Addition) |
|---------|----------|--------------|
| CR Workflow | ✅ | Nutzt C |
| Agent Attribution | ❌ | ✅ Actor/Model/Tools |
| Pre-flight Enforcement | ❌ | ✅ Block vor Arbeit |
| Accountability Validation | ❌ | ✅ Mandatory links |
| Active Intervention | ❌ | ✅ Block/Fail |

### Accountable-Agent-Layer-Interventionspunkte

```
Intent (AI-Assisted)
        ↓
┌─────────────────────────┐
│ 1. PRE-FLIGHT CHECK     │ ← B INTERVENTION
│    - CR linked?         │
│    - CR APPROVED?       │
│    → BLOCK if no        │
└─────────────────────────┘
        ↓ (if pass)
┌─────────────────────────┐
│ 2. CAPTURE              │ ← B INTERVENTION
│    - Tools used         │
│    - Files affected     │
└─────────────────────────┘
        ↓
┌─────────────────────────┐
│ 3. VALIDATE             │ ← B INTERVENTION
│    - Mandatory links    │
│    - Hierarchy check    │
│    → BLOCK if fail      │
└─────────────────────────┘
        ↓
┌─────────────────────────┐
│ 4. EVIDENCE             │ ← B INTERVENTION
│    - Generate AC-evidence│
│    - Reference CR-ev    │
└─────────────────────────┘
```

### Mandatory Accountability Data

**AgentContext:**
```yaml
agent_id: String        # z.B. "claude-code-001"
agent_name: String      # z.B. "Claude Code"
model: String           # z.B. "claude-sonnet-4"
tools_used: [String]    # z.B. ["file_edit", "terminal"]
session_id: String      # Reference zu Session Manager
```

**ChangeIntent:**
```yaml
description: String     # Was wird geändert?
change_type: Enum       # feature, bugfix, refactor, test, docs
files_affected: [String] # Auto-erfasst
estimated_impact: Enum  # CRITICAL, HIGH, MEDIUM, LOW
```

**AccountabilityLinks (STRICT MODE):**
```yaml
cr_id: String           # MUSS existieren, Status APPROVED
requirement_refs: [String]  # Min 1, valide IDs
```

### Block/Fail Conditions

**HARD BLOCK (Exit 1):**
```python
if not cr_id:
    BLOCK("Missing cr_id (mandatory in strict mode)")
    
if cr.status != "APPROVED":
    BLOCK(f"CR-{cr_id} status is {cr.status}, must be APPROVED")
    
if not requirement_refs or len(refs) == 0:
    BLOCK("Missing requirement_refs (mandatory in strict mode)")
    
if any(not valid_id_pattern(r) for r in refs):
    BLOCK(f"Invalid requirement ID format: {invalid_ids}")
    
# HIERARCHY CHECK
if "US" in levels and "SYS-REQ" not in levels:
    BLOCK("US-level change must have SYS-REQ linkage")
```

**WARNING (Allow with status):**
```python
if requirement_file_not_found:
    WARN("Requirement files not found (may be created later)")
    
if derivation_obligation_unaddressed:
    WARN("Derivation obligations detected but not addressed")
```

---

## F) Accountable Agent Layer — Evidence Chain, DoD, Verification

### Evidence Chain

**Accountability Evidence (B):**
```json
{
  "accountable_change": {
    "accountable_id": "AC-58D0D7B9",
    "agent_context": { ... },
    "change_intent": { ... },
    "accountability_links": {
      "cr_id": "CR-001",
      "requirement_refs": ["SW-REQ-001"]
    },
    "status": "validated"
  },
  "validation": { "valid": true, "issues": [] },
  "referenced_c_evidence": {
    "cr_evidence_path": "changes/evidence/CR-001_20260410_143000.json",
    "cr_evidence_hash": "sha256:..."
  },
  "evidence_chain": {
    "this_evidence": "changes/evidence/AC-58D0D7B9_20260410_100500.json",
    "linked_cr": "changes/CR-001.md",
    "chain_integrity": "verified"
  }
}
```

### Accountable-Agent-Layer-DoD

1. [ ] Pre-flight blockt ohne APPROVED CR
2. [ ] Strict mode blockt missing cr_id
3. [ ] Strict mode blockt missing requirements
4. [ ] Hierarchy check: US ohne SYS-REQ blockt
5. [ ] AgentContext erfasst alle Felder
6. [ ] Evidence generated mit CR-Referenz
7. [ ] Accountable Agent Layer nutzt Compliance-Change-Control-Services (keine Duplikation)

### Accountable-Agent-Layer-Verification

- Pre-flight Test: mit/ohne CR
- Strict Mode Test: mit/ohne Links
- Hierarchy Test: US→SYS-REQ Pfad
- Dependency Check: B importiert C

---

## G) Framework Assets Used (PRECIS)

| Asset | Quelle | Nutzung |
|-------|--------|---------|
| **Artefakt-Hierarchie** | `docs/guides/curaops_v31_traceability.md:106-161` | V-Modell Struktur |
| **Pflichtfelder US** | `docs/guides/curaops_v31_traceability.md:789-813` | US-Template |
| **Pflichtfelder SYS-REQ** | `docs/guides/curaops_v31_traceability.md:815-837` | SYS-REQ-Template |
| **Pflichtfelder SW-ARCH** | `docs/guides/curaops_v31_traceability.md:874-896` | SW-ARCH-Template |
| **Pflichtfelder SW-REQ** | `docs/guides/curaops_v31_traceability.md:914-930` | SW-REQ-Template |
| **Pflichtfelder CR** | `docs/guides/curaops_v31_traceability.md:950-970` | CR-Template |
| **Link-Semantik** | `docs/guides/curaops_v31_traceability.md:411-443` | Bidirektionale Links |
| **DOC_TYPES** | `src/compliance/traceability_validation_service.py:67-77` | ID-Patterns |

---

## H) Unresolved Decisions (max 2)

1. **Session-CR Binding:**
   - A: Explizit `--cr` Argument (Default)
   - B: Auto-binding via Session Manager

2. **AI Quality Check:**
   - A: Rule-based only (Default)
   - B: Rule-based + LLM suggestions

---

**END OF CORRECTED SPECIFICATION**
