# Matrix OS failure-driven-loop Thin Adapter

Status: narrow Matrix OS adapter contract for compatible failure-driven-loop result JSONL.

This adapter is translation-only. It does not execute the failure-driven-loop runtime, analyze patterns, mutate rules, enforce policy, call external CLIs, modify the failure-driven-loop repository, or claim production audit readiness.

## Source inventory

Reference repo inspected read-only:

```text
/home/roberto_schmidt/projects/failure-driven-loop
```

Observed source project facts:

| Area | Finding |
|---|---|
| Repo | `git@github.com:WietRob/failure-driven-loop.git` |
| Branch | `master` tracking `origin/master` |
| Latest observed commit | `745eaa1 fix: update Quick Start to examples/minimal path` |
| Tag | `v1.0.0` |
| Package | `failure-driven-loop` version `1.0.0` |
| Primary scripts | `fdl-validate-naming`, `fdl-validate-links`, `fdl-log-feedback`, `fdl-analyze-patterns`, `fdl-tree-analyzer` |
| Existing JSONL | feedback logs: `skills/feedback_tracker/logs/feedback.jsonl`, `failure_loop/logs/feedback.jsonl` |
| Observed feedback shape | `timestamp`, `session_id`, `type`, `context`, `feedback`, `category`, `severity` |
| Pattern report shape | documentation shows pattern reports with `pattern_id`, `error_type`, `root_cause`, `occurrence_count`, `affected_files`, `suggested_rule`, `target_skill`, `priority` |
| Local test note | repo tests currently require installed CLI entry points; Matrix OS did not mutate or install the source repo |

## Matrix OS fixture input contract

Matrix OS defines a small explicit fixture contract because the source repo has feedback logs and pattern reports but no stable Matrix OS evidence JSONL contract.

Input JSONL schema version:

```text
failure-loop.result.v1
```

Example:

```json
{
  "schema_version": "failure-loop.result.v1",
  "result_id": "fl_001",
  "observed_at": "2026-05-13T18:45:00Z",
  "source": {"name": "failure-driven-loop", "version": "1.0.0"},
  "failure": {
    "kind": "test_failure",
    "signature": "pytest::test_example::AssertionError",
    "summary": "Assertion failed in test_example",
    "artifact_path": "reports/pytest.txt"
  },
  "recommendation": {
    "type": "rule_proposal",
    "rule_id": "rule_pytest_assertion",
    "title": "Require regression test before merge"
  },
  "severity": "warning",
  "metadata": {"repo": "matrix-os"}
}
```

Required fields:

- `schema_version`
- `result_id`
- `observed_at`
- `source.name`
- `failure.kind`
- `failure.signature`
- `failure.summary`
- `severity`

Optional fields:

- `source.version`
- `failure.artifact_path`
- `recommendation`
- `metadata`
- `correlation_id`
- `run_id`

Supported `failure.kind` values:

- `test_failure`
- `lint_failure`
- `typecheck_failure`
- `ci_failure`
- `traceability_failure`
- `naming_failure`

Supported recommendation types:

- `rule_proposal`

## Event mapping

| Input condition | Matrix OS event type | Subject kind | Notes |
|---|---|---|---|
| Any valid result | `failure.observed` | `failure_loop_failure` | Observed failure evidence |
| Valid result with `recommendation.type=rule_proposal` | `rule.proposed` | `failure_loop_rule_proposal` | Proposal evidence only; not enforcement |

Severity is copied from input after validation against Matrix OS severities.

Artifact references:

| Input field | Matrix OS reference |
|---|---|
| `failure.artifact_path` | `{"kind":"failure-loop.artifact","path":...,"external_result_id":...}` |

## Non-enforcement rule

`rule.proposed` is evidence only.

The adapter always sets:

```json
{
  "enforced": false,
  "policy_action": "none"
}
```

Matrix OS does not turn a proposal into an enforced rule in this adapter.

## CLI

```bash
python3 -m curaops.cli.main evidence convert-failure-loop INPUT.jsonl OUTPUT.jsonl
python3 -m curaops.cli.main evidence adapter show failure-loop
python3 -m curaops.cli.main evidence validate OUTPUT.jsonl
python3 -m curaops.cli.main evidence summarize OUTPUT.jsonl
```

## Fail-closed behavior

The adapter rejects:

- unknown `schema_version`
- missing required fields
- unsupported `failure.kind`
- unsupported `recommendation.type`
- invalid UTC timestamp format
- invalid severity
- malformed JSON
- non-object metadata

## Boundaries

Matrix OS owns:

- EventEnvelope
- local JSONL output
- translation-only adapter
- registry descriptor
- CLI conversion/discovery

failure-driven-loop owns:

- its repository
- its product direction
- feedback tracker semantics
- pattern detection
- rule proposal semantics
- runtime loop behavior
- enforcement logic

This adapter does not:

- execute failure-driven-loop
- mutate `/home/roberto_schmidt/projects/failure-driven-loop`
- enforce proposed rules
- add a policy engine
- add dashboard/MCP runtime
- add CAS/peekxd/OpenCode/ai-router adapters
- add shell interception
- execute destructive commands
- claim production audit retention, cloud persistence, or external certification
