# Matrix OS Product Coherence

Status: product-value validation for the merged Matrix OS harness stack.

Matrix OS is now more than a package baseline plus separate utilities. The coherent product shape is an Agent Accountability & Compliance Harness: a local, explicit, evidence-first control plane that links change intent, agent accountability, traceability checks, external producer evidence, safety blocks, failure learning, and future UI/gateway surfaces without pretending to be a production platform yet.

## Current merged stack

| Slice | Merged value |
|---|---|
| Foundation / Packaging / CLI | Stable `curaops` package, `matrix-cli`, import/test baseline |
| Compliance Change Control | Change Request lifecycle, validation rules, evidence generation |
| Accountable Agent Layer | Agent/change/requirement linkage and accountability evidence |
| ASPICE Support Utilities | Traceability conflict detection and link-management support |
| Architecture / Documentation Index | Authoritative docs and historical-doc boundaries |
| UI / MCP / Editor Scaffolding | Preserves original Matrix UI and declares non-production UI/MCP/editor boundaries |
| Evidence Backbone | Canonical EventEnvelope, local JSONL store, validate/summarize CLI |
| agent-evidence-plane Thin Adapter | Translation-only agent run evidence |
| Safety Guard Adapter | Translation-only blocked/allowed/approval safety evidence |
| Evidence Adapter Registry | Discoverable adapter metadata and fail-closed lookup |
| failure-driven-loop Thin Adapter | Translation-only failure evidence and non-enforced rule proposals |
| Evidence Operator Reports | Read-only reports that answer product-coherence questions from validated evidence streams |
| Evidence Report Golden Fixtures | Deterministic EventEnvelope fixture plus expected text/Markdown/JSON outputs for report regression |
| Evidence Report Contract Versioning + CI Gate | Explicit `MXOS-REPORT-1.0` contract metadata plus focused CI workflow for evidence/report gates |

## Product thesis

The harness has value when an operator can answer questions that no single module can answer alone:

| Operator question | Modules required |
|---|---|
| Which agent changed what, under which approved CR, with which evidence? | CCC + AAL + agent-evidence-plane + Evidence Backbone + Registry |
| What risky action was blocked, why, and by which producer? | Safety Guard Adapter + Evidence Backbone + summary CLI |
| What failure was observed and what rule was proposed without enforcing it? | failure-driven-loop Adapter + Evidence Backbone |
| Which requirement/test/code traceability gap exists? | ASPICE Support + Evidence Backbone |
| Where could this be shown later? | UI scaffolding + Harness Gateway descriptors |

## Gaps closed by the combination

| Gap | Closed by |
|---|---|
| CR evidence without agent accountability | AAL links agent/change/requirement evidence |
| Agent logs without compliance context | agent-evidence-plane events can share CR correlation ids |
| Safety checks outside audit stream | Safety Guard result conversion emits Matrix OS evidence |
| Failure loops becoming implicit policy | failure-loop adapter records `rule.proposed` as evidence only |
| Traceability support isolated from operations | ASPICE evidence can share the same EventEnvelope stream |
| Adapter surface becoming loose | Evidence Adapter Registry gives discoverable metadata and fail-closed unknown lookup |
| UI being forgotten during CLI-first hardening | Scaffolding keeps original Matrix UI as preserved host surface |

## Open gaps

| Gap | Status |
|---|---|
| Production dashboard | Open; explicitly not claimed |
| MCP server runtime | Open; contract/scaffolding only |
| Real Hermes/OpenCode/Zed runner execution | Open; future adapter work |
| Production audit retention/cloud persistence | Open; local JSONL only |
| Security hardening | Open; not implemented by this slice |
| Automatic rule enforcement | Open by design; proposed rules are not enforced |
| CAS/peekxd/OpenCode/ai-router adapters | Open; future focused slices |

## Monster-system risk

Risk: Matrix OS could become a large collection of adapters and UI ideas without proving operator value.

Mitigation in this slice:

1. scenario tests combine modules instead of only checking imports,
2. gateway descriptors keep future runners generic and external,
3. docs mark production/dashboard/runtime claims as out of scope,
4. original UI is mapped as a future display surface instead of rewritten,
5. provenance unknowns are marked UNKNOWN instead of invented.

## Scenario pack

The product-value scenario pack is implemented in `tests/test_product_coherence_scenarios.py` with fixtures under `tests/fixtures/evidence/product_coherence/`.

| Scenario | Proof |
|---|---|
| AI-assisted compliant change | Approved CR + AAL linkage + agent run evidence answer who/what/under which CR |
| Unsafe/destructive action blocked | Safety Guard blocked event answers risky action/reason/producer |
| Repeated failure creates non-enforced rule proposal | failure-loop emits `failure.observed` and `rule.proposed`, with `enforced=false` |
| ASPICE traceability gap | `aspice.check.completed` identifies missing verification-case link |
| Combined operator timeline | Combined stream validates and summarizes seven meaningful events |

## Acceptance answers

| Question | Answer source |
|---|---|
| What agent/action happened? | `agent.run.completed`, AAL payload |
| Was there an approved CR? | `change_request.evidence.generated` payload |
| Which requirement/traceability object was involved? | `requirement_refs`, `aspice.check.completed` subject |
| Was a risky action blocked? | `safety_guard.action.blocked` |
| Was a failure observed? | `failure.observed` |
| Was a rule proposed? | `rule.proposed` |
| Was any proposed rule enforced? | No: `enforced=false`, `policy_action=none` |
| Which adapter produced which evidence? | Evidence Adapter Registry descriptors, producers, and operator report adapter counts |
| Which external project remains standalone? | Gateway boundaries and adapter docs |
| Which Matrix OS surface could show the result later? | UI value map and Gateway editor surface descriptors |

## Operator report layer

The evidence operator report layer is implemented in `curaops/evidence/reporting.py` with CLI access through:

```bash
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format text
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format markdown
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format json
```

It reads existing Matrix OS evidence only. `tests/test_evidence_report_golden_outputs.py` locks a deterministic `tests/fixtures/evidence/operator_report/product_coherence.events.jsonl` stream against expected text, Markdown, and JSON outputs. `tests/test_evidence_report_contract_version.py` pins those outputs to report contract `MXOS-REPORT-1.0`, which is exposed in JSON as `report_schema_version` and in text/Markdown metadata. The golden outputs are regression contracts for operator-facing accountability answers, not production audit retention.

`.github/workflows/matrix-os-evidence-quality.yml` defines a focused evidence/report quality gate for pull requests and manual dispatch. It runs the focused test suite, exact CLI golden-output comparisons, and ruff on the evidence/report surface. It does not claim branch protection, production readiness, runtime execution, or policy enforcement.

The report/golden layer does not create a new adapter, run external tools, launch a dashboard, provide MCP runtime, retain production audit data, or enforce proposed rules.

## Product status

Matrix OS is a coherent local harness/control-plane baseline with a local operator report over validated evidence streams. It is not yet a production platform, certification system, cloud audit service, dashboard product, MCP runtime, policy-enforcement runtime, or runner execution bridge.
