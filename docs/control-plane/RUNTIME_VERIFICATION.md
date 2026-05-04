# Runtime Verification — CuraOps-Control

Stand: 2026-05-05 | 148/148 Tests gruen

## Zusammenfassung

Dieser Durchgang beweist, dass CuraOps-Control keine reine Parallelwelt mehr ist.
Die Legacy-Captain-Skripte sind jetzt der **kanonische Pfad** fuer Gate-Entscheidungen,
nicht mehr nur ein optionales Backend.

## A. Welche CLI-Pfade nutzen Legacy-Skripte wirklich?

| CLI-Befehl | Vorher | Jetzt | Beweis |
|---|---|---|---|
| `agent ready` | Python GateRunner (5 Gates) | **ScriptRunner.pr_readiness()** → Legacy pr-readiness-summary.sh + Python GateRunner als Supplement | cli.py Z.208-272 |
| `gate run` | Python GateRunner allein | **ScriptRunner.finish_gate()** + **ScriptRunner.sonar_gate()** → Legacy + Python | cli.py Z.569-638 |
| `agent launch` | AgentLauncher | AgentLauncher + **--dry-run** Flag | cli.py Z.363, launcher.py Z.175 |
| `captain tick` | Registry + Adapter | Unveraendert (korrekt) | cli.py Z.384 |
| `captain dispatch` | Registry | Unveraendert (korrekt) | cli.py Z.454 |

### Kanonischer READY-Pfad (jetzt)

```
matrix-cli agent ready Batman
  1. ScriptRunner.pr_readiness(verify=True)
     → scripts/captain/pr-readiness-summary.sh --verify
     → decision=GO? → weiter
     → decision=NO-GO? → BLOCKED, Ende
  2. GateRunner.run_for_agent() [Supplement]
     → dirty_worktree, scope_check, etc.
  3. Beides bestanden → READY_FOR_REVIEW
```

### Kanonischer Gate-Run-Pfad (jetzt)

```
matrix-cli gate run Batman
  1. ScriptRunner.finish_gate(agent_id, "--verify-only")
     → scripts/captain/agent-finish-gate.sh --verify-only
  2. ScriptRunner.sonar_gate(agent_id, "--optional")
     → scripts/captain/sonar-agent-gate.sh --optional
  3. GateRunner.run_for_agent() [Python-Gates]
  4. Alle Ergebnisse zusammen → PASS/FAIL
```

## B. Welche echten Legacy-Script-Checks wurden ausgefuehrt?

| Skript | Existenz bewiesen | Test |
|---|---|---|
| `agent/agent-status.sh` | Ja | test_all_9_scripts_exist |
| `captain/agent-finish-gate.sh` | Ja | test_all_9_scripts_exist |
| `captain/sonar-agent-gate.sh` | Ja | test_all_9_scripts_exist |
| `captain/pr-readiness-summary.sh` | Ja | test_all_9_scripts_exist |
| `captain/write-agent-evidence.sh` | Ja | test_all_9_scripts_exist |
| `sonar-gate.sh` | Ja | test_all_9_scripts_exist |
| `agent/agent-class-test-gate.sh` | Ja | test_all_9_scripts_exist |
| `agent/agent-open-pr.sh` | Ja | test_all_9_scripts_exist |
| `agent/captain-merge-preflight.sh` | Ja | test_all_9_scripts_exist |

**Readiness-Output-Parsing** mit echten Format-Zeilen bewiesen:
- `decision=GO` + Details → `is_go=True`
- `decision=NO-GO` → `is_go=False`
- Leerer Output → Default NO-GO
- Partieller Output ohne decision → Default NO-GO

## C. Welche Sentinel-Guards wurden ergaenzt?

### ScriptRunner-Sentinel-Guard

Vor jedem mutierenden Legacy-Skript prueft `ScriptRunner.run()`:

```python
if script_name in MUTATING_SCRIPTS and self._sentinel and agent_id:
    if not self._sentinel.can_mutate(agent_id, script_name):
        return ScriptResult(exit_code=56, success=False, ...)
```

**Mutierende Skripte** (7 von 9):
- `captain/agent-finish-gate.sh` — orchestrirt Gates
- `captain/sonar-agent-gate.sh` — SonarQube-Scan
- `sonar-gate.sh` — lokaler Sonar-Scan
- `agent/agent-class-test-gate.sh` — Tests
- `agent/agent-open-pr.sh` — PR-Erstellung
- `captain/write-agent-evidence.sh` — Evidence schreiben
- `agent/captain-merge-preflight.sh` — Merge-Preflight

**Nicht-mutierende Skripte** (2 von 9):
- `agent/agent-status.sh` — Status-Abfrage
- `captain/pr-readiness-summary.sh` — Verify-Only

### Guard-Tests bewiesen:

