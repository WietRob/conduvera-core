# Matrix OS Harness Gateway Architecture

Status: generic contract for future Matrix OS harness/gateway integrations. This now includes a descriptor-only dry-run route planner; no runtime execution is implemented.

This document defines how Matrix OS can later launch, observe, approve/block, and convert evidence from external runners/tools without hardcoding any runner into Compliance Change Control, Accountable Agent Layer, ASPICE, or Evidence Backbone.

No runtime is implemented by this slice.

## Gateway principle

Matrix OS owns generic harness boundaries, not external engines.

| Matrix OS may own | Matrix OS must not claim here |
|---|---|
| Runner descriptors | real Hermes/OpenCode/local-shell execution |
| Tool descriptors | shell interception or destructive execution |
| Editor surface descriptors | Zed plugin/runtime implementation |
| Gateway capability descriptors | MCP server runtime |
| Evidence conversion contracts | automatic rule enforcement |
| Approval/block boundary metadata | production safety policy |

## Contract package

Implemented in:

```text
curaops/harness/gateway.py
```

Descriptors:

| Descriptor | Purpose |
|---|---|
| `GatewayCapability` | names what Matrix OS can launch/observe/approve/convert later |
| `RunnerDescriptor` | describes future runner families such as Hermes/OpenCode/local shell/Pi Agent Harness |
| `ToolDescriptor` | describes evidence producers, safety tools, and computer-use tools |
| `EditorSurfaceDescriptor` | describes Matrix UI and future editor/MCP surfaces |
| `HarnessGatewayRegistry` | stable fail-closed registry of the descriptors |
| `OperatorIntent` / `RoutePlan` | dry-run route planning from operator intent to ranked descriptors, evidence outputs, and approval gate |
| `route-plan.v1` JSON | stable operator handoff contract for future UI/automation consumers, locked by golden fixtures |

## Capability boundaries

| Capability | Matrix OS ownership now | Runtime implemented? |
|---|---|---|
| launch | descriptor only | no |
| observe | evidence contract | no |
| approve/block | policy decision boundary only | no |
| convert evidence | translation adapter contract | no |

## Registered runner families

| Runner | Family | Status | Boundary |
|---|---|---|---|
| Hermes | agent orchestrator | future-adapter-contract-only | standalone; not executed by Matrix OS |
| OpenCode | coding agent | future-adapter-contract-only | standalone; not executed by Matrix OS |
| local shell | shell | future-adapter-contract-only | no shell interception or execution in this slice |
| Pi Agent Harness | agent-harness runtime candidate | future-adapter-contract-only | `earendil-works/pi` descriptor only; not Raspberry Pi hardware; not executed by Matrix OS |

## Registered tool/capability surfaces

| Tool | Family | Current role |
|---|---|---|
| agent-evidence-plane | evidence producer | translation-only adapter exists |
| CuraOps Safety Guard | safety producer | translation-only adapter exists; can express block evidence |
| failure-driven-loop | failure-learning producer | translation-only adapter exists; rule proposals are not enforced |
| peekxd | computer-use | future capability descriptor only |

## Zed / editor boundary

Zed/MCP is a future adapter candidate, not an implementation in this slice.

| Ownership | Boundary |
|---|---|
| Matrix OS | generic `EditorSurfaceDescriptor`, evidence links, future adapter path |
| Zed | editor/plugin/runtime behavior |
| MCP future adapter | reviewed adapter change through Gateway Registry -> EditorSurfaceDescriptor -> MCP/adapter contract |
| CCC/AAL/Evidence | remain runner/editor agnostic |

Matrix OS must not hardcode Zed-specific logic into CCC, AAL, ASPICE, or Evidence Backbone. A future Zed route should attach through gateway descriptors and an explicit adapter PR.

## Dry-run route planner

Implemented in:

```text
curaops/harness/route_plan.py
```

CLI:

```bash
python3 -m curaops.cli.main harness route-plan --intent "Run agent task with evidence capture"
python3 -m curaops.cli.main harness route-plan --intent "Run agent task with evidence capture" --format json
python3 -m curaops.cli.main harness route-plan --intent "Run agent task with evidence capture" --format json --output route-plan.json
python3 -m curaops.cli.main harness route-plan-view --input tests/fixtures/harness/route_plan/agent-task.json
```

