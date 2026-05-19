# Matrix OS Route-Plan Panel Golden Outputs

Status: stable UI snapshot contract for the non-interactive route-plan panel renderer.

## Purpose

This document defines the golden-output contract for `render_route_plan_panel_text(...)`. The contract freezes the operator-facing panel text that a future Matrix UI panel can use as a stable snapshot target.

The data path is:

```text
route-plan.v1 JSON -> build_route_plan_panel(...) -> render_route_plan_panel_text(...) -> exact panel snapshot text
```

The snapshots are not produced by scraping CLI output. They are rendered from the validated panel model, which itself consumes the existing `route-plan.v1` source contract through the route-plan viewer validation path.

## Fixture list

Golden panel snapshots live under `tests/fixtures/harness/route_plan_panel/` and mirror the canonical route-plan fixture stems:

| Route-plan fixture | Panel golden output | Scenario |
|---|---|---|
| `agent-task.json` | `agent-task.txt` | Agent task with evidence capture |
| `dangerous-file-operation.json` | `dangerous-file-operation.txt` | Safety boundary before a dangerous file operation |
| `failed-agent-run.json` | `failed-agent-run.txt` | Failed-run review with evidence-only rule proposal |
| `operator-ui-view.json` | `operator-ui-view.txt` | Future Matrix UI/editor display handoff |
| `unknown-intent.json` | `unknown-intent.txt` | Fail-closed unknown intent requiring human route decision |

## Why this matters

PR #25 stabilized the route-plan JSON handoff. PR #26 added a read-only viewer. PR #27 locked viewer text snapshots. PR #28 added a Textual-compatible panel model.

This slice locks the panel renderer output itself, so the future Matrix UI route can attach to a stable panel display contract without scraping CLI output and without inventing runtime behavior.

## Boundaries

The golden outputs intentionally show boundary evidence:

- `Runtime execution: no`
- `Shell execution: no`
- `Destructive command path: no`
- `Production dashboard claim: no`
- `Panel boundary: Display-only ... no live UI route ...`

This contract does not implement:

- live Matrix UI route/sidebar integration,
- interactive Textual behavior,
- app startup,
- runtime execution,
- agent execution,
- Hermes/OpenCode/Zed/MCP implementation,
- Pi fork or Raspberry Pi/SSH/pi-hermes work,
- new adapters,
- shell interception,
- destructive command paths,
- production dashboard behavior,
- branch protection or governance changes.

## Validation

`tests/test_route_plan_panel_golden_outputs.py` verifies:

- exact fixture parity between canonical `route-plan.v1` JSON files and panel text snapshots,
- exact `render_route_plan_panel_text(build_route_plan_panel(...))` equality for every fixture,
- non-execution and no-dashboard boundary invariants,
- product scenario content for agent-task, dangerous-action, failed-run, UI-view, and unknown-intent outputs,
- `MatrixRoutePlanPanel.from_route_plan_file(...)` construction without starting or mounting a live Textual app,
- compatibility with existing route-plan JSON fixture, viewer golden-output, and panel-model tests.
