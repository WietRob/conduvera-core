# Reviewer-Verdikt: backend_policy-Port (DOD-10, unabhängiges semantisches Review)

- **Review-Typ:** DOD-10 unabhängiges semantisches Review (frische Session, kein Implementierungskontext)
- **Repo:** /home/roberto_schmidt/projects/matrix-os-wt-goal-contract
- **Branch:** task/goal-contract-fixture
- **Geprüfter Commit:** `c9db0d62255efe9f2c2f0ccdad65ccebae50386f`
- **Datum:** 2026-08-04
- **Reviewer-Runtime:** deepseek/deepseek-v4-flash-0731 (nous), Profil orchestrator (Subagent)

---

REVIEWER-VERDIKT: BESTANDEN

---

## BEGRÜNDUNG

### 1. Legacy-Parität (DOD-01/03/04) — PASS

Zeile-für-Zeile-Vergleich `legacy/buildroom/source/buildroom_backend_policy.py` (58 Z., frozen) vs. `curaops/buildroom/backend_policy.py` (78 Z.):

- **Maschinell verifiziert:** Der komplette Code-Abschnitt ab `from __future__ import annotations` (legacy Z.8 / neu Z.28) ist **51 Code-Zeilen exakt identisch** (String-Vergleich der beiden Blobs). Die neue Datei unterscheidet sich NUR durch das erweiterte Provenienz-/Scope-Docstring (neu Z.1–26); kein einziges Code-Token abweichend.
- **Konstanten/API identisch:** `POLICY_PATH` (legacy Z.15 / neu Z.35), `KNOWN_BACKENDS = ("native", "codex_cli", "opencode_cli")` (Z.16 / Z.36), `BackendPolicyError(ValueError)` (Z.19–20 / Z.39–40), `load_backend_policy` (Z.23–48 / Z.43–68), `require_backend_enabled` (Z.51–58 / Z.71–78).
- **Fehlercodes identisch:** `EXECUTION_BACKEND_POLICY_REQUIRED` (missing/unreadable), `EXECUTION_BACKEND_POLICY_INVALID` (Format/Validierung), `UNKNOWN_BACKEND:<backend>`, `BACKEND_DISABLED_BY_OWNER:<backend>`. Validierungslogik (Set-Gleichheit mit KNOWN_BACKENDS, native=={enabled:True}, codex/opencode disabled_by_owner + requires_explicit_owner_activation) in beiden identisch.
- **Rückgabe-Reihenfolge identisch:** `{name: dict(backends[name]) for name in KNOWN_BACKENDS}` — deterministisch native→codex_cli→opencode_cli, unabhängig von YAML-Reihenfolge.
- **Legacy-Integrität:** sha256 des Legacy-Blobs == `c17ed5a491b17800aa1056443da24d6f2f8843287e0c735a3d77d3e6ea0f9ac8`, exakt wie im Port-Docstring (backend_policy.py Z.4–5) und der Behaviour-Matrix (Z.3–4) behauptet.
- **Differentialtests** `tests/buildroom/test_backend_policy_differential.py`: führen für identische Inputs Legacy UND Neu aus und vergleichen Rückgabewert, Exception-Typ-Name, Fehlercode/Message (Z.55–61 `_run`), deterministische Reihenfolge (Z.121), Side Effects/env (Z.165–171). **Frisch ausgeführt: 21 passed** — deckungsgleich mit `evidence/checks/backend_policy_differential.out` (21 passed).
- **Behaviour-Matrix** `backend-policy-behaviour-matrix.md`: 17 Verhaltensfälle (Z.36–54) — gültig/fehlend/unbekannt/deaktiviert/leer/falscher Typ/YAML-Invalid/Default/fail-closed; API vollständig inventarisiert (Z.6–12), Caller als nicht portiert deklariert (Z.18–23), Side Effects „KEINE" (Z.25–32).

### 2. Boundary-Einhaltung (DOD-05/06/08) — PASS

