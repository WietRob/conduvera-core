# Known Gaps — Offene Luecken und TODOs

## Uebersicht

Dieses Dokument listet die bekannten Luecken und noch nicht implementierten Features der CuraOps-Control v0. Der Status quo: 124 Tests gruen, Kern-Infrastruktur steht, aber wesentliche Erweiterungen fehlen.

---

## 1. Fehlende Execution-Backend-Adapter

### Droid-Adapter

Es gibt keinen Adapter fuer den Droid-Agenten. Droid wird als potentielles Execution-Backend genannt, aber es existiert keine Integration in den `AgentLauncher`, keine spezifischen Gate-Profile und keine CLI-Commands fuer Droid-spezifische Operationen.

**Aufwand**: Mittel. Benoetigt Launcher-Erweiterung, eigenes Gate-Profile, Worktree-Konventionen.

### Zed-Adapter

Gleiches gilt fuer Zed. Kein Adapter, keine Integration, keine Konfiguration.

**Aufwand**: Mittel. Vergleichbar mit Droid.

### Andere Backends

Die Architektur ist auf weitere Backends vorbereitet (das Launcher-Interface ist generisch), aber es gibt nur Implementierungen fuer OpenCode und Manual.

---

## 2. Fehlende Skills

Die folgenden Skills sind in der Planung aber nicht implementiert:

| Skill | Beschreibung | Prioritaet |
|---|---|---|
| `spec-driven-development` | Automatische Spec-Generierung aus Task-Beschreibung und Validierung gegen implementierten Code | Hoch |
| `local-gates` | Lokale Gate-Evaluation ohne Netzwerkzugriff, fuer Offline-Szenarien auf dem Pi | Mittel |
| `worktree-hygiene` | Automatische Worktree-Bereinigung nach Agent-STOPPED/CRASHED, Vermeidung von stale Worktrees | Hoch |
| `auto-recovery` | Automatische Wiederherstellung nach CRASHED, inkl. Worktree-Reset und Registry-Bereinigung | Mittel |
| `multi-agent-coordination` | Koordination mehrerer Agenten im selben Repo, Dependency-Management zwischen Agent-Tasks | Niedrig |
| `evidence-chain` | Kryptografische Verkettung von Evidence-Eintraegen fuer tamper-proof Audit-Trails | Niedrig |

---

## 3. Pi Harness Bootstrap / Ops / Smoke-Tests

### Bootstrap

Es gibt kein automatisiertes Bootstrap-Skript fuer die Pi-Umgebung. Folgendes fehlt:

- Automatische Verzeichniserstellung (`.curaops/control/`, `.captain/state/streams/`)
- Initiale Konfigurationsdatei-Generierung (`gates.yaml`, Gateway-Config)
- Registry-Initialisierung
- Erster Health-Check

### Ops

Es gibt keine operationalen Runbooks oder Automatisierung fuer:
- Backup/Restore der Registry und EventLogs
- Log-Rotation fuer EventLog und Audit-Log
- Monitoring-Integration (Metriken, Alerts)
- Automatische Updates des Harness

### Smoke-Tests auf dem Pi

Obwohl 124 Unit/Integration-Tests existieren, gibt es keine end-to-end Smoke-Tests die auf dem Pi ausgefuehrt werden:
- Gateway-Start → Agent-Boot → Gate-Run → READY → PR → Merge
- Multi-Agent-Szenarien mit Worktree-Sentinel
- Gateway-Failover-Verhalten (lokal nicht verfuegbar)
- StreamState-Transitions mit echtem Agent-Backend

---

## 4. GitHub Issue/PR Bridge

Es gibt **keine direkte Integration mit der GitHub API**. Folgendes fehlt:

### Issue-Bridge
- Automatisches Erstellen von GitHub Issues aus Tasks
- Status-Sync zwischen Registry und GitHub Issue Labels
- Assignment von Agenten zu Issues

