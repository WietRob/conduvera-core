# Compliance Change Control / Accountable Agent Layer Regelwerk — Verbindliche Spezifikation

> **⚠️ LEGACY WARNING:** This is a mixed-content document. Do not extend. Use authoritative docs instead:
> - For C: COMPLIANCE_CHANGE_CONTROL_*.md
> - For B: ACCOUNTABLE_AGENT_LAYER_*.md


**Status:** DEPRECATED — Do Not Extend  
**Version:** 1.0.0  
**Date:** 2026-04-10  
**Gültig für:** Compliance Change Control (Compliance-CR) + Accountable Agent Layer (Accountable Agent)
**Replaced by:** COMPLIANCE_CHANGE_CONTROL_RULES.md + ACCOUNTABLE_AGENT_LAYER_RULES.md

---

## 1. Pragmatische ASPICE-Hierarchie (verbindlich)

```
CR
└── SYS-REQ (nur bei Systemwirkung/Safety/Regulatory)
    └── SW-REQ (Pflicht für fast jeden Software-Change)
        ├── SW-ARCH (nur bei Struktur/Interfaces)
        └── CODE (Implementierung — verlinktes Artefakt)
            └── TEST/EVIDENCE (Verifikation — Pflicht vor Close)
```

**Was NICHT Pflicht ist:**
- User Stories (optional, oberhalb von SYS-REQ erlaubt, aber nicht kanonisch)
- NFR als eigene Hierarchie (wird als Tag auf SYS-REQ/SW-REQ modelliert)
- IF-SYS (optional, nur bei externen Schnittstellen)

---

## 2. Wann welcher Level Pflicht ist

### 2.1 SYS-REQ Pflicht wenn:
- [ ] Extern sichtbares Verhalten geändert wird
- [ ] Safety-relevante Wirkung besteht
- [ ] Regulatorische Anforderungen berührt werden (GDPR, ISO, etc.)
- [ ] Systemweite Schnittstellen verändert werden
- [ ] Außenschnittstellen (APIs, Hardware) betroffen sind

**Wenn SYS-REQ Pflicht:**
- CR muss auf SYS-REQ verlinken
- SW-REQ muss von SYS-REQ ableiten (`derived_from`)

### 2.2 SW-REQ Pflicht wenn:
- [ ] Softwareverhalten geändert wird
- [ ] Logik/Funktion geändert wird
- [ ] Datenverarbeitung geändert wird
- [ ] Fehlverhalten behoben wird, das fachlich relevant ist

**HARTE REGEL:**
> Ohne SW-REF oder begründete Ausnahme kein fachlicher Software-Change.

**Wenn SW-REQ Pflicht:**
- CR muss auf SW-REQ verlinken
- Code muss auf SW-REQ verlinken (`implements`)
- Test muss auf SW-REQ verlinken (`validates`)

### 2.3 SW-ARCH Pflicht wenn:
- [ ] Komponentenverantwortung verschoben wird
- [ ] Interfaces geändert werden
- [ ] Datenmodell/Funktionsschnittstellen geändert werden
- [ ] Sicherheitsmechanismen strukturell angepasst werden
- [ ] Technische Architekturentscheidung betroffen ist

**Wenn SW-ARCH Pflicht:**
- CR muss auf SW-ARCH verlinken
- SW-REQ muss von SW-ARCH constrainiert sein (`constrained_by`)
- ADR sollte erstellt werden

### 2.4 CODE (Pflicht-Verlinkung, kein Requirement)
- Jede Code-Änderung muss auf SW-REQ verlinken
- Kein "freier" Code ohne Requirement-Bezug

### 2.5 TEST/EVIDENCE Pflicht vor Close
- [ ] Mindestens ein Test pro SW-REQ
- [ ] Test-Ergebnis dokumentiert
- [ ] Evidence-Datei generiert

---

## 3. Parent/Child-Regeln pro Ebene

