# Matrix OS

Matrix OS is currently a Python package and CLI-based harness/control plane for compliance-oriented agent workflows.

Current merged scope:

| Slice | Status | Responsibility |
|---|---|---|
| Foundation / Packaging / CLI Baseline | Merged | `curaops` package baseline and root CLI |
| Compliance Change Control | Merged | Change Request lifecycle, validation, evidence, verification cases |
| Accountable Agent Layer | Merged | AI-assisted change accountability gates and evidence |
| ASPICE Support Utilities | Merged | Traceability conflict detection and link-management support |
| MCP / UI / Editor Scaffolding | Merged | Original Matrix UI preservation and discovery-only scaffolding |
| Evidence Backbone Adapter Contract | Merged | Harness-side event envelope, local JSONL store, validate/summarize CLI |
| agent-evidence-plane Thin Adapter | Merged | Convert a small supported external JSONL subset into Matrix OS evidence events |
| Safety Guard Adapter Contract | Merged | Convert compatible trust/safety result JSONL into Matrix OS evidence events |
| Evidence Adapter Registry | Merged | Discover registered adapters and their explicit contracts |
| failure-driven-loop Thin Adapter | Merged | Convert compatible failure-loop result JSONL into Matrix OS evidence events |
| Product Coherence & Harness Gateway Validation | Merged | Prove Matrix OS product scenarios and generic future runner/editor boundaries |
| Evidence Operator Report Pack | Current | Render operator-readable text/Markdown/JSON reports over validated evidence streams |

This repository is not yet a production-ready platform. UI/MCP/editor scaffolding is discovery-only, the evidence backbone plus thin external adapters are local harness-side contracts, and broad external adapter work remains future scope.

## Current CLI

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
python3 -m curaops.cli.main evidence adapters
python3 -m curaops.cli.main evidence adapter show agent-evidence-plane
python3 -m curaops.cli.main evidence adapter show safety-guard
python3 -m curaops.cli.main evidence adapter show failure-loop
python3 -m curaops.cli.main evidence convert-agent-plane --help
python3 -m curaops.cli.main evidence convert-safety-guard --help
python3 -m curaops.cli.main evidence convert-failure-loop --help
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format markdown
```

Root command namespaces:

| Namespace | Purpose |
|---|---|
| `version` | Print CLI/package baseline version |
| `doctor` | Run minimal package/import smoke check |
| `cr` | Compliance Change Control |
| `accountable` | Accountable Agent Layer |
| `aspice` | ASPICE Support Utilities |
| `scaffold` | UI/MCP/editor scaffolding manifest |
| `evidence` | Evidence backbone validate/summarize/convert/discovery/report utilities |

## Authoritative docs

Start here:

1. `docs/MATRIX_OS_PRODUCT_COHERENCE.md`
2. `docs/MATRIX_OS_ARCHITECTURE.md`
3. `docs/MATRIX_OS_MODULE_BOUNDARIES.md`
4. `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md`
5. `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md`
6. `docs/MATRIX_OS_UI_VALUE_MAP.md`
7. `docs/MATRIX_OS_ORIGIN_AND_PROVENANCE.md`
8. `docs/MATRIX_OS_SCAFFOLDING.md`
9. `docs/MATRIX_OS_EVIDENCE_BACKBONE.md`
10. `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`
11. `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md`
12. `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md`
13. `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md`
14. `docs/MATRIX_OS_EVIDENCE_OPERATOR_REPORTS.md`
15. `docs/RELEASE_TRAIN_STATUS.md`
16. `docs/DOCUMENTATION_INVENTORY.md`

Module-specific docs:

| Module | Docs |
|---|---|
| Compliance Change Control | `docs/COMPLIANCE_CHANGE_CONTROL_*` |
| Accountable Agent Layer | `docs/ACCOUNTABLE_AGENT_LAYER_*` |
| ASPICE Support Utilities | `curaops/skills/aspice_conflict_detector/SKILL.md`, `curaops/skills/aspice_link_manager/README.md` |
| Evidence Backbone | `docs/MATRIX_OS_EVIDENCE_BACKBONE.md`, `curaops/evidence/` |
| agent-evidence-plane Thin Adapter | `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`, `curaops/evidence/adapters/agent_evidence_plane.py` |
| Safety Guard Adapter Contract | `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md`, `curaops/evidence/adapters/safety_guard.py` |
| Evidence Adapter Registry | `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md`, `curaops/evidence/adapters/registry.py` |
| failure-driven-loop Thin Adapter | `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md`, `curaops/evidence/adapters/failure_loop.py` |
| Evidence Operator Reports | `docs/MATRIX_OS_EVIDENCE_OPERATOR_REPORTS.md`, `curaops/evidence/reporting.py` |
| Product Coherence Scenarios | `docs/MATRIX_OS_PRODUCT_COHERENCE.md`, `tests/test_product_coherence_scenarios.py` |
| Harness Gateway Contract | `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md`, `curaops/harness/gateway.py` |
| UI Value Map / Provenance | `docs/MATRIX_OS_UI_VALUE_MAP.md`, `docs/MATRIX_OS_ORIGIN_AND_PROVENANCE.md` |

## Historical docs

Older TUI, UI, routing, and phase-plan documents remain in the repository as historical reference. They are not the current implementation map. See `docs/DOCUMENTATION_INVENTORY.md` for the deprecated-document map.

## Release train

Merged:

- PR #4 Foundation / Packaging / CLI Baseline
- PR #5 Compliance Change Control Core
- PR #6 Accountable Agent Layer
- PR #7 ASPICE Support Utilities
- PR #8 Architecture / Documentation Index
- PR #9 MCP / UI / Editor Scaffolding

- PR #10 Evidence Backbone Adapter Contract
- PR #11 agent-evidence-plane Thin Adapter
- PR #12 Safety Guard Adapter Contract
- PR #13 Evidence Adapter Registry
- PR #14 failure-driven-loop Thin Adapter
- PR #15 Product Coherence & Harness Gateway Validation

Current:

- Evidence Operator Report Pack: operator-readable reports from existing evidence streams; no new adapter, runtime execution, dashboard, MCP runtime, or production audit claim

Planned:

- Later focused adapter slices for Safety Guard, agent-evidence-plane, CAS, peekxd, OpenCode plugin, and ai-router
