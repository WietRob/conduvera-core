# Naming Gate GESCHLOSSEN + GitHub-Distribution (2026-08-07)

## Naming Gate (Owner-Entscheid)
```text
matrix-os              -> WietRob/conduvera-core          (PUBLIC, umbenannt)
conduvera-hermes-adapter -> WietRob/conduvera-hermes-adapter (PRIVATE, neu)
conduvera-platform     -> WietRob/conduvera-platform      (PRIVATE, neu)
```

## Publikation (2026-08-07)
- conduvera-core: rename matrix-os -> conduvera-core via gh (PUBLIC, GitHub
  Redirect aktiv — WietRob/matrix-os leitet weiter, HTTP 200)
  - main 63fb334cc02ee101f95c48e41de9dcfcfd5f6f9c (kanonisch, CI-grün)
- conduvera-hermes-adapter: PRIVATE, main 007fc0b (0.1.3, lokales Gate 4/4)
- conduvera-platform: PRIVATE, main 2869716 (Lock + Gate 3/3)
- Lokale Remotes aktualisiert (core: git@github.com:WietRob/conduvera-core.git)

## KEINE CI — lokale Gates bleiben die Qualitätsautorität
- Adapter: scripts/local-quality-gate.sh (pytest + ruff + SonarQube-Scan +
  SonarQube-QG-advisory) — PRIMARY GATES PASSED (4/4)
- Platform: scripts/local-quality-gate.sh (YAML + Struktur + Tippfehler) —
  PRIMARY GATES PASSED (3/3)
- Kein .github/workflows in Adapter/Platform — bewusst (Owner-Entscheid:
  "keine ci sondern loacl gates..inckl. sonatr cube")
- SonarQube: Server 10.3 (127.0.0.1:9000), Scanner 5.0.1 gepinnt,
  Projekt conduvera-hermes-adapter QG=OK

## Heads (final, alle Porcelain 0)
- core: 63fb334 (unverändert, jetzt WietRob/conduvera-core)
- adapter: 007fc0b (0.1.3, F1-Fix + Gate)
- platform: 2869716 (Namen + Gate)

## Status
```text
GITHUB_DISTRIBUTION = PUBLISHED (core PUBLIC, adapter/platform PRIVATE)
CONDUVERA_PLATFORM = REVIEWED_LOCAL_COMPOSITION_AUTHORITY
OPERATIONAL_PRODUCTION = NOT_YET (kein Produktiv-Cutover)
```