### 3.1 CR → Requirements
- CR hat `impacts: [Requirement-IDs]`
- Requirements haben `changed_by: [CR-ID]` (auto)

### 3.2 SYS-REQ → SW-REQ
- Pflicht: SYS-REQ hat `refined_in: [SW-REQ-IDs]`
- Pflicht: SW-REQ hat `derived_from: [SYS-REQ-ID]`
- Kardinalität: 1 SYS-REQ → 1-7 SW-REQs

### 3.3 SW-REQ → CODE
- Pflicht: SW-REQ hat `implemented_in: [File-Paths]`
- Pflicht: Code hat `implements: [SW-REQ-ID]` (in Docstring/Header)
- Kardinalität: 1 SW-REQ → 1-n Files

### 3.4 SW-REQ → TEST
- Pflicht: SW-REQ hat `validated_by: [TC-IDs]`
- Pflicht: Test hat `validates: [SW-REQ-ID]`
- Kardinalität: Mindestens 1 Test pro SW-REQ

### 3.5 SW-ARCH → SW-REQ (Constraint)
- Wenn SW-ARCH existiert: SW-ARCH hat `constrains: [SW-REQ-IDs]`
- SW-REQ hat `constrained_by: [SW-ARCH-ID]`

---

## 4. Minimale Pflichtfelder pro Requirement

### 4.1 SYS-REQ
```yaml
id: SYS-REQ-[Nr]                    # Pflicht
title: String                       # Pflicht
type: system_requirement            # Pflicht
domain: String                      # Pflicht
status: Enum [DRAFT, APPROVED, IMPLEMENTED, VERIFIED]  # Pflicht
description: String (normativer Satz)  # Pflicht (MUSS/SOLL/KANN)
derived_from: ID [US-ID oder CR-ID]   # Pflicht (Quelle)
refined_in: [SW-REQ-IDs]            # Pflicht (Child-Links)
validated_by: [TC-ST-IDs]           # Pflicht (Test-Links)
acceptance_criteria: [String]       # Pflicht (min 1)
safety_tag: Enum [SAFETY-CRITICAL, SAFETY-RELATED, NONE]  # Pflicht
compliance_tags: [GDPR, ISO27001, etc.]  # Optional
owner: String                       # Pflicht
```

### 4.2 SW-REQ
```yaml
id: SW-REQ-[Nr]                     # Pflicht
title: String                       # Pflicht
type: software_requirement          # Pflicht
domain: String                      # Pflicht
status: Enum [DRAFT, APPROVED, IMPLEMENTED, VERIFIED]  # Pflicht
description: String (normativer Satz)  # Pflicht
derived_from: ID [SYS-REQ-ID]       # Pflicht (Parent)
constrained_by: [SW-ARCH-IDs]       # Pflicht wenn ARCH existiert
implemented_in: [File-Paths]        # Pflicht (nach Implementation)
validated_by: [TC-IT-IDs, TC-UT-IDs]  # Pflicht (min 1 IT + 1 UT)
acceptance_criteria: [String]       # Pflicht (min 1)
safety_tag: Enum [SAFETY-CRITICAL, SAFETY-RELATED, NONE]  # Pflicht
compliance_tags: [GDPR, etc.]       # Optional
component: String                   # Pflicht (Modul/Class-Name)
owner: String                       # Pflicht
```

### 4.3 SW-ARCH
```yaml
id: SW-ARCH-[Nr]                    # Pflicht
title: String                       # Pflicht
type: architecture                  # Pflicht
domain: String                      # Pflicht
status: Enum [DRAFT, APPROVED, IMPLEMENTED]  # Pflicht
description: String                 # Pflicht (Pattern/Constraint)
derived_from: ID [SYS-REQ-ID]       # Pflicht (Quelle)
constrains: [SW-REQ-IDs]            # Pflicht (constrained Requirements)
validated_by: [TC-IT-IDs]           # Pflicht (Compliance Tests)
acceptance_criteria: [String]       # Pflicht (min 1)
pattern_name: String                # Optional (z.B. "Protocol-based")
owner: String                       # Pflicht
```

