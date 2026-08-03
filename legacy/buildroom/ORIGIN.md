# Buildroom Legacy Source Baseline — Origin

Importdatum: 2026-08-03
Quelle: `/home/roberto_schmidt/.hermes/scripts/` (live operational Buildroom runtime)
Ziel: `legacy/buildroom/` in diesem Repository (matrix-os, branch task/buildroom-legacy-baseline)
Zweck: versionierter, reproduzierbarer Migrations-Baseline für die spätere
Absorption von Buildroom als internes Modul von Conduvera Core (working
name; formerly Matrix OS). Dies ist eine Migrations-Baseline, KEIN neuer
Runtime. Der Live-Betrieb unter `~/.hermes/scripts/` bleibt unverändert.

## Autoritäten

- Roberto_Brain ist die Architektur-/Owner-Entscheidungs-SSoT
  (Commit `9383e7fca2aeda49854443934e8e22de3bac5b94` — Conduvera/Matrix-OS
  design baseline, 2026-08-03).
- Buildroom ist ein internes Zukunfts-Modul von Matrix OS, kein separates
  Produkt (Owner-Entscheid 4/5, 2026-08-01).
- Naming-Stand: Matrix OS = PUBLIC_NAME_DEPRECATED_PENDING_REPLACEMENT;
  Conduvera = WORKING_NAME_PENDING_CLEARANCE. Keine Repo-/Package-/CLI-
  Umbenennung (Naming Gate ausstehend).

## Importierte Inhalte

| Verzeichnis | Inhalt | Anzahl |
|---|---|---|
| `source/` | aktive Buildroom-Python-Module + benötigte Abhängigkeiten (inkl. Orchestrator `peekxd_buildroom_loop_v20.py`, `manual_authorization.py`, `fleet_router.py`, `orchestrator_router_bridge.py`) | 19 |
| `tests/` | Charakterisierungs-Testdateien (`tests/test_buildroom*.py`, `test_*capability*.py`) | 32 |
| `wrappers/` | Shell-Wrapper (`buildroom_autopilot_runner.sh`, `freeze-watchdog.sh`, `stability-watchdog*.sh`) | 4 |

Historische Orchestrator-Versionen `peekxd_buildroom_loop_v13..v19_1.py`
(9 Dateien) sind NICHT als Quelltext importiert; ihre SHA256-Hashes und
Metadaten stehen in `SOURCE_MANIFEST.json` (kind=historical). Sie werden
nur als Referenz/Hashes geführt, nicht als aktive Quelle.

## Provenance-Regeln

- Quelltext wurde byte-für-byte kopiert (SHA256-verifiziert gegen die
  Live-Dateien); keine Refaktorierung, keine Import-Änderung.
- Secret-Kandidaten-Scan vor dem Import: 0 Treffer (65 Dateien geprüft).
- Kein Live-State, keine Laufzeitdaten, keine Secrets wurden kopiert.
- Vollständige Metadaten je Datei: `SOURCE_MANIFEST.json` (schema:
  buildroom-legacy-source-manifest/v1).

## Abgrenzung

- Dieses Verzeichnis wird NICHT vom Package `curaops` importiert und ist
  kein Runtime-Pfad. Es dient als frozen source + Test-Baseline.
- Erste Read-only-Integrations-Scheibe (Strangler-Slice) liegt unter
  `curaops/buildroom/` (siehe `BUILDROOM_SHADOW_EQUIVALENCE_REPORT.json`
  und `tests/buildroom/`).
