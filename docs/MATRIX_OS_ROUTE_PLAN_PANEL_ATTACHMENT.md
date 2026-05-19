# Matrix OS Route-Plan Panel Attachment

Status: non-live Matrix UI route-plan panel attachment.

## Purpose

This slice makes the route-plan panel discoverable from the preserved Matrix UI shell without turning it into a live runtime route or production dashboard.

The attachment path is:

```text
Sidebar Route Plan button -> MatrixOS route_plan view -> route-plan artifact selector -> MatrixRoutePlanPanel.from_route_plan_file(...) -> stable panel snapshot contract
```

The view resolves its default artifact through `curaops.harness.route_plan_artifacts.default_route_plan_artifact()`. The default remains `agent-task`, but tests can select any canonical artifact id through `MatrixOS._create_route_plan_panel_view(artifact_id)`. The app helper also prepends read-only picker state so the panel path displays the selected artifact id, label, scenario, available artifacts, and no-runtime/no-browser boundaries before the stable panel body.

## Implemented UI surface

`src/core/app.py` now exposes:

- a `Route Plan` sidebar button with id `btn_route_plan`,
- a `route_plan` view factory in `MatrixOS._create_view_widget(...)`,
- `MatrixOS.action_show_route_plan()` status/update dispatch,
- button dispatch from `btn_route_plan` to the non-live panel view,
- selector-backed artifact resolution for the five canonical route-plan fixtures,
- read-only picker state rendering for selected artifact id, label, scenario, available artifacts, and boundaries.

The rendered content is still produced from the validated route-plan panel model and panel golden snapshot contract.

## What this proves

Matrix OS can now expose a discoverable route-plan panel surface in the existing Textual UI shell while preserving the no-runtime contract:

```text
route-plan.v1 JSON -> artifact selector -> selected artifact path -> panel model -> panel renderer -> non-live Matrix UI view factory
```

This closes the previous gap between a standalone panel model and an app-discoverable UI route.

## Boundaries

This attachment does not implement:

- runtime execution,
- agent execution,
- live runner state,
- interactive Textual behavior,
- arbitrary filesystem browsing,
- user-upload loading,
- live file watching,
- new route-plan generation,
- Hermes/OpenCode/Zed/MCP implementation,
- adapter expansion,
- shell interception,
- destructive command paths,
- production dashboard behavior,
- branch protection or governance changes.

The route-plan panel remains display-only. `Runtime execution: no`, `Shell execution: no`, `Destructive command path: no`, and `Production dashboard claim: no` remain required boundary evidence.

## Validation

`tests/test_matrix_ui_route_plan_panel_attachment.py` verifies:

- the route-plan panel is discoverable from the sidebar,
- the Matrix app can create the `route_plan` view without starting a live runtime,
- the app-created panel matches the stable panel snapshot contract,
- all five canonical artifacts can be selected and matched to their panel snapshots,
- selected artifact id, label, and scenario are displayed in the non-live panel render path,
- unknown artifact ids fail closed,
- the default `route_plan` view still resolves to `agent-task`,
- the sidebar button dispatches to the non-live panel view,
- the attachment does not create new route plans or execute anything.

Existing panel model, panel golden-output, viewer, route-plan, and widget tests remain compatibility gates.

## Future path

A later slice may add non-live artifact picker interaction or selector list display refinement. That should remain display-only until a separate reviewed runtime-execution design exists.
