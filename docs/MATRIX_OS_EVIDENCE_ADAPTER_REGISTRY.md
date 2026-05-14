# Matrix OS Evidence Adapter Registry

Status: authoritative discovery index for Matrix OS evidence adapters.

This registry describes evidence adapters that already exist in Matrix OS. It is metadata-only: it does not execute external tools, import external projects, create new adapters, or broaden the Matrix OS event registry.

## Purpose

Matrix OS now has more than one evidence adapter. The registry answers:

- Which adapters are available?
- Which event types can each adapter produce?
- What external input contract does each adapter expect?
- Is the adapter translation-only or runtime-executing?
- Is it production-ready?
- Which CLI command and docs belong to it?

## Registered adapters

| Adapter ID | Display name | Source project | Execution mode | Production status |
|---|---|---|---|---|
| `agent-evidence-plane` | agent-evidence-plane Thin Adapter | agent-evidence-plane | translation-only | local-contract-only / not-production-runtime |
| `safety-guard` | Safety Guard Adapter Contract | CuraOps Safety Guard | translation-only | local-contract-only / not-production-runtime |
| `failure-loop` | failure-driven-loop Thin Adapter | failure-driven-loop | translation-only | local-contract-only / not-production-runtime |

No other adapters are registered by this slice.

## Descriptor fields

Each adapter descriptor contains:

| Field | Meaning |
|---|---|
| `adapter_id` | stable Matrix OS adapter id |
| `name` | human-readable display name |
| `source_project` | external producer/project name |
| `module_path` | Matrix OS adapter module |
| `docs_path` | authoritative adapter documentation |
| `input_contract` | expected external input shape/version |
| `supported_event_types` | explicit Matrix OS event types this adapter may emit |
| `cli_commands` | Matrix OS CLI commands for conversion/discovery |
| `execution_mode` | `translation-only` or future explicitly reviewed mode |
| `production_status` | readiness boundary |
| `external_repo_policy` | whether the external repo is standalone/vendored/executed |

## agent-evidence-plane descriptor

| Field | Value |
|---|---|
| Adapter ID | `agent-evidence-plane` |
| Source project | `agent-evidence-plane` |
| Module path | `curaops.evidence.adapters.agent_evidence_plane` |
| Docs path | `docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md` |
| Input contract | `agent-evidence-plane JSONL schema_version 0.1.0` |
| Execution mode | `translation-only` |
| Production status | `local-contract-only / not-production-runtime` |
| External repo policy | standalone; not vendored; not modified by Matrix OS |
| CLI | `python3 -m curaops.cli.main evidence convert-agent-plane INPUT.jsonl OUTPUT.jsonl` |

Supported event types:

- `agent.run.started`
- `agent.run.completed`
- `agent.run.failed`
- `failure.observed`

## Safety Guard descriptor

| Field | Value |
|---|---|
| Adapter ID | `safety-guard` |
| Source project | `CuraOps Safety Guard` |
| Module path | `curaops.evidence.adapters.safety_guard` |
| Docs path | `docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md` |
| Input contract | `Safety Guard result JSONL schema_version safety-guard.result.v1` |
| Execution mode | `translation-only` |
| Production status | `local-contract-only / not-production-runtime` |
| External repo policy | standalone; not vendored; not executed by Matrix OS |
| CLI | `python3 -m curaops.cli.main evidence convert-safety-guard INPUT.jsonl OUTPUT.jsonl` |

Supported event types:

- `safety_guard.check.completed`
- `safety_guard.action.allowed`
- `safety_guard.action.blocked`
- `safety_guard.approval.required`

## failure-loop descriptor

| Field | Value |
|---|---|
| Adapter ID | `failure-loop` |
| Source project | `failure-driven-loop` |
| Module path | `curaops.evidence.adapters.failure_loop` |
| Docs path | `docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md` |
| Input contract | `failure-loop result JSONL schema_version failure-loop.result.v1` |
| Execution mode | `translation-only` |
| Production status | `local-contract-only / not-production-runtime` |
| External repo policy | standalone; not vendored; not executed by Matrix OS |
| CLI | `python3 -m curaops.cli.main evidence convert-failure-loop INPUT.jsonl OUTPUT.jsonl` |

Supported event types:

- `failure.observed`
- `rule.proposed`

`rule.proposed` is proposal evidence only. It is not treated as an enforced rule.

## CLI discovery

```bash
python3 -m curaops.cli.main evidence adapters
python3 -m curaops.cli.main evidence adapter show agent-evidence-plane
python3 -m curaops.cli.main evidence adapter show safety-guard
python3 -m curaops.cli.main evidence adapter show failure-loop
```

Unknown adapter IDs fail closed with a non-zero exit code:

```bash
python3 -m curaops.cli.main evidence adapter show unknown-adapter
```

## Boundary

This registry may own:

- adapter metadata
- adapter discovery CLI
- documentation index
- explicit event-type lists for registered adapters

This registry does not:

- add a new external adapter
- execute agent-evidence-plane
- execute Safety Guard
- execute failure-driven-loop
- enforce proposed failure-loop rules
- add shell interception
- run destructive commands
- add CAS, peekxd, OpenCode, or ai-router adapters
- add dashboard or MCP runtime
- claim production audit retention, cloud persistence, or certification readiness
- accept arbitrary external event types

## Adding future adapters

Future adapters must be added by focused changes that define:

1. external input contract,
2. explicit Matrix OS event types,
3. execution mode,
4. production status,
5. docs path,
6. tests for fail-closed lookup/conversion behavior.

The registry is not an extension point for silently accepting unreviewed event types.
