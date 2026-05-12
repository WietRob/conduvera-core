# Matrix OS

Matrix OS is currently a Python package and CLI-based harness/control plane for compliance-oriented agent workflows.

Current merged scope:

| Slice | Status | Responsibility |
|---|---|---|
| Foundation / Packaging / CLI Baseline | Merged | `curaops` package baseline and root CLI |
| Compliance Change Control | Merged | Change Request lifecycle, validation, evidence, verification cases |
| Accountable Agent Layer | Merged | AI-assisted change accountability gates and evidence |
| ASPICE Support Utilities | Merged | Traceability conflict detection and link-management support |

This repository is not yet a production-ready platform. UI/MCP/editor scaffolding and external adapter work are planned future slices.

## Current CLI

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
```

Root command namespaces:

| Namespace | Purpose |
|---|---|
| `version` | Print CLI/package baseline version |
| `doctor` | Run minimal package/import smoke check |
| `cr` | Compliance Change Control |
| `accountable` | Accountable Agent Layer |
| `aspice` | ASPICE Support Utilities |

## Authoritative docs

Start here:

1. `docs/MATRIX_OS_ARCHITECTURE.md`
2. `docs/MATRIX_OS_MODULE_BOUNDARIES.md`
3. `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md`
4. `docs/RELEASE_TRAIN_STATUS.md`
5. `docs/DOCUMENTATION_INVENTORY.md`

Module-specific docs:

| Module | Docs |
|---|---|
| Compliance Change Control | `docs/COMPLIANCE_CHANGE_CONTROL_*` |
| Accountable Agent Layer | `docs/ACCOUNTABLE_AGENT_LAYER_*` |
| ASPICE Support Utilities | `curaops/skills/aspice_conflict_detector/SKILL.md`, `curaops/skills/aspice_link_manager/README.md` |

## Historical docs

Older TUI, UI, routing, and phase-plan documents remain in the repository as historical reference. They are not the current implementation map. See `docs/DOCUMENTATION_INVENTORY.md` for the deprecated-document map.

## Release train

Merged:

- PR #4 Foundation / Packaging / CLI Baseline
- PR #5 Compliance Change Control Core
- PR #6 Accountable Agent Layer
- PR #7 ASPICE Support Utilities

Planned:

- MCP / UI / Editor Scaffolding slice
- Later focused adapter slices for Safety Guard, agent-evidence-plane, CAS, failure-loop, peekxd, OpenCode plugin, and ai-router
