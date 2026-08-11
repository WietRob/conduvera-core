# Durable Code-Change — Internal Alpha v1 Live-Proof

**Datum:** 2026-08-11 · **Basis:** conduvera-core 3ad5c06b (vor PR)
**Service:** conduvera-control-plane.service (systemd user, kein EnvironmentFile)
**Fixture:** `~/projects/conduit-fixture` (dediziertes Git-Fixture, Base 8cb595f3)
**Harness:** native `codex_cli` (codex-cli 0.147.0, `codex exec` non-interaktiv)

## Vollständiger Live-Codex-Code-Change-Job

```
BuildroomBridge.submit(task_id=CODEX-FINAL-1, attempt_id=cfx1,
  task_class=code_change, repo=conduit-fixture, base_commit=8cb595f3,
  override_harness=codex_cli)
  -> submit_job -> TaskPayloadStore -> queue -> claim -> dispatch_claimed
  -> codex exec --sandbox danger-full-access --json <instructions>
  -> Monitor -> COMPLETED

job_4a180eb468dd · attempt cfx1 · session mxs_15d013b1754d4868
Worktree: ~/.local/state/conduvera/worktrees/CODEX-FINAL-1-cfx1 (detached 8cb595f)
```

## Codex-Task-Ergebnis (Work E)

```
calc.py VOR  (Worktree):  return a - b  # BUG: should be a + b
calc.py NACH (Worktree):  return a + b
pytest im Worktree:       1 passed in 0.08s (exit_code 0 im stdout-JSONL)
Patch (git diff --binary):
  -    return a - b  # BUG: should be a + b
  +    return a + b
stdout/stderr Artifakte:  mxs_15d013b1754d4868.stdout.txt (Codex-JSONL inkl.
  command_execution exit_code:0 + "1 passed"), stderr.txt
```

## Base-Repository unverändert (Akzeptanz 11)

```
~/projects/conduit-fixture: Porcelain 0, calc.py = "return a - b" (BUG bleibt
  im Base — Codex schrieb NUR in den dedizierten Worktree).
git worktree list --porcelain zeigt den detached Worktree (8cb595f detached).
```

## Durable Payload Store (Work B, Akzeptanz A)

```
State-Dir 0700 · Payload-Datei 0600 · atomar (tmp+fsync+rename) · writer-lock
payloads/pl_4997f6df3e9541b5.json  = { instructions, repo, base_commit,
  test_plan, expected_artifacts, secret_refs, created_at, retention_until,
  content_sha256 }
QUEUE/REGISTRY/OUTBOX: NUR payload_ref + content_sha256 — KEIN Raw-Task-Text
Restart-Proof (Work F): queued Attempt überlebte Daemon-Restart, exakte
  Instructions wurden nach Capacity-Freigabe auto-dispatched.
```

## Exactly-Once (Akzeptanz B)

```
Ein Attempt verursacht genau EINEN gateway.start_session-Aufruf
(dispatch_claimed: nach CLAIMED -> RUNNING, zweiter dispatch rejected).
Ein terminaler State/Event genau einmal (_emitted_terminal).
Duplicate-Dispatch idempotent abgelehnt (Test).
```

## task_command entfernt (Work C, Akzeptanz C)

```
submit_job-Signatur: task_command entfernt (nicht mehr public).
Adapter: "bash -c <caller>"-Zweig entfernt — kein externer Shell-Pfad.
dispatch_claimed ruft start_session GENAU EINMAL.
Negative Tests: public submit reject task_command; Shell-Metazeichen im
  Payload erreichen nie einen Shell-Aufruf; failed start hinterlässt kein
  unregistriertes Child.
```

## Pi-Quarantäne (Work D, Akzeptanz D)

```
pi_cli: enabled=false in harness-registry.yaml · kein native_pi-TaskClass ·
kein pi_cli in DEFAULT_BINDINGS · nicht in Service-adapter_ids-Default.
Global installiert + ~/.pi/agent/models.json + Pi-Evidence bleiben erhalten.
```

## Secret-Boundary (Work E, Akzeptanz E)

```
Service-Unit: KEIN EnvironmentFile (lädt nicht mehr secrets.env).
Service-argv: nur "/usr/bin/python3 -m conduvera.control_plane.server".
0 Secret-Variablen im Service-Env (keine LITELLM/OPENAI/TOKEN).
fingerprint.command redacted (_redact_command) — kein Raw-Prompt im Registry.
Registry/Queue/Outbox: 0 Secrets, 0 Raw-Task-Text.
Rotiertes Credential bleibt gültig; keine Werte ausgegeben (nur Namen/Präsenz).
```

## Sandbox-Hinweis (transparent)

bwrap workspace-write ist auf diesem Host durch AppArmor blockiert
(`kernel.apparmor_restrict_unprivileged_userns=1`, kein sudo). Codex läuft
daher mit `--sandbox danger-full-access` IM isolierten systemd-Scope
(cwd=Worktree, KillMode=control-group). Die Worktree-Grenze wird durch
Scope-Isolation + byte-identische Base-Verifikation nach dem Lauf
durchgesetzt. Das ist kein Auth-/Routing-/ODS-Change — native Codex-Auth
(~/.codex) unverändert.
```

## Tests

```
Volle Suite: 319 passed, 1 skipped · ruff: 0 Fehler
12 neue Durable-Tests: Payload-Roundtrip, 0600/0700, Hash-Mismatch-Reject,
Missing-Reject, Retention-Idempotenz, Restart-Survival mit exakten
Instructions, Exactly-One-Start, No-Plaintext-in-Stores, task_command-Reject,
Shell-Metachar-Negativ, Duplicate-Dispatch-Reject.
```