---

## 5. Minimale Pflichtfelder pro CR

```yaml
id: CR-[Nr]                         # Auto-generiert
title: String                       # Pflicht (max 80 chars)
status: Enum [SUBMITTED, APPROVED, IN_PROGRESS, IMPLEMENTED, CLOSED, REJECTED]  # Pflicht
created: Date                       # Auto
requester: String                   # Pflicht

problem: String                     # Pflicht (Was ist das Problem?)
justification: String               # Pflicht (Warum nötig?)

impact_level: Enum [SYS, SW-REQ, SW-ARCH, CODE]  # Pflicht (auto-erkannt)
requirement_refs: [IDs]             # Pflicht (min 1)

affected_files: [File-Paths]        # Pflicht (bei IMPLEMENTED)
affected_tests: [TC-IDs]            # Pflicht (bei IMPLEMENTED)

parent_impact: Bool                 # Pflicht (Ändert Parent-Requirement?)
child_derivations: [IDs]            # Pflicht wenn Parent-Impact (neue Children)

reviewer: String                    # Pflicht (bei APPROVED)
approval_date: Date                 # Pflicht (bei APPROVED)
approval_comment: String            # Optional

evidence_refs: [File-Paths]         # Pflicht (bei CLOSED)
commits: [SHA]                      # Pflicht (bei IMPLEMENTED)

safety_impact: Enum [NONE, LOW, MEDIUM, HIGH]  # Pflicht
compliance_impact: [Tags]           # Pflicht wenn Regulatory
```

---

## 6. Harte Regeln (verbindlich)

### Regel 1: CR-Pflicht
> **Ohne CR kein regulärer Change.**

- Jeder Engineering-Change startet mit CR
- Keine Code-Änderungen ohne CR (außer Emergency-Fix mit nachgelagerter CR)
- Accountable Agent Layer blockiert AI-Changes ohne CR

### Regel 2: SW-REQ-Pflicht
> **Ohne SW-REQ oder begründete Ausnahme kein fachlicher Software-Change.**

- Jede Software-Änderung muss auf SW-REQ verlinken
- Ausnahme erfordert Team-Lead-Approval + Dokumentation
- Accountable Agent Layer blockiert bei fehlender SW-REQ-Referenz

### Regel 3: ARCH-Pflicht bei Struktur
> **Wenn Architektur betroffen ist, muss SW-ARCH mit rein.**

- Interface-Änderungen → SW-ARCH Pflicht
- Komponentenverschiebung → SW-ARCH Pflicht
- Safety-Mechanismus-Änderung → SW-ARCH Pflicht
- Accountable Agent Layer warnt wenn ARCH-Impact erkannt aber kein SW-ARCH verlinkt

### Regel 4: SYS-Pflicht bei Systemwirkung
> **Wenn Systemwirkung betroffen ist, muss SYS-REQ mit rein.**

- Extern sichtbares Verhalten → SYS-REQ Pflicht
- Safety-relevant → SYS-REQ Pflicht
- Regulatory → SYS-REQ Pflicht
- Accountable Agent Layer blockiert bei SYS-Impact aber fehlendem SYS-REQ

### Regel 5: Evidence-Pflicht vor Close
> **Ohne Evidence kein Close.**

- Evidence-Datei muss existieren
- Muss Test-Ergebnisse enthalten
- Muss Traceability-Links verifizieren
- C blockiert CLOSE ohne Evidence

### Regel 6: Accountable-Agent-Layer-Block bei AI-Changes
> **B blockiert AI-Changes ohne CR + Requirement-Linkage.**

