# Matrix OS UI Value Map

Status: preservation and future-value map for the original Matrix UI/TUI.

This document does not rewrite the UI and does not claim a production dashboard. It maps where the existing Matrix UI surfaces could later show compliance/accountability/evidence/harness information.

## Confirmed preserved UI surfaces

| Surface | Source | Current status | Future value slot |
|---|---|---|---|
| Textual app shell | `src/core/app.py` | preserved | host for operator views |
| Entrypoints | `matrix-os`, `mxos`, `python3 -m src.core.app` | preserved | launch preserved TUI |
| Matrix rain identity | `src/ui/widgets/matrix_rain.py`, `src/ui/themes/matrix.tcss` | preserved | product identity / operator context |
| Sidebar navigation | `src/core/app.py` | preserved | future CR/evidence/approval navigation |
| File browser | `src/ui/widgets/file_browser.py` | preserved | inspect changed files, requirements, evidence artifacts |
| Terminal | `src/ui/widgets/terminal.py` | preserved | future runner console view, still not automatic shell interception |
| Process monitor | `src/ui/widgets/process_monitor.py` | preserved | future runner/tool status view |
| Code editor | `src/ui/widgets/code_editor.py` | preserved | future CR-linked edit/review surface |
| Split pane | `src/ui/widgets/split_pane.py` | preserved | future editor + evidence/terminal view |
| Monitoring dashboard widget | `src/ui/widgets/monitoring_dashboard.py` | preserved historical/current widget | not a production dashboard claim |
| Design comparison docs | `docs/UI_DESIGN_COMPARISON.md`, `ANALYSIS_MATRIX_OS_TUI.md` | historical reference | visual/product lineage reference |

## Future value mapping

| Product information | Candidate UI place | Why |
|---|---|---|
| CR status | Sidebar badge or status panel | operators need change intent before acting |
| Evidence requirements | Main content panel / split pane | shows required handoff evidence before any future execution |
| Route-plan candidate ranking | Code editor / split pane | displays existing `route-plan.v1` JSON artifacts as a read-only route-plan viewer stub and non-interactive Textual-compatible panel model with exact viewer and panel snapshot fixtures |
| Runner status | Process monitor / terminal surface | maps naturally to running/pending/exited tools |
| Editor/Zed-like workflow | Code editor / split pane | attach requirement and CR context to files |
| Approval inbox | Sidebar + main approval panel | future safety/change approvals without shell interception |
| Traceability gap | File browser + evidence timeline | link requirement docs to code/tests/evidence |
| Safety block | Status bar or evidence timeline | make blocked action/reason visible |
| Rule proposal | Evidence timeline | show proposed rule without enforcing it |

## Zed / editor boundary

Zed/MCP remains future adapter work.

| Boundary | Rule |
|---|---|
| Matrix OS | owns generic editor surface descriptor and evidence/UI mapping |
| Zed | owns editor/plugin/runtime |
| Integration path | Gateway Registry -> EditorSurfaceDescriptor -> MCP/adapter PR |
| Hardcoding ban | no Zed-specific logic inside CCC, AAL, ASPICE, or Evidence Backbone |

## No rewrite claim

This slice intentionally does not:

- rewrite `src/core/app.py`,
- change Textual widget behavior outside the route-plan panel model,
- build a production dashboard,
- implement an MCP server,
- implement Zed runtime integration,
- implement runner execution,
- add shell interception.

## Validation

Current UI/widget tests still pass. `tests/test_product_coherence_scenarios.py` verifies that the scaffold manifest still exposes the original Matrix UI, Matrix rain path, terminal/process/file/editor surfaces, and no-UI-rewrite/no-production-dashboard exclusions. `tests/test_matrix_ui_route_plan_viewer.py` verifies the read-only route-plan viewer stub consumes existing `route-plan.v1` fixtures and renders intent, chosen candidate, candidate ranking, evidence requirements, approval gate, and non-execution boundaries without live runtime or dashboard claims. `tests/test_route_plan_viewer_golden_outputs.py` locks the operator snapshots that a future non-interactive UI panel can consume. `tests/test_route_plan_panel_model.py` verifies the Textual-compatible route-plan panel model can be built and its widget shell constructed without running a live app. `tests/test_route_plan_panel_golden_outputs.py` locks exact panel renderer snapshots as the future UI snapshot contract.
