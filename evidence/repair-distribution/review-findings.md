# Review-Findings (deleg_d9f6d0ba) — BESTANDEN 15/15, nicht-blockierend

## F-A (moderat) — Adapter-Gate verschluckt pytest-Exit-Code
- Skript: scripts/local-quality-gate.sh (Adapter 43edf9a), Zeile ~41:
  PYTEST_OUT="$(cd "$REPO_ROOT" && python3 -m pytest ... || true)" -> PYTEST_RC immer 0
- Wirkung: Ein Failing-Test (Regression) wird als PASS pytest + exit 0 gemeldet.
- Keine DOD-Verletzung (DOD-07 prüft dirty-tree), aber Gate-Zuverlässigkeitslücke.
- Fix-Empfehlung (Reviewer): if out="$(pytest ...)"; then rc=0; else rc=$?; fi
- Folgepunkt: beim nächsten Adapter-Gate-Update (nicht in diesem Goal — DOD-15).

## F-B (minor) — Legacy-Artefakte im Adapter-Repo
- artifact-manifest.json/provenance-receipt.json/SBOM.spdx.json (Root) + evidence/releases/0.1.3-8ab8404
  binden Ancestors e3dc820/8ab8404 mit altem Wheel-SHA e793dc8a (publiziert: 32b96d).
- Kanonische Kette (Platform-Attestations/43edf9a == Lock == GitHub) ist konsistent
  und wird vom Platform-Gate erzwungen. Legacy-Rest, kein Drift.

## F-C (Hinweis) — platform-truth.py hardcodierter PLATFORM-Pfad
- --verify liest Lock des lokalen Repos; auf Maschine ohne lokalen Checkout FAIL.
- Auf dieser Maschine LOCAL_MATCH; frischer-Clone-Gate lief 6/6 (DOD-06 erfüllt).
