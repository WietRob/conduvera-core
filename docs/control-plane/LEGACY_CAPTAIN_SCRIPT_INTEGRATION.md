# Legacy Captain Script Integration

## Uebersicht

Die 9 kanonischen Legacy-Skripte aus `~/projects/CuraOps_VRP/scripts/` werden ueber `scripts_bridge.py` in den CuraOps-Control-Harness integriert. Die Integration folgt dem Prinzip **Wrapper, nicht Rewrite**: jedes Skript bleibt in seiner urspruenglichen Form erhalten und wird durch eine Methode in der `ScriptRunner`-Klasse gekapselt.

Es wird **keine neue Gate-Semantik** eingefuehrt. Die Skripte bleiben die kanonische Wahrheitsquelle fuer ihre jeweilige Domane.

---

## Architektur

```
Legacy-Skript          scripts_bridge.py              Harness-Aktion
(bin/bash)        ──►  ScriptRunner.run_*()      ──►  Registry / EventLog / StreamState
                        │
                        ├─ subprocess.run()
                        ├─ Exit-Code auswerten
                        └─ Evidence aus stdout extrahieren
```

### ScriptRunner

Die Klasse `ScriptRunner` kapselt jeden Aufruf. Sie nutzt `ScriptConfig` fuer Pfad- und Argumentkonfiguration und fuehrt Skripte via `subprocess.run()` aus. Exit-Codes werden in strukturierte Ergebnisse uebersetzt, Evidence-Daten aus `stdout` geparsed.

### Exit-Code-Semantik

| Exit-Code | Bedeutung | Harness-Verhalten |
|---|---|---|
| `0` | OK / Bestanden | Gate/Aktion als erfolgreich markiert |
| `1` | Fail / Fehler | Gate als fehlgeschlagen markiert, Agent ggf. BLOCKED |
| `2` | Skipped | Uebersprungen, kein Gate-Fehler (nur bei optionalen Gates) |
| `56` | Blocked | Explizite Blockierung, Agent wird BLOCKED gesetzt |

---

## Skript-Tabelle

| # | Skriptname | `scripts_bridge.py` Methode | Exit-Codes | Harness-Verhalten |
|---|---|---|---|---|
| 1 | `agent-status` | `run_agent_status()` | 0=Erfolg, 1=Fehler | Liest aktuellen Agent-Status und gibt ihn an Registry/CLI zurueck. Bei Fehler wird EventLog-Eintrag geschrieben. |
| 2 | `agent-finish-gate` | `run_agent_finish_gate()` | 0=bestanden, 1=fehlgeschlagen, 56=blocked | Evaluiert ob der Agent seine Task abgeschlossen hat. Bei 0 kann der Agent in den READY-Workflow eintreten. Bei 1/56 wird der Agent BLOCKED mit entsprechender `blocked_reason`. |
| 3 | `sonar-agent-gate` | `run_sonar_agent_gate()` | 0=bestanden, 1=fehlgeschlagen, 2=skipped | Agent-spezifisches Sonar-Qualitaetsgate. Exit 2 nur erlaubt wenn Gate als optional+pass konfiguriert ist. Sonst fuehrt Exit 2 zu BLOCKED. |
| 4 | `pr-readiness-summary` | `run_pr_readiness_summary()` | 0=bereit, 1=nicht bereit | Prueft PR-Bereitschaft (Tests, Scope, Dirty-Check). Evidence wird aus stdout als Zusammenfassung extrahiert und im `ready_evidence` des AgentRecord gespeichert. |
| 5 | `write-agent-evidence` | `run_write_agent_evidence()` | 0=geschrieben, 1=Fehler | Schreibt Evidence-Daten fuer den Agenten. Evidence wird im AgentRecord unter `ready_evidence` abgelegt und im EventLog dokumentiert. |
| 6 | `sonar-gate` | `run_sonar_gate()` | 0=bestanden, 1=fehlgeschlagen, 2=skipped | Globales Sonar-Gate (nicht agent-spezifisch). Gleiche Skip-Semantik wie `sonar-agent-gate`. Wird im Gate-Runner-Kontext ausgefuehrt. |
| 7 | `agent-class-test-gate` | `run_agent_class_test_gate()` | 0=bestanden, 1=fehlgeschlagen | Prueft ob Agent-Klasse (general, sensitive, etc.) mit den erlaubten Operationen kompatibel ist. Fehlschlag blockiert den Agenten. |
| 8 | `agent-open-pr` | `run_agent_open_pr()` | 0=PR erstellt, 1=Fehler, 56=blocked | Oeffnet einen Pull-Request fuer die Agent-Aenderungen. Vorbedingung: Agent ist READY und hat `current-head` Evidence. Bei 56 (z.B. Scope-Verletzung) wird der Agent BLOCKED. |
| 9 | `captain-merge-preflight` | `run_captain_merge_preflight()` | 0=preflight bestanden, 1=fehlgeschlagen, 56=blocked | Finale Pruefung vor dem Merge. Verifiziert `head_sha`, sauberen Worktree, bestehende Gates und vollstaendige Evidence. Nur bei Exit 0 wird der Merge freigegeben. |

---

## Ablauf: Skriptaufruf im Harness

```
1. Harness erkennt Bedarf fuer Skript-Aktion
   │
2. ScriptRunner.run_<skript>() wird aufgerufen
   │
   ├─ ScriptConfig zusammenstellen (Pfad, Args, Env)
   ├─ subprocess.run() ausfuehren
   ├─ Exit-Code auswerten
   └─ Evidence aus stdout parsen (falls vorhanden)
        │
3. Exit-Code → Harness-Aktion
   │
   ├─ 0 → Erfolg, EventLog-Eintrag, ggf. Status-Update
   ├─ 1 → Fehler, EventLog-Eintrag, ggf. Agent BLOCKED
   ├─ 2 → Skipped, EventLog-Eintrag, nur bei optionalen Gates akzeptiert
   └─ 56 → Blocked, Registry.set_blocked(), blocked_reason setzen
```

---

## Wichtige Hinweise

### Keine neue Gate-Semantik

Die Legacy-Skripte definieren die Gate-Logik. `scripts_bridge.py` ist ein reiner Wrapper, der Exit-Codes uebersetzt und Evidence sammelt. Es werden keine zusaetzlichen Gate-Regeln implementiert.

### Evidence-Extraktion

Evidence wird ausschliesslich aus `stdout` der Skripte extrahiert. Das Parsing erfolgt in `ScriptRunner` nach jedem Aufruf. Die extrahierten Daten werden im `ready_evidence`-Feld des `AgentRecord` gespeichert.

### Skript-Pfade

Alle Skripte liegen unter `~/projects/CuraOps_VRP/scripts/`. Die Pfade werden ueber `ScriptConfig` verwaltet und koennen ueber die CLI angepasst werden.

### Fehlertoleranz

Bei unerwarteten Exit-Codes (nicht 0/1/2/56) wird der Agent in den Status `CRASHED` gesetzt und ein EventLog-Eintrag mit dem unerwarteten Code erstellt.
