# Worktree Safety Policy

## Uebersicht

Der `WorktreeSentinel` schuetzt Agent-Worktrees vor gleichzeitigen, konkurrierenden Mutationen. Die Policy definiert drei Operationsklassen und regelt, welche Operationen in welchem Agent-Zustand erlaubt sind.

**Kernprinzip**: Ein aktiver Agent hat exklusiven Schreibzugriff auf seinen Worktree. Andere Agenten oder Prozesse duerfen nur lesen.

---

## Operationsklassen

### READ_ONLY
Operationen die den Worktree nicht veraendern. Immer erlaubt, unabhaengig vom Agent-Status.

**Beispiele**: `git status`, `cat`, `ls`, `head`, `tail`, `grep`, `find`, `git log`, `git diff`, `wc`

### MUTATING
Operationen die Dateien oder den Git-Zustand im Worktree veraendern. Nur erlaubt wenn **kein Agent aktiv** ist.

**Beispiele**: `pytest`, `sonar`, `black`, `git checkout`, `git add`, `git commit`, `npm install`, `pip install`, Datei schreiben/bearbeiten

### DESTRUCTIVE
Operationen die den Worktree grundlegend veraendern oder zerstoeren. **Immer blockiert**, unabhaengig vom Agent-Status.

**Beispiele**: `git reset --hard`, `git clean -fd`, `rm -rf`, `git rebase`, Worktree-Loeschung

---

## `can_mutate()` Regeln

```python
def can_mutate(agent_id: str, operation: Operation) -> bool:
    if operation.class == READ_ONLY:
        return True                           # Immer erlaubt

    if operation.class == DESTRUCTIVE:
        return False                          # Immer blockiert

    if operation.class == MUTATING:
        return not _is_agent_active(agent_id) # Nur wenn Agent inaktiv
```

### Entscheidungsbaum

```
can_mutate(agent_id, operation)?
│
├─ READ_ONLY?  ──────► TRUE  (immer)
│
├─ DESTRUCTIVE? ─────► FALSE (immer)
│
└─ MUTATING?
   │
   ├─ _is_agent_active(agent_id) == TRUE?  ──► FALSE
   │
   └─ _is_agent_active(agent_id) == FALSE? ──► TRUE
```

---

## `_is_agent_active()` — Aktivitaetspruefung

Die Methode prueft ob ein Agent aktiv ist, indem sie seinen Status in der Registry abfragt. Ein Agent gilt als **aktiv** wenn sein Status einer der folgenden ist:

| Status | Bedeutung | Aktiv? |
|---|---|---|
| `BOOTING` | Agent startet gerade | **Ja** |
| `ACTIVE` | Agent arbeitet aktiv im Worktree | **Ja** |
| `READY` | Agent ist fertig, Worktree noch belegt | **Ja** |
| `BLOCKED` | Agent ist blockiert | Nein |
| `STOPPED` | Agent wurde gestoppt | Nein |
| `CRASHED` | Agent ist abgestuerzt | Nein |

**Warum BOOTING und READY als aktiv?**

- `BOOTING`: Der Agent initialisiert seinen Workspace. Mutationen wuerden den Startprozess korrumpieren.
- `READY`: Der Agent hat den Worktree noch nicht freigegeben (PR/Merge steht noch aus). Mutationen wuerden die Evidence invalidieren.

---

## Beispiele

### Szenario 1: Agent ist ACTIVE

```
Agent "agent-001" hat Status ACTIVE im Worktree /wt/issue-42

Operation              Klasse       can_mutate()   Ergebnis
─────────────────────────────────────────────────────────────
git status             READ_ONLY    TRUE           ✓ Erlaubt
cat src/main.py        READ_ONLY    TRUE           ✓ Erlaubt
ls -la                 READ_ONLY    TRUE           ✓ Erlaubt
git log --oneline      READ_ONLY    TRUE           ✓ Erlaubt
grep -r "TODO"         READ_ONLY    TRUE           ✓ Erlaubt
pytest tests/          MUTATING     FALSE          ✗ Blockiert
sonar-scanner          MUTATING     FALSE          ✗ Blockiert
black src/             MUTATING     FALSE          ✗ Blockiert
git add .              MUTATING     FALSE          ✗ Blockiert
npm install            MUTATING     FALSE          ✗ Blockiert
git reset --hard       DESTRUCTIVE  FALSE          ✗ Blockiert
rm -rf src/            DESTRUCTIVE  FALSE          ✗ Blockiert
```

### Szenario 2: Kein Agent aktiv

```
Worktree /wt/issue-42 hat keinen aktiven Agent

Operation              Klasse       can_mutate()   Ergebnis
─────────────────────────────────────────────────────────────
git status             READ_ONLY    TRUE           ✓ Erlaubt
pytest tests/          MUTATING     TRUE           ✓ Erlaubt
black src/             MUTATING     TRUE           ✓ Erlaubt
git add .              MUTATING     TRUE           ✓ Erlaubt
git reset --hard       DESTRUCTIVE  FALSE          ✗ Blockiert
rm -rf src/            DESTRUCTIVE  FALSE          ✗ Blockiert
```

### Szenario 3: Agent ist READY (PR offen)

```
Agent "agent-001" hat Status READY, PR #123 ist offen

Operation              Klasse       can_mutate()   Ergebnis
─────────────────────────────────────────────────────────────
git diff HEAD~1        READ_ONLY    TRUE           ✓ Erlaubt
cat evidence.json      READ_ONLY    TRUE           ✓ Erlaubt
pytest tests/          MUTATING     FALSE          ✗ Blockiert (Evidence wuerde invalidiert)
black src/             MUTATING     FALSE          ✗ Blockiert
git reset --hard       DESTRUCTIVE  FALSE          ✗ Blockiert
```

### Szenario 4: Agent ist CRASHED

```
Agent "agent-001" hat Status CRASHED, Worktree /wt/issue-42

Operation              Klasse       can_mutate()   Ergebnis
─────────────────────────────────────────────────────────────
git status             READ_ONLY    TRUE           ✓ Erlaubt
git checkout main      MUTATING     TRUE           ✓ Erlaubt (Agent inaktiv)
pytest tests/          MUTATING     TRUE           ✓ Erlaubt
rm -rf /wt/issue-42    DESTRUCTIVE  FALSE          ✗ Blockiert (nie erlaubt)
```

---

## CLI-Nutzung

```bash
# Worktree inspizieren
curaops-control worktree inspect --agent agent-001

# Pruefen ob eine Operation erlaubt ist
curaops-control worktree check-mutate --agent agent-001 --operation "pytest"
```

---

## Integration mit dem Harness

Der `WorktreeSentinel` wird an folgenden Stellen im Harness referenziert:

1. **AgentLauncher.launch()**: Prueft vor dem Start ob der Worktree frei ist
2. **GateRunner**: `DirtyCheckGate` nutzt den Sentinel um Worktree-Zustand zu validieren
3. **CLI**: Direkte Inspektion und Pruefung durch Operatoren
4. **scripts_bridge.py**: Legacy-Skripte koennen Sentinel-Checks vor Mutationen durchfuehren

Der Sentinel nutzt die `AgentRegistry` als Datenquelle. Es gibt keine separate Zustandsverwaltung — die Registry ist die Single Source of Truth fuer Agent-Status.
