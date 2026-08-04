# Behaviour-Matrix: buildroom_no_progress (Legacy → Neu, DOD-01/02)

Quelle: legacy/buildroom/source/buildroom_no_progress.py (98 Zeilen, frozen,
SOURCE_MANIFEST sha256 e11034326f7f47f5e70e0b5acff84ab7a06f8094689f57a8726b7b7fab7ac7a7)

## Öffentliche API (vollständig inventarisiert)

- `NoProgressResult` (frozen dataclass): `count: int`, `terminal_hold: bool`,
  `fingerprint: tuple[str, ...]`
- `observe_reconciliation(state, *, phase, status, blocker, task_id,
  task_board="", evidence_fingerprint, log_fingerprint, threshold=3) -> NoProgressResult`

## Eingabe-/Zustandsmodell

- `state` ist ein MutableMapping (dict); liest/schreibt `state["no_progress"]`
  (dict) und bei terminal_hold zusätzlich `state["status"]`,
  `state["blocker"]`, `state["root_blocker"]`.
- Fingerprint = (phase, status, blocker, task_id, evidence_fingerprint,
  log_fingerprint) — alle als str.
- Schwellwert: `threshold >= 1`, sonst ValueError "NO_PROGRESS_THRESHOLD_INVALID".
- Zeit: `observed_at = datetime.now(timezone.utc).isoformat()` je Aufruf
  (nicht deterministisch; nur in State gespeichert, nie verglichen).

## Caller (Legacy, NICHT portiert in diesem Goal)

- legacy/buildroom/source/peekxd_buildroom_loop_v20.py (BuildroomOrchestrator.
  record_no_progress — Orchestrator-Methode)
- legacy/buildroom/source/buildroom_cycle49_preflight.py
- legacy/buildroom/tests/test_buildroom_no_progress.py (8 Tests)

## Verhaltensfälle (empirisch verifiziert, DOD-06-Abdeckung)

| # | Ereignisfolge | Legacy-Ergebnis |
|---|---------------|-----------------|
| 1 | leerer Zustand, 1x observe | count=1, hold=False, np={count:1,...} |
| 2 | 2x identisch | count=2, hold=False, status bleibt WAITING |
| 3 | 3x identisch (Schwelle) | count=3, hold=True, status=HOLD_FOR_BOSS, blocker=REPEATED_NO_PROGRESS, root_blocker=<original> |
| 4 | 4x identisch (Schwelle+1) | count=4, hold=True (bleibt), keine weitere Mutation |
| 5 | neue Evidence (evidence_fingerprint != "") | count=0, hold=False, reset_reason=NEW_EVIDENCE, status zurück zu WAITING |
| 6 | neuer task_id | count=1 (Frischsequenz), hold=False |
| 7 | geänderter log_fingerprint | count=1, hold=False |
| 8 | geänderter phase | count=1, hold=False |
| 9 | geänderter status | count=1, hold=False |
| 10 | geänderter blocker | count=1, hold=False |
| 11 | threshold=1 | sofort count=1, hold=True |
| 12 | threshold=2 | bei 2. identischem count=2, hold=True |
| 13 | HOLD | mutiert NUR status/blocker/root_blocker; phase/pr/task_bindings unverändert |
| 14 | threshold=0/-1 | ValueError NO_PROGRESS_THRESHOLD_INVALID |
| 15 | State-Keys nach HOLD | neu: no_progress + root_blocker; sonst unverändert |
| 16 | Task-Wechsel t_a→t_b | count=1 (Frischsequenz je Task) |
| 17 | first_observed_at bleibt über identische Sequenz | wird beim 1. Aufruf gesetzt und beibehalten solange Fingerprint gleich |

## State-Mutationen (vollständig, je Schritt)

Schreiben immer: `state["no_progress"]` = {count, fingerprint(list),
terminal_hold, threshold, first_observed_at, last_observed_at, root_blocker,
task_binding{task_id, board}, evidence_fingerprint, log_fingerprint}
(+ reset_reason "NEW_EVIDENCE" nur im Evidence-Reset-Zweig)
Bei terminal_hold zusätzlich: `state["status"]="HOLD_FOR_BOSS"`,
`state["blocker"]="REPEATED_NO_PROGRESS"`, `state["root_blocker"]=<blocker>`.

## Reset-Semantik

- evidence_fingerprint != "" → sofortiger Reset auf count=0 mit
  reset_reason="NEW_EVIDENCE" (vor Fingerprint-Vergleich).
- Jede Änderung eines Fingerprint-Bestandteils (phase/status/blocker/
  task_id/evidence/log) → neue Sequenz ab count=1.
- threshold-Wertwechsel: threshold wird je Aufruf aus dem Argument
  übernommen; count zählt nur bei identischem Fingerprint weiter.

## Zeit-/Reihenfolgeabhängigkeiten

- Keine Abhängigkeit von absoluter Zeit; only timestamps gespeichert.
- Sequenzabhängig: count baut auf `state["no_progress"]` des VORHERIGEN
  Aufrufs auf (State-getrieben, kein globaler State).

## Side Effects

- Nur Mutationen am übergebenen `state`-dict. Kein I/O, kein Netzwerk,
  kein ~/.hermes-Zugriff, keine Subprozesse. Tests nutzen KEINEN
  Live-Hermes-State (frische dicts).
