# Conduvera Operational Harness Control Plane v1 — Operating Instructions

## Übersicht

Persistenter Conduvera-Steuerungsdienst (Unix-Socket, localhost-only), der
MANAGED Harness-Sessions in transienten user systemd scopes betreibt:
Hermes (scoped), native Codex CLI, OpenCode. Buildroom reicht Jobs über eine
schmale Bridge ein; der Router wählt Harness + Model-Binding deterministisch.

## Installation / Start (nach Reboot)

```bash
# 1. Unit installieren und aktivieren
cp deploy/conduvera-control-plane.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now conduvera-control-plane.service

# 2. Status prüfen
systemctl --user status conduvera-control-plane.service

# 3. Doctor (Harnesses + Registry)
conduvera control-plane doctor
conduvera control-plane doctor --json
```

## Exakte CLI-Befehle

```bash
# Service-Health
conduvera control-plane health

# Job einreichen (Router wählt Harness deterministisch)
conduvera control-plane submit --task TASK-001 --attempt a1 \
  --harness hermes_scoped --prompt "Antworte mit genau einem Wort: PONG"

# Listen
conduvera control-plane list
conduvera control-plane list --json

# Inspect/Status einer Session
conduvera control-plane inspect mxs_<id>
conduvera control-plane inspect mxs_<id> --json

# Cancel (nur MANAGED; EXTERNAL_* wird abgelehnt)
conduvera control-plane cancel mxs_<id>

# Cleanup (nur Session-eigene Resourcen)
conduvera control-plane cleanup mxs_<id>

# Reconcile nach Service-Restart
conduvera control-plane reconcile

# Capabilities einer Harness
conduvera control-plane capabilities hermes_scoped
conduvera control-plane capabilities codex_cli
conduvera control-plane capabilities opencode_cli
```

## Buildroom-Bridge

```python
from conduvera.control_plane.buildroom_bridge import BuildroomBridge
bridge = BuildroomBridge()
r = bridge.submit(task_id="JOB-1", attempt_id="a1", task_class="fixture",
                  prompt="Antworte mit genau einem Wort: PONG")
# r["session"]["session_id"], r["harness"], r["route_decision"]
bridge.status(sid); bridge.cancel(sid)
```

Legacy-Direktpfad: `BuildroomBridge(legacy_direct=True)` — Rollback-Flag.

## Event-Outbox (n8n-konsument, nie Autorität)

```python
from conduvera.control_plane.outbox import EventOutbox
ob = EventOutbox("~/.local/state/conduvera/outbox/events.jsonl",
                 webhook_url="http://127.0.0.1:5678/webhook/conduvera")
ob.append(event)   # redacted (Secrets -> [REDACTED])
ob.read(limit=100)
```

## Rollback / Uninstall

```bash
# Stop + Disable
systemctl --user stop conduvera-control-plane.service
systemctl --user disable conduvera-control-plane.service

# Unit entfernen
rm ~/.config/systemd/user/conduvera-control-plane.service
systemctl --user daemon-reload

# State entfernen (Registry, Worktrees, Evidence, Outbox)
rm -rf ~/.local/state/conduvera/
```

## Betriebs-Regeln

- Sessions starten IMMER in einem eigenen transienten scope (systemd-run
  --user --scope); Prozessgruppen-Fallback nur wenn Scopes nicht verfügbar.
- Ownership = pid + start_time + boot_id (PID allein ist nie Beweis);
  PID-Reuse -> LOST, nie Kontrolle über fremden Prozess.
- EXTERNAL_MANUAL_OBSERVED / EXTERNAL_UNKNOWN: control_rights=none,
  cancel() lehnt ab.
- Timeout: SIGTERM -> 3s grace -> SIGKILL nur an den eigenen Scope.
- Registry: atomare Writes, mode 0600, Schema-Version 1.
- pause/steer/resume/checkpoint/attach/streaming: strukturiert UNSUPPORTED (v1).
