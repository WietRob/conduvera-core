# Runtime Handoff Gaps — Live-Proof (RUNTIME-HANDOFF-V1)

**Datum:** 2026-08-12 · **Basis:** conduvera-core 3e31f5f (vor PR)
**Service:** conduvera-control-plane.service (Capacity 1)

## Work A — Secret-safe Payload (stdin-Transport)

OpenCode liest den Prompt von **STDIN** (`opencode run` ohne message-arg),
nicht aus argv. `_opencode_args` hängt keinen Prompt-Argument an; der Adapter
piped ihn via `proc.stdin` durch (systemd-run + cwd_exec reichen stdin durch).

Live-Beweis (RH-OPCODE/rh1, job_519cc8701a62):
```
fingerprint.command: systemd-run ... python3 -m cwd_exec --cwd <wt>
                     --task-id RH-OPCODE --attempt-id rh1
                     --repo <repo_path> --base 8cb595f3 ... -- [opencode run ...]
RAW-PROMPT im command: False   <- kein "Fix calc.py"/"add(a,b)" im argv
binding-args im spawn: True    <- --task-id/--attempt-id/--repo/--base da
harness erhält exakten Prompt (calc.py fix erzeugt, pytest 1 passed, exit 0)
```

## Work B — Registered Worktree Binding

cwd_exec validiert gegen `git worktree list --porcelain` des allowlisteten
Repos + erwarteten base_commit + task/attempt-Bindung. Negativ-Tests:
- unregistrierte Dir unter Root abgelehnt
- falscher base_commit abgelehnt (head != expected)
- falsche task/attempt-Bindung abgelehnt (binding mismatch)
- symlink escape abgelehnt
- pruned Worktree abgelehnt
(8 Runtime-Handoff-Tests green)

## Work C — Exact Exit-Code Propagation (exit 7)

Kette: Adapter-Watchdog `proc.wait()` -> collect_evidence exit_code ->
engine `_handle_process_gone` -> session/attempt/job FAILED + exit_code ->
console JSON/human.

- Live: cwd_exec + exit7.py (sys.exit(7)) -> rc=7 (direkter Executor-Beweis)
- Integration: Fake-Gateway exit 7 -> job.state FAILED, job.exit_code=7,
  console terminal exit_code=7 (2 Tests green)

## Work D — Live Operator-Console Lifecycle (Capacity 1)

```
1. LIVE-A (opencode, job_eca8618a072a) submitted -> nimmt Slot
2. LIVE-B (opencode, job_4fa0dd692023) submitted -> QUEUED
3. Während A läuft (console snapshot):
   counts: queued=1 running=1
   RUNNING: LIVE-A scope=conduvera-mxs_...cb9e138e7c4d04.scope elapsed=5.3s base=8cb595f3ca
   QUEUED:  LIVE-B state=QUEUED payload=pl_6885a1e0e hash=sha256:2fbdd
4. Nach A's Ende: B auto-dispatched (Capacity-Freisetzung)
   Beide TERMINAL: LIVE-B COMPLETED exit 0, LIVE-A COMPLETED exit 0
5. Sortierung newest-first: LIVE-B (05:20:35) > LIVE-A (05:20:11) > RH-OPCODE
   --limit 3 deterministisch (Human + JSON zeigen dieselben neuesten 3)
```

## Base-Repo
```
VOR:  tree ec3f64c0da2f7d0d721d49552f71623b8eb80b59 · porcelain 0
NACH: tree ec3f64c0da2f7d0d721d49552f71623b8eb80b59 · porcelain 0
calc.py im Base bleibt "return a - b" (BUG unverändert)
```

## Tests
Volle Suite: 345 passed, 1 skipped · ruff 0
8 Runtime-Handoff (Work B) + 2 Exit-Code-Propagation (Work C) + angepasste
Regression (opencode stdin).
