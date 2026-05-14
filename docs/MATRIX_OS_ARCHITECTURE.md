# Matrix OS Architecture

Status: authoritative architecture overview for the merged Matrix OS state including UI/MCP/editor scaffolding and the evidence backbone contract.

Matrix OS is currently a Python package and CLI-based harness/control plane for compliance-oriented agent workflows. The merged runtime focuses on package structure, Change Request control, accountable AI-assisted change gates, ASPICE traceability support, evidence contracts, translation-only external evidence adapters, and declarative UI/gateway boundaries.

This document describes the current merged repository state. It is not a production-readiness statement and does not describe planned UI/MCP/editor or external-adapter features as already implemented.

## Current architecture

```text
Matrix OS Harness
├── Foundation / Packaging / CLI Baseline
│   ├── Python package: curaops
│   └── CLI entrypoint: python3 -m curaops.cli.main
├── Compliance Change Control
│   ├── Package: curaops.skills.change_request
│   └── CLI: matrix CLI namespace `cr`
├── Accountable Agent Layer
│   ├── Package: curaops.skills.accountable_agent
│   └── CLI: matrix CLI namespace `accountable`
├── ASPICE Support Utilities
│   ├── Package: curaops.skills.aspice_conflict_detector
│   ├── Package: curaops.skills.aspice_link_manager
│   └── CLI: matrix CLI namespace `aspice`
└── Evidence Backbone Adapter Contract
    ├── Package: curaops.evidence
    ├── Store: changes/evidence/events.jsonl
    ├── Adapters: agent-evidence-plane, Safety Guard, failure-loop
    ├── Registry: curaops.evidence.adapters.registry
    └── CLI: matrix CLI namespace `evidence`
└── Harness Gateway Contract
    ├── Package: curaops.harness.gateway
    └── Scope: descriptors only; no runtime execution
```

## Module responsibilities

| Module | Owns | Does not own |
|---|---|---|
| Matrix OS Harness | Package baseline, CLI shell, orchestration surface, module boundaries | External engine internals, production deployment, certification claims |
| Compliance Change Control | CR lifecycle, CR validation, CR evidence, verification-case management | Agent identity/accountability policy, ASPICE traceability graph semantics |
| Accountable Agent Layer | AI-assisted change pre-flight, accountability registration, CR linkage checks, accountable evidence | CR lifecycle transitions, CR approval authority, ASPICE link maintenance |
| ASPICE Support Utilities | Traceability conflict detection, requirement-to-file links, bidirectional link updates, traceability matrix support | CR lifecycle, AI-agent accountability, UI/MCP/editor integration |
| Evidence Backbone Adapter Contract | Matrix OS event envelope, local JSONL store convention, validate/summarize utilities, adapter protocol, adapter registry | Production audit retention, cloud persistence, external adapter runtimes |
| Product Coherence Scenario Pack | Operator-value scenario fixtures/tests across CCC, AAL, ASPICE, Evidence, adapters, registry, and UI scaffolding | Production-readiness claim, runtime integration, dashboard |
| Harness Gateway Contract | Generic descriptors for future Hermes/OpenCode/local-shell runners, tools, editor surfaces, and gateway capabilities | Real runner execution, MCP server runtime, Zed plugin, shell interception |
| External Engines / Adapters | Safety Guard, agent-evidence-plane, failure-driven-loop remain standalone with narrow Matrix OS translation adapters; CAS, peekxd, OpenCode plugin, ai-router remain future candidates | Core ownership inside Matrix OS without explicit focused adapter PRs |

## Current data/control flow

1. Foundation exposes the package and CLI baseline.
2. Compliance Change Control creates and manages Change Requests through the `cr` CLI and `ChangeRequestService` API.
3. Accountable Agent Layer consumes approved-or-later CR state and enforces accountability gates for AI-assisted changes.
4. ASPICE utilities support traceability documents and code/test links independently of CR approval and accountable-agent registration.
5. Evidence backbone validates and summarizes Matrix OS harness-side evidence event streams.
6. Translation-only adapters convert approved external fixture/result/event streams into canonical Matrix OS evidence.
7. Product coherence scenarios prove the combined stream can answer operator questions.
8. Gateway descriptors document future runner/tool/editor boundaries without runtime execution.

## CLI surface

Authoritative command discovery is the CLI itself:

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
```

Current root commands:

| Namespace | Responsibility |
|---|---|
| `version` | Baseline version display |
| `doctor` | Minimal package/import smoke check |
| `cr` | Compliance Change Control |
| `accountable` | Accountable Agent Layer |
| `aspice` | ASPICE Support Utilities |
| `scaffold` | UI/MCP/editor scaffolding manifest |
| `evidence` | Evidence backbone validate/summarize/convert/discovery utilities |

## External and future modules

These names are tracked as future adapter candidates, not merged Matrix OS runtime modules:

| Candidate | Current status |
|---|---|
| Safety Guard | External trust-funnel project; translation-only Matrix OS adapter exists |
| agent-evidence-plane | External evidence/audit sidecar; translation-only Matrix OS adapter exists |
| failure-driven-loop | External failure-learning project; translation-only Matrix OS adapter exists |
| CAS Extractor | Future adapter/capability candidate |
| peekxd | Future adapter/capability candidate |
| OpenCode plugin | Future adapter/capability candidate |
| ai-router | Future adapter/capability candidate |
| Hermes/OpenCode/local shell runners | Future gateway runner candidates; descriptors only |
| Zed/MCP editor surface | Future editor adapter candidate; descriptor only |
| UI/MCP/editor scaffolding | Merged scaffolding; original Matrix UI preserved, MCP/editor contracts remain non-production scaffolding |
| Evidence backbone contract | Current harness-side contract; local JSONL only, no production audit retention or external adapter runtime |

## Production-readiness boundary

The merged repository has passing local tests for the focused modules, but Matrix OS is not yet production-ready. Missing production gates include deployment model, security hardening, persistence/backups beyond local JSONL, audit-retention policy, migration strategy, runtime adapter contracts beyond translation-only evidence adapters, CI policy, and operational runbooks.
