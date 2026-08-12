# Goal Ledger — deliver-conduvera-operational-activity-workspace-v1

## Arbeitsschritte (workstreams)
- WS-A: Product Contract + Rebaseline
- WS-B: Activity Workspace (graphical)
- WS-C: Live Update + Consistency
- WS-D: Operator Actions (cancel/retry/cleanup/inspect)
- WS-E: Restart + Recovery
- WS-F: Multi-Harness real work (Hermes + OpenCode)
- WS-G: Failure + Safety Matrix

## Verifizierte Fakten (Rebaseline, 2026-08-12)
- core head 537ddf3dd4c7 == GH; adapter d1cedd219478; platform ed3b951701d4
- Service: conduvera-control-plane active, Capacity 2; Porcelain 0
- Base-Tree ec3f64c0da2f7d0d721d49552f71623b8eb80b59 (fixture)
- Control-Plane: Unix-socket JSON API (daemon.py), KEIN HTTP, KEINE UI-Foundation
- console endpoint (JSON): queued/running/terminal + counts (PR #44/#46)
- console_view sortiert newest-first; --limit deterministisch (PR #46)
- exit_code: Adapter-Watchdog -> collect_evidence -> engine -> job -> console (PR #46)
- cwd_exec registry-bound (git worktree porcelain + base + task/attempt) (PR #46)
- opencode Prompt via STDIN (secret-safe argv) (PR #46)
- task_command entfernt; kein bash -c (PR #40-43)
- TaskPayloadStore persistent, Hash-verify (PR #40)
- Harnesse: hermes_scoped, codex_cli, opencode_cli, hermes (pi_cli disabled)

## Aktuelles Design (Entscheidungen)
- D1: Kein neues schweres UI-Framework. conduvera-core hat keine UI-Foundation;
  eigenständiges HTML/JS-Workspace (`conduvera/ui/activity.html`) + minimaler
  HTTP-Bridge um den bestehenden Daemon = kleinste produktionsfähige Lösung
  (Browser kann Unix-Socket nicht direkt ansprechen).
- D2: HTTP `GET /api/console` + `POST /api/<action>` delegieren an den
  bestehenden Service (gleiche Records, keine doppelte State-Authority).
- D3: Unix-Socket-Daemon bleibt State-Authority; HTTP-Server ist reiner Adapter.

## Akzeptanz-Szenarien
- (ausstehend, in WS-G abzuschließen)

## Offene Fehler
- (keine bekannt bei Start)

## Nächste Aktion
- WS-A: API/Event-Contract finalisieren; HTTP-Bridge bauen (PR #1)
