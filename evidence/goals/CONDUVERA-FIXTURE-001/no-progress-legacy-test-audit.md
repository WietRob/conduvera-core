# Legacy-Test-Ausführung: test_buildroom_no_progress.py (isolierter Setup-Befund)

Datum: 2026-08-04
Goal: port-buildroom-no-progress-with-proven-differential-parity

## Setup

```bash
env PYTHONPATH="$WT/legacy/buildroom/source" uv run python -m pytest \
  -q --no-header -p no:cacheprovider legacy/buildroom/tests/test_buildroom_no_progress.py
```

(Isoliertes Import-Setup: nur legacy/buildroom/source auf PYTHONPATH; kein
Live-~/.hermes-State; frische State-dicts in allen Tests.)

## Ergebnis: 8 passed, 1 failed

| Test | Ergebnis |
|---|---|
| test_first_two_identical_observations_remain_waiting | PASS |
| test_third_identical_observation_enters_terminal_hold | PASS |
| test_new_evidence_resets_counter | PASS |
| test_fresh_replacement_task_resets_counter | PASS |
| test_terminal_hold_never_merges_or_transitions_phase | PASS |
| test_peekxd_reviewer_reconciliation_uses_generic_terminal_hold | PASS |
| test_exact_board_worker_log_is_resolved_without_legacy_global_fallback | PASS |
| test_safety_gate_no_progress_uses_live_status_and_enters_hold | PASS |
| test_autopilot_runner_stops_immediately_on_terminal_hold | FAIL |

## Befund zum einzigen Fehlschlag (kein Paritätsproblem)

`test_autopilot_runner_stops_immediately_on_terminal_hold` prüft NICHT die
Python-Funktion `observe_reconciliation`, sondern das SHELL-Skript
`buildroom_autopilot_runner.sh` (liest es per `Path(__file__).parents[1] /
"buildroom_autopilot_runner.sh"` und prüft den HOLD_FOR_BOSS-Gate).

Im frozen Legacy-Snapshot liegt diese Datei unter
`legacy/buildroom/wrappers/buildroom_autopilot_runner.sh` — NICHT an dem vom
Test erwarteten Ort `legacy/buildroom/buildroom_autopilot_runner.sh`.
Deshalb `FileNotFoundError` (nicht ein Semantik-Fehler der Policy).

Verifiziert (read-only): Das Skript in `wrappers/` ENTHÄLT den Gate
`if [[ "$STATUS" == HOLD_FOR_BOSS ]]; then` (Zeile 64) VOR
`(no state change this tick — continuing)` (Zeile 80) — die vom Test
geforderte Semantik (Stopp bei HOLD_FOR_BOSS vor weiterem Tick) ist im
Skript korrekt umgesetzt. Der Test scheitert ausschließlich am Pfad-
Mismatch des frozen Snapshot-Layouts.

## Einordnung (Arbeitsauftrag Punkt 9)

Der Fehlschlag wurde NICHT als „nicht im Scope" verworfen, sondern:
1. isoliert ausgeführt (8/9 grün),
2. Root-Cause exakt benannt (frozen-Layout: wrappers/ vs erwartet buildroom/),
3. Skript-Inhalt verifiziert (Gate-Semantik korrekt vorhanden),
4. als Legacy-Test-Infrastruktur-Mismatch dokumentiert — kein Port-Thema.

Die Funktion `observe_reconciliation` selbst ist vollständig abgedeckt durch:
- 8 bestandene Legacy-Tests (inkl. Reset, Schwelle, Hold, Task-Wechsel),
- 18 neue Differentialtests (Legacy vs Neu, identische Ereignisfolgen,
  vollständiger State-Vergleich vor/nach jedem Schritt).

Das frozen Legacy wird NICHT mutiert (keine Datei wird an den vom Test
erwarteten Ort kopiert) — das würde die SOURCE_MANIFEST-Integrität brechen.
