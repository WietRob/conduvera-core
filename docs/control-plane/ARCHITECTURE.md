# CuraOps-Control — Gesamtarchitektur

## Uebersicht

CuraOps-Control ist das Steuerungs- und OrchestrierungsLayer fuer Agenten-Workflows im Matrix-OS-Ökosystem. Die Architektur ist **dreischichtig** aufgebaut und trennt sauber zwischen Zustandsverwaltung, KI-Routing und Ausfuehrung.

```
┌─────────────────────────────────────────────────────┐
│  Execution Backends                                  │
│  (OpenCode, Manual, zukuenftig: Droid, Zed)          │
├─────────────────────────────────────────────────────┤
│  Pi-native AI Gateway (FastAPI)                      │
│  Auth · Routing · Sensitive-Class Policies · Audit   │
├─────────────────────────────────────────────────────┤
│  Harness Core                                        │
│  Registry · EventLog · Gates · StreamState · Sentinel│
└─────────────────────────────────────────────────────┘
```

---

## Schicht 1: Harness Core

Der Harness Core bildet das Fundament. Er verwaltet Agent-Zustand, erfasst Ereignisse, evaluiert Gate-Regeln, trackt Stream-Transitions und schuetzt Worktrees vor parallelen Mutationen.

### Module

#### `registry.py` — AgentRegistry
Zentrales Zustandsverzeichnis aller Agenten. Jeder Agent wird als `AgentRecord` mit Feldern wie `agent_id`, `tool`, `task`, `issue`, `worktree`, `session`, `gate_profile`, `status`, `scope_files`, `credentials_ref`, `blocked_reason` und `ready_evidence` registriert. Statuswerte: `BOOTING`, `ACTIVE`, `READY`, `BLOCKED`, `STOPPED`, `CRASHED`. Persistenz ueber `.conduvera/control/registry.json`.

#### `eventlog.py` — EventLog
Append-only JSONL-Logfile unter `.conduvera/control/events.jsonl`. Jede signifikante Harness-Aktion (Registrierung, Gate-Run, Statuswechsel, Stream-Transition) wird mit Zeitstempel und Kontext dokumentiert. Dient als Audit-Trail und Grundlage fuer Debugging.

#### `gates.py` — GateRunner + Builtin Gates
Evaluiert vordefinierte Qualitaets- und Berechtigungsregeln bevor ein Agent in den READY-Zustand wechselt. Fuenf eingebaute Gates: `FinishGate`, `TestGate`, `SonarGate`, `DirtyCheckGate`, `ScopeGate`. Gate-Profile werden in `.conduvera/control/policies/gates.yaml` konfiguriert und jedem Agent bei der Registrierung zugewiesen.

#### `stream_state.py` — StreamStateStore
Verwaltet den Lebenszyklus von Agent-Interaktionen ueber 12 Zustaende und 5 Reply-Typen (`AgentReply`). Erzwingt `head_sha`-Konsistenz bei `READY_FOR_REVIEW`. Pro-Agent-Zustand in `.captain/state/streams/<agent>.json` persistiert. Transition-Matrix definiert gueltige Zustandswechsel.

#### `worktree_sentinel.py` — WorktreeSentinel
Schuetzt Worktrees vor gleichzeitigen Mutationen durch mehrere Agenten. `can_mutate(agent_id, operation)` klassifiziert Operationen als `READ_ONLY`, `MUTATING` oder `DESTRUCTIVE`. Nur `READ_ONLY` ist bei aktivem Agent (Status `ACTIVE`, `BOOTING`, `READY`) erlaubt. Nutzt die Registry fuer Aktivitaetspruefung.

#### `scripts_bridge.py` — ScriptRunner
Wrapper-Schicht fuer die 9 kanonischen Legacy-Skripte aus `~/projects/CuraOps_VRP/scripts/`. Jedes Skript wird als Methode gekapselt, Exit-Codes werden in Harness-Aktionen uebersetzt (0=OK, 1=fail, 56=blocked, 2=skipped). Evidence wird aus stdout extrahiert. Keine neue Gate-Semantik.

#### `launcher.py` — AgentLauncher
Orchestriert den 7-Schritt-Workflow zum Starten eines Agenten: Registrierung, Gate-Profile-Zuweisung, Worktree-Setup, Environment-Variablen (`OPENAI_BASE_URL`, `X_GATEWAY_CLIENT`, `AGENT_ID`, `TASK_KEY`), Start, Status-Update, EventLog-Eintrag. Liefert ein `LaunchResult` zurueck.

#### `cli.py` — Typer CLI
17 Sub-Commands aufgeteilt in fuenf Gruppen: Agent-Management (`boot`, `status`, `ready`, `blocked`, `evidence`, `sync`, `stop`, `list`), Captain-Orchestrierung (`tick`, `next`, `dispatch`, `dashboard`), Gate-Verwaltung (`run`, `profiles`, `list`), Stream-Steuerung (`show`, `transition`, `reply`, `blocked`), Worktree/Sentinel (`inspect`, `check-mutate`), Gateway (`route`, `smoke`, `audit`, `serve`) und Dashboard (`show`).

---

## Schicht 2: Pi-native AI Gateway

### Modul `gateway/`

