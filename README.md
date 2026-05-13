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
| Evidence Backbone Adapter Contract | Current | Harness-side event envelope, local JSONL store, validate/summarize CLI |
| agent-evidence-plane Thin Adapter | Current | Convert a small supported external JSONL subset into Matrix OS evidence events |

This repository is not yet a production-ready platform. UI/MCP/editor scaffolding is discovery-only, the evidence backbone and agent-evidence-plane adapter are local harness-side contracts, and broad external adapter work remains future scope.

## Current CLI

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
python3 -m curaops.cli.main evidence convert-agent-plane --help
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
| `evidence` | Evidence backbone validate/summarize utilities |

## Authoritative docs

Start here:

1. `docs/MATRIX_OS_ARCHITECTURE.md`
2. `docs/MATRIX_OS_MODULE_BOUNDARIES.md`
3. `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md`
4. `docs/MATRIX_OS_SCAFFOLDING.md`
5. `docs/MATRIX_OS_EVIDENCE_BACKBONE.md`
6. `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`
7. `docs/RELEASE_TRAIN_STATUS.md`
8. `docs/DOCUMENTATION_INVENTORY.md`

Module-specific docs:

| Module | Docs |
|---|---|
| Compliance Change Control | `docs/COMPLIANCE_CHANGE_CONTROL_*` |
| Accountable Agent Layer | `docs/ACCOUNTABLE_AGENT_LAYER_*` |
| ASPICE Support Utilities | `curaops/skills/aspice_conflict_detector/SKILL.md`, `curaops/skills/aspice_link_manager/README.md` |
| Evidence Backbone | `docs/MATRIX_OS_EVIDENCE_BACKBONE.md`, `curaops/evidence/` |
| agent-evidence-plane Thin Adapter | `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`, `curaops/evidence/adapters/agent_evidence_plane.py` |

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

Current:

- Evidence Backbone Adapter Contract: harness-side event contract; no agent-evidence-plane absorption
- agent-evidence-plane Thin Adapter: translation-only adapter for a small supported event subset; no vendoring or external repo modification

Planned:

- Later focused adapter slices for Safety Guard, agent-evidence-plane, CAS, failure-loop, peekxd, OpenCode plugin, and ai-router
