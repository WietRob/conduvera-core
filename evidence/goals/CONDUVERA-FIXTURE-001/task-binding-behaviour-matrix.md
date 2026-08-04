# Behaviour-Matrix: buildroom_task_binding (Legacy → Neu, DOD-01/02)

Quelle: legacy/buildroom/source/buildroom_task_binding.py (140 Zeilen, frozen,
SOURCE_MANIFEST sha256 af607e0d5c9fb2763b1309750e61abbd5ec9dfc7ed9b9809b10adf375ed3b86b)

## Öffentliche API (vollständig inventarisiert)

- `TaskBinding` (frozen dataclass): task_id, board, phase, cycle, created_at,
  evidence_path=None, dispatched_head=None, repo=None, default_branch=None
  - __post_init__-Validierung:
    - task_id: `^t_[a-f0-9]+$` → sonst ValueError "KANBAN_TASK_ID_INVALID"
    - board: `^[a-z0-9][a-z0-9-]*$` → sonst ValueError "KANBAN_BOARD_INVALID"
    - phase: `^[A-Z][A-Z0-9_]*$` → sonst ValueError "BUILDROOM_PHASE_INVALID"
    - cycle >= 1 → sonst ValueError "BUILDROOM_CYCLE_INVALID"
    - created_at nicht leer → sonst ValueError "TASK_BINDING_CREATED_AT_REQUIRED"
  - `to_dict()`: asdict minus None/""-Werte
- `store_task_binding(state, binding)`: state["task_bindings"][phase] =
  binding.to_dict(); legt task_bindings an falls fehlt; ValueError
  "TASK_BINDINGS_INVALID" falls task_bindings kein dict; ersetzt bestehendes
  Phase-Binding (Replacement)
- `binding_for_phase(state, phase, *, allow_legacy=True) -> TaskBinding | None`:
  - current-schema: state["task_bindings"][phase] → TaskBinding (raw nicht
    dict → ValueError "TASK_BINDING_INVALID"); cycle-Default aus
    state["cycle"]; phase-Default aus Argument; None-Felder → None
  - legacy-fallback (nur wenn allow_legacy): state["task_ids"][phase] +
    state["task_boards"][phase] → TaskBinding (cycle aus state["cycle"]=1,
    created_at aus state["last_run"] oder "legacy-state-binding")
    - WICHTIG (empirisch): die legacy task_id wird GEGEN das Regex validiert
      (t_old → KANBAN_TASK_ID_INVALID); board fehlt → ValueError
      "TASK_BOARD_REQUIRED:<phase>:<task_id>"
  - allow_legacy=False ohne current → None; leerer State → None
- `clear_task_binding(state, phase) -> TaskBinding | None`: gibt binding
  zurück (via binding_for_phase), entfernt task_bindings[phase] UND die
  Legacy-Mirrors task_ids[phase] + task_boards[phase]
- `kanban_argv(operation, binding=None, *, board=None, extra=()) -> list[str]`:
  - Task-Ops (show/runs/log/context/complete/block/unblock/archive/comment):
    binding erforderlich (sonst ValueError "TASK_BINDING_REQUIRED:<op>");
    board aus binding
  - Board-Ops (create/dispatch): board-Arg erforderlich (sonst ValueError
    "KANBAN_BOARD_REQUIRED:<op>")
  - sonst: ValueError "KANBAN_OPERATION_UNSUPPORTED:<op>"
  - board-Validierung erneut (ValueError "KANBAN_BOARD_INVALID")
  - argv = ["hermes","kanban","--board",<board>,<op>] + [task_id bei task-op]
    + extra (als str)

## Caller (Legacy, NICHT portiert in diesem Goal)

- peekxd_buildroom_loop_v20.py (BuildroomOrchestrator.create_task_with_verify
  etc.)
- buildroom_cycle49_preflight.py
- buildroom_no_progress.py (task_binding-Eintrag in no_progress-State)
- Tests: test_buildroom_task_binding_cycle49.py, test_buildroom_no_progress.py,
  test_buildroom_cycle49_preflight.py, test_buildroom_task_terminal_truth.py

