# Matrix OS Release Train Status

Status: authoritative release-train index after PR #7.

This document tracks merged slices and planned next slices. It is not a product launch announcement and not a production-readiness claim.

## Merged release train

| PR | Slice | Status | Merge commit | Scope |
|---:|---|---|---|---|
| #4 | Foundation / Packaging / CLI Baseline | Merged | `7330883` | Python package baseline, CLI shell, import/package contract |
| #5 | Compliance Change Control Core | Merged | `97aed2a` | CR lifecycle, validation, evidence, verification cases |
| #6 | Accountable Agent Layer | Merged | `06663a1` | AI-assisted change accountability gates and evidence |
| #7 | ASPICE Support Utilities | Merged | `7d4f4b3` | Traceability conflict detector, link manager, minimal ASPICE CLI |

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
```

## Planned next PRs

| Planned PR | Scope | Boundary |
|---|---|---|
| Next scaffolding slice | MCP / UI / Editor Scaffolding | Add scaffolding separately from compliance, accountability, and ASPICE core |
| Later adapter slices | Safety Guard adapter | Keep Safety Guard standalone; integrate through a narrow adapter only |
| Later adapter slices | agent-evidence-plane adapter | Treat as reusable evidence/audit sidecar, not absorbed core |
| Later adapter slices | CAS Extractor adapter/capability | Define a focused contract before integration |
| Later adapter slices | failure-driven-loop adapter/capability | Define a focused contract before integration |
| Later adapter slices | peekxd adapter/capability | Define a focused contract before integration |
| Later adapter slices | OpenCode plugin adapter/capability | Define a focused contract before integration |
| Later adapter slices | ai-router adapter/capability | Define a focused contract before integration |

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
```

## Not production-ready yet

The current release train does not yet establish:

- deployment architecture
- hosted service operations
- security threat model and hardening
- persistence/backup/retention policy
- external-adapter contracts
- CI enforcement policy
- migration/upgrade procedures
- user-facing UI/MCP/editor workflows
- certification or compliance approval

## Release discipline

Future PRs should remain focused slices. Avoid re-opening the superseded integration PR, avoid broad architecture synthesis mixed with runtime changes, and keep external engines/adapters outside Matrix OS core until a specific adapter contract is reviewed.
