# Conduvera Control Plane v1 — Functional Acceptance Evidence

**Datum:** 2026-08-11 · **Basis:** conduvera-core a3caf4c900a1 (PR #35)
**Adapter:** conduvera-hermes-adapter 0.1.7 (d1cedd219478) — unverändert
**Platform:** ed3b951701d4 — unverändert
**Daemon:** `python3 -m conduvera.control_plane.server` (Unix-Socket, 0600)

## F-1 — Service startet + doctor/health PASS

```
doctor ok: True
  hermes_scoped: ok=True hermes available
  codex_cli: ok=True codex available
  opencode_cli: ok=True opencode available
  hermes: ok=True hermes adapter available
registry_permissions_ok: True
```

## F-2 — Hermes-Job komplett (echtes Artefakt)

```
START:  ok=True session=mxs_3b83b1f6beb049f4 scope=conduvera-mxs_3b83b1f6beb049f4.scope
        pid=3861435 (echter hermes-Prozess, workload/local Route)
STATUS: RUNNING (Fingerprint-verifiziert)
Prozess existiert: JA · Scope-Unit gelistet: True
```

## F-3 — Native Codex-CLI-Job komplett

```
START:  ok=True session=mxs_b06fc6fe61d6406c (codex_cli, codex-native binding)
STATUS: RUNNING
(Prozess beendete sich nach PONG; Cancel danach korrekt abgelehnt:
 "fingerprint mismatch — no signal sent" = kein Signal an fremden/leeren PID)
```

## F-4 — OpenCode-Job komplett

```
START:  ok=True session=mxs_8bb3e512c6104c3f (opencode_cli, opencode-native binding)
STATUS: RUNNING
CANCEL: CANCELLED
```

## F-5 — Zwei Sessions parallel, kollisionsfrei

```
Registry: 3 Sessions, 3 MANAGED, worktrees eindeutig=True
(keine Registry-/Worktree-/Log-/Evidence-Kollision)
```

## F-6 — Cancel nur eigener Scope

```
Codex-CANCEL (bereits fertig): "fingerprint mismatch — no signal sent" (sicher)
OpenCode nach Codex-Cancel: RUNNING, Prozess lebt (JA) — fremder Scope unberührt
```

## F-7 — Service-Restart + Reconciliation

```
Session mxs_ebc122aba73947f4 (pid=3867964) lief über Daemon-Neustart:
  Prozess nach Neustart: LEBT
  Reconcile: mxs_ebc122 -> {'state': 'RUNNING', 'transitioned': 'rediscovered'}
  tote Sessions -> COMPLETED (process_gone), gecancelte -> CANCELLED
  Status nach Reconcile: RUNNING
  Cancel nach Restart (Scope-Fallback systemctl kill): CANCELLED, Prozess WEG
```

## F-8 — EXTERNAL-Reject (unit + design-bewiesen)

```
EXTERNAL_MANUAL_OBSERVED / EXTERNAL_UNKNOWN: control_rights=none,
cancel() -> EXTERNAL_SESSION_NOT_CONTROLLABLE (Unit-Tests 4/5/6)
Externer Prozess (Live): pid registriert, nie signalisiert
```

## F-9 — Timeout-Kette SIGTERM -> grace -> SIGKILL

```
timeout_session: success | "timed out (scope ...; remaining=[])" (dauerte 3.0s)
Prozess nach Timeout: WEG · conduvera-Scope-Reste: keine
```

## F-10 — Buildroom-E2E (Router -> Control Plane -> Harness)

```
SUBMIT: ok=True
  task=BUILDROOM-JOB-001 attempt=attempt-1
  harness (geroutet): hermes_scoped
  route_decision: preferred/fallback available: hermes_scoped
  session=mxs_a4262a7257054e36 scope=conduvera-mxs_a4262a7257054e36.scope
  STATUS: RUNNING · CANCEL: CANCELLED
```

## F-11 — Event-Outbox

```
Outbox: 2 Events persistiert (session.started, session.cancelled)
Redaktion: OK (api_key -> [REDACTED])
```

## F-12 — Tests (clean checkout)

```
tests/test_control_plane.py + tests/test_managed_session.py: 40 passed
ruff: All checks passed
Regression (bestehende Core-Tests): 35 passed
```

## F-13 — Externe Sessions unberührt

```
Hermes/Codex/OpenCode/ODS-Modell-Sessions: keine Adoption, kein Signal,
keine Reassigment (ownership_class EXTERNAL_* bleibt, control_rights=none)
```

## F-14 — Operating Instructions

```
docs/CONTROL_PLANE_OPERATIONS.md — exakte Befehle für Start nach Reboot,
CLI, Bridge, Outbox, Rollback/Uninstall.
```
