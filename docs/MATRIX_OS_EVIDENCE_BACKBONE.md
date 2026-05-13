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
| agent-evidence-plane | separate project | not copied, not vendored, not absorbed |
| Safety Guard / CAS / failure-loop / peekxd / OpenCode / ai-router | external adapters | not integrated |

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

Future external producers must adapt into this registry through explicit PRs.

## Writer / reader interface

Python API:

```python
from curaops.evidence import EventEnvelope, EvidenceStore

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
from curaops.evidence import validate_event_stream, summarize_event_stream

validate_event_stream("changes/evidence/events.jsonl")
summarize_event_stream("changes/evidence/events.jsonl")
```

Adapter protocol:

```python
from curaops.evidence import EvidenceProducer

class FutureAdapter(EvidenceProducer):
    def produce_events(self):
        ...
```

This protocol is only the Matrix OS harness-side boundary. It is not an external adapter implementation.

## CLI

```text
python3 -m curaops.cli.main evidence --help
python3 -m curaops.cli.main evidence validate changes/evidence/events.jsonl
python3 -m curaops.cli.main evidence summarize changes/evidence/events.jsonl
```

The CLI validates and summarizes event streams. It does not start an MCP runtime, dashboard, external adapter, cloud persistence, or production audit service.

## Non-goals

This slice does not include:

- production audit retention
- cloud persistence
- external compliance certification
- agent-evidence-plane product merge
- Safety Guard adapter
- CAS adapter
- failure-loop adapter
- peekxd adapter
- OpenCode plugin adapter
- ai-router adapter
- dashboard implementation
- MCP runtime

## Readiness note

The contract is suitable as a local harness baseline and adapter boundary. It is not production-ready evidence infrastructure. Production readiness still requires retention policy, access control, migration strategy, CI policy, operational runbooks, and external-adapter review.
