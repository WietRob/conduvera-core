# Matrix OS Route-Plan Artifact Picker UI State

Status: non-live UI state for the canonical route-plan artifact picker.

## Purpose

The route-plan panel now carries explicit read-only picker state so operators can see which canonical artifact is selected before reading the panel body.

This slice does not add live switching. It only exposes deterministic state for the selected artifact and the available canonical artifact ids.

## Data path

```text
artifact id
-> RoutePlanArtifact registry
-> RoutePlanArtifactPickerState
-> rendered picker state
-> MatrixRoutePlanPanel renderable prefix
-> existing panel snapshot body
```

Default behavior remains:

```text
MatrixOS._create_view_widget("route_plan") -> selected artifact: agent-task
```

Explicit test/helper behavior:

```text
MatrixOS._create_route_plan_panel_view("dangerous-file-operation")
```

## Picker state fields

- `schema_version: route-plan-artifact-picker.v1`
- `selected_artifact_id`
- `selected_label`
- `selected_scenario`
- canonical artifact list
- `runtime_execution: false`
- `dynamic_user_file_loading: false`
- `arbitrary_filesystem_browser: false`
- `route_plan_generation: false`
- `dashboard_claim: false`
- read-only display boundary

## Available artifacts

| Artifact id | Label | Scenario |
|---|---|---|
| `agent-task` | Agent task with evidence capture | AI-assisted code change |
| `dangerous-file-operation` | Dangerous file operation safety gate | dangerous file operation |
| `failed-agent-run` | Failed agent run review loop | failed agent run |
| `operator-ui-view` | Operator UI view handoff | operator wants UI view |
| `unknown-intent` | Unknown intent fail-closed route | fail-closed unknown intent |

## Boundaries

This picker state does not:

- execute runtime candidates,
- run agents,
- execute shell commands,
- create destructive command paths,
- generate new route plans,
- watch files,
- load user uploads,
- browse arbitrary filesystem paths,
- implement MCP/Zed,
- expand adapters,
- claim production dashboard behavior.

## Validation

- `tests/test_route_plan_artifact_picker_state.py`
- `tests/test_matrix_ui_route_plan_panel_attachment.py`
