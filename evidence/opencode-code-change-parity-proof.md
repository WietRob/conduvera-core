# OpenCode Code-Change Parity — Live-Proof

**Datum:** 2026-08-11 · **Basis:** conduvera-core 7a3bdd70 (vor PR)
**Service:** conduvera-control-plane.service · **Harness:** native opencode_cli (1.18.3)
**Fixture:** ~/projects/conduit-fixture (Base 8cb595f3)

## Vollständiger Live-OpenCode-Code-Change-Job

```
BuildroomBridge.submit(task_id=OPENCODE-FIX-006, attempt_id=of6,
  task_class=code_change, repo=conduit-fixture, base_commit=8cb595f3,
  override_harness=opencode_cli)
  -> submit_job -> TaskPayloadStore -> queue -> claim -> dispatch_claimed
  -> opencode run --format json <instructions> (systemd-scope, cwd=worktree)
  -> Monitor -> COMPLETED exit 0

job_113939107b72 · attempt of6 · session mxs_0d59fc20... (scope conduvera-mxs_*.scope)
Worktree: ~/.local/state/conduvera/worktrees/OPENCODE-FIX-006-of6 (detached 8cb595f)
```

## OpenCode-Task-Ergebnis (native_opencode code-change parity)

```
calc.py VOR  (Worktree):  return a - b  # BUG: should be a + b
calc.py NACH (Worktree):  return a + b
relativePath: "calc.py"   <- relativ zum WORKTREE (nicht mehr home/.../conduit-fixture/)
pytest im Worktree:       1 passed in 0.07s (exit_code 0)
BASE-Repo: unverändert    "return a - b" (BUG bleibt im Base), Porcelain 0
```

## Wichtigster Fix dieser Parity

**systemd-run `--working-directory` reicht für OpenCode NICHT aus.** Es setzt
nur die opencode "instance directory", aber das tatsächliche grandchild-cwd
(was OpenCode für git-Auflösung nutzt) erbt den CALLER-PWD (Service-WD). Damit
edierte OpenCode das BASE-Repo (relativePath home/.../conduit-fixture/calc.py).

Fix: fester interner Wrapper `cd <worktree> && exec <binary> <args>` im
systemd-scope, wobei **alle Caller-Argumente (inkl. Prompt) via shlex.quote**
gequotet werden (kein `bash -c <caller>`-Injection). Nach dem Fix:
relativePath = "calc.py" (Worktree), Base unverändert.

Zusatzfix: `_systemd_scope_available()` nutzte eine feste `--unit=conduvera-probe`
die bei wiederholten Aufrufen kollidierte -> instabil. Jetzt eindeutige
Unit-UUID + `_use_scope()` re-checkt zur Dispatch-Zeit.

## Secret-Leak behoben (Seiteneffekt der Parity-Arbeit)

Ein alter Pi-Eval-Scope (`conduvera-mxs_46c10d7a2a414b9b.scope`) zeigte
`--api-key sk-dre...` in `systemctl list-units` (Secret im Prozess-argv).
Wurde beendet. Dies war ein Altbestand aus der Pi-Evaluation, kein neuer
Leak durch diese Arbeit.

## OpenCode-Harness-Kapazität (ehrlich)

- discover/validate/start/status/cancel/evidence/cleanup: ✓ (systemd-scope)
- code_change live bewiesen (calc.py-Fix, pytest pass) ✓
- pause/steer/checkpoint/attach: UNSUPPORTED (kein Fake)
- Modell: OpenCode-eigene native Auth (~/.local/share/opencode/auth.json) +
  Default-Modell aus opencode.json — kein ODS/LiteLLM/Route-Change

## Tests

Volle Suite: 320 passed, 1 skipped · ruff 0.
13 durable-code-change-Tests bleiben grün (task_command-Reject, shlex-Wrapper,
Payload-Roundtrip, Exactly-Once, Hash-Mismatch, Restart-Survival).
