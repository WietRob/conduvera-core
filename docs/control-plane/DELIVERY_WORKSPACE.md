# Delivery Workspace (v1)

This document describes the Conduvera Delivery Workspace: how a completed
managed code-change job becomes a reviewable GitHub pull request, the control
plane delivery domain, the fail-closed publish gate, the GitHub bridge
contract, cleanup/retention, and the operator workflow.

## Overview

The workspace no longer stops at `submit -> run -> COMPLETED -> inspect`. It
delivers the full operator workflow:

```
submit code-change job
  -> isolated MANAGED execution
  -> inspect actual changes, tests, logs and EvidenceBundle
  -> pass a fail-closed publish gate
  -> create exactly one task branch and exactly one GitHub PR
  -> track GitHub checks, review state, merge conflicts and base drift
  -> surface actionable attention states
  -> preserve evidence across restart and cleanup
  -> leave merge as an explicit human action in v1
```

## Delivery domain

`DeliveryService` (`conduvera/control_plane/delivery_service.py`) owns the
`DeliveryRecord` state machine and the immutable `Job -> Attempt -> Session`
link. Records are persisted in the Control-Plane-owned `DeliveryStore`
(`delivery_store.py`, 0600 files, atomic writes, append-only transition
history) outside agent-writable worktrees. Exact restart reconstruction is
supported; unknown or inconsistent remote state becomes an attention state,
never a fabricated green.

Delivery states: `NOT_READY`, `READY_TO_PUBLISH`, `PUBLISHING`, `PR_OPEN`,
`CI_PENDING`, `CI_FAILED`, `REVIEW_CHANGES_REQUESTED`, `NEEDS_REBASE`,
`MERGE_CONFLICT`, `MERGE_READY`, `MERGED`, `PR_CLOSED`, `DELIVERY_FAILED`.

One job may have several attempts; only an explicitly selected terminal
COMPLETED attempt may be the active delivery source. Publishing a later attempt
never silently overwrites an earlier delivery's history.

## Fail-closed pre-publish gate

A job is publishable only when all required facts hold. The gate reports
exactly why publication is blocked, with structured negative codes:

- `JOB_NOT_COMPLETED`
- `ATTEMPT_NOT_SELECTED`
- `EXTERNAL_SESSION_NOT_PUBLISHABLE`
- `WORKTREE_NOT_OWNED`
- `BASE_COMMIT_INVALID`
- `EMPTY_CHANGESET`
- `FORBIDDEN_PATH`
- `SECRET_PATTERN_DETECTED`
- `EVIDENCE_MISSING`
- `EVIDENCE_INVALID`
- `DELIVERY_ALREADY_BOUND`
- `BASE_DRIFT_REQUIRES_REBASE`

No caller-controlled shell string is used; all Git/GitHub commands use
structured argv, validated identifiers and explicit working directories.

## GitHub delivery provider

`GitHubDeliveryProvider` (`github_provider.py`) is a thin shell-free boundary
around the authenticated `gh` CLI. Repository and branch names come only from
allowlisted/normalized sources; credentials are inherited from the
authenticated environment and never logged; errors map to structured product
errors.

Publishing:

1. re-reads the exact owned worktree and selected Attempt;
2. derives a deterministic sanitized branch name `conduvera/<task>/<attempt>`;
3. creates a single commit of the approved change set (deterministic,
   non-secret message);
4. pushes the task branch without force;
5. creates exactly one PR against the recorded base branch;
6. persists branch SHA, PR number, URL, base SHA and head SHA;
7. is idempotent (repeated Publish returns the same record/branch/PR);
8. detects an existing compatible remote branch/PR after restart;
9. fails closed if a remote branch with the same name has an unexpected SHA.

The PR body contains Conduvera job/attempt/session/delivery IDs, repo and exact
base/head SHAs, harness metadata, changed-file summary, test/gate summary,
EvidenceBundle references, remaining limitations, and a statement that merge is
a human action. It never contains raw prompts, secrets, tokens, or local
absolute paths. No automatic merge in v1.

