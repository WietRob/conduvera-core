# Matrix OS Route-Plan Artifact Picker Widget

Status: non-live Textual-compatible picker/list widget over canonical route-plan artifacts.

## Purpose

The route-plan UI path now has a visible read-only picker/list widget instead of only a text state prefix. Operators can see the available canonical artifacts and the selected artifact before reading the route-plan panel body.

## Read-only widget contract

Module:

- `src/ui/widgets/route_plan_artifact_picker.py`

Public construction helpers:

- `build_route_plan_artifact_picker_model(selected_artifact_id: str | None = None)`
- `render_route_plan_artifact_picker_text(model)`
- `MatrixRoutePlanArtifactPicker.from_selected_artifact(artifact_id)`

The widget is a Textual `Static` shell. It is safe to construct in tests and does not require `app.run()`.

## Display fields

The picker render includes:

- selected artifact id,
- selected artifact label,
- selected artifact scenario,
- all five canonical artifacts,
- visual selected marker,
- runtime/file/browser/generation/dashboard boundary flags.

## Selected marker

The selected artifact line is marked with:

```text
▶ artifact-id
```

Non-selected artifacts are rendered without the marker.

## Relationship to existing route-plan objects

```text
RoutePlanArtifact registry
-> RoutePlanArtifactPickerState
-> MatrixRoutePlanArtifactPickerModel
-> MatrixRoutePlanArtifactPicker render
-> MatrixRoutePlanPanel render prefix
-> existing route-plan panel body
```

The picker widget does not duplicate selector metadata. It reads through the existing `curaops.harness.route_plan_artifacts` registry/state helpers.

## Boundaries

This widget does not add:

- live switching,
- interactive Textual behavior,
- runtime execution,
- agent execution,
- shell/destructive command paths,
- dynamic user file loading,
- arbitrary filesystem browsing,
- file watching,
- route-plan generation,
- production dashboard behavior,
- MCP/Zed integration,
- adapter expansion,
- branch protection or governance changes.

## Validation

- `tests/test_route_plan_artifact_picker_widget.py`
- `tests/test_matrix_ui_route_plan_panel_attachment.py`
