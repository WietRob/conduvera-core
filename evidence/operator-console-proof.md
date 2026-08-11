# Operator Console — Live-Proof (OPERATOR-CONSOLE-V1)

**Datum:** 2026-08-11 · **Basis:** conduvera-core cff25934 (vor PR)
**Service:** conduvera-control-plane.service

## Neue Operator-Surface: `conduvera control-plane console [--json]`

Konsolidierte Ansicht über die reale Control-Plane-API (Daemon-Methode
`console`, kein Öffnen von State-Dateien). Drei Sektionen mit Zählern:

```
Operator Console — queued=N running=M terminal=K (server_time)
[QUEUED]    job_id/task_id/harness/type/payload_ref/base/hash/queued_s
[RUNNING]   session_id/task_id/harness/elapsed_s/scope/pid/worktree/base/deadline
[TERMINAL]  job_id/task_id/state/exit/reason/evidence(result_refs)/payload/hash
```

## Live-Ergebnis (gegen laufende Control Plane)

```
counts: queued=0 running=0 terminal=14
TERMINAL enthält CONSOLE-RUN (job_a43d9f258daa) COMPLETED exit=0,
  evidence=[stdout.txt#<hash>, stderr.txt#<hash>], payload=pl_..., hash=sha256:...
```

## Eigenschaften (Tests abgesichert)
- `console_view` liefert queued/running/terminal + counts + server_time_utc
- queued zeigt payload_ref + content_sha256 (nie raw Prompt)
- running zeigt worktree/base_commit/elapsed_s/deadline_utc
- terminal zeigt state/reason/exit_code/result_refs
- `--json` und Human-Form zeigen dieselbe Wahrheit (getestet)
- kein raw Prompt in der gesamten Ansicht (getestet: SECRET_RAW_PROMPT_MARKER
  fehlt im repr)

## Tests
335 passed, 1 skipped · ruff 0
3 neue Operator-Console-Tests.

## Nächster Schritt (nach PR)
Kein neues Goal. Operator Console ist damit abgeschlossen; Betrieb erfolgt
über `conduvera control-plane console`.
