# C Core Implementation Decision

## Evidence Sources
- CONFORMANCE_AUDIT_REPORT.md (audit result: no usable implementation)
- COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md v2.0.0 (canonical module layout + code patterns)
- COMPLIANCE_CHANGE_CONTROL_RULES.md v2.0.0 (field contracts, bugfix policy)
- COMPLIANCE_CHANGE_CONTROL_PROCESS.md v2.0.0 (9-state machine, transition matrix, mandatory fields by state)

## A) KEEP / REUSE

| What | Decision | Rationale |
|------|----------|-----------|
| `curaops/skills/aspice-link-manager/` | KEEP AS-IS | Reuse per C-IMPLEMENTATION_CONTRACT §C.1 |
| `curaops/cli/main.py` | KEEP | CLI framework reuse per §C.1 |
| `curaops/cli/completion.py` | KEEP | Shell completion utility |
| `curaops/skills/session-manager/` | KEEP | Reference only, per §C.1 |

## B) FREEZE AS LEGACY (do not delete, do not import from new code)

| What | Decision | Rationale |
|------|----------|-----------|
| `curaops/skills/change-request/` | FREEZE | Old v0.x prototype. 6/9 states, 4/20 fields, 0 bugfix rules. Tests test prototype, not docs. |
| `curaops/skills/change_request` symlink | FREEZE | Packaging hack for hyphenated dir. Will be replaced. |
| `curaops/skills/accountable-agent/` | FREEZE | Accountable Agent Layer is out of scope for this step. Will be rebuilt separately. |
| `curaops/skills/accountable_agent` symlink | FREEZE | Same packaging hack. |
| `curaops/cli/commands/skills.py` (Compliance Change Control / Accountable Agent Layer sections) | FREEZE | CLI wiring for old prototype. Will be replaced per §G. |

## C) REPLACE COMPLETELY

| What | Old | New |
|------|-----|-----|
| C core package | `curaops/skills/change-request/__init__.py` (monolith) | `curaops/skills/change_request/` (proper Python package with submodules) |
| C CLI commands | Inline in `curaops/cli/commands/skills.py` | `curaops/cli/commands/cr.py` (per §B.2) |

## D) Exact Target Module Tree

```
curaops/skills/change_request/              # Python-package-safe (underscore)
├── __init__.py                             # Public API re-exports
├── models.py                               # CRStatus, ChangeType, ImpactLevel, SafetyImpact,
│                                           # VerificationType, VerificationStatus,
│                                           # ChangeRequest, VerificationCase dataclasses
├── state_machine.py                        # CRStateMachine: 9-state matrix + mandatory field gating
├── validation.py                           # CRValidator: ID patterns, impact, derivation, bugfix rules
├── evidence.py                             # CREvidenceGenerator: CCC-1.1.0 schema, JSON output
├── persistence.py                          # Markdown CR files, verification artifacts
├── service.py                              # ChangeRequestService, VerificationService
└── tests/
    ├── test_models.py                      # Model construction and field validation
    ├── test_state_machine.py               # Transition matrix + field gating
    ├── test_validation.py                  # Bugfix rules, ID patterns, impact detection
    ├── test_evidence.py                    # Evidence schema CCC-1.1.0
    ├── test_persistence.py                 # Markdown read/write roundtrip
    └── test_contracts.py                   # 8 required contract scenarios from spec

curaops/cli/commands/
└── cr.py                                   # C CLI (replaces cr_app section in skills.py)
```

Decision: `change_request` (underscore) chosen per C-IMPLEMENTATION_CONTRACT §B.3 and B-RULES §7.
This matches the doc-specified import path and is Python-package-safe.
