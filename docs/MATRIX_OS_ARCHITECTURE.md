# Matrix OS Architecture

Status: authoritative architecture overview for the merged Matrix OS state including UI/MCP/editor scaffolding and the evidence backbone contract.

Matrix OS is currently a Python package and CLI-based harness/control plane for compliance-oriented agent workflows. The merged runtime focuses on package structure, Change Request control, accountable AI-assisted change gates, and ASPICE traceability support.

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
    ├── Package: curaops.evidence.adapters.agent_evidence_plane
    ├── Package: curaops.evidence.adapters.safety_guard
    └── CLI: matrix CLI namespace `evidence`
```

## Module responsibilities

| Module | Owns | Does not own |
|---|---|---|
| Matrix OS Harness | Package baseline, CLI shell, orchestration surface, module boundaries | External engine internals, production deployment, certification claims |
| Compliance Change Control | CR lifecycle, CR validation, CR evidence, verification-case management | Agent identity/accountability policy, ASPICE traceability graph semantics |
| Accountable Agent Layer | AI-assisted change pre-flight, accountability registration, CR linkage checks, accountable evidence | CR lifecycle transitions, CR approval authority, ASPICE link maintenance |
| ASPICE Support Utilities | Traceability conflict detection, requirement-to-file links, bidirectional link updates, traceability matrix support | CR lifecycle, AI-agent accountability, UI/MCP/editor integration |
| Evidence Backbone Adapter Contract | Matrix OS event envelope, local JSONL store convention, validate/summarize utilities, adapter protocol, thin agent-evidence-plane and Safety Guard evidence translations | Production audit retention, cloud persistence, external adapter runtimes, agent-evidence-plane product ownership, Safety Guard runtime/policy ownership |
| External Engines / Adapters | Safety Guard, agent-evidence-plane, CAS, failure-loop, peekxd, OpenCode plugin, ai-router, other independently maintainable engines | Core ownership inside Matrix OS until adapter PRs define explicit contracts |

## Current data/control flow

1. Foundation exposes the package and CLI baseline.
2. Compliance Change Control creates and manages Change Requests through the `cr` CLI and `ChangeRequestService` API.
3. Accountable Agent Layer consumes approved-or-later CR state and enforces accountability gates for AI-assisted changes.
4. ASPICE utilities support traceability documents and code/test links independently of CR approval and accountable-agent registration.
5. Evidence backbone validates and summarizes Matrix OS harness-side evidence event streams.
6. Thin evidence adapters translate compatible local agent-evidence-plane and Safety Guard JSONL into Matrix OS envelopes without owning external runtimes.
7. Future adapters may connect external engines into the harness, but those engines remain separately maintainable unless a later focused change defines a narrow adapter contract.

## CLI surface

Authoritative command discovery is the CLI itself:

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
python3 -m curaops.cli.main evidence convert-agent-plane --help
python3 -m curaops.cli.main evidence convert-safety-guard --help
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
| `evidence` | Evidence backbone validate/summarize/convert utilities |

## External and future modules

These names are tracked as future adapter candidates, not merged Matrix OS runtime modules:

| Candidate | Current status |
|---|---|
| Safety Guard | Standalone external trust-funnel project; Matrix OS owns only the evidence translation adapter |
| agent-evidence-plane | Standalone evidence/audit sidecar candidate; Matrix OS owns only the thin evidence translation adapter |
| CAS Extractor | Future adapter/capability candidate |
| failure-driven-loop | Future adapter/capability candidate |
| peekxd | Future adapter/capability candidate |
| OpenCode plugin | Future adapter/capability candidate |
| ai-router | Future adapter/capability candidate |
| UI/MCP/editor scaffolding | Merged scaffolding; original Matrix UI preserved, MCP/editor contracts remain non-production scaffolding |
| Evidence backbone contract | Current harness-side contract; local JSONL only, no production audit retention or external adapter runtime |

## Production-readiness boundary

The merged repository has passing local tests for the focused modules, but Matrix OS is not yet production-ready. Missing production gates include deployment model, security hardening, persistence/backups beyond local JSONL, audit-retention policy, migration strategy, broader external-adapter contracts, CI policy, and operational runbooks. The Safety Guard adapter is evidence translation only; it does not execute commands, intercept shells, or implement a production safety-policy engine.
