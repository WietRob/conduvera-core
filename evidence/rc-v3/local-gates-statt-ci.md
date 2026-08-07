# Lokale Quality Gates statt CI — conduvera (2026-08-07)

## Entscheidung (Owner)
Keine GitHub-CI für die Conduvera-Komponenten. Qualitätsautorität sind
**lokale Gates inkl. SonarQube** (SonarQube Local Gate, Server 10.3 auf
127.0.0.1:9000, Docker-Scanner 5.0.1 gepinnt).

## Gates
| Komponente | Gate-Skript | Prüfungen | Letzter Lauf |
|---|---|---|---|
| conduvera-hermes-adapter | scripts/local-quality-gate.sh | pytest · ruff (Pin >=0.15,<0.16) · SonarQube-Scan · SonarQube-QG (advisory) | PRIMARY GATES PASSED (4/4) |
| conduvera-platform | scripts/local-quality-gate.sh | YAML-Syntax · Struktur-Check · conduitvera-Tippfehler | PRIMARY GATES PASSED (3/3) |

## SonarQube
- Server: 10.3.0.82913 (UP auf 127.0.0.1:9000)
- Scanner: sonarsource/sonar-scanner-cli:5.0.1 (gepinnt — latest bricht)
- Projekt: conduvera-hermes-adapter — QG-Status OK
- Token: persistiert in ~/.config/curaops/sonar.env (44 Zeichen, valid:true,
  Wert nie ausgegeben)

## Gate-Semantik (Skill-Konvention)
- Functional Gates (pytest/ruff/YAML/Struktur): **blocker** — FAIL = nicht
  abnahmefähig
- SonarQube QG (projektbezogen, Coverage/Hotspots): **advisory** — wird
  geloggt, blockiert aber nicht (historische Metriken, kein Stream-Fix nötig)
- Exit 0 nur bei allen Functional Gates grün

## Heads (nach dieser Arbeit)
- adapter: 007fc0b (0.1.3 — F1-Fix SBOM sourceInfo 2d6641e + Gate)
- platform: 4309752 (Gate)
- core: 63fb334 unverändert · goal-contract: 41c5e0f unverändert
- Porcelain: 0/0/0/0

## GITHUB_DISTRIBUTION
ENGINEERING_READY_BUT_NAMING_GATE_OPEN — Repos sind lokal gate-gesichert;
Publikation (Remotes, Push) wartet auf das Naming Gate (Owner-Entscheid).
