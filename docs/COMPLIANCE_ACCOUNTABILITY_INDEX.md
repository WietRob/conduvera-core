# Compliance and Accountability Index

Status: authoritative documentation index for the merged Matrix OS compliance stack, scaffolding surface, and evidence backbone.

This document maps the currently merged compliance/accountability modules and their public entry points. It is descriptive only; it does not claim production readiness.

## Merged modules

| Module | Merged in | Runtime package | CLI namespace | Responsibility |
|---|---:|---|---|---|
| Foundation / Packaging / CLI Baseline | PR #4 | `curaops` | root CLI | Python package baseline, import contract, CLI shell, `version`, `doctor` |
| Compliance Change Control | PR #5 | `curaops.skills.change_request` | `cr` | Change Request lifecycle, validation, evidence generation, verification-case management |
| Accountable Agent Layer | PR #6 | `curaops.skills.accountable_agent` | `accountable` | AI-assisted change accountability gates, CR linkage validation, accountability evidence |
| ASPICE Support Utilities | PR #7 | `curaops.skills.aspice_conflict_detector`, `curaops.skills.aspice_link_manager` | `aspice` | Traceability support, conflict detection, link updates, traceability matrix support |
| Evidence Backbone Adapter Contract | Current | `curaops.evidence` | `evidence` | Harness-side evidence event envelope, local JSONL store, validation/summarization |
| agent-evidence-plane Thin Adapter | Current | `curaops.evidence.adapters.agent_evidence_plane` | `evidence convert-agent-plane` | Convert a small supported external JSONL subset into Matrix OS events |
| Safety Guard Adapter Contract | Current | `curaops.evidence.adapters.safety_guard` | `evidence convert-safety-guard` | Convert compatible trust/safety result JSONL into Matrix OS events |
| Evidence Adapter Registry | Current | `curaops.evidence.adapters.registry` | `evidence adapters`, `evidence adapter show` | Discover registered evidence adapters and their explicit event/input contracts |
| failure-driven-loop Thin Adapter | PR #14 | `curaops.evidence.adapters.failure_loop` | `evidence convert-failure-loop` | Convert compatible failure-loop result JSONL into Matrix OS evidence events; proposed rules are evidence only |
| Product Coherence & Harness Gateway Validation | PR #15 | `curaops.harness.gateway`, scenario tests | test/docs | Validate operator scenarios, generic gateway descriptors, UI value map, provenance note |
| Evidence Operator Report Pack | PR #16 | `curaops.evidence.reporting` | `evidence report` | Render operator-readable text/Markdown/JSON reports over validated evidence streams |
| Evidence Report Golden Fixtures | PR #17 | `curaops.evidence.reporting`, fixtures | tests | Regression contract comparing deterministic product-coherence evidence to expected report outputs |
| Evidence Report Contract Versioning + CI Gate | Current | `curaops.evidence.reporting`, GitHub Actions | `evidence report-contract`, CI | Explicit `MXOS-REPORT-1.0` report metadata and focused evidence/report quality workflow |

## CLI command index

Verified CLI namespaces:

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
```

Root commands:

| Command | Purpose |
|---|---|
| `version` | Print baseline CLI version |
| `doctor` | Run minimal package/import smoke check |
| `cr` | Compliance Change Control lifecycle |
| `accountable` | Accountable Agent Layer checks/evidence |
| `aspice` | ASPICE Support Utilities |
| `scaffold` | Matrix OS UI/MCP/editor scaffolding |
| `evidence` | Matrix OS evidence backbone validation/summarization |

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

Scaffolding commands:

| Command | Purpose |
|---|---|
| `scaffold status` | Show UI/MCP/editor scaffolding status without launching runtime services |
| `scaffold show ui` | Show original Matrix UI scaffold details and source-path checks |
| `scaffold show mcp` | Show MCP contract-only scaffold details |
| `scaffold show editor` | Show editor scaffold details and source-path checks |

Evidence backbone commands:

| Command | Purpose |
|---|---|
| `evidence` | Evidence backbone utilities |
| `evidence adapters` | List registered Matrix OS evidence adapters |
| `evidence adapter show` | Show one evidence adapter descriptor; unknown ids fail closed |
| `evidence validate` | Validate a Matrix OS evidence event JSONL stream |
| `evidence summarize` | Summarize a valid Matrix OS evidence event JSONL stream |
| `evidence report` | Render an operator-readable evidence report from a valid Matrix OS event JSONL stream |
| `evidence report-contract` | Print the stable Evidence Operator Report contract version |
| `evidence convert-agent-plane` | Convert compatible agent-evidence-plane JSONL events into Matrix OS evidence JSONL |
| `evidence convert-safety-guard` | Convert compatible Safety Guard result JSONL into Matrix OS evidence JSONL |
| `evidence convert-failure-loop` | Convert compatible failure-loop result JSONL into Matrix OS evidence JSONL |

## Authoritative module docs

| Area | Authoritative docs |
|---|---|
| Overall architecture | `docs/MATRIX_OS_ARCHITECTURE.md`, `docs/MATRIX_OS_MODULE_BOUNDARIES.md` |
| Product coherence / scenarios | `docs/MATRIX_OS_PRODUCT_COHERENCE.md`, `tests/test_product_coherence_scenarios.py` |
| Harness gateway contract | `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md`, `curaops/harness/gateway.py` |
| UI value map / provenance | `docs/MATRIX_OS_UI_VALUE_MAP.md`, `docs/MATRIX_OS_ORIGIN_AND_PROVENANCE.md` |
| MCP / UI / Editor scaffolding | `docs/MATRIX_OS_SCAFFOLDING.md` |
| Evidence backbone | `docs/MATRIX_OS_EVIDENCE_BACKBONE.md` |
| agent-evidence-plane thin adapter | `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md` |
| Safety Guard adapter contract | `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md` |
| Evidence adapter registry | `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md` |
| failure-driven-loop thin adapter | `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md` |
| Evidence operator reports | `docs/MATRIX_OS_EVIDENCE_OPERATOR_REPORTS.md`, `tests/test_evidence_operator_report.py`, `tests/test_evidence_report_golden_outputs.py`, `tests/test_evidence_report_contract_version.py` |
| Release train | `docs/RELEASE_TRAIN_STATUS.md` |
| Compliance/accountability index | this file |
| Compliance Change Control | `docs/COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md`, `docs/COMPLIANCE_CHANGE_CONTROL_PROCESS.md`, `docs/COMPLIANCE_CHANGE_CONTROL_RULES.md`, `docs/COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md` |
| Accountable Agent Layer | `docs/ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md`, `docs/ACCOUNTABLE_AGENT_LAYER_PROCESS.md`, `docs/ACCOUNTABLE_AGENT_LAYER_RULES.md`, `docs/ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md` |
| ASPICE utilities | `curaops/skills/aspice_conflict_detector/SKILL.md`, `curaops/skills/aspice_link_manager/README.md` |

## Non-goals in the current merged stack

The merged stack is not a production certification claim. UI/MCP/editor support is currently discovery-only scaffolding, and the evidence backbone plus thin external adapters are local Matrix OS harness-side contracts. The report layer is read-only over existing evidence. The gateway descriptors are declarative future boundaries only. It does not include an MCP server runtime, UI rewrite, production dashboard, IDE plugin, language-server integration, agent execution bridge, real Hermes/OpenCode/Zed execution, shell interception, destructive command execution, automatic rule enforcement, production audit retention, cloud persistence, or external certification. Broad Safety Guard runtime work, broad agent-evidence-plane product work, CAS/peekxd/OpenCode/ai-router adapters, and deployment hardening remain outside the current merged stack.
