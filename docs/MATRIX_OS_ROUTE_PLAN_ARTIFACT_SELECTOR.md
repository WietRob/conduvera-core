# Matrix OS Route-Plan Artifact Selector

Status: non-live selector over canonical route-plan artifacts.

## Purpose

The route-plan panel is no longer tied to a single demo fixture. Matrix OS now has a small read-only selector model that exposes the canonical `route-plan.v1` artifacts by stable id and resolves them into panel input paths.

The selector is intentionally narrow: it lists only known artifacts under `tests/fixtures/harness/route_plan/` and fails closed for unknown ids.

## Artifact list

| Artifact id | Scenario | Expected candidate | Default |
|---|---|---|---|
| `agent-task` | AI-assisted code change | `hermes` | yes |
| `dangerous-file-operation` | Dangerous file operation | `safety-guard` | no |
| `failed-agent-run` | Failed agent run | `failure-driven-loop` | no |
| `operator-ui-view` | Operator wants UI view | `matrix-ui-code-editor` | no |
| `unknown-intent` | Fail-closed unknown intent | none | no |

## Selection flow

```text
artifact id
-> RoutePlanArtifact
-> route-plan.v1 path
-> MatrixRoutePlanPanel.from_route_plan_file(...)
-> panel model
-> deterministic panel render
```

Default behavior:

```text
default_route_plan_artifact() -> agent-task
MatrixOS._create_view_widget("route_plan") -> MatrixOS._create_route_plan_panel_view(None)
```

Explicit test/helper behavior:

```text
MatrixOS._create_route_plan_panel_view("dangerous-file-operation")
```

## Why this matters

The non-live route-plan panel is now useful across the five canonical operator scenarios instead of being hardcoded to `agent-task.json`. Future UI work can present the artifact list as a read-only selector without scraping CLI output or browsing arbitrary files. `docs/MATRIX_OS_ROUTE_PLAN_ARTIFACT_PICKER_UI_STATE.md` defines the follow-up UI state that displays selected artifact id, label, scenario, available artifacts, and no-runtime/no-browser boundaries in the non-live panel path.

## Boundaries

This selector does not:

- execute route-plan candidates,
- run agents,
- generate new route plans,
- browse arbitrary filesystem paths,
- load user uploads,
- watch files live,
- intercept shell commands,
- create destructive command paths,
- implement MCP/Zed integrations,
- expand adapters,
- claim production dashboard behavior.

Unknown artifact ids fail closed with `KeyError`.

## Validation

- `tests/test_route_plan_artifact_selector.py`
- `tests/test_route_plan_artifact_picker_state.py`
- `tests/test_matrix_ui_route_plan_panel_attachment.py`
