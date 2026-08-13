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
| Evidence Operator Report Pack | Merged | Render operator-readable text/Markdown/JSON reports over validated evidence streams |
| Evidence Report Golden Fixtures | Merged | Regression-lock operator report outputs with deterministic golden evidence |
| Evidence Report Contract Versioning + CI Gate | Merged | Expose `MXOS-REPORT-1.0` report metadata and enforce focused evidence/report CI workflow |
| Governance Hardening & Required Review Policy | Merged | Document branch protection, release review model, and CODEOWNERS routing draft |
| Governance Enforcement Decision | Merged | Decide required approval vs operational Kanban; keep settings unchanged for now |
| Operator Workflow Vertical Slice | Merged | Read-only harness status connecting evidence, adapters, gateway descriptors, and Matrix UI attach point |
| Runtime Decision / Dry-Run Gateway | Merged | Descriptor-only route planner from operator intent to candidate ranking, evidence plan, and approval gate |
| Route Plan Golden Fixtures & Operator Handoff Contract | Merged | Regression-lock `route-plan.v1` JSON handoff fixtures for future UI/automation consumers without runtime execution |
| Route-Plan Viewer Golden Outputs & Operator Snapshot Pack | Merged | Regression-lock read-only route-plan viewer snapshots for future Matrix UI panel consumers without live UI/runtime execution |
| Minimal Textual Route-Plan Panel Model | Merged | Provide a non-interactive Textual-compatible panel model over validated `route-plan.v1` fixtures without live UI/runtime execution |
| Route-Plan Panel Golden Render Fixtures | Merged | Freeze exact panel-render snapshots as the future UI snapshot contract without live UI/runtime execution |
| Non-Live Matrix UI Route-Plan Panel Attachment | Merged | Add a discoverable Matrix UI route-plan panel view over the stable snapshot contract without runtime/dashboard behavior |
| Non-Live Route-Plan Artifact Selector | Merged | Select among canonical route-plan artifacts for the non-live panel without filesystem browsing or execution |
| Non-Live Route-Plan Artifact Picker UI State | Merged | Display selected artifact id, label, scenario, and read-only picker boundaries in the non-live panel path |
| Non-Live Route-Plan Artifact Picker List Widget | Merged | Historical (non-live) picker widget; superseded by the Delivery Workspace |

This repository contains the Conduvera operational harness control plane with a
live **trusted Delivery Workspace** (v1). The activity browser workspace turns
a completed, explicitly-selected managed code-change Attempt into an immutable
operator-approved PublishCandidate and publishes exactly that candidate to one
GitHub branch and one PR — with no automatic merge and no raw prompt / secret /
local path in public artefacts.

Alpha vs trusted v1: the earlier alpha published an unconstrained live worktree
diff (TOCTOU, empty PR body). trusted v1 requires explicit Attempt selection,
an immutable approved PublishCandidate (exact file/diff/tree/evidence/gate
hashes), atomic exact-changeset commits, and a complete PR contract. The former
final acceptance run is a superseded diagnostic, not binding.

### Delivery CLI

```bash
conduvera control-plane delivery list
conduvera control-plane delivery inspect <job-or-delivery>
conduvera control-plane delivery preflight <job-or-delivery> [--attempt-id X]
conduvera control-plane delivery select-attempt <job> --attempt-id X
conduvera control-plane delivery candidate-list
conduvera control-plane delivery candidate-approve --candidate-id cand_...
conduvera control-plane delivery publish <job-or-delivery> [--candidate-id cand_...]
conduvera control-plane delivery sync <job-or-delivery>
conduvera control-plane delivery cleanup <job-or-delivery>
```

