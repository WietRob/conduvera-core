# ADR — Runtime Decision and Dry-Run Gateway

Status: Accepted

## Context

PR S evaluated Pi Agent Harness (`earendil-works/pi`, `pi.dev`) as a possible Matrix OS runtime/control-center base. The decision from that evaluation is C: borrow Pi Agent Harness concepts only.

Matrix OS already has Compliance Change Control, Accountable Agent Layer, Evidence Backbone, translation-only evidence adapters, a Harness Gateway Registry, and read-only operator status. Those components make Matrix OS a harness/control plane. They do not make Matrix OS a runtime that can launch Hermes, OpenCode, local shell commands, Zed/MCP, or Pi Agent Harness.

## Decision

Matrix OS remains the harness/control plane.

Pi Agent Harness is not forked, not vendored, not executed, and not treated as Raspberry Pi hardware, `pi-hermes`, SSH, or a home-control node. Matrix OS may borrow Pi concepts such as route planning, provider/backend selection, session/run lifecycle ideas, skills/extensions vocabulary, and UI patterns.

The next product-value step is a descriptor-only dry-run Gateway route planner:

```text
operator intent
 -> route-plan classification
 -> descriptor/capability matching
 -> candidate ranking
 -> required evidence plan
 -> required approval gate
 -> execute_now=false
```

Runtime execution remains future work behind separately reviewed adapter contracts.

## Options considered

| Option | Meaning | Benefits | Risks | Decision |
|---|---|---|---|---|
| A) Fork/integrate Pi | Make Pi Agent Harness a Matrix OS foundation/runtime | Mature TypeScript runtime, sessions, providers, TUI/web UI | Collapses Matrix OS evidence/control-plane boundary; high coupling; large fork burden | Rejected |
| B) Bind Hermes/OpenCode directly as runtime | Build immediate runtime bridge to existing agent tools | Faster visible execution path | Premature execution before route, approval, safety, fallback, and evidence contracts | Rejected for now |
| C) Descriptor-only gateway route planning | Plan routes and evidence without execution | Small testable product slice; preserves boundaries; supports future backend choice | Does not execute tasks yet | Accepted |
| D) Only document more | Defer implementation | Lowest code risk | Docs-only drift; no operator-facing behavior | Rejected |

## Consequences

- `curaops/harness/route_plan.py` owns the first dry-run planner contract.
- `python3 -m curaops.cli.main harness route-plan --intent <...>` renders the dry-run route plan.
- All candidates remain descriptor-only and non-executing.
- `pi-agent-harness` may appear as a route candidate only with `runtime_enabled=False` and `execution_status="future-adapter-contract-only"`.
- Safety Guard, agent-evidence-plane, and failure-loop remain translation/evidence concepts, not launched tools.
- Original Matrix UI/editor surfaces remain display/attach-only candidates; no production dashboard is claimed.
- Unknown intent fails closed and requires a human route decision.

## Non-goals

- No Pi fork.
- No Raspberry Pi, SSH, `pi-hermes`, or home-control work.
- No runtime execution.
- No Hermes/OpenCode/Zed/MCP implementation.
- No new external adapter.
- No shell interception or destructive command path.
- No production dashboard or branch-protection/governance change.

## Verification

The contract is verified by:

- `tests/test_harness_route_plan.py`
- `tests/test_harness_gateway_contract.py`
- CLI smoke: `python3 -m curaops.cli.main harness route-plan --intent "Run agent task with evidence capture"`

Expected output must show `execute_now: false`, candidate ranking, later execution boundary, non-execution boundary, required evidence outputs, and approval gate.
