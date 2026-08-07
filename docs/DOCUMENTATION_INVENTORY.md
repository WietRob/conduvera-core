# Matrix OS Documentation Inventory

Status: authoritative documentation inventory for the architecture/documentation index slice.

This inventory classifies authoritative and historical Matrix OS documents across the current release train. Historical documents remain available for context, but current implementation guidance should start from the authoritative docs listed here.

| File | Current role | Action | Reason |
|---|---|---|---|
| `README.md` | Entry point | Update | Previous README described an older TUI-centric state; now points to the merged package/CLI harness docs |
| `docs/MATRIX_OS_ARCHITECTURE.md` | Authoritative overview | Create | Needed top-level architecture aligned to the current merged Matrix OS package/CLI harness state |
| `docs/MATRIX_OS_MODULE_BOUNDARIES.md` | Authoritative boundary map | Create | Needed clear ownership split for harness, CCC, AAL, ASPICE, and external engines |
| `docs/MATRIX_OS_SCAFFOLDING.md` | Authoritative scaffolding contract | Create | Preserves original Matrix UI and defines MCP/editor scaffolding boundaries without implementation claims |
| `docs/MATRIX_OS_EVIDENCE_BACKBONE.md` | Authoritative evidence backbone contract | Create | Defines Matrix OS harness-side event envelope, local JSONL store, and adapter boundary without absorbing agent-evidence-plane |
| `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md` | Authoritative thin-adapter boundary | Create | Defines read-only local agent-evidence-plane translation without vendoring or product launch |
| `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md` | Authoritative Safety Guard adapter boundary | Create | Defines read-only trust/safety evidence translation without execution, shell interception, vendoring, or release creation |
| `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md` | Authoritative evidence adapter registry | Create | Metadata-only index of registered adapters, event types, CLI commands, and execution/readiness boundaries |
| `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md` | Authoritative failure-loop adapter boundary | Create | Defines translation-only failure/result evidence mapping without runtime execution, rule enforcement, or external repo mutation |
| `docs/MATRIX_OS_PRODUCT_COHERENCE.md` | Authoritative product coherence/value proof | Create | Shows how merged modules answer operator questions together without monster-system overclaim |
| `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md` | Authoritative generic gateway boundary | Create | Defines Hermes/OpenCode/Zed/MCP/local-shell/peekxd future descriptors without runtime execution |
| `docs/MATRIX_OS_ROUTE_PLAN_HANDOFF_CONTRACT.md` | Authoritative route-plan handoff contract | Create | Defines stable `route-plan.v1` JSON fixtures for future UI/automation consumers without runtime execution |
| `docs/MATRIX_OS_ROUTE_PLAN_VIEWER_OUTPUTS.md` | Authoritative route-plan viewer snapshot contract | Create | Defines exact read-only `route-plan-view` operator outputs for future UI panel consumers without live UI/runtime execution |
| `docs/MATRIX_OS_ROUTE_PLAN_PANEL_MODEL.md` | Authoritative route-plan panel model contract | Create | Defines non-interactive Textual-compatible panel model over validated route-plan fixtures without live UI/runtime execution |
| `docs/MATRIX_OS_ROUTE_PLAN_PANEL_GOLDEN_OUTPUTS.md` | Authoritative route-plan panel snapshot contract | Create | Defines exact panel renderer golden outputs as future UI snapshot contract without live UI/runtime execution |
| `docs/MATRIX_OS_ROUTE_PLAN_PANEL_ATTACHMENT.md` | Authoritative non-live route-plan panel UI attachment | Create | Defines discoverable Matrix UI sidebar/view attachment over the panel snapshot contract without runtime/dashboard behavior |
| `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_SELECTOR.md` | Authoritative non-live route-plan artifact selector | Create | Defines fixed canonical artifact selection for the route-plan panel without arbitrary filesystem browsing or execution |
| `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_UI_STATE.md` | Authoritative non-live route-plan artifact picker UI state | Create | Defines selected artifact id/label/scenario display and read-only picker boundaries in the non-live panel path |
| `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_WIDGET.md` | Authoritative non-live route-plan artifact picker widget | Create | Defines visible read-only picker/list widget, selected marker, and construction-only Textual shell |
| `docs/MATRIX_OS_UI_VALUE_MAP.md` | Authoritative original UI value map | Create | Maps preserved TUI surfaces to future CR/evidence/runner/editor use without UI rewrite or dashboard claim |
| `docs/MATRIX_OS_ORIGIN_AND_PROVENANCE.md` | Authoritative provenance note | Create | Separates confirmed Matrix UI lineage facts from UNKNOWN Pi/fork claims |
| `docs/MATRIX_OS_EVIDENCE_OPERATOR_REPORTS.md` | Authoritative evidence report layer | Update | Defines read-only text/Markdown/JSON operator reports, `MXOS-REPORT-1.0` contract versioning, golden-output regression fixtures, and the focused CI quality gate without runtime or production-audit claims |
| `docs/MATRIX_OS_OPERATOR_WORKFLOW_PRODUCT_COHERENCE.md` | Authoritative operator workflow framing | Create | Records the product-coherence check required before coding the read-only operator status slice |
| `docs/MATRIX_OS_OPERATOR_WORKFLOW.md` | Authoritative operator workflow slice | Create | Explains `harness status`, connected modules, UI attach point, and read-only boundaries |
| `docs/MATRIX_OS_GOVERNANCE_POLICY.md` | Authoritative governance policy | Update | Documents verified branch protection, required evidence/report status check, review roles, CODEOWNERS routing draft, and links to the enforcement decision |
| `docs/MATRIX_OS_GOVERNANCE_ENFORCEMENT_DECISION.md` | Authoritative governance decision record | Create | Records the required approval vs operational Kanban decision and keeps settings unchanged for now |
| `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md` | Authoritative command/module index | Create | Needed navigable index for compliance, accountability, ASPICE, and CLI commands |
| `docs/RELEASE_TRAIN_STATUS.md` | Authoritative release status | Create | Needed current release-train status and next planned PRs |
| `docs/COMPLIANCE_CHANGE_CONTROL_ARCHITECTURE.md` | Current CCC architecture | Keep | Describes merged PR #5 module; some historical API sketches remain non-authoritative next to current CLI/API docs |
| `docs/COMPLIANCE_CHANGE_CONTROL_IMPLEMENTATION_CONTRACT.md` | Current CCC implementation contract | Keep | Useful implementation detail for merged PR #5 |
| `docs/COMPLIANCE_CHANGE_CONTROL_PROCESS.md` | Current CCC process | Keep | Describes merged PR #5 process |
| `docs/COMPLIANCE_CHANGE_CONTROL_RULES.md` | Current CCC rules | Keep | Describes merged PR #5 rules; CLI help remains command source of truth |
| `docs/ACCOUNTABLE_AGENT_LAYER_ARCHITECTURE.md` | Current AAL architecture | Keep | Describes merged PR #6 slice |
| `docs/ACCOUNTABLE_AGENT_LAYER_IMPLEMENTATION.md` | Current AAL implementation | Keep | Describes merged PR #6 files and behavior |
| `docs/ACCOUNTABLE_AGENT_LAYER_PROCESS.md` | Current AAL process | Keep | Describes merged PR #6 process |
| `docs/ACCOUNTABLE_AGENT_LAYER_RULES.md` | Current AAL rules | Keep | Describes merged PR #6 rules |
| `conduvera/skills/aspice_conflict_detector/SKILL.md` | Current ASPICE utility doc | Keep | Describes merged PR #7 conflict detector |
| `conduvera/skills/aspice_link_manager/README.md` | Current ASPICE utility doc | Keep | Describes merged PR #7 link manager |
| `docs/QUICKSTART.md` | Historical / deprecated | Deprecate | Describes older app-centric quickstart; current CLI docs are authoritative |
| `docs/UI_DESIGN_COMPARISON.md` | Historical / deprecated | Deprecate | UI comparison is not merged runtime scope |
| `docs/PHASE1_ENHANCEMENTS.md` | Historical / deprecated | Deprecate | Older UI/phase planning document; not current architecture |
| `docs/PHASE2_IMPLEMENTATION.md` | Historical / deprecated | Deprecate | Older functional-widget implementation notes; not current architecture |
| `docs/PHASE5_IMPLEMENTATION.md` | Historical / deprecated | Deprecate | Older phase implementation notes; not current release-train source |
| `docs/PHASE6_IMPLEMENTATION.md` | Historical / deprecated | Deprecate | AI-router integration notes are not current merged Matrix OS runtime |
| `docs/PHASE6.1_IMPROVEMENTS.md` | Historical / deprecated | Deprecate | Routing-improvement notes are future/legacy context only |
| `docs/PHASE7_IMPLEMENTATION.md` | Historical / deprecated | Deprecate | BERT routing/user-feedback notes are not current merged runtime |
| `docs/PHASE7_PLAN.md` | Historical / deprecated | Deprecate | BERT routing/user-feedback plan is not current release-train source |
| `ANALYSIS_MATRIX_OS_TUI.md` | Historical / deprecated | Deprecate | TUI analysis remains reference material, not current merged module map |