Historical note: earlier UI/MCP/editor work was discovery-only scaffolding (see
PR #33 and the non-live picker rows below); the current Delivery Workspace is a
real operator surface backed by the Control-Plane authority, not scaffolding.

The current `main` branch governance is documented in `docs/MATRIX_OS_GOVERNANCE_POLICY.md`: the evidence/report quality gate is enforced as a strict required status check, while required GitHub pull-request approvals and conversation resolution are not currently enforced.

## Current CLI

```bash
python3 -m conduvera.cli.main --help
python3 -m conduvera.cli.main cr --help
python3 -m conduvera.cli.main accountable --help
python3 -m conduvera.cli.main aspice --help
python3 -m conduvera.cli.main scaffold --help
python3 -m conduvera.cli.main evidence --help
python3 -m conduvera.cli.main evidence adapters
python3 -m conduvera.cli.main evidence adapter show agent-evidence-plane
python3 -m conduvera.cli.main evidence adapter show safety-guard
python3 -m conduvera.cli.main evidence adapter show failure-loop
python3 -m conduvera.cli.main evidence convert-agent-plane --help
python3 -m conduvera.cli.main evidence convert-safety-guard --help
python3 -m conduvera.cli.main evidence convert-failure-loop --help
python3 -m conduvera.cli.main evidence report EVENTS.jsonl --format markdown
python3 -m conduvera.cli.main evidence report-contract
python3 -m conduvera.cli.main harness status --events tests/fixtures/evidence/operator_report/product_coherence.events.jsonl
python3 -m conduvera.cli.main harness route-plan --intent "Run agent task with evidence capture"
python3 -m conduvera.cli.main harness route-plan --intent "Run agent task with evidence capture" --format json
python3 -m conduvera.cli.main harness route-plan --intent "Run agent task with evidence capture" --format json --output route-plan.json
python3 -m conduvera.cli.main harness route-plan-view --input tests/fixtures/harness/route_plan/agent-task.json
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
| `harness` | Read-only operator status and descriptor-only dry-run route plans over evidence, adapters, gateway descriptors, and UI attach points |

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
15. `docs/MATRIX_OS_OPERATOR_WORKFLOW.md`
16. `docs/MATRIX_OS_OPERATOR_WORKFLOW_PRODUCT_COHERENCE.md`
17. `docs/RELEASE_TRAIN_STATUS.md`
18. `docs/MATRIX_OS_GOVERNANCE_POLICY.md`
19. `docs/MATRIX_OS_GOVERNANCE_ENFORCEMENT_DECISION.md`
20. `docs/ADR_RUNTIME_DECISION_AND_DRY_RUN_GATEWAY.md`
21. `docs/MATRIX_OS_ROUTE_PLAN_HANDOFF_CONTRACT.md`
22. `docs/MATRIX_OS_ROUTE_PLAN_VIEWER_OUTPUTS.md`
23. `docs/MATRIX_OS_ROUTE_PLAN_PANEL_MODEL.md`
24. `docs/MATRIX_OS_ROUTE_PLAN_PANEL_GOLDEN_OUTPUTS.md`
25. `docs/MATRIX_OS_ROUTE_PLAN_PANEL_ATTACHMENT.md`
26. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_SELECTOR.md`
27. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_UI_STATE.md`
28. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_WIDGET.md`
29. `docs/DOCUMENTATION_INVENTORY.md`

Module-specific docs:

| Module | Docs |
|---|---|
| Compliance Change Control | `docs/COMPLIANCE_CHANGE_CONTROL_*` |
| Accountable Agent Layer | `docs/ACCOUNTABLE_AGENT_LAYER_*` |
| ASPICE Support Utilities | `conduvera/skills/aspice_conflict_detector/SKILL.md`, `conduvera/skills/aspice_link_manager/README.md` |
| Evidence Backbone | `docs/MATRIX_OS_EVIDENCE_BACKBONE.md`, `conduvera/evidence/` |
| agent-evidence-plane Thin Adapter | `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`, `conduvera/evidence/adapters/agent_evidence_plane.py` |
| Safety Guard Adapter Contract | `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md`, `conduvera/evidence/adapters/safety_guard.py` |
| Evidence Adapter Registry | `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md`, `conduvera/evidence/adapters/registry.py` |
| failure-driven-loop Thin Adapter | `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md`, `conduvera/evidence/adapters/failure_loop.py` |
| Evidence Operator Reports | `docs/MATRIX_OS_EVIDENCE_OPERATOR_REPORTS.md`, `conduvera/evidence/reporting.py`, `tests/fixtures/evidence/operator_report/`, `tests/test_evidence_report_contract_version.py` |
| Operator Workflow | `docs/MATRIX_OS_OPERATOR_WORKFLOW.md`, `docs/MATRIX_OS_OPERATOR_WORKFLOW_PRODUCT_COHERENCE.md`, `conduvera/harness/operator_status.py`, `tests/test_harness_operator_status.py` |
| Governance Policy | `docs/MATRIX_OS_GOVERNANCE_POLICY.md`, `CODEOWNERS`, `.github/workflows/matrix-os-evidence-quality.yml` |
| Product Coherence Scenarios | `docs/MATRIX_OS_PRODUCT_COHERENCE.md`, `tests/test_product_coherence_scenarios.py` |
| Harness Gateway Contract | `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md`, `docs/ADR_RUNTIME_DECISION_AND_DRY_RUN_GATEWAY.md`, `docs/MATRIX_OS_ROUTE_PLAN_HANDOFF_CONTRACT.md`, `docs/MATRIX_OS_ROUTE_PLAN_VIEWER_OUTPUTS.md`, `docs/MATRIX_OS_ROUTE_PLAN_PANEL_MODEL.md`, `docs/MATRIX_OS_ROUTE_PLAN_PANEL_GOLDEN_OUTPUTS.md`, `docs/MATRIX_OS_ROUTE_PLAN_PANEL_ATTACHMENT.md`, `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_SELECTOR.md`, `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_UI_STATE.md`, `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_WIDGET.md`, `conduvera/harness/gateway.py`, `conduvera/harness/route_plan.py`, `conduvera/harness/route_plan_viewer.py`, `conduvera/harness/route_plan_artifacts.py`, `src/ui/widgets/route_plan_panel.py`, `src/ui/widgets/route_plan_artifact_picker.py`, `tests/test_harness_route_plan.py`, `tests/test_route_plan_golden_fixtures.py`, `tests/test_matrix_ui_route_plan_viewer.py`, `tests/test_route_plan_viewer_golden_outputs.py`, `tests/test_route_plan_panel_model.py`, `tests/test_route_plan_panel_golden_outputs.py`, `tests/test_matrix_ui_route_plan_panel_attachment.py`, `tests/test_route_plan_artifact_selector.py`, `tests/test_route_plan_artifact_picker_state.py`, `tests/test_route_plan_artifact_picker_widget.py`, `tests/fixtures/harness/route_plan/`, `tests/fixtures/harness/route_plan_view/`, `tests/fixtures/harness/route_plan_panel/` |
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
- PR #16 Evidence Operator Report Pack
- PR #17 Evidence Report Golden Fixtures
- PR #18 Evidence Report Contract Versioning + CI Gate
- PR #19 Governance Hardening & Required Review Policy
- PR #20 Governance Enforcement Decision
- PR #21 Operator Workflow Vertical Slice
- PR #22 Pi Agent Harness Evaluation

- PR #23 Runtime Decision / Dry-Run Gateway
- PR #24 Route Plan JSON Output
- PR #25 Route Plan Golden Fixtures & Operator Handoff Contract
- PR #26 Minimal Matrix UI Route-Plan Viewer Stub

- PR #27 Route-Plan Viewer Golden Outputs & Operator Snapshot Pack

- PR #28 Minimal Textual Route-Plan Panel Model

- PR #29 Route-Plan Panel Golden Render Fixtures

- PR #30 Non-Live Matrix UI Route-Plan Panel Attachment

- PR #31 Non-Live Route-Plan Artifact Selector

- PR #32 Non-Live Route-Plan Artifact Picker UI State

Current release train (Delivery Workspace trusted v1):

- PR #59–#74 Delivery Workspace backend + UI + SSE + corrective gates
- PR #76 Trusted PublishCandidate domain + atomic exact-changeset publication

Historical (non-live scaffolding, superseded):

- PR #33 Non-Live Route-Plan Artifact Picker List Widget (historical, replaced by the Delivery Workspace)

Planned:

- PR #34 Non-Live Picker Selection Preview
- Later focused adapter slices for CAS, peekxd, OpenCode plugin, and ai-router