The planner maps an operator intent to ranked descriptor candidates, required evidence outputs, and a required approval gate. It always renders `execute_now: false`. Text output is for operators; `--format json` emits the stable `route-plan.v1` machine-readable contract, and `--output` writes that dry-run contract to a file without executing any candidate. `route-plan-view` is a read-only Matrix UI viewer stub over an existing route-plan JSON artifact; it renders intent, chosen candidate, candidate ranking, evidence requirements, approval gate, and non-execution boundary without starting a runtime or claiming a production dashboard. `docs/MATRIX_OS_ROUTE_PLAN_HANDOFF_CONTRACT.md` defines the operator handoff schema and canonical fixtures under `tests/fixtures/harness/route_plan/`; `docs/MATRIX_OS_ROUTE_PLAN_VIEWER_OUTPUTS.md` defines exact viewer snapshot outputs under `tests/fixtures/harness/route_plan_view/`. `src/ui/widgets/route_plan_panel.py` adapts the validated viewer model into a non-interactive Textual-compatible panel model documented in `docs/MATRIX_OS_ROUTE_PLAN_PANEL_MODEL.md`; exact panel renderer snapshots live under `tests/fixtures/harness/route_plan_panel/` and are documented in `docs/MATRIX_OS_ROUTE_PLAN_PANEL_GOLDEN_OUTPUTS.md`. `src/core/app.py` now exposes a non-live `route_plan` view and sidebar button documented in `docs/MATRIX_OS_ROUTE_PLAN_PANEL_ATTACHMENT.md`. It does not attach runtime execution. Unknown intent fails closed and requires human route decision.

| Intent family | Typical selected descriptor | Required proof |
|---|---|---|
| AI-assisted code change / agent task | `hermes`, with `opencode` and `pi-agent-harness` as descriptor candidates | CCC/AAL plus `agent.run.completed` evidence plan |
| Dangerous file operation | `safety-guard` evidence path before any shell boundary | `safety_guard.action.blocked` or reviewed safety evidence |
| Failed agent run | `failure-driven-loop` evidence path | `failure.observed` and `rule.proposed` evidence-only; no enforcement |
| Operator UI view | original Matrix UI/editor surface | display/attach-only plan; no production dashboard claim |
| Unknown intent | no candidate | fail closed; human route decision required |

## Future integration route

```text
Gateway Registry
 -> RunnerDescriptor / ToolDescriptor / EditorSurfaceDescriptor
 -> focused adapter PR
 -> explicit evidence/event contract
 -> fail-closed tests
 -> optional UI value map slot
```

## Not implemented

This slice does not implement:

- Hermes execution
- OpenCode execution
- local shell execution
- Zed/MCP runtime
- MCP server
- peekxd integration
- CAS adapter
- ai-router adapter
- dashboard
- shell interception
- destructive execution
- production audit retention
- cloud persistence
- automatic rule enforcement

## Validation

`tests/test_harness_gateway_contract.py` verifies that descriptors are generic, fail closed on unknown ids, keep external projects standalone, and do not enable runtimes. `tests/test_harness_route_plan.py` verifies operator-value dry-run scenarios, candidate ranking, evidence requirements, approval gates, fail-closed unknown intent handling, stable JSON contract output, `--output` file writing, and CLI smoke output. `tests/test_route_plan_golden_fixtures.py` verifies exact `route-plan.v1` golden fixture matches for canonical operator handoff scenarios. `tests/test_matrix_ui_route_plan_viewer.py` verifies the read-only viewer stub consumes those fixtures without runtime execution or dashboard claims. `tests/test_route_plan_viewer_golden_outputs.py` verifies exact CLI/rendered viewer snapshots for the canonical route-plan fixtures. `tests/test_route_plan_panel_model.py` verifies the non-interactive Textual-compatible panel model and widget shell over the same validated fixtures. `tests/test_route_plan_panel_golden_outputs.py` verifies exact panel renderer snapshots and UI snapshot boundary invariants. `tests/test_matrix_ui_route_plan_panel_attachment.py` verifies the non-live Matrix UI route-plan view/sidebar attachment over the stable snapshot contract.
