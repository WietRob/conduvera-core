# Matrix OS Safety Guard Adapter Contract

Status: narrow Matrix OS adapter contract for compatible CuraOps Safety Guard result JSONL.

This document defines the Safety Guard adapter boundary. Matrix OS does not absorb, vendor, launch, release, install, or execute CuraOps Safety Guard. The adapter reads compatible Safety Guard result dictionaries and writes Matrix OS `EventEnvelope` JSONL through the Matrix OS Evidence Backbone.

## Boundary decision

| Area | Decision |
|---|---|
| Matrix OS owns | Evidence event envelope, local JSONL evidence store, adapter protocol, validation/summarization CLI, narrow conversion CLI |
| CuraOps Safety Guard owns | Rust CLI, shell-wrapper behavior, pattern matcher, release/tag lifecycle, install docs, safety roadmap |
| Adapter owns | Translation from a small compatible result subset into Matrix OS evidence events |
| Not owned here | destructive command execution, shell interception, install automation, release creation, production safety policy, dashboard, MCP runtime |

## Read-only inventory summary

Local reference repo: `/home/roberto_schmidt/projects/curaops-safety-guard`

Observed state:

| Item | CuraOps Safety Guard value |
|---|---|
| Package | Rust crate `curaops-safety-guard` |
| Version | `0.1.0` in `Cargo.toml` and Clap metadata |
| Git branch | `master` tracking `origin/master` |
| Remote | `git@github.com:WietRob/curaops-safety-guard.git` |
| Tag | `v0.1.0` |
| CLI purpose | Check whether a path is safe to delete before `rm` proceeds |
| CLI input | path plus options such as `--recursive`, `--quiet`, `--verbose`, `--config` |
| Current decisions | Safe, Blocked, Excluded; specification also describes confirmation/exit-code 2 semantics |
| Current structured JSON output | Not observed in code/docs; adapter starts from explicit JSONL fixtures/results |
| Audit behavior | Blocked operations are logged best-effort to a local safety-guard log |

The adapter does not call the CLI because this adapter is evidence translation only and must not execute destructive commands or shell interception.

## Safety Guard result fixture contract

Because the current Safety Guard CLI output is human-oriented text/exit code rather than a stable JSON event stream, Matrix OS defines a narrow import fixture for evidence bridging:

```json
{
  "schema_version": "safety-guard.result.v1",
  "result_id": "sg_001",
  "checked_at": "2026-05-13T18:45:00Z",
  "tool": {"name": "curaops-safety-guard", "version": "0.1.0"},
  "action": {"kind": "delete", "command": "rm production.db", "path": "production.db", "recursive": false},
  "verdict": "blocked",
  "reason": "Path matches protected pattern",
  "matched_pattern": ".*production.*",
  "exit_code": 1,
  "forced": false
}
```

Unsupported or malformed result objects fail closed with `ValidationError`.

## Supported event types

The adapter intentionally supports only a small explicit subset:

| Safety Guard verdict | Matrix OS event type | Severity |
|---|---|---|
| `check_completed` | `safety_guard.check.completed` | `info` |
| `allowed` | `safety_guard.action.allowed` | `info` |
| `blocked` | `safety_guard.action.blocked` | `error` |
| `blocked` with `forced=true` | `safety_guard.action.blocked` | `critical` |
| `approval_required` | `safety_guard.approval.required` | `warning` |

Arbitrary Safety Guard verdicts or event types are not accepted.

## Translation policy

| Safety Guard field | Matrix OS target |
|---|---|
| `result_id` | preserved as `payload.external_result_id`; Matrix ID becomes `mxev_sg_<result_id>` |
| `checked_at` | `occurred_at`; must be UTC RFC3339 with `Z` suffix |
| `tool` | Matrix OS `producer` plus `adapter=matrix-os.safety-guard` |
| `action.kind` / `action.path` | Matrix OS `subject` |
| `action` | copied into `payload.action` |
| `verdict` / `reason` / `matched_pattern` / `exit_code` / `forced` | copied into `payload` |
| `action.path` | preserved as a Matrix OS reference |

Matrix OS recomputes its own `event_hash` and `integrity.hash`.

## CLI

```bash
python3 -m conduvera.cli.main evidence convert-safety-guard INPUT.jsonl OUTPUT.jsonl
python3 -m conduvera.cli.main evidence validate OUTPUT.jsonl
python3 -m conduvera.cli.main evidence summarize OUTPUT.jsonl
```

## Non-goals

This adapter does not:

- modify `/home/roberto_schmidt/projects/curaops-safety-guard`
- vendor or bulk-copy Safety Guard code
- create a Safety Guard release or tag
- install Safety Guard or configure shell wrappers
- execute `rm`, shell commands, or Safety Guard itself
- add shell interception or agent runtime changes
- add a production policy engine
- add Safety Guard dashboard or MCP runtime
- add CAS, failure-loop, peekxd, OpenCode, or ai-router adapters
- claim production audit retention, cloud persistence, or external certification

## Validation gates

The adapter is covered by tests for:

- blocked result conversion
- allowed result conversion
- approval-required result conversion
- check-completed result conversion
- forced blocked result severity
- malformed result rejection
- unsupported verdict rejection
- Matrix OS envelope validation
- EvidenceStore roundtrip
- CLI conversion success and failure
