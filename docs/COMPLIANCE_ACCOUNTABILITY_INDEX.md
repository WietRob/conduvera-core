# Compliance & Accountability Documentation Index

**Status:** OFFICIAL  
**Version:** 4.0.0  
**Date:** 2026-04-19

---

## Quick Navigation

| Need | Document |
|------|----------|
| **Compliance Change Control Rules** | [COMPLIANCE_CHANGE_CONTROL_RULES.md](./COMPLIANCE_CHANGE_CONTROL_RULES.md) |
| **Compliance Change Control Process** | [COMPLIANCE_CHANGE_CONTROL_PROCESS.md](./COMPLIANCE_CHANGE_CONTROL_PROCESS.md) |
| **Compliance Change Control Implementation** | [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md) |
| **Compliance Change Control Architecture** | [COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md](./COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md) |
| **Accountable Agent Layer Rules** | [ACCOUNTABLE_AGENT_LAYER_RULES.md](./ACCOUNTABLE_AGENT_LAYER_RULES.md) |
| **Accountable Agent Layer Process** | [ACCOUNTABLE_AGENT_LAYER_PROCESS.md](./ACCOUNTABLE_AGENT_LAYER_PROCESS.md) |
| **Accountable Agent Layer Implementation** | [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md) |
| **Accountable Agent Layer Architecture** | [ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md](./ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md) |

---

## Authoritative Documents (Source of Truth)

### Compliance Change Control

| Document | Purpose | Status |
|----------|---------|--------|
| [COMPLIANCE_CHANGE_CONTROL_RULES.md](./COMPLIANCE_CHANGE_CONTROL_RULES.md) | Binding rules for CR workflow | ✅ AUTHORITATIVE |
| [COMPLIANCE_CHANGE_CONTROL_PROCESS.md](./COMPLIANCE_CHANGE_CONTROL_PROCESS.md) | State machines, transitions, evidence | ✅ AUTHORITATIVE |
| [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md) | Module design, schemas, DoD (Compliance Change Control only) | ✅ AUTHORITATIVE |
| [COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md](./COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md) | Architecture package | ✅ AUTHORITATIVE |

### Accountable Agent Layer

| Document | Purpose | Status |
|----------|---------|--------|
| [ACCOUNTABLE_AGENT_LAYER_RULES.md](./ACCOUNTABLE_AGENT_LAYER_RULES.md) | Blocking rules, intervention logic | ✅ AUTHORITATIVE |
| [ACCOUNTABLE_AGENT_LAYER_PROCESS.md](./ACCOUNTABLE_AGENT_LAYER_PROCESS.md) | Intervention points, state machine | ✅ AUTHORITATIVE |
| [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md) | Module design, schemas, DoD (Accountable Agent Layer only) | ✅ AUTHORITATIVE |
| [ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md](./ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md) | Architecture, dependency on Compliance Change Control, DoD | ✅ AUTHORITATIVE |

---

## Legacy Mixed Documents (Deprecated — Do Not Extend)

> **⚠️ WARNING:** These documents contain mixed Compliance Change Control + Accountable Agent Layer content. Do not modify or extend. Use authoritative docs above.

| Document | Content | Replacement |
|----------|---------|-------------|
| [COMPLIANCE_CHANGE_CONTROL_RULES_BINDING.md](./COMPLIANCE_CHANGE_CONTROL_RULES_BINDING.md) | Mixed Compliance Change Control + Accountable Agent Layer rules | Use separate RULES.md files |
| [COMPLIANCE_CHANGE_CONTROL_PROCESS_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_PROCESS_CONTRACT.md) | Mixed Compliance Change Control + Accountable Agent Layer process | Use separate PROCESS.md files |
| [COMPLIANCE_ACCOUNTABILITY_ARCHITECTURE.md](./COMPLIANCE_ACCOUNTABILITY_ARCHITECTURE.md) | Mixed C+B architecture | Use Compliance Change Control Architecture + Accountable Agent Layer Architecture |
| [COMPLIANCE_ACCOUNTABILITY_SPECIFICATION.md](./COMPLIANCE_ACCOUNTABILITY_SPECIFICATION.md) | Mixed operational spec | Use Compliance Change Control Process + Accountable Agent Layer Process |

---

## Domain Language

### Official Names

| Concept | Official Name | Legacy (deprecated) |
|---------|---------------|---------------------|
| Safety Guard | Safety Guard | Historical module identifier only; do not use shorthand in public docs |
| Compliance Change Control | Compliance Change Control | Historical module identifier only; do not use shorthand in public docs |
| Accountable Agent Layer | Accountable Agent Layer | Historical module identifier only; do not use shorthand in public docs |