### PR-Bridge
- Automatisches Oeffnen von Pull-Requests nach READY (das Legacy-Skript `agent-open-pr` existiert, aber es gibt keine native Implementierung)
- PR-Status-Tracking im StreamState
- Merge-Status-Updates an GitHub

### Comment-Policy
- Die harte Regel "Kein direkter GitHub-Kommentar als steuernder Status" gilt, aber es gibt keinen Mechanismus um dies durchzusetzen oder zu ueberwachen

---

## 5. Evidence Store

Der aktuelle Evidence Store ist ein **Dictionary im AgentRecord** (`ready_evidence`-Feld in der Registry). Einschraenkungen:

- **Keine Historie**: Evidence wird ueberschrieben, keine Versionierung
- **Keine Query-Moeglichkeit**: Evidence kann nicht durchsucht oder gefiltert werden
- **Keine Verifikation**: Evidence-Inhalte werden nicht gegen erwartete Schemata validiert
- **Grossebeschränkung**: Die gesamte Evidence liegt in `registry.json`, was bei grossen Agenten unpraktisch wird
- **Kein separater Storage**: Evidence ist an den AgentRecord gekoppelt, nicht unabhaengig abfragbar

**Potentielle Loesung**: Eigener Evidence Store (z.B. SQLite oder separates JSONL-File) mit Referenz aus dem AgentRecord.

---

## 6. TUI — Nur Anzeige, Nicht Steuerung

Die bestehende TUI (Terminal User Interface) ueber `curaops-control dashboard show` und die CLI-Commands sind **read-only**. Es fehlt:

### Steuerungs-Features
- Interaktiver Agent-Start/Stop aus der TUI
- Gate-Ergebnisse live anzeigen und interaktiv acknowledge
- StreamState-Transitions aus der TUI triggern
- Evidence-Browser mit Detail-Ansicht

### Navigation
- Scrollbare Agent-Liste mit Status-Filter
- EventLog-Tail (live-Updates)
- Gateway-Traffic-Monitor

### TBD: TUI-Framework
Die Frage ob Rich, Textual oder ein anderes TUI-Framework verwendet wird, ist noch offen.

---

## 7. Weitere offene Punkte

### Stream State Persistence
Die StreamState-Dateien in `.captain/state/streams/` haben keine automatische Bereinigung. Abgeschlossene oder verwaiste Streams akkumulieren sich.

### Gate Profile Management
Es gibt kein CLI-Command zum Erstellen oder Bearbeiten von Gate-Profilen. Profile muessen manuell in `gates.yaml` gepflegt werden.

### Credentials Management
Das Feld `credentials_ref` im AgentRecord ist ein Platzhalter. Es gibt keinen Credentials-Store oder eine Integration mit Secrets-Management.

### Logging-Standardisierung
EventLog und Audit-Log verwenden unterschiedliche Formate und Speicherorte. Eine Vereinheitlichung steht aus.

### Error Recovery im Launcher
Der `AgentLauncher` hat keine robuste Fehlerbehandlung fuer teilweise ausgefuehrte Starts (z.B. Registry-Eintrag erstellt, aber Prozessstart fehlgeschlagen). Cleanup fehlt.

### Concurrent Registry Access
Die Registry (`registry.json`) wird ohne Locking gelesen/geschrieben. Bei parallelen Agenten koennen Race Conditions auftreten.

---

## Zusammenfassung

| Kategorie | Anzahl offener Punkte | Kritikalitaet |
|---|---|---|
| Fehlende Backend-Adapter | 2 | Mittel |
| Fehlende Skills | 6 | Hoch-Mittel |
| Pi Ops/Bootstrap/Smoke | 3 | Hoch |
| GitHub Integration | 3 | Hoch |
| Evidence Store | 5 | Mittel |
| TUI Steuerung | 3 | Niedrig |
| Sonstige | 6 | Mittel |

**Gesamt**: ~28 offene Punkte fuer die Roadmap nach v0.
