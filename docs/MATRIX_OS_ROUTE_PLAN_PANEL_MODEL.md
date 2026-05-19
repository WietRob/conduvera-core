# Matrix OS Route-Plan Panel Model

Status: minimal, non-interactive Textual-compatible panel model for route-plan handoff artifacts.

## Purpose

The route-plan panel model moves the route-plan UI path one step closer to the preserved Matrix UI without starting a live UI route or claiming dashboard behavior.

The data path is:

```text
route-plan.v1 JSON -> validated viewer model -> Textual-compatible panel model
```

The panel model consumes the same validated source contract as `harness route-plan-view`. It structures the stable operator fields for a future Matrix UI panel, while keeping execution disabled.

## Relationship to the release train

| Slice | Relationship |
|---|---|
| PR #25 route-plan JSON fixtures | Provides canonical `route-plan.v1` handoff artifacts |
| PR #26 route-plan viewer | Validates source artifacts and creates the read-only viewer model |
| PR #27 viewer golden outputs | Stabilizes operator-facing text snapshots |
| PR #28 route-plan panel model | Adapts the validated viewer model into a Textual-compatible panel model |

## Implemented surface

The implementation lives in `src/ui/widgets/route_plan_panel.py`:

- `MatrixRoutePlanPanelModel`
- `build_route_plan_panel(input_path)`
- `render_route_plan_panel_text(model)`
- `MatrixRoutePlanPanel.from_route_plan_file(input_path)`

`MatrixRoutePlanPanel` is a non-interactive Textual `Static` widget shell. Tests construct it without running a live app.

## Stable panel fields

The panel model carries:

- `schema_version: matrix-ui-route-plan-panel.v1`
- `source_schema_version: route-plan.v1`
- intent
- chosen candidate, or `none`
- candidate ranking
- evidence requirements
- approval gate
- fail-closed state
- unknown capabilities
- runtime execution boundary
- shell/destructive-command boundary
- production dashboard boundary
- non-execution boundary
- panel boundary
- operator snapshot note

## Why this closes a product gap

Before this slice, Matrix OS had a stable CLI/viewer output but no UI-side model shape. This panel model creates the attach point that a future Matrix UI route can consume without scraping terminal output and without inventing new runtime behavior.

## Boundaries

This slice does not implement:

- live UI integration,
- interactive dashboard behavior,
- runtime execution,
- agent execution,
- Hermes/OpenCode/Zed/MCP implementation,
- adapter expansion,
- shell interception,
- destructive command execution,
- branch protection or governance changes.

`Runtime execution: no` and `Production dashboard claim: no` are intentional boundary evidence.

## Validation

`tests/test_route_plan_panel_model.py` verifies:

- canonical route-plan fixtures build panel models,
- the panel uses the existing viewer/source validation path,
- agent-task, dangerous-action, failed-run, UI-view, and unknown-intent scenarios preserve their operator meaning,
- invalid schema and execution-enabled source artifacts are rejected,
- rendering is deterministic,
- the Textual widget shell can be constructed without running a live app,
- existing widget tests still pass as a compatibility gate.

## Future path

The next focused slice can attach the panel to an actual Matrix UI route only after explicit review. That future route should remain display-only until a separate reviewed runtime-execution design exists.