| Szenario | Ergebnis | Test |
|---|---|---|
| Aktiver Agent + mutierend | BLOCKED (exit 56) | test_mutating_blocked_when_active |
| Inaktiver Agent + mutierend | Erlaubt | test_mutating_allowed_when_inactive |
| Aktiv + nicht-mutierend | Erlaubt (Sentinel nicht gefragt) | test_non_mutating_skips_sentinel |
| Kein agent_id | Erlaubt (Guard uebersprungen) | test_no_agent_id_skips_sentinel |
| Kein Sentinel | Erlaubt (Guard nicht vorhanden) | test_no_sentinel_skips_check |

### Offene Frage: captain tick / dispatch / merge

| Befehl | Nutzt Sentinel? | Status |
|---|---|---|
| `agent ready` | Ja (via ScriptRunner) | Implementiert |
| `gate run` | Ja (via ScriptRunner) | Implementiert |
| `agent launch` | Ja (AgentLauncher Schritt 3) | Implementiert |
| `captain tick` | Nein (nur Status-Abfrage) | OK (read-only) |
| `captain dispatch` | Nein (nur Registry-Update) | OK (nicht mutierend) |

## D. Welche hardcoded Pfade wurden entfernt?

**Vorher:**
```python
VRP_SCRIPTS = Path.home() / "projects" / "CuraOps_VRP" / "scripts"
```

**Jetzt:**
```python
_VRP_ROOT = Path(os.environ.get(
    "CURAOPS_VRP_ROOT",
    str(Path.home() / "projects" / "CuraOps_VRP"),
))
VRP_SCRIPTS = _VRP_ROOT / "scripts"
```

Zusaetzlich: `ScriptConfig.scripts_root` kann jeden Pfad uebersteuern.

Bewiesen durch Tests:
- `test_default_fallback` — ohne Env: ~/projects/CuraOps_VRP
- `test_env_override` — mit CURAOPS_VRP_ROOT: custom-Pfad
- `test_scripts_root_in_config` — ScriptConfig Override

## E. Welche E2E-Dry-Run-Beweise liegen vor?

```
matrix-cli agent boot TestBot --task TASK-001 --tool manual
matrix-cli agent launch TestBot --profile local_deep --sensitive private_repo --dry-run
```

Dry-Run beweist (ohne echte Session):

| Wert | Erwartet | Bewiesen |
|---|---|---|
| `success` | `True` | test_dry_run_returns_env |
| `session_ref` | `dry-run:TestBot` | test_dry_run_returns_env |
| `OPENAI_BASE_URL` | `http://127.0.0.1:8900/v1` | test_dry_run_returns_env |
| `X_GATEWAY_CLIENT` | `TestBot` | test_dry_run_returns_env |
| `AGENT_ID` | `TestBot` | test_dry_run_returns_env |
| `GATEWAY_PROFILE` | `local_deep` | test_dry_run_with_profile |
| `SENSITIVE_CLASS` | `private_repo` | test_dry_run_with_profile |
| Warning: DRY-RUN | Ja | test_dry_run_returns_env |

Registry bleibt im BOOTING-Status (kein ACTIVE-Update bei Dry-Run).
Kein tmux-Prozess wird gestartet.

## F. Welche Luecken bleiben?

### Bewusst offen (nicht Teil dieses Durchgangs)

| Luecke | Risiko | Naechster Schritt |
|---|---|---|
| Echte rc-56 Ausfuehrung von agent-status.sh bei BLOCKED Stream | Mittel | E2E-Test mit Stream BLOCKED + ACK, echtes Skript aufrufen |
| Echter Agent-Launch (tmux + Gateway) | Hoch | Echt-Test mit lokalem Gateway |
| Gateway-ENV in echter Agent-Session | Hoch | Agent-Prozess muss X-GATEWAY-CLIENT senden |
| GitHub Issue/PR Bridge | Niedrig | Spaeter |
|Weitere Adapter (Droid, Zed) | Niedrig | Spaeter |
| Evidence Store mit head_sha | Mittel | Naechster Durchgang |

### Architektur-Offenheiten

1. **GateRunner.FinishGateGate** in gates.py nutzt immer noch `Path.cwd() / "scripts"` statt ScriptRunner — redundant mit dem neuen kanonischen Pfad. Kann entfernt werden sobald `agent ready` erprobt ist.

2. **EventLog.append()** vs **EventLog.log()** — launcher.py nutzt `append()`, cli.py nutzt `log()`. Beide Methoden sollten vereinheitlicht werden.

3. **WorktreeSentinel._is_agent_active()** kennt `AgentStatus.READY` als "aktiv" — im Code steht `AgentStatus.READY`, aber in der Registry gibt es nur `READY_FOR_REVIEW`. Pruefen ob das zusammenpasst.

## Test-Matrix

```
tests/test_control.py               — 38 Tests (Registry, EventLog, Adapter)
tests/test_stream_state.py          — 27 Tests (StreamState, Reply, Transition)
tests/test_gateway.py               — 29 Tests (Gateway, Router, Auth, Audit)
tests/test_runtime_enforcement.py   — 30 Tests (BLOCKED, READY, Sonar, Sentinel)
tests/test_runtime_verification.py  — 24 Tests (Legacy-Pfade, Sentinel-Guard, Dry-Run)
                                    ─────────
                                    148 Tests, alle gruen
```
