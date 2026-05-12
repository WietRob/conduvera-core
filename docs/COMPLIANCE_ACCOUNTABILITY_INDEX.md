# Compliance and Accountability Index

Status: authoritative documentation index for the merged Matrix OS compliance stack as of PR #7.

This document maps the currently merged compliance/accountability modules and their public entry points. It is descriptive only; it does not claim production readiness.

## Merged modules

| Module | Merged in | Runtime package | CLI namespace | Responsibility |
|---|---:|---|---|---|
| Foundation / Packaging / CLI Baseline | PR #4 | `curaops` | root CLI | Python package baseline, import contract, CLI shell, `version`, `doctor` |
| Compliance Change Control | PR #5 | `curaops.skills.change_request` | `cr` | Change Request lifecycle, validation, evidence generation, verification-case management |
| Accountable Agent Layer | PR #6 | `curaops.skills.accountable_agent` | `accountable` | AI-assisted change accountability gates, CR linkage validation, accountability evidence |
| ASPICE Support Utilities | PR #7 | `curaops.skills.aspice_conflict_detector`, `curaops.skills.aspice_link_manager` | `aspice` | Traceability support, conflict detection, link updates, traceability matrix support |

## CLI command index

Verified CLI namespaces:

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
```

Root commands:

| Command | Purpose |
|---|---|
| `version` | Print baseline CLI version |
| `doctor` | Run minimal package/import smoke check |
| `cr` | Compliance Change Control lifecycle |
| `accountable` | Accountable Agent Layer checks/evidence |
| `aspice` | ASPICE support utilities |

Compliance Change Control commands:

| Command | Purpose |
|---|---|
| `cr create` | Create a Change Request in DRAFT or EMERGENCY state |
| `cr submit` | Transition DRAFT/EMERGENCY to SUBMITTED |
| `cr approve` | Transition SUBMITTED to APPROVED |
| `cr reject` | Transition to REJECTED |
| `cr start` | Transition APPROVED to IN_PROGRESS |
| `cr complete` | Transition IN_PROGRESS to IMPLEMENTED |
| `cr verify` | Transition IMPLEMENTED to VERIFIED after evidence generation |
| `cr close` | Transition VERIFIED to CLOSED |
| `cr revise` | Transition REJECTED to DRAFT |
| `cr status` | Show CR status and details |
| `cr list` | List Change Requests |
| `cr evidence` | Generate CCC evidence for a CR |
| `cr validate` | Validate a CR against C rules |
| `cr verification` | Manage verification cases |

Accountable Agent Layer commands:

| Command | Purpose |
|---|---|
| `accountable pre-flight` | Run the AAL pre-flight gate before AI-assisted work |
| `accountable preflight` | Alias for `pre-flight` |
| `accountable register` | Register an accountable AI-assisted change |
| `accountable validate` | Validate accountable change links |
| `accountable evidence` | Generate accountable-change evidence |

ASPICE Support Utility commands:

| Command | Purpose |
|---|---|
| `aspice check` | Check ASPICE traceability conflicts |
| `aspice link` | Link a requirement document to an implementation file |
| `aspice update-all` | Update bidirectional traceability links for Markdown documents |

## Authoritative module docs

| Area | Authoritative docs |
|---|---|
| Overall architecture | `docs/MATRIX_OS_ARCHITECTURE.md`, `docs/MATRIX_OS_MODULE_BOUNDARIES.md` |
| Release train | `docs/RELEASE_TRAIN_STATUS.md` |
| Compliance/accountability index | this file |
| Compliance Change Control | `docs/COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md`, `docs/COMPLIANCE_CHANGE_CONTROL_PROCESS.md`, `docs/COMPLIANCE_CHANGE_CONTROL_RULES.md`, `docs/COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md` |
| Accountable Agent Layer | `docs/ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md`, `docs/ACCOUNTABLE_AGENT_LAYER_PROCESS.md`, `docs/ACCOUNTABLE_AGENT_LAYER_RULES.md`, `docs/ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md` |
| ASPICE utilities | `curaops/skills/aspice_conflict_detector/SKILL.md`, `curaops/skills/aspice_link_manager/README.md` |

## Non-goals in the current merged stack

The merged stack is not a production certification claim. It does not yet include UI/MCP/editor scaffolding, Safety Guard adapter work, agent-evidence-plane adapter work, CAS/failure-loop/peekxd/OpenCode/ai-router adapters, deployment hardening, or external compliance certification.