## Abhängigkeiten

- Nur stdlib: dataclasses (asdict, dataclass), typing, re. KEINE
  Kanban-/Path-/SQLite-Helfer, KEIN Datei-I/O, KEIN Live-State.

## Verhaltensfälle (empirisch verifiziert, 30 Fälle)

| # | Fall | Legacy-Ergebnis |
|---|------|-----------------|
| 1 | gültiges Binding | to_dict ohne None/"" |
| 2 | task_id nicht t_[hex] | ValueError KANBAN_TASK_ID_INVALID |
| 3 | task_id t_xyz (nicht hex) | ValueError KANBAN_TASK_ID_INVALID |
| 4 | board mit Großbuchstabe | ValueError KANBAN_BOARD_INVALID |
| 5 | board mit Unterstrich | ValueError KANBAN_BOARD_INVALID |
| 6 | phase klein | ValueError BUILDROOM_PHASE_INVALID |
| 7 | phase mit Bindestrich | ValueError BUILDROOM_PHASE_INVALID |
| 8 | cycle=0 | ValueError BUILDROOM_CYCLE_INVALID |
| 9 | cycle=-1 | ValueError BUILDROOM_CYCLE_INVALID |
| 10 | created_at="" | ValueError TASK_BINDING_CREATED_AT_REQUIRED |
| 11 | to_dict filtert None/"" | nur gesetzte Felder |
| 12 | store legt task_bindings an | state["task_bindings"][phase]=to_dict |
| 13 | store mit task_bindings=str | ValueError TASK_BINDINGS_INVALID |
| 14 | store ersetzt bestehendes Phase-Binding | Replacement (task_id t_old→t_deadbeef) |
| 15 | current-schema lookup | TaskBinding aus raw (cycle aus state) |
| 16 | raw nicht dict | ValueError TASK_BINDING_INVALID |
| 17 | legacy-fallback mit ungültiger task_id | ValueError KANBAN_TASK_ID_INVALID (Regex!) |
| 18 | legacy ohne board | ValueError TASK_BOARD_REQUIRED:<phase>:<task_id> |
| 19 | allow_legacy=False ohne current | None |
| 20 | leerer State | None |
| 21 | clear entfernt binding + Mirrors | binding zurück; task_bindings/task_ids/task_boards bereinigt |
| 22 | task-op mit binding | argv mit binding.board |
| 23 | task-op ohne binding | ValueError TASK_BINDING_REQUIRED:<op> |
| 24 | board-op mit board | argv mit board |
| 25 | board-op ohne board | ValueError KANBAN_BOARD_REQUIRED:<op> |
| 26 | board-op invalid board | ValueError KANBAN_BOARD_INVALID |
| 27 | unsupported op | ValueError KANBAN_OPERATION_UNSUPPORTED:<op> |
| 28 | task-op invalid binding-board | ValueError KANBAN_BOARD_INVALID |
| 29 | extra-Args | argv += extra als str |
| 30 | alle 9 Task-Ops | argv[4:] == [op, task_id] |

## State-Mutationen

- store: schreibt state["task_bindings"][phase] (setdefault task_bindings)
- clear: pop auf task_bindings/task_ids/task_boards
- binding_for_phase: KEINE Mutation (reine Lese-/Konstruktionslogik)

## Idempotenz / Duplicate / Replacement

- store ist idempotent für identische Bindings; ersetzt bei gleichem Phase
  (Replacement, kein Duplicate-Key-Fehler)
- binding_for_phase ist rein (kein State-Write)
- clear ist idempotent (pop auf fehlendem Key ist no-op)

## Side Effects

- KEINE Datei-/Kanban-/SQLite-Side-Effects im Modul selbst (nur
  State-dict-Mutation). kanban_argv erzeugt nur Argumentlisten (kein
  Subprocess). Orchestrator-Caller (peekxd/cycle49) führen die realen
  Side-Effects aus — NICHT portiert in diesem Goal.
