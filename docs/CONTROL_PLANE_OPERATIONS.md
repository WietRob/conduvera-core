# Conduvera Managed Control Plane v1 — Internal Alpha (Operating Instructions)

## Übersicht

Persistenter Conduvera-Steuerungsdienst (systemd user service, Unix-Socket
localhost-only) für MANAGED Harness-Sessions:

- jede Session läuft in einem transienten user systemd scope (echte
  cgroup-Isolation, KillMode=control-group);
- jeder MANAGED Task erhält einen ECHTEN Git-Worktree aus einem exakten
  Base-Commit (proven via `git worktree list --porcelain`);
- Multi-Session-Scheduler: persistente Queue, globale + per-Harness
  Concurrency-Limits, Tombstones/Retention;
- Multi-Harness: Hermes (scoped), native Codex CLI, OpenCode (Capability-
  Subset, strukturiert UNSUPPORTED für fehlende Operationen);
- Restart-sichere Reconciliation (Fingerprint-basiert, PID-Reuse → LOST);
- Timeout: SIGTERM → grace → SIGKILL nur an den eigenen Scope;
- Buildroom-Bridge (submit → router → control plane → harness → evidence);
- Event-Outbox (MXOS-EVIDENCE-1.0.0, redacted, n8n-konsument).

## Start nach Reboot

```bash
systemctl --user enable --now conduvera-control-plane.service
systemctl --user status conduvera-control-plane.service
conduvera control-plane doctor
```

## Operator-CLI (alle mit --json)

```bash
conduvera control-plane health
conduvera control-plane submit --task TASK-001 --attempt a1 \
  --harness hermes_scoped --prompt "..."        # -> job_id/attempt_id/session_id
conduvera control-plane list                     # jobs + sessions
conduvera control-plane inspect <session_id>     # Status + worktree + scope
conduvera control-plane cancel <session_id>
conduvera control-plane cleanup <session_id>
conduvera control-plane reconcile                # nach Service-Restart
conduvera control-plane capabilities <harness>
conduvera control-plane logs <session_id>
```

## Buildroom-Bridge

```python
from conduvera.control_plane.buildroom_bridge import BuildroomBridge
b = BuildroomBridge()
r = b.submit(task_id="JOB-1", attempt_id="a1", task_class="fixture",
             repo="conduvera-core",
             base_commit="f54b759b100b4ee9b4cdf46c245f1db48972fee7",
             prompt="sleep 25 && echo PONG", timeout_s=90)
# r["job_id"], r["attempt_id"], r["session"]["session_id"], r["harness"]
b.status(sid); b.cancel(sid)
```

Legacy-Direktpfad: `BuildroomBridge(legacy_direct=True)` (Rollback-Flag).

## State-Verzeichnisse (XDG, nie /tmp)

```text
~/.local/state/conduvera/
  registry/sessions.json      (0600, Schema-Version)
  scheduler/queue.json        (0600, atomar, Jobs + Attempts + Tombstones)
  worktrees/<task>-<attempt>/ (echte Git-Worktrees)
  evidence/                   (Event-Envelopes)
  outbox/events.jsonl         (redacted Event-Outbox)
```

## Rollback / Uninstall

```bash
systemctl --user stop conduvera-control-plane.service
systemctl --user disable conduvera-control-plane.service
rm ~/.config/systemd/user/conduvera-control-plane.service
systemctl --user daemon-reload
rm -rf ~/.local/state/conduvera/    # State (Worktrees, Registry, Queue, Evidence)
```

## Betriebs-Regeln

- Ownership = pid + start_time + boot_id (+ command-Beobachtung); PID allein
  ist nie Beweis; PID-Reuse → LOST.
- EXTERNAL_MANUAL_OBSERVED / EXTERNAL_UNKNOWN: control_rights=none; cancel()
  lehnt ab (EXTERNAL_SESSION_NOT_CONTROLLABLE).
- pause/steer/resume/checkpoint/attach/streaming: strukturiert UNSUPPORTED.
- Pi bleibt deaktiviert (Sandbox/Permission-Contract nicht durchsetzbar).
- Keine Secrets/Auth-Daten in Registry oder Evidence (redacted).
