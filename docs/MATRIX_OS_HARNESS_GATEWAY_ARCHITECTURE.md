# Matrix OS Harness Gateway Architecture

Status: generic contract for future Matrix OS harness/gateway integrations.

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
| `RunnerDescriptor` | describes future runner families such as Hermes/OpenCode/local shell |
| `ToolDescriptor` | describes evidence producers, safety tools, and computer-use tools |
| `EditorSurfaceDescriptor` | describes Matrix UI and future editor/MCP surfaces |
| `HarnessGatewayRegistry` | stable fail-closed registry of the descriptors |

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

`tests/test_harness_gateway_contract.py` verifies that descriptors are generic, fail closed on unknown ids, keep external projects standalone, and do not enable runtimes.
