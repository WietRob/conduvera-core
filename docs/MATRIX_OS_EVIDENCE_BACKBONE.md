# Matrix OS Evidence Backbone Contract

Status: authoritative harness-side evidence contract for Matrix OS.

This document defines the narrow Matrix OS evidence backbone adapter contract. It does not absorb agent-evidence-plane and does not implement broad adapters.

## Purpose

Matrix OS now has several modules that generate or consume evidence:

- Compliance Change Control writes CR evidence files.
- Accountable Agent Layer writes accountability evidence and references CCC evidence.
- ASPICE utilities perform traceability checks that can later emit auditable events.
- Gate/scaffold workflows need a stable event stream before UI or MCP runtimes consume evidence.

The evidence backbone provides a common event envelope and JSONL store so future modules do not invent incompatible evidence event formats.

## Ownership boundary

| Area | Owner | Status |
|---|---|---|
| Matrix OS event envelope | Matrix OS | merged harness-side contract |
| Matrix OS JSONL store convention | Matrix OS | merged harness-side contract |
| Matrix OS evidence CLI validate/summarize | Matrix OS | discovery/validation utility |
| Matrix OS evidence adapter registry | Matrix OS | metadata-only discovery index for registered adapters; no runtime execution |
| failure-driven-loop thin adapter | Matrix OS | explicit translation boundary for compatible failure-loop result JSONL; no runtime execution or rule enforcement |
| agent-evidence-plane thin adapter | Matrix OS | explicit translation boundary for a small supported event subset; no vendoring |
| Safety Guard adapter contract | Matrix OS | explicit translation boundary for compatible Safety Guard result JSONL; no runtime execution |
| agent-evidence-plane | separate project | not copied, not vendored, not absorbed |
| Safety Guard | separate project | not copied, not vendored, not executed |
| failure-driven-loop | separate project | not copied, not vendored, not executed; proposed rules are not enforced by Matrix OS |
| CAS / peekxd / OpenCode / ai-router | external adapter candidates | not integrated |

## Event store path convention

Default project-local event stream:

```text
changes/evidence/events.jsonl
```

The store is JSONL: one validated event envelope per line.

## Event envelope

Schema version:

```text
MXOS-EVIDENCE-1.0.0
```

Required fields:

| Field | Meaning |
|---|---|
| `schema_version` | Matrix OS evidence contract version |
| `event_id` | `mxev_...` event identifier |
| `event_type` | registered Matrix OS core event type |
| `occurred_at` | UTC timestamp with `Z` suffix |
| `producer.name` | producer identity |
| `subject.kind` | subject category |
| `payload` | event-specific object |
| `event_hash` | deterministic SHA-256 over canonical event payload excluding hash fields |
| `integrity.hash` | same hash as `event_hash` |

Optional fields:

| Field | Meaning |
|---|---|
| `severity` | `debug`, `info`, `warning`, `error`, or `critical` |
| `correlation_id` | CR, AC, run, or operator correlation ID |
| `run_id` | gate/agent run identifier |
| `references` | file/evidence/document references |
| `links` | event-to-event links |

## Core event types

Current Matrix OS registry:

| Event type | Intended producer |
|---|---|
| `change_request.evidence.generated` | Compliance Change Control |
| `accountable_change.evidence.generated` | Accountable Agent Layer |
| `aspice.check.completed` | ASPICE Support Utilities |
| `gate.run.completed` | Matrix OS harness/gates |
| `agent.run.started` | agent-evidence-plane thin adapter |
| `agent.run.completed` | agent-evidence-plane thin adapter |
| `agent.run.failed` | agent-evidence-plane thin adapter |
| `failure.observed` | agent-evidence-plane thin adapter; failure-driven-loop thin adapter |
| `rule.proposed` | failure-driven-loop thin adapter |
| `safety_guard.check.completed` | CuraOps Safety Guard adapter |
| `safety_guard.action.allowed` | CuraOps Safety Guard adapter |
| `safety_guard.action.blocked` | CuraOps Safety Guard adapter |
| `safety_guard.approval.required` | CuraOps Safety Guard adapter |

Future external producers must adapt into this registry through explicit PRs.

## Writer / reader interface

Python API:

```python
from conduvera.evidence import EventEnvelope, EvidenceStore

event = EventEnvelope.create(
    event_type="gate.run.completed",
    producer={"name": "matrix-os.gate"},
    subject={"kind": "gate", "id": "unit"},
    payload={"status": "passed"},
)
EvidenceStore().append(event)
```

Reader/validator:

```python
from conduvera.evidence import validate_event_stream, summarize_event_stream

validate_event_stream("changes/evidence/events.jsonl")
summarize_event_stream("changes/evidence/events.jsonl")
```

Adapter protocol:

```python
from conduvera.evidence import EvidenceProducer

class FutureAdapter(EvidenceProducer):
    def produce_events(self):
        ...
```

This protocol is only the Matrix OS harness-side boundary. It is not an external adapter implementation.

## CLI

```text
python3 -m conduvera.cli.main evidence --help
python3 -m conduvera.cli.main evidence adapters
python3 -m conduvera.cli.main evidence adapter show agent-evidence-plane
python3 -m conduvera.cli.main evidence adapter show safety-guard
python3 -m conduvera.cli.main evidence adapter show failure-loop
python3 -m conduvera.cli.main evidence validate changes/evidence/events.jsonl
python3 -m conduvera.cli.main evidence summarize changes/evidence/events.jsonl
python3 -m conduvera.cli.main evidence convert-agent-plane agent-plane.jsonl matrix-os-events.jsonl
python3 -m conduvera.cli.main evidence convert-safety-guard safety-guard.jsonl matrix-os-events.jsonl
python3 -m conduvera.cli.main evidence convert-failure-loop failure-loop.jsonl matrix-os-events.jsonl
```

The CLI discovers registered adapters, validates/summarizes streams, and performs narrow explicit conversions into Matrix OS event streams. It does not start an MCP runtime, dashboard, broad external adapter, cloud persistence, or production audit service.

## Non-goals

This slice does not include:

- production audit retention
- cloud persistence
- external compliance certification
- agent-evidence-plane product merge
- broad agent-evidence-plane adapter beyond `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md`
- broad Safety Guard integration beyond `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md`
- Safety Guard runtime/policy engine integration
- CAS adapter
- broader failure-loop runtime/policy-engine integration
- peekxd adapter
- OpenCode plugin adapter
- ai-router adapter
- dashboard implementation
- MCP runtime

## Readiness note

The contract is suitable as a local harness baseline and adapter boundary. It is not production-ready evidence infrastructure. Production readiness still requires retention policy, access control, migration strategy, CI policy, operational runbooks, and external-adapter review.
