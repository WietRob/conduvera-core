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
| #10 | Evidence Backbone Adapter Contract | Merged | `41b060b` | Harness-side event envelope, JSONL store, validate/summarize CLI |
| #11 | agent-evidence-plane Thin Adapter | Merged | `805adce` | Translate a small supported external-event subset into Matrix OS events |
| #12 | Safety Guard Adapter Contract | Merged | `93118b2` | Translate compatible Safety Guard trust/safety results into Matrix OS events |
| #13 | Evidence Adapter Registry | Merged | `2e2b8c7` | Metadata-only registry and CLI discovery for existing evidence adapters |
| #14 | failure-driven-loop Thin Adapter | Merged | `58b8906` | Translate compatible failure-loop result JSONL into Matrix OS evidence events |
| #15 | Product Coherence & Harness Gateway Validation | Merged | `661589b` | Scenario proof, generic gateway contract, UI value map, provenance note |
| #16 | Evidence Operator Report Pack | Merged | `50614d7` | Read-only operator reports over validated Matrix OS evidence streams |
| TBD | Evidence Report Golden Fixtures | Current | TBD | Golden EventEnvelope fixture and expected text/Markdown/JSON report outputs |

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
python3 -m curaops.cli.main evidence convert-agent-plane --help
python3 -m curaops.cli.main evidence convert-safety-guard --help
python3 -m curaops.cli.main evidence adapters
python3 -m curaops.cli.main evidence adapter show agent-evidence-plane
python3 -m curaops.cli.main evidence adapter show safety-guard
python3 -m curaops.cli.main evidence adapter show failure-loop
python3 -m curaops.cli.main evidence convert-failure-loop --help
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format json
python3 -m pytest tests/test_evidence_report_golden_outputs.py
```

## Release train next slices

| Slice | Scope | Status | Boundary |
|---|---|---|---|
| MCP / UI / Editor Scaffolding | Original Matrix UI preservation plus MCP/editor contracts | Merged | Scaffolding only; no server, adapter, or production dashboard claim |
| Evidence Backbone Adapter Contract | Harness-side evidence event contract and local JSONL store | Merged | No production audit retention or cloud persistence |
| agent-evidence-plane Thin Adapter | Translate compatible local agent-evidence-plane events into Matrix OS envelopes | Merged | No vendoring, no external repo modification, no public launch |
| Safety Guard Adapter Contract | Translate compatible local Safety Guard trust/safety results into Matrix OS envelopes | Merged | No execution, shell interception, repo modification, release creation, or production policy claim |
| Evidence Adapter Registry | Discover existing evidence adapters and their explicit contracts | Merged | Registry metadata only; no new adapter, runtime execution, or production audit claim |
| failure-driven-loop Thin Adapter | Translate compatible local failure-loop result JSONL into Matrix OS envelopes | Merged | No runtime execution, rule enforcement, external repo modification, or production policy claim |
| Product Coherence & Harness Gateway Validation | Prove combined operator scenarios and define generic future runner/editor gateway boundaries | Merged | No new external adapter, no runtime execution, no MCP server, no dashboard, no production claim |
| Evidence Operator Report Pack | Render operator-readable reports for product-coherence evidence questions | Merged | No new adapter, no runtime execution, no dashboard, no production audit retention, no automatic rule enforcement |
| Evidence Report Golden Fixtures | Lock operator report outputs against deterministic product-coherence evidence | Current | Regression fixtures only; no runtime execution, no dashboard, no MCP runtime, no production audit retention, no rule enforcement |
| Later adapter slices | Broader Safety Guard runtime integration | Planned | Only after evidence bridge proves the boundary; keep Safety Guard standalone |
| Later adapter slices | Broader agent-evidence-plane adapter | Planned | Only after thin adapter proves the boundary; keep sidecar separate |
| Later adapter slices | CAS Extractor adapter/capability | Planned | Define a focused contract before integration |
| Later runtime slices | Broader failure-driven-loop policy/runtime capability | Planned | Only after translation-only evidence proves operator value; no automatic rule enforcement yet |
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
python3 -m curaops.cli.main evidence convert-agent-plane --help
python3 -m curaops.cli.main evidence convert-safety-guard --help
python3 -m curaops.cli.main evidence adapters
python3 -m curaops.cli.main evidence adapter show agent-evidence-plane
python3 -m curaops.cli.main evidence adapter show safety-guard
python3 -m curaops.cli.main evidence adapter show failure-loop
python3 -m curaops.cli.main evidence convert-failure-loop --help
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format json
```

## Not production-ready yet

The current release train does not yet establish:

- deployment architecture
- hosted service operations
- security threat model and hardening
- production audit-retention policy beyond local JSONL contract
- external-adapter contracts beyond the reviewed translation-only adapters and gateway descriptors
- CI enforcement policy
- migration/upgrade procedures
- user-facing UI/MCP/editor workflows
- certification or compliance approval

## Release discipline

Future PRs should remain focused slices. Avoid re-opening the superseded integration PR, avoid broad architecture synthesis mixed with runtime changes, and keep external engines/adapters outside Matrix OS core until a specific adapter contract is reviewed.