## Base drift and safe republish

Before publication and every republish/sync the current target branch is
fetched read-only and the recorded base is compared with the remote base:

- `MATCH`: publication may continue.
- `BEHIND` with a clean rebase possible: rebase in the owned task branch,
  rerun gates, generate new evidence, publish the new exact head.
- conflict / unsafe drift: state `NEEDS_REBASE` or `MERGE_CONFLICT`, preserve
  worktree and evidence, expose attention, never force-push.
- remote unavailable: `DELIVERY_FAILED` or explicit `REMOTE_UNAVAILABLE`
  attention, never assumed green.

## GitHub status synchronization

`sync` reads the open PR and maps open/closed/merged state, current base/head
SHAs, required and reported checks, pending/success/failure checks, review
approvals and changes requested, mergeability and behind-base condition.

State mapping: pending checks -> `CI_PENDING`; failed check -> `CI_FAILED`;
changes requested -> `REVIEW_CHANGES_REQUESTED`; conflict/behind -> `NEEDS_REBASE`
or `MERGE_CONFLICT`; all available required conditions green -> `MERGE_READY`;
no configured required checks -> explicit `NO_REQUIRED_CHECKS` attention (never
fabricated green); merged -> `MERGED`; closed without merge -> `PR_CLOSED`.

Sync is idempotent, restart-safe, manually triggerable, periodically refreshed
while a PR is open, bounded and failure-tolerant, and read-only with respect to
reviews and merge.

## Cleanup and retention

Disposable runtime resources (owned worktree, transient scope/process
artefacts, temporary staging files) are removed by cleanup. Durable product
truth (Job/Attempt/Session history, EvidenceBundle, DeliveryRecord + history,
GitHub branch/PR identity, publication/sync receipts) is never removed.

- cleanup never controls/removes EXTERNAL sessions;
- cleanup does not close an open PR or delete a remote task branch;
- cleanup does not delete EvidenceBundles;
- cleanup is idempotent;
- a worktree may be removed only when publication state and evidence retention
  make that safe;
- a failed or conflicted unpublished delivery preserves its worktree for
  operator recovery unless an explicit safe cleanup is chosen;
- the UI states exactly what will be removed.

Acceptance-specific remote cleanup (closing/deleting the temporary acceptance
PR/branch) belongs to the acceptance runner, not normal product cleanup.

## CLI

```bash
conduvera control-plane delivery inspect <job-or-delivery>
conduvera control-plane delivery preflight <job-or-delivery>
conduvera control-plane delivery publish <job-or-delivery> [--base-branch main]
conduvera control-plane delivery sync <job-or-delivery>
conduvera control-plane delivery list [--json]
conduvera control-plane delivery cleanup <job-or-delivery> [--safe-only/--no-safe-only]
```

All commands support `--json`. The same truth is exposed through the browser,
the HTTP JSON API and the CLI (one Control-Plane authority).

## Browser delivery workspace

The activity workspace (served at `/ui/`) keeps the queue/running/terminal
view and adds a real detail surface per Job/Attempt: Job+execution metadata,
changed-file list and safe diff viewer, evidence hashes and references,
pre-publish gate result, branch/PR/base/head SHAs, checks/reviews summary,
mergeability and attention reasons, and operator actions (Publish PR, Refresh
GitHub, Preflight, Inspect, Cancel, Cleanup, Open PR).

Live updates arrive over a restart-safe SSE event stream (`/api/events`) with
monotonically ordered ids, Last-Event-ID resume, automatic reconnect and a
bounded polling fallback when the stream is unavailable.

## Security and trust boundary

- No raw prompt or secret occurs in argv, process fingerprint, event stream,
  registry, DeliveryRecord, branch name, commit message, PR body, logs,
  screenshots or evidence metadata.
- EXTERNAL sessions are read-only: no Publish action, no DeliveryRecord, no
  managed GitHub authority.
- Agent-writable worktree files are never treated as terminal evidence
  authority for non-acceptance harnesses.
