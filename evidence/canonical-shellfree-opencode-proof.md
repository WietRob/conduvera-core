# Canonical EvidenceBundle — Shell-free cwd executor + merged-main OpenCode proof

**Datum:** 2026-08-11 · **Merged-main Beweis nach PR #42**
**Harness:** native opencode_cli (1.18.3) · **Fixture:** ~/projects/conduit-fixture

## Status der historischen Runs
- OPENCODE-FIX-001..005: **FAILED_DIAGNOSTIC** (Base-Write-Bug während
  Shell-Wrapper-Umbau, nicht kanonisch)
- OPENCODE-FIX-006: **SUPERSEDED** (bash-Wrapper, durch shell-freien cwd_exec
  abgelöst)
- OPENCODE-SHELLFREE-2/osf2: **CANONICAL** (merged-main, shell-frei)
- OPENCODE-CANONICAL-2/oc2: **CANONICAL_BESTAETIGUNG** (aktuellerer main
  inkl. operator-console, PR #44)

## Bestätigungslauf (OPENCODE-CANONICAL-2) — main 121fea94

```
core commit: 121fea94af90 (nach PR #42+#43+#44)
task_id:     OPENCODE-CANONICAL-2
job_id:      job_4ddd2f3c863a
attempt_id:  oc2
session_id:  mxs_19cfcc775fdf4f62
scope:       conduvera-mxs_19cfcc775fdf4f62.scope
harness:     opencode_cli (native Auth, opencode.json default model)
base_commit: 8cb595f3cabd1c5f54ed123b391673b3740ef51b
worktree:    ~/.local/state/conduvera/worktrees/OPENCODE-CANONICAL-2-oc2
lifecycle:   COMPLETED · exit 0
Spawn:       systemd-run --scope ... python3 -m cwd_exec --cwd <wt> -- \
             opencode run --format json --dir <wt> "<instructions>"
             (cwd_exec: True, bash/sh: False, raw prompt: False, redacted: True)
Ergebnis:    Worktree calc.py "a - b" → "a + b"; relativePath "calc.py"
             pytest 1 passed; BASE calc.py "a - b" unverändert;
             BASE tree ec3f64c0da2f7d0d721d49552f71623b8eb80b59 == vor;
             BASE porcelain 0 vor und nach.
```

## Canonical Run (OPENCODE-SHELLFREE-2)

```
core commit: 1973ef4535c0 (vor PR) → nach PR #42
task_id:     OPENCODE-SHELLFREE-2
job_id:      job_52f8e53f1244
attempt_id:  osf2
session_id:  mxs_ee3264cea36c4f60
scope:       conduvera-mxs_ee3264cea36c4f60.scope
harness:     opencode_cli (model: opencode.json default, native Auth)
base_commit: 8cb595f3cabd1c5f54ed123b391673b3740ef51b
worktree:    ~/.local/state/conduvera/worktrees/OPENCODE-SHELLFREE-2-osf2
payload_ref: pl_<id> (TaskPayloadStore, hash-verifiziert)
lifecycle:   COMPLETED (process exited normally)
exit_code:   0 (pytest 1 passed)
```

## Spawn (kein bash/sh)
```
systemd-run --user --scope --unit <scope> --collect --quiet \
  /usr/bin/python3 -m conduvera.harness.cwd_exec --cwd <worktree> -- \
  opencode run --format json --dir <worktree> "<instructions>"
```
argv-basiert, shell-frei (os.chdir + os.execvpe), Prompt unverändert.

## Ergebnisse
```
Worktree calc.py:  "return a + b"   (OpenCode-Fix im dedizierten Worktree)
relativePath:      "calc.py"        (relativ zum Worktree, NICHT Base)
pytest im Worktree: 1 passed in 0.08s
BASE calc.py:      "return a - b"   (unverändert)
BASE tree:         ec3f64c0da2f7d0d721d49552f71623b8eb80b59 (vor == nach)
BASE porcelain:    0 (vor und nach)
```

## Adversarial-Beweis (Tests, nicht Quelltext-grep)
- Prompt mit `$(touch /tmp/conduvera-injected)` `; touch ...-2` `` `touch ...-3` ``
  Quotes, Newlines, Backslashes:
  - erreicht das Fixture UNVERÄNDERT (argv[-1] == prompt)
  - erzeugt KEINE Marker-Datei (0 nach Lauf)
  - kein Shell-Parent (unmittelbarer Parent ist python3/execvpe)
- Boundary: nicht-allowlistete/relative/symlink-cwd + leere argv abgelehnt
- Exactly-once: ein Attempt = ein cwd_exec-Helper + ein Harness

## Secret-Boundary
- kein Secret in argv (cwd_exec nimmt nur --cwd + bin + argv, nie Keys)
- kein EnvironmentFile im Service · Service-argv nur `python3 -m server`
- kein Raw-Prompt in Registry/Queue/Outbox (nur payload_ref + hash)

## Tests
Volle Suite: 332 passed, 1 skipped · ruff 0
12 neue Security-Tests (cwd_exec + adversarial + boundary + exactly-once)
