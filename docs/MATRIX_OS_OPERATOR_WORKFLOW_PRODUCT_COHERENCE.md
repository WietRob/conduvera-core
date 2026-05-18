# Matrix OS Operator Workflow Product Coherence

## Operator question

This slice answers: "What does Matrix OS know right now about my harness state, evidence stream, available runner/tool surfaces, and next operator action?"

It should let an operator inspect evidence and harness readiness without launching agents, shells, MCP servers, dashboards, or external adapters.

## Existing modules connected

- Evidence Backbone: reads Matrix OS evidence events from a JSONL event stream or the local evidence-store convention.
- Operator Reports: reuses report-level event summary semantics and contract-versioned evidence reporting instead of inventing a second report model.
- Adapter Registry: lists the existing translation-only adapter metadata and fail-closed boundaries.
- Harness Gateway descriptors: lists generic runner/tool/capability/editor-surface descriptors without executing them.
- Preserved Matrix UI/TUI: treats the original code editor and split-pane surface as the future attach point for an operator-facing evidence timeline and runner-status panel.

## Product value over governance expansion

Another governance slice can prove that Matrix OS is controlled. This slice proves Matrix OS is useful: it turns existing compliance/evidence/harness contracts into one read-only operator answer with actionable next-step hints.

## Original Matrix UI/TUI direction

The CLI remains the first narrow vertical slice, but the output is shaped around UI panels the original Matrix experience can later host: harness surfaces, evidence summary, signal detection, and next-step hints. The implementation must preserve existing UI code and document the attach point rather than replacing the Matrix UI with a dashboard claim.

## Generic Hermes/OpenCode/Zed integration

Hermes, OpenCode, Zed, local shell, and related tools remain generic descriptors or external producers. Matrix OS observes translated evidence and declarative capabilities only. It does not execute those tools, hardcode their runtime behavior, register MCP tools, or create new adapters in this slice.