### Canonical Verification Model

| Entity | Types | ID Patterns | Defined In |
|--------|-------|-------------|------------|
| VerificationCase | unit, software_integration, software_verification, system_integration, system_verification | TC-UT-*, TC-SIT-*, TC-SVT-*, TC-SYSIT-*, TC-SYST-* | C-RULES §4.4, C-PROCESS §B.3 |
| Evidence / VerificationResult | Execution result artifact | Per CR evidence file | C-PROCESS §B.4 |

**Separation:** VerificationCase = specification. Evidence/VerificationResult = execution result.

### Repository Locations

```
/home/roberto_schmidt/projects/
├── curaops-safety-guard/          # Safety Guard (standalone)
└── matrix-os/                     # Compliance & Accountability
    ├── curaops/skills/
    │   ├── change_request/        # Compliance Change Control
    │   ├── accountable_agent/     # Accountable Agent Layer
    │   └── aspice_link_manager/   # Shared Link Management
    └── docs/
        ├── COMPLIANCE_CHANGE_CONTROL_*.md   # Compliance Change Control docs (authoritative)
        ├── ACCOUNTABLE_AGENT_LAYER_*.md     # Accountable Agent Layer docs (authoritative)
        └── COMPLIANCE_ACCOUNTABILITY_*.md   # Mixed (legacy, do not extend)
```

---

## Reading Order

### For Compliance Change Control Implementation:
1. [COMPLIANCE_CHANGE_CONTROL_RULES.md](./COMPLIANCE_CHANGE_CONTROL_RULES.md) — what is required
2. [COMPLIANCE_CHANGE_CONTROL_PROCESS.md](./COMPLIANCE_CHANGE_CONTROL_PROCESS.md) — how it works
3. [COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md](./COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md) — how to build it
4. [COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md](./COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md) — system design

### For Accountable Agent Layer Implementation:
1. [ACCOUNTABLE_AGENT_LAYER_RULES.md](./ACCOUNTABLE_AGENT_LAYER_RULES.md) — blocking rules
2. [ACCOUNTABLE_AGENT_LAYER_PROCESS.md](./ACCOUNTABLE_AGENT_LAYER_PROCESS.md) — intervention workflow
3. [ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md](./ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md) — how to build it
4. [ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md](./ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md) — system design

---

## Document Status Summary

| Category | Count | Documents |
|----------|-------|-----------|
| **Authoritative Compliance Change Control** | 4 | RULES, PROCESS, IMPLEMENTATION_CONTRACT, ARCHITECTURE |
| **Authoritative Accountable Agent Layer** | 4 | RULES, PROCESS, IMPLEMENTATION, ARCHITECTURE |
| **Legacy Mixed** | 4 | RULES_BINDING, PROCESS_CONTRACT, ACCOUNTABILITY_ARCH, ACCOUNTABILITY_SPEC |
| **Index** | 1 | This file |

**Total:** 13 documents

---

## Shared-Interface Sections

The following sections are intentionally duplicated across C and B authoritative docs because they describe the shared repo structure and interface:

| Section | Compliance Change Control Location | Accountable Agent Layer Location |
|---------|------------|------------|
| Module Ownership Matrix | IMPLEMENTATION_CONTRACT B.2 | IMPLEMENTATION Section B |
| Directory Structure | IMPLEMENTATION_CONTRACT B.3 | IMPLEMENTATION Section B |
| Exit Codes | IMPLEMENTATION_CONTRACT G.3 | IMPLEMENTATION D.2 |

---

## Naming History

| Date | Action |
|------|--------|
| 2026-04-10 | Normalized from internal shorthand to professional names |
| 2026-04-10 | Split mixed documents into authoritative C-only and B-only |
| 2026-04-10 | Extracted B implementation from C-IMPL to ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md |
| 2026-04-10 | Extracted B architecture from ACCOUNTABILITY-ARCH to ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md |
| 2026-04-10 | Cleaned cross-contamination: C-IMPL is now C-only, Accountable Agent Layer Implementation is now B-only |
| 2026-04-19 | Applied bugfix-policy hardening (D1-D22, E1-E12) and level-specific VerificationCase model |
| 2026-04-19 | Bumped all docs to v2.0.0 (C-RULES/PROCESS/ARCHITECTURE were already v2.0.0) |
| 2026-04-19 | Compliance Change Control Implementation Contract synced from v1.0.0 to v2.0.0 |
| 2026-04-19 | B docs bumped from v1.0.0 to v2.0.0 with bugfix-specific blocks/warnings/evidence |

---

**END OF INDEX**
