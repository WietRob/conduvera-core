# Matrix OS agent-evidence-plane Thin Adapter

Status: narrow Matrix OS adapter contract for compatible local agent-evidence-plane JSONL events.

This document defines the agent-evidence-plane thin-adapter boundary. Matrix OS does not absorb, vendor, launch, or modify agent-evidence-plane. The adapter reads compatible JSON event dictionaries and writes Matrix OS `EventEnvelope` JSONL through the Matrix OS Evidence Backbone.

## Boundary decision

| Area | Decision |
|---|---|
| Matrix OS owns | `EvidenceProducer` protocol, `EventEnvelope`, Matrix OS JSONL store, `matrix-cli evidence validate/summarize`, thin conversion CLI |
| agent-evidence-plane owns | its repo, schema, CLI, tests, JSONL helpers, future product direction |
| Adapter owns | translation from a small compatible subset of agent-evidence-plane events into Matrix OS envelopes |
| Not owned here | production retention, dashboards, MCP runtime, Safety Guard, CAS, failure-loop, peekxd, OpenCode, ai-router |

## Read-only inventory summary

Local reference repo: `/home/roberto_schmidt/projects/agent-evidence-plane`

Observed contract:

| Item | agent-evidence-plane value |
|---|---|
| Schema version | `0.1.0` |
| Event ID format | `evt_*` |
| Required fields | `schema_version`, `event_id`, `event_type`, `occurred_at`, `producer`, `subject`, `payload` |
| Producer requirement | `producer.name` |
| Subject requirement | `subject.kind` |
| Optional fields | `severity`, `correlation_id`, `run_id`, `evidence`, `links` |
| JSONL helper | `src/agent_evidence_plane/jsonl.py` |
| CLI | `validate`, `append`, `summarize`, `gate run`, `convert cas` |

## Supported event types

The adapter intentionally supports only a small explicit subset:

| agent-evidence-plane type | Matrix OS type | Reason |
|---|---|---|
| `agent.run.started` | `agent.run.started` | Agent-run lifecycle start evidence |
| `agent.run.completed` | `agent.run.completed` | Agent-run lifecycle completion evidence |
| `agent.run.failed` | `agent.run.failed` | Agent-run lifecycle failure evidence |
| `failure.observed` | `failure.observed` | Failure-loop observation evidence candidate |

Unsupported event types fail closed with `ValidationError`. Matrix OS does not accept arbitrary external event types silently.

## Translation policy

| External field | Matrix OS target |
|---|---|
| `event_id` | preserved as `payload.external_event_id`; Matrix ID becomes `mxev_aep_<external_event_id>` |
| `event_type` | mapped only if in the explicit supported set |
| `occurred_at` | preserved; must be UTC RFC3339 `Z` |
| `producer` | preserved and annotated with `adapter=matrix-os.agent-evidence-plane` |
| `subject` | preserved as Matrix OS `subject` |
| `payload` | nested as `payload.external_payload` |
| `evidence.artifact_path` / `evidence.path` | preserved as a Matrix OS reference when present |
| `evidence.sha256` | preserved on the Matrix OS reference when present |
| `links[].event_id` | converted to external links using `external_event_id` |

Matrix OS recomputes its own `event_hash` and `integrity.hash`; external hash semantics are not trusted as Matrix OS integrity.

## CLI

```bash
python3 -m curaops.cli.main evidence convert-agent-plane INPUT.jsonl OUTPUT.jsonl
python3 -m curaops.cli.main evidence validate OUTPUT.jsonl
python3 -m curaops.cli.main evidence summarize OUTPUT.jsonl
```

## Non-goals

This adapter does not:

- modify `/home/roberto_schmidt/projects/agent-evidence-plane`
- vendor or bulk-copy agent-evidence-plane code
- create or launch an agent-evidence-plane GitHub repo
- add Safety Guard, CAS, failure-loop, peekxd, OpenCode, or ai-router adapters
- add dashboard or MCP runtime
- claim production audit retention or cloud persistence
- claim external certification

## Validation gates

The adapter is covered by tests for:

- valid external event translation
- malformed event rejection
- artifact/reference preservation
- Matrix OS envelope validation
- EvidenceStore roundtrip
- unsupported event-type fail-closed behavior
- CLI conversion success and failure