- Pre-flight Check: CR vorhanden?
- Pre-flight Check: CR Status = APPROVED?
- Pre-flight Check: Requirement-Refs vorhanden?
- Strict Mode: Keine Ausnahmen

---

## 7. Wann Accountable Agent Layer blockiert (verbindlich)

### 7.1 Hard Block (Exit 1, Arbeit verweigert)

```
IF no CR linked to session:
    BLOCK("Kein CR verlinkt. Run: curaops cr link --session <id> --cr <cr-id>")

IF CR.status != APPROVED:
    BLOCK(f"CR-{cr_id} Status ist {status}, muss APPROVED sein")

IF requirement_refs empty:
    BLOCK("Keine Requirement-Refs. Mindestens SW-REQ erforderlich.")

IF valid_id_pattern check fails:
    BLOCK(f"Ungültiges ID-Format: {invalid_ids}")

IF SYS-Impact detected AND no SYS-REQ in refs:
    BLOCK("System-Impact erkannt aber kein SYS-REQ verlinkt")

IF ARCH-Impact detected AND no SW-ARCH in refs:
    BLOCK("Architektur-Impact erkannt aber kein SW-ARCH verlinkt")
```

### 7.2 Warning (Allow mit Status "warning")

```
IF requirement file not found:
    WARN("Requirement-Datei nicht gefunden, wird erwartet")

IF derivation obligation detected but not addressed:
    WARN("Ableitungspflicht nicht adressiert")

IF test coverage < 100% for modified SW-REQ:
    WARN("Testabdeckung unvollständig")
```

### 7.3 Info (Nur Dokumentation)

```
IF AI-Suggestion available:
    INFO("Vorschlag: Ähnlicher Change in CR-XXX")
```

---

## 8. Was "Done" bedeutet

### 8.1 CR ist "Done" (CLOSED) wenn:
- [ ] Status = CLOSED
- [ ] Evidence-Datei existiert
- [ ] Alle verlinkten Requirements existieren
- [ ] Bidirektionale Links verifiziert
- [ ] Test-Evidence vorhanden
- [ ] Commits verlinkt
- [ ] Safety/Compliance-Tags geprüft

### 8.2 Requirement ist "Done" (VERIFIED) wenn:
- [ ] Status = VERIFIED
- [ ] Implementierung verlinkt
- [ ] Tests verlinkt und PASSED
- [ ] Review durchgeführt
- [ ] Acceptance Criteria erfüllt

### 8.3 AI-Change ist "Done" wenn:
- [ ] Accountable-Agent-Layer-Change erstellt
- [ ] Validation = passed
- [ ] Evidence generiert
- [ ] CR auf IMPLEMENTED oder CLOSED

---

## 9. Schnittstelle C ↔ B

### 9.1 C bietet an (API):
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
```

### 9.2 B nutzt C (keine Duplikation):
```python
from curaops.skills.change_request import (
    ChangeRequestService,
    generate_cr_evidence,
    validate_cr_traceability,
)

# B blockiert wenn C sagt:
# - CR nicht existiert
# - Status nicht APPROVED
# - Links ungültig
```

### 9.3 B ergänzt:
```python
AccountableAgentService:
  - pre_flight_check(session_id) → Bool
  - register_accountable_change(agent_ctx, intent, cr_id, refs) → AC-ID
  - validate_accountability(ac_id) → Report
  - generate_accountability_evidence(ac_id) → Path
```

---

## 10. Offene Punkte (max 2)

### OP-1: Emergency-Changes
- Was passiert bei Production-Incident ohne vorherige CR?
- Vorschlag: Emergency-CR retroaktiv mit 24h Frist

### OP-2: CR-Scope vs. Session-Scope
- Bindet B an Session oder an einzelne Changes?
- Vorschlag: Session hat Default-CR, kann pro Change override werden

---

**ENDE REGELWERK**

Dieses Dokument ist verbindlich für Compliance-Change-Control- und Accountable-Agent-Layer-Implementation.
