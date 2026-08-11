# Conduvera Buildroom Operational Pilot — Live Acceptance Proof

**Datum:** 2026-08-11 · **Basis:** conduvera-core e1375f290ac3 (PR #37)
**Service:** conduvera-control-plane.service (systemd user, engine: dispatcher+monitor)
**Capacity für Akzeptanz:** global_concurrency=1 (CONDUVERA_GLOBAL_CONCURRENCY=1)

## 1 — Service nach Reboot + Doctor
```
systemctl --user is-enabled: enabled
Active: active (running) | Doctor ok: True (4 Harnesse)
```

## 2-6 — Queue-Capacity-1 + Auto-Dispatch + Completion
```
PILOT-A4 (Hermes): QUEUED -> RUNNING -> COMPLETED (t+3s)
PILOT-B4 (Codex):  QUEUED (Capacity 1) -> auto-dispatch nach A4 -> COMPLETED (t+9s)
= automatischer Queue-Dispatch OHNE manuellen Eingriff
```

## 7 — Cancel nur eigener Scope (Race-Fix)
```
PILOT-C1b (sleep 60): RUNNING, C2b QUEUED -> C1b CANCEL: CANCELLED
-> C2b auto-gestartet (Capacity frei); C1b bleibt CANCELLED (Race-Fix:
  Monitor überschreibt terminalen Cancel nicht mehr mit COMPLETED)
```

## 8 — Timeout automatisch durch den Service
```
PILOT-T1 (sleep 60, timeout 15): t+18s TIMED_OUT terminal=True
Service selbst: session.timeout.requested -> SIGTERM -> grace -> SIGKILL
Prozess WEG — kein menschliches systemctl kill nötig
```

## 9 — Restart mit laufender + gequeuer Session
```
Vor Restart: R9a RUNNING, R9b QUEUED
Nach Restart: Reconcile -> R9a rediscovered (RUNNING, 1 Instanz, kein Duplikat)
R9b blieb QUEUED und startete später automatisch (COMPLETED)
```

## 10 — Nonzero-Exit -> FAILED
```
PILOT-F3 (exit 3): FAILED, exit_code=3, reason="process exited with code 3"
Exit-Code via Adapter-Watchdog (proc.wait), nicht systemd-Status
```

## 11 — Base-Repo unverändert
```
Tree VOR:  0be1cf7d4ff116d7496028ff7f70643e00c76074
Tree NACH: 0be1cf7d4ff116d7496028ff7f70643e00c76074 (identisch)
Porcelain: 0 Änderungen
```

## 12 — Worktrees in git worktree list --porcelain
```
31+ Worktrees gelistet (inkl. Session-Worktrees); git worktree remove --force
+ prune sauber (BUILDROOM-PILOT-FINAL2-bf2 entfernt, Metadaten korrekt)
```

## 13 — Externe Session-Fingerprints unverändert
```
hermes 5196/5310/6415: UNVERÄNDERT | codex 50599/50643: UNVERÄNDERT
(opencode/codex pid 35001 war ein transienter hermes-Snapshot-Helfer,
  der natürlich endete — keine Pilot-Session nutzte diese PID;
  31 Pilot-PIDs enthalten 35001 nicht)
```

## 14 — Keine Secrets/Prompts in State
```
sessions.json: 0 Secret-Matches | queue.json: 0 (prompt redacted) |
events.jsonl: 0 — Prompt-Summary konstant "[prompt redacted]" + sha256-Hash
```

## Buildroom-Handoff + EvidenceBundle
```
BUILDROOM-PILOT-FINAL2 (bf2, job_e3d3b42ad63f):
  session mxs_a3735cfc77bd45e5, lifecycle COMPLETED, exit 0,
  harness hermes_scoped, worktree/BUILDROOM-PILOT-FINAL2-bf2,
  base e1375f290ac3, scope conduvera-mxs_....scope,
  evidence_ref conduvera://session/mxs_a3735cfc77bd45e5/evidence
Bridge: wait_terminal(attempt_id) löst Session-ID aus Queue-State auf
```

## Event-Kette (Outbox)
```
job.accepted, attempt.created, session.queued, session.claimed,
session.start.requested, session.started, session.status.observed,
session.completed/failed/cancelled, session.timeout.requested,
session.timed_out, session.reconciled — vollständig, keine fehlenden Typen
Worktree-Fehler-Loop gefixt: 1 Event pro Fehler (vorher 652 Spam)
```

## Tests
```
300 passed, 1 skipped (volle Suite) · ruff: 0 Fehler
14 neue Pilot-Tests: FIFO-Capacity-1, Claim-One-Owner, Release,
process_gone->COMPLETED, Timeout-Escalation, Terminal-Exactly-Once,
External-Never-Monitored, Repo-Allowlist, Identifier-Normalisierung,
Duplicate-Reject, Prompt-Redaction, Outbox-Durable-Delivery
```