- **Kein Legacy-Import in Produktion:** `grep 'from legacy|import legacy|legacy.buildroom' curaops/ --include=*.py` → 0 Treffer (kein einziges Import-Statement; das Wort „legacy" kommt in curaops/ nur in Docstring-Provenienz vor). Nur die Testdatei lädt Legacy via sys.path (test_backend_policy_differential.py Z.29, Z.32) — DOD-05 exakt so spezifiziert.
- **Nur Execution-Backend-Autorität:** Statischer Negativtest (Z.144–161) prüft nach Docstring-Stripping: keine `litellm/ai_stack/ai-stack/bws/bitwarden/subprocess/requests/os.environ/os.getenv`. Unabhängiger grep bestätigt: im Modul erscheinen diese Begriffe nur in Docstring-Zeile 13 (Scope-Statement). Dynamisch (Z.164–171): env vor/nach identisch. Keine Registry, kein Evidence-Schema, keine zweite Policy-Authority — Modul ist pure Policy-Prüfung (nur `yaml.safe_load` + Validierung).
- **Nicht portiert:** `no_progress`, `task_binding`, `fleet_router` → 0 Treffer in curaops/. `git diff --name-status c9db0d6^ c9db0d6 -- curaops/` zeigt exakt EINE neue Datei: `curaops/buildroom/backend_policy.py`.
- **Integration deferred:** `legacy/` komplett unverändert (kein einziger geänderter Pfad unter legacy/); buildroom_core/buildroom_execution bleiben Legacy-Caller. Keine simulierte Integration im Diff.

### 3. Tests (DOD-07) — PASS

- **Frisch ausgeführt (read-only Testlauf):** `pytest -q tests/buildroom/test_backend_policy_differential.py` → **21 passed**; volle Regression `pytest -q` → **301 passed, 2 skipped**. Beide Ergebnisse stimmen exakt mit den committeten .out-Dateien überein.
- **Anti-Tamper verifiziert:** sha256sum der drei Checks == Manifest `evidence/checks/_backend_policy.json` exakt: `regression_full_backend_policy.out` `6e4060…5657`, `backend_policy_differential.out` `a43b1c…bf49`, `architecture_consistency.out` `a3b87b…63e4`. Keine Rewrites nach dem Lauf.

### 4. Kein Scope Creep (DOD-09) — PASS

Semantischer YAML-Vergleich (yaml.safe_load beider Commit-Versionen von `system-capabilities.yaml`, Feld-Ebene): exakt **10 Feld-Differenzen**, alle gefordert:

- `conduvera_release` (OPS-003): LIVE_PROVEN → **DESIGNED_ONLY** (+ missing_gate-Begründungstext).
- `buildroom_module` (CORE-002) aufgeteilt in `buildroom_fixture_seam` (NEU, LIVE_PROVEN) / `real_buildroom_execution_path` (NEU, NOT_PROVEN) / `buildroom_absorption` (NEU, NOT_STARTED); Mutter-Status LIVE_PROVEN → NOT_PROVEN.
- `conduvera_core` (CORE-001) aufgeteilt in `core_adapter_seam` (NEU, RELEASE_CANDIDATE) / `conduvera_core_full_control_plane` (NEU, PARTIAL); Mutter-Status LIVE_PROVEN → NOT_OPERATIONAL.
- `buildroom_backend_policy_slice` (CORE-002B1): NEU, **LIVE_PROVEN**.

Die beiden Mutter-Statuskorrekturen (CORE-001/002) sind die konsistente Konsequenz der geforderten Aufteilungen (kein Komponententeil darf LIVE_PROVEN behaupten, wenn nur ein Teil-Slice bewiesen ist) — kein neuer Evidence-Anspruch, kein Scope-Creep. **Alle übrigen 24 Komponenten: null Feld-Differenzen** (MODEL/ODS/CAP/HARNESS/SEC/UI/OPS-001/002/004 unverändert).

Diagramme `docs/CONDUVERA_ARCHITECTURE_DIAGRAM.md` + `docs/architecture.mmd`: jeweils nur der B2-Node ergänzt (1 Zeile). `tests/test_architecture_consistency.py`: nur Status-Validierungsmenge um die 4 neuen Statuswerte erweitert (Z.62–64) — notwendige Begleitänderung.

### 5. Commit-Identität (DOD-11) — PASS

- `git rev-parse HEAD` == `c9db0d62255efe9f2c2f0ccdad65ccebae50386f` (vor und nach dem Review identisch; `git diff` requested→HEAD leer, kein Mid-Review-Drift).
- `git status --porcelain` exakt leer — **vor** den Testläufen und **nach** den Testläufen erneut verifiziert.
- `git show --stat c9db0d6`: **12 Dateien** — 1 neues Modul (curaops/buildroom/backend_policy.py), 1 neue Testdatei (tests/buildroom/test_backend_policy_differential.py), Behaviour-Matrix (neu), system-capabilities.yaml (Katalog-Korrekturen), 2 Diagramm-Dateien (+1 je), 3 Checks + _backend_policy.json-Manifest, goal-receipt.json, tests/test_architecture_consistency.py — exakt die erwartete Artefaktmenge.

### 6. Rechte-Attest (Post-Verdikt)

- Nach dem Schreiben dieses Verdikts: `git status --porcelain` → nur dieses Verdikt als untracked (`git ls-files` enthält es nicht, 0 Treffer). Der geprüfte Commit-Tree bleibt unverändert.
- GEPRÜFTER-TREE-UNVERÄNDERT: ja

## FINDINGS

- **Keine P1/P2-Findings.**
- P3-Beobachtung (kein Blocker): Die system-capabilities.yaml wurde vollständig von YAML-Flow-Style auf Block-Style umformatiert (~700 kosmetische Zeilen). Semantisch neutral — maschinell verifiziert (nur die 10 erwarteten Feld-Differenzen, keine Wertänderung in den übrigen 24 Komponenten). Reine Format-Konvertierung, kein Scope-Creep.

## COMMIT-SHA-GEPRÜFT

`c9db0d62255efe9f2c2f0ccdad65ccebae50386f`

---

## Geprüfte Artefakte

- legacy/buildroom/source/buildroom_backend_policy.py (58 Z., sha256 c17ed5a…9ac8)
- curaops/buildroom/backend_policy.py (78 Z.)
- tests/buildroom/test_backend_policy_differential.py (183 Z., 21 Tests)
- evidence/goals/CONDUVERA-FIXTURE-001/backend-policy-behaviour-matrix.md (17 Fälle)
- evidence/goals/CONDUVERA-FIXTURE-001/system-capabilities.yaml (alt 27 / neu 33 Komponenten, Feld-Level-Diff)
- evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json (backend_policy_dod_matrix DOD-10/11 PENDING vor diesem Review)
- evidence/checks/backend_policy_differential.out (21 passed), regression_full_backend_policy.out (301 passed, 2 skipped), architecture_consistency.out (6 passed, 1 skipped), _backend_policy.json (SHA256-Manifest, alle 3 Hashes verifiziert)
- docs/CONDUVERA_ARCHITECTURE_DIAGRAM.md, docs/architecture.mmd (B2-Node)
- tests/test_architecture_consistency.py (Statuswerte-Menge)

## Freigabe-Umfang

Das BESTANDEN gilt für den **backend_policy-Slice** (Port + Differential-Parität + Boundary + Katalog/Dokumentation). Es setzt NICHT frei: REAL_BUILDROOM_EXECUTION_PATH (NOT_PROVEN), BUILDROOM_ABSORPTION (NOT_STARTED), no_progress/task_binding-Ports, Caller-Integration in buildroom_core/buildroom_execution (explizit deferred), OPERATIONAL_PRODUCTION (NOT_YET).
