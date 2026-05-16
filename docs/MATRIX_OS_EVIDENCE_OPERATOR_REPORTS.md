# Matrix OS Evidence Operator Reports

Status: authoritative operator-report layer for Matrix OS evidence streams.

Matrix OS evidence operator reports turn validated `EventEnvelope` JSONL streams into deterministic text, Markdown, or JSON summaries that answer accountability and compliance questions an operator can read without inspecting raw event payloads.

## Purpose

The report layer proves the merged evidence backbone, adapter registry, and product-coherence scenarios can answer useful questions from already-produced evidence:

- which agent/action happened,
- under which Change Request,
- which requirement or traceability object was involved,
- what risky safety action was blocked and why,
- what failure was observed,
- what rule was proposed,
- whether the proposed rule was enforced,
- which adapter produced each evidence family.

## Input

Input is a local Matrix OS `EventEnvelope` JSONL stream:

```bash
python3 -m curaops.cli.main evidence report changes/evidence/events.jsonl
```

The report command uses the evidence backbone reader, so malformed JSON, unsupported event types, missing hashes, or invalid envelopes fail closed before any report is produced.

## Output formats

```bash
python3 -m curaops.cli.main evidence report EVENTS.jsonl
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format text
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format markdown
python3 -m curaops.cli.main evidence report EVENTS.jsonl --format json
```

Text and Markdown are for operators. JSON is for tests and future local tooling. Output is deterministic: events are sorted by timestamp and event id, and counts are sorted by key. The report also carries Change Request status so the operator-facing agent/action answer can distinguish an approved CR from an unknown or unapproved CR.

## Operator questions answered

| Question | Evidence source |
|---|---|
| Which agent changed what under which CR? | `accountable_change.evidence.generated` plus shared CR/run ids |
| What safety action was blocked and why? | `safety_guard.action.blocked` payload and producer adapter metadata |
| What failure was observed? | `failure.observed` payload |
| What rule was proposed? | `rule.proposed` payload |
| Was the proposed rule enforced? | `enforced=false` and `policy_action=none` |
| Which requirement or traceability object is relevant? | `requirement_refs`, requirement references, and `aspice.check.completed` gaps |
| Which adapter produced the evidence? | `producer.adapter` counts and per-answer adapter fields |

## Boundaries and non-goals

Evidence operator reports are a read-only report layer over existing Matrix OS evidence streams.

They do not include:

- a new adapter,
- external runtime execution,
- Hermes/OpenCode/Zed execution,
- MCP runtime,
- shell interception,
- destructive execution,
- dashboard or UI runtime,
- cloud persistence,
- production audit retention,
- automatic rule enforcement,
- modification of external repositories.

Proposed rules remain evidence only. A report can say a rule was proposed and not enforced; it must not apply that rule or claim policy enforcement.

## Golden fixtures and regression contract

`tests/fixtures/evidence/operator_report/` contains the deterministic product-coherence report contract:

- `product_coherence.events.jsonl` is the validated Matrix OS `EventEnvelope` stream.
- `product_coherence.expected.txt` is the expected text output.
- `product_coherence.expected.md` is the expected Markdown output.
- `product_coherence.expected.json` is the expected JSON output.

`tests/test_evidence_report_golden_outputs.py` compares generated report output to those golden files. Intentional operator-output changes must update the matching golden files in the same change; accidental drift should fail the regression gate.

These golden files are test fixtures only. They are not production audit retention, do not create a dashboard, do not execute external runtimes, and do not enforce proposed rules.

## Relationship to Product Coherence tests

`tests/test_evidence_operator_report.py` builds the same product-coherence evidence pattern exercised by `tests/test_product_coherence_scenarios.py`:

- a Change Request and accountable agent event,
- an agent-evidence-plane translated run event,
- a Safety Guard blocked action,
- a failure-driven-loop failure and non-enforced rule proposal,
- an ASPICE traceability gap.

The report layer is the operator-readable proof over that stream.

## Relationship to future UI

The report can later feed a Matrix UI surface, but no UI work is implemented here. The original Matrix UI remains preserved by the scaffolding/value-map slices; the report command only renders terminal/Markdown/JSON output.

## Product status

This is a local harness-side accountability report. It is not a production audit system, certification claim, hosted dashboard, or policy-enforcement runtime.