## Current authoritative reading order

1. `README.md`
2. `docs/MATRIX_OS_PRODUCT_COHERENCE.md`
3. `docs/MATRIX_OS_ARCHITECTURE.md`
4. `docs/MATRIX_OS_MODULE_BOUNDARIES.md`
5. `docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md`
6. `docs/MATRIX_OS_ROUTE_PLAN_HANDOFF_CONTRACT.md`
7. `docs/MATRIX_OS_ROUTE_PLAN_VIEWER_OUTPUTS.md`
8. `docs/MATRIX_OS_ROUTE_PLAN_PANEL_MODEL.md`
9. `docs/MATRIX_OS_ROUTE_PLAN_PANEL_GOLDEN_OUTPUTS.md`
10. `docs/MATRIX_OS_ROUTE_PLAN_PANEL_ATTACHMENT.md`
11. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_SELECTOR.md`
12. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_UI_STATE.md`
13. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_WIDGET.md`
14. `docs/MATRIX_OS_UI_VALUE_MAP.md`
15. `docs/MATRIX_OS_ORIGIN_AND_PROVENANCE.md`
16. `docs/MATRIX_OS_SCAFFOLDING.md`
17. `docs/MATRIX_OS_EVIDENCE_BACKBONE.md`
18. `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`
19. `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md`
20. `docs/MATRIX_OS_EVIDENCE_ADAPTER_REGISTRY.md`
21. `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md`
22. `docs/MATRIX_OS_EVIDENCE_OPERATOR_REPORTS.md`
23. `docs/MATRIX_OS_OPERATOR_WORKFLOW_PRODUCT_COHERENCE.md`
24. `docs/MATRIX_OS_OPERATOR_WORKFLOW.md`
25. `docs/MATRIX_OS_GOVERNANCE_POLICY.md`
26. `docs/MATRIX_OS_GOVERNANCE_ENFORCEMENT_DECISION.md`
27. `docs/COMPLIANCE_ACCOUNTABILITY_INDEX.md`
28. `docs/RELEASE_TRAIN_STATUS.md`
29. Module-specific docs for CCC, AAL, and ASPICE as needed

## Deprecated-document rule

Deprecated documents are retained for historical context only. If a deprecated document conflicts with the current architecture, module boundaries, release-train status, or CLI help, the current authoritative docs and CLI help win.
