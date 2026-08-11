# Conduvera Managed Control Plane v1 — Internal Alpha Live-Akzeptanz

**Datum:** 2026-08-11 · **Basis:** conduvera-core f54b759b100b (PR #36)
**Adapter:** conduvera-hermes-adapter 0.1.7 (unverändert) · Platform ed3b951 (unverändert)
**Service:** conduvera-control-plane.service (systemd user, active)

## A+B — Zwei MANAGED Sessions parallel (Hermes + Codex)

```
A Hermes: job=job_3bdda2f4788d session=mxs_e28441d2282f4d37
  worktree=~/.local/state/conduvera/worktrees/ALPHA-A-hermes-a1
  HEAD=f54b759b100b (exakt), git worktree list: OK
B Codex:  job=job_0af2cfa9a7a1 session=mxs_7a8c92b28f6e45e9
  worktree=~/.local/state/conduvera/worktrees/ALPHA-B-codex-b1
  HEAD=f54b759b100b (exakt), git worktree list: OK
Status: A RUNNING | B RUNNING (gleichzeitig)
Registry: 10 Sessions, 10 MANAGED, distinct task/attempt/session IDs
```

## C — Cancel nur eigener Scope

```
A CANCEL: CANCELLED | B nach A-Cancel: RUNNING (unberührt)
conduvera-Scope-Units: 2 -> 1 (nur A-Scope endete)
```

## D — Timeout-Kette (SIGTERM -> grace -> SIGKILL)

```
Session mxs_bad3ee1b42f74312 (sleep 30, timeout 8):
  SIGTERM -> 3s grace -> SIGKILL (Kette 3.0s)
  Prozess beendet (nur Zombie <defunct> bis Parent-Reap), Scope-Unit weg
  (kein sleep-30-Prozess mehr; systemd list-units leer)
```

## E — Restart + Reconciliation (kein Duplikat, keine Adoption)

```
E1 (laufende Session über Restart): mxs_7a8c92b2 (sleep 40 lief aus) ->
   Reconcile: COMPLETED process_gone (ehrliche Wahrheit), 1 Instanz
E2 (frisch, sleep 60): mxs_f0dff1d2611e4f1a pid=3978627
   Daemon-Restart -> Reconcile: {state: RUNNING, transitioned: rediscovered}
   Status: RUNNING, Session-Instanzen: 1 (kein Duplikat)
   Cancel nach Restart: CANCELLED
```

## F — Harmless-Task gegen Git-Fixture-Repo

```
Fixture: /tmp/tmpdyje_rk4/fixture-repo base=029f02c618a7
Worktree: /tmp/alpha-fixture-wts/FIXTURE-TASK-f1 HEAD=029f02c618a7 (detached)
Output result.txt NUR im Worktree; Base-Repo-Tree unverändert; Base sauber;
git worktree list --porcelain: OK; Worktree-Removal sauber
```

## G — Service Disable/Restart (Rollback-Pfad)

```
stop + disable: Symlink entfernt, Service gestoppt
enable --now: neu aktiviert, active (running), Doctor ok
```

## Buildroom-Handoff

```
BUILDROOM-ALPHA-1 / ba-1 -> Router (hermes_scoped) -> submit -> job/attempt
session=mxs_6e502035b33b41f2 worktree=BUILDROOM-ALPHA-1-ba-1
scope=conduvera-mxs_6e502035b33b41f2.scope
STATUS RUNNING -> CANCEL CANCELLED
```

## Outbox (MXOS-EVIDENCE-1.0.0)

```
57 Events: job.accepted(6), attempt.created(6), session.queued(2),
  session.start.requested(4), session.started(4), session.cancelled(1),
  session.reconciled(34) — Redaktion OK (keine api_key)
```

## Scheduler-Queue live

```
job_08234384b158: "job queued (harness hermes_scoped limit 2 reached)" —
  per-Harness-Concurrency-Limit greift; Attempt-State-Sync bei Cancel/
  Reconcile (Fix committet: _mark_attempt_terminal)
```

## Tests

```
tests/test_control_plane.py + tests/test_internal_alpha.py: 43 passed
volle Suite (273 Core + neue): 287 passed, 1 skipped · ruff: 0 Fehler
```
