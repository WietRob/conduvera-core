# Automatischer Skill-Writer — Identifikation + Gate-Kontrolle (Baseline-Goal)

Datum: 2026-08-04
Ziel: establish-canonical-pre-buildroom-system-baseline

## Identifizierter Writer

- Modul: /home/roberto_schmidt/projects/hermes-agent/agent/curator.py
- CLI: hermes curator (status/pause/resume/pin), /curator Slash-Command
- Trigger: INACTIVITY-basiert (kein Cron) — maybe_run_curator() nach
  interval_hours (Default 7 Tage) ohne vorherigen Lauf
- Schreibt: agent-created Skills via skill_manage (patch/edit/create),
  References, Memories; LLM-Pass (Konsolidierung) ist konfigurierbar aus
  (consolidation off im letzten Lauf)
- Verzeichnisse: ~/.hermes/profiles/<profile>/skills/ (inkl. References),
  memories/, logs/curator/
- Zustand: ~/.hermes/profiles/orchestrator/skills/.curator_state
  (last_run_at, paused, run_count)

## Aktueller Zustand (read-only verifiziert)

- last_run_at: 2026-08-02T15:35:54 (5 Läufe gesamt)
- paused: false
- interval: Default 7 Tage → nächster automatischer Lauf frühestens
  2026-08-09 — AUSSERHALB des Zeitfensters dieses Goals
- Die bekannten Mutationen (12:44, 14:39–14:40, 16:50, 21:23 am 2026-08-03)
  stammen aus diesem Curator-/Lernmechanismus (agent-created Skills werden
  nach abgeschlossenen Goals als References + Pattern ergänzt)

## Freeze/Read-only-Modus

- EXISTIERT: set_paused(True)/set_paused(False) persistiert in
  .curator_state["paused"]; CLI: hermes curator pause / resume.
- Reversibel: ja (resume stellt den Scheduler wieder her)
- Während dieses Goals: KEIN PAUSE nötig, da der nächste automatische Lauf
  (frühestens 09.08) außerhalb des Zeitfensters liegt. Zur Sicherheit wird
  das vollständige Skill-Inventar pre/post gemessen; jede Abweichung =
  UNEXPECTED_SKILL_MUTATION → Goal stoppt.

## Konsequenz

Der Writer ist identifiziert, sein Trigger-Fenster bekannt, ein reversibler
Freeze existiert. Kein PASS wird durch Umbenennung in „externer Lernprozess"
erzeugt — der Mechanismus ist hiermit namentlich und code-seitig belegt.
