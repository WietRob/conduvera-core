# Matrix OS Release Train Status

Status: authoritative release-train index including the evidence backbone contract.

This document tracks merged slices and planned next slices. It is not a product launch announcement and not a production-readiness claim.

## Merged release train

| PR | Slice | Status | Merge commit | Scope |
|---:|---|---|---|---|
| #4 | Foundation / Packaging / CLI Baseline | Merged | `7330883` | Python package baseline, CLI shell, import/package contract |
| #5 | Compliance Change Control Core | Merged | `97aed2a` | CR lifecycle, validation, evidence, verification cases |
| #6 | Accountable Agent Layer | Merged | `06663a1` | AI-assisted change accountability gates and evidence |
| #7 | ASPICE Support Utilities | Merged | `7d4f4b3` | Traceability conflict detector, link manager, minimal ASPICE CLI |
| #8 | Architecture / Documentation Index | Merged | `75144a0` | Module boundaries, release train, documentation inventory |
| #9 | MCP / UI / Editor Scaffolding | Merged | `09a6ef9` | Original Matrix UI preserved, MCP/editor discovery-only scaffolding |
| #10 | Evidence Backbone Adapter Contract | Current | TBD | Harness-side event envelope, JSONL store, validate/summarize CLI |

Closed as superseded:

| PR | Status | Reason |
|---:|---|---|
| #3 | Closed | Superseded by focused release-train PRs #4 through #7 |

## Current merged command surface

```bash
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
```

## Release train next slices

| Slice | Scope | Status | Boundary |
|---|---|---|---|
| MCP / UI / Editor Scaffolding | Original Matrix UI preservation plus MCP/editor contracts | Merged | Scaffolding only; no server, adapter, or production dashboard claim |
| Evidence Backbone Adapter Contract | Harness-side evidence event contract and local JSONL store | Current | No agent-evidence-plane absorption; no external adapter runtime |
| Later adapter slices | Safety Guard adapter | Planned | Keep Safety Guard standalone; integrate through a narrow adapter only |
| Later adapter slices | agent-evidence-plane adapter | Planned | Treat as reusable evidence/audit sidecar, not absorbed core |
| Later adapter slices | CAS Extractor adapter/capability | Planned | Define a focused contract before integration |
| Later adapter slices | failure-driven-loop adapter/capability | Planned | Define a focused contract before integration |
| Later adapter slices | peekxd adapter/capability | Planned | Define a focused contract before integration |
| Later adapter slices | OpenCode plugin adapter/capability | Planned | Define a focused contract before integration |
| Later adapter slices | ai-router adapter/capability | Planned | Define a focused contract before integration |

## Current local verification set

The current release train is verified locally with these focused gates:

```bash
python3 -m pytest tests/test_packaging_contract.py
python3 -m pytest curaops/skills/change_request/tests
python3 -m pytest curaops/skills/accountable_agent/tests
python3 -m pytest curaops/skills/aspice_conflict_detector/test_conflict_detector.py
python3 -m pytest curaops/skills/aspice_link_manager/tests
python3 -m curaops.cli.main --help
python3 -m curaops.cli.main cr --help
python3 -m curaops.cli.main accountable --help
python3 -m curaops.cli.main aspice --help
python3 -m curaops.cli.main scaffold --help
python3 -m curaops.cli.main evidence --help
```

## Not production-ready yet

The current release train does not yet establish:

- deployment architecture
- hosted service operations
- security threat model and hardening
- production audit-retention policy beyond local JSONL contract
- external-adapter contracts
- CI enforcement policy
- migration/upgrade procedures
- user-facing UI/MCP/editor workflows
- certification or compliance approval

## Release discipline

Future PRs should remain focused slices. Avoid re-opening the superseded integration PR, avoid broad architecture synthesis mixed with runtime changes, and keep external engines/adapters outside Matrix OS core until a specific adapter contract is reviewed.
