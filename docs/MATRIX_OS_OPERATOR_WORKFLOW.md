# Matrix OS Operator Workflow

Status: authoritative product-facing workflow slice for read-only harness operator status.

## Purpose

The operator workflow answers one practical question:

> What does Matrix OS know right now, which harness surfaces exist, what did the latest evidence stream say, and what should the operator inspect next?

This is a product-value slice, not another governance expansion. It connects existing Matrix OS contracts into a useful read-only status view.

## Command

Default local evidence-store convention:

```bash
python3 -m curaops.cli.main harness status
```

Committed product-coherence fixture:

```bash
python3 -m curaops.cli.main harness status --events tests/fixtures/evidence/operator_report/product_coherence.events.jsonl
```

The command prints:

- read-only boundary status;
- latest evidence report contract and event counts;
- observed evidence adapters;
- registered translation-only adapter metadata;
- generic harness runner/tool descriptors;
- preserved Matrix UI attach point;
- operator signals and next-step hints.

## Connected modules

| Area | Reused contract | Operator value |
|---|---|---|
| Evidence Backbone | Validated `EventEnvelope` JSONL stream | Shows event totals, event types, producers, subjects, and adapter observations |
| Operator Reports | `MXOS-REPORT-1.0` evidence report semantics | Reuses approved-CR, agent-action, safety-block, failure/rule, and traceability-gap extraction |
| Adapter Registry | `list_adapter_descriptors()` | Lists adapter metadata without executing external tools |
| Harness Gateway | `HarnessGatewayRegistry.default()` | Lists runners, tools, capabilities, and surfaces without launching them |
| Matrix UI/TUI | `matrix-ui-code-editor` surface descriptor | Documents the future attach point for CR status, evidence timeline, runner status, and approval inbox |

## Read-only boundary

`harness status` does not:

- launch Hermes, OpenCode, local shell, Zed, MCP, peekxd, or any other runtime;
- execute adapter conversions;
- create a dashboard runtime;
- mutate governance, branch protection, required approval, or review settings;
- enforce proposed rules;
- create production audit-retention claims;
- add a new external adapter.

It only reads an existing event stream and declarative in-repo registries.

## Operator signals

The status view turns existing evidence report fields into direct operator signals:

- approved CR present?
- accountable agent action present?
- safety block present?
- failure or rule proposal present?
- traceability gap present?

When a signal is present, the command emits a next-step hint. Examples:

- inspect the linked agent action before execution when an approved CR exists;
- verify changed files and requirements when an agent action exists;
- keep a blocked action blocked until explicit human review;
- treat proposed rules as evidence only, not enforcement;
- create or link verification evidence for traceability gaps.

## UI/TUI attach point

This slice keeps implementation CLI-only and preserves the original Matrix UI/TUI. The UI attach point is the existing `matrix-ui-code-editor` harness surface, with future panels for:

- CR status;
- evidence timeline;
- runner status;
- approval inbox.

No dashboard claim is made. A future UI PR can render the same `HarnessOperatorStatus` data model inside the preserved TUI without changing the read-only product contract.

## Generic Hermes/OpenCode/Zed handling

Hermes, OpenCode, Zed/MCP, local shell, peekxd, Safety Guard, failure-loop, and agent-evidence-plane remain generic descriptors or standalone external producers. Matrix OS only observes translated evidence and registry metadata. It does not hardcode runtime-specific behavior or execute any runner.

## Product gaps remaining

- The TUI does not yet render the status model.
- No live event tail is implemented.
- No operator inbox or CR drill-down exists yet.
- No runtime adapter execution is implemented by design.
- The command is fixture/local-stream based until a future UX slice wires richer operator navigation.