FastAPI-basierter KI-Gateway, der direkt auf dem Pi laeuft. **Kein LiteLLM** (Supply-Chain-Risiko Q1/2026).

| Datei | Funktion |
|---|---|
| `app.py` | FastAPI-Applikation mit `/health`, `/v1/models`, `/v1/chat/completions` |
| `auth.py` | `ClientRegistry` — Authentifizierung ueber `X-Gateway-Client`-Header |
| `backends.py` | `BackendProxy` — httpx-basierter Proxy zu lokalen/Cloud-Backends |
| `config.py` | `ProfileConfig`, `SensitiveClass` — Profile und Sensitivitaetsklassen |
| `router.py` | `GatewayRouter` — Routing-Entscheidung basierend auf Client und Sensitivitaet |
| `audit.py` | Audit-Log aller Gateway-Requests |

### Sensitive-Class Policies

Nur Clients mit der Klasse `general` duerfen Cloud-Backends erreichen. Sensible Klassen werden auf lokale Modelle beschraenkt. Im MVP gibt es keine Cloud-Fallbacks.

---

## Schicht 3: Execution Backends

Die Ausfuehrungsschicht umfasst die tatsaechlichen Agent-Runners:

- **OpenCode**: Primaeres Agent-Backend fuer autonome Codierung
- **Manual**: Manuelle Ausfuehrung durch menschliche Operatoren
- **Geplant**: Droid- und Zed-Adapter (noch nicht implementiert)

Jeder Backend-Typ wird ueber den `AgentLauncher` gestartet und erhaelt seine Environment-Konfiguration vom Harness Core.

---

## Datenfluss: Agent-Boot bis READY

```
1. CLI: curaops-control agent boot
   │
   ├─► Registry.register() → AgentRecord (status=BOOTING)
   ├─► EventLog.append("agent_booted")
   └─► GateProfile laden/zuweisen
        │
2. AgentLauncher.launch() [7-Schritt-Workflow]
   │
   ├─► Worktree-Setup
   ├─► Env-Variablen setzen
   ├─► Registry.set_active() → status=ACTIVE
   └─► Agent-Prozess starten
        │
3. Agent arbeitet im Worktree (geschuetzt durch WorktreeSentinel)
   │
   ├─► KI-Requests laufen ueber AI Gateway
   ├─► StreamState trackt Interaktion
   └─► Legacy-Operationen ueber scripts_bridge.py
        │
4. Agent meldet Fertigstellung
   │
   ├─► GateRunner.run_all() evaluiert alle Gates:
   │   ├─ FinishGate: Task abgeschlossen?
   │   ├─ TestGate: Tests bestanden?
   │   ├─ SonarGate: Qualitaetsgate bestanden? (kein skip ausser optional+pass)
   │   ├─ DirtyCheckGate: Worktree sauber?
   │   └─ ScopeGate: Nur eigene Dateien geaendert?
   │
   ├─► Alle Gates bestanden → Registry.set_ready() → status=READY
   │   └─► EventLog.append("agent_ready")
   │
   └─► Gate fehlgeschlagen → Registry.set_blocked() → status=BLOCKED
       └─► blocked_reason dokumentiert
```

---

## Harte Regeln

1. Kein Agent ohne Registry-Eintrag
2. Kein READY ohne `curaops-control agent ready`
3. Kein Merge ohne `current-head` Evidence
4. Kein skipped Sonar als READY (ausser optional+pass)
5. Kein Dirty Worktree als READY
6. Kein fremder Scope
7. Kein CI-Rerun bei Billing Freeze
8. Kein direkter GitHub-Kommentar als steuernder Status
9. Jede Session muss in der Registry stehen
10. Jeder Agent bekommt ein Gate Profile

---

## Testabdeckung

Die aktuelle Suite umfasst 397+ Tests (Delivery-Domain, Event-Stream, Evidence,
Operator-Actions, cwd_exec-Security, Pi, Console) und laeuft gruen. Die
nachfolgende Tabelle ist historisch (v0).

| Suite | Anzahl |
|---|---|
| Control (Registry, EventLog, Gates, Sentinel, Launcher) | 38 |
| Stream State | 27 |
| Gateway | 29 |
| Runtime Enforcement | 30 |

---

## Delivery Workspace v1

Die Control-Plane erweitert den Execution-Layer um einen Delivery-Domain:

```
ControlPlaneService
  -> DeliveryService (DeliveryRecord-Zustandsmaschine)
       -> DeliveryStore (Control-Plane-owned, 0600, append-only History)
       -> PrePublishGate (fail-closed, strukturierte Negativ-Codes)
       -> GitHubDeliveryProvider (shell-frei, task-branch + ein PR)
       -> BaseDrift (MATCH/BEHIND/AHEAD/DIVERGED/UNAVAILABLE)
       -> StatusSync (checks/reviews/mergeability -> Delivery-States)
       -> Cleanup (disposable vs durable)
  -> EventStreamBus (WS-F) + HTTP /events SSE-Endpoint
  -> Activity UI (Detail-Panel, Diff, Evidence, Attention, Actions)
```

Siehe [docs/control-plane/DELIVERY_WORKSPACE.md](DELIVERY_WORKSPACE.md) fuer den
vollstaendigen Delivery-/GitHub-Bridge-Contract und Operator-Workflow.
