# Reviewer-Verdikt — Goal integrate-buildroom-core-guards-into-real-caller (DOD-17, Runde 2)

REVIEWER-VERDIKT: **BESTANDEN**

COMMIT-SHA-GEPRÜFT: `a34f92e8c484d26b2e198d417e15a38891718d05` (Branch `task/goal-contract-fixture`, HEAD exakt gleich; `git status --porcelain` exakt leer VOR und NACH allen Review-Aktionen — einzige Schreib-Aktion ist dieses Verdikt-Dokument)

GEPRÜFTER-TREE-UNVERÄNDERT: ja — nach dem Schreiben dieses Verdikts ist `git ls-files | grep -c reviewer-verdict-managed-integration-r2` → 0 (Verdikt untracked, nicht Teil des Commits)

---

## BEGRÜNDUNG (semantisch, pro Prüfpunkt)

### 1. ALLOWLIST-FIX — PASS
- `evidence/evidence-allowlist.yaml` enthält exakt die 5 neuen Muster (Z. 32–37): `fixtures/live/verify_managed_live.py`, `fixtures/live/managed/managed-3x-live-evidence.json`, `fixtures/live/managed/run-*/managed-state.json`, `fixtures/live/managed/run-*/state/call-trace.json`, `fixtures/live/managed/run-*/evidence/mxos-evidence-*.json`.
- Alle 10 committeten managed-Artefakte (`git ls-files fixtures/live/managed` = 9 Dateien + `fixtures/live/verify_managed_live.py`) sind abgedeckt:
  - `run-0/1/2/managed-state.json` → Muster `run-*/managed-state.json` ✓
  - `run-0/1/2/state/call-trace.json` → Muster `run-*/state/call-trace.json` ✓
  - `run-0/1/2/evidence/mxos-evidence-ATT-*.json` → Muster `run-*/evidence/mxos-evidence-*.json` ✓ (fnmatch-`*` matcht kein `/`; die konkreten Pfade passen positionsgenau)
  - `managed-3x-live-evidence.json` + `verify_managed_live.py` → exakte Muster ✓
- `tests/test_evidence_allowlist.py` (3 Tests: machine-readable, forbidden-artifacts, all-evidence-allowlisted) grün — committet `evidence/checks/evidence_allowlist.out`: `3 passed in 0.03s`; in frischer Suite enthalten (370 passed).
- KEIN ungelistetes managed-Artefakt: 0 Treffer.

### 2. VOLLE SUITE reproduzierbar — PASS
- Frischer Lauf mit exakt dem Evidence-Befehl `uv run python -m pytest -q --no-header -p no:cacheprovider`: **370 passed, 2 skipped in 0.90s**.
- Committet `evidence/checks/regression_full_managed.out`: **370 passed, 2 skipped in 0.91s** — Count identisch (Zeitdifferenz 0.01s = dokumentierte Messtoleranz).
- Sha256-Abgleich exakt: `sha256sum evidence/checks/regression_full_managed.out` = `f6628e70939d07eab0ad3967d7d0693a7e3a4f6e2b1c2dcb65bb1eef36c1c693` == `_managed.json` → `output_sha256: sha256:f6628e70939d07eab0ad3967d7d0693a7e3a4f6e2b1c2dcb65bb1eef36c1c693` (regression_full_managed), exitcode 0. `.out` ist frisch und unmanipuliert auf diesem Head.
- `_managed.json` deckt zudem managed_execution_tests (`14 passed`) und evidence_allowlist (`3 passed`) mit exitcode 0 ab.

### 3. SEMANTISCHER KERN (stichprobenhaft) — PASS
- **Policy-before-spawn:** `curaops/buildroom/managed_execution.py` Z. 199–224 — `require_backend_enabled(backend, …)` (Z. 200) läuft VOR `self._gateway.start_session(...)` (Z. 253). Policy-Block-Pfad (Z. 212–224) liefert `status="policy_blocked"` mit `session_id=""`, ohne PID/PGID, ohne Spawn — fail-closed.
- **no_progress im Caller:** `observe_reconciliation(...)` (Z. 344–352) im `execute()`-Pfad (Schritt 9 der MANDATORY ORDER), Ergebnis fließt in Terminal-Status `hold`/`completed` (Z. 356–357).
- **Kein getattr im produktiven Pfad:** einziger `getattr`-Treffer Z. 503 liegt INNERHALB der Test-only-Klasse `_TestOnlyGateway` (Z. 472–525); der produktive Pfad konstruiert `HarnessGatewayService` (Z. 126–129, 238–241).
- Fix selbst semantisch neutral: Diff entfernt nur den unused `load_backend_policy`-Import (managed_execution.py, -1 Zeile) — kein Verhaltensdelta.

### 4. LIVE-BEWEIS unverändert — PASS
- `fixtures/live/managed/managed-3x-live-evidence.json`: `verdict: "PASS 3/3 LIVE"`, alle 3 runs `completed` mit `response_exact: true` (`CONDUVERA_FIXTURE_OK`), `pgid_remaining: 0`, `clean: true`, `zombies: []`, `orphans: []`, `foreign_process_changed: false`.
- **Echte Modellidentität:** alle 3 runs `model_identity: "openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"` == Live-Manifest `~/.local/share/ai-stack/routes/local-mode.yaml` → Route `workload/local` → `upstream_model: openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`. NICHT `fixture-model-local`.
- Kreuz-Check gegen Verifier: `fixtures/live/verify_managed_live.py` erzeugt `verdict` `"PASS 3/3 LIVE"` (Z. 131–132, 148) und liest `model_identity` aus dem trace (Z. 103, 110) — Evidence stammt aus dem Verifier, nicht erfunden.
- Unverändert: `git show a34f92e --stat -- fixtures/` → leer (keine Live-Fixture im Fix-Commit geändert; Beweis aus R1-Vorgänger e0e71ab unangetastet übernommen).

### 5. KEIN SCOPE CREEP — PASS
- `git show --stat a34f92e` (9 Dateien): nur die 3 Fixes (`evidence-allowlist.yaml` +6, `tests/buildroom/test_managed_execution.py` 14 Zeilen, `managed_execution.py` -1) + regenerierte Evidence (`_managed.json`, 3 `.out`, `goal-receipt.json`) + R1-Verdikt-Dokument committet (`evidence/goals/CONDUVERA-FIXTURE-001/reviewer-verdict-managed-integration.md`, allowlisted unter `evidence/goals/**`, dokumentarisches Artefakt des Review-Prozesses — kein Code).
- Keine Statusänderungen (kein `status_gate.out` o. ä. im Commit), kein vierter Helper-Port (keine neuen Helper-Module), kein Merge (single parent `e0e71ab`), kein Runtime-Cutover.
- Testfix (test_dod13_no_foreign_process_changed, Z. 253–267) ist semantisch gleichwertig: vorher ps-Gesamtzahl (flaky), jetzt nur codex/opencode-Zeilen wie `verify_5x` — Assertion `after == before` statt Zeilenzahl.

### 6. COMMIT-IDENTITÄT — PASS
- `git rev-parse HEAD` == `a34f92e8c484d26b2e198d417e15a38891718d05` (IDENTITY-MATCH, voller SHA, kein Typ-Expand).
- `git status --porcelain` exakt leer VOR dem Review UND nach dem frischen Suite-Lauf.
- Hinweis (kein Finding): Der Task-Kontext nannte als Workspace `~/projects/CuraOps_VRP`; der zu prüfende Commit existiert dort NICHT, sondern ist HEAD des Goal-Contract-Repos `~/projects/matrix-os-wt-goal-contract` (dorthin zeigt auch der geforderte Verdikt-Pfad). Das Review wurde daher korrekt im Goal-Contract-Repo ausgeführt; die dortigen committeten Artefakte (fixtures/live/managed, evidence/checks, curaops/buildroom) stimmen exakt mit der Task-Beschreibung überein.

## FINDINGS
- Keine P1/P2/P3-Findings.

## FREIGABE-SCOPE (was BESTANDEN NICHT freigibt)
- Freigabe nur für den Fix-Commit `a34f92e8` als DOD-17-Runde-2-Review: Allowlist-Fix vollständig, Suite reproduzierbar (370 passed, 2 skipped), semantischer Kern intakt, Live-Beweis echt und unverändert, kein Scope-Creep.
- Freigibt NICHT: `OPERATIONAL_PRODUCTION` (Receipt: `NOT_YET`), System-Baseline-Review (`NOT_REQUESTED`) — unverändert gültig.

## EVIDENZ-INSPIZIERT
- evidence/evidence-allowlist.yaml (Z. 32–37), tests/test_evidence_allowlist.py (Z. 46–73), curaops/buildroom/managed_execution.py (Z. 199–224, 253, 344–352, 472–525), tests/buildroom/test_managed_execution.py (Z. 253–267), evidence/checks/regression_full_managed.out, evidence/checks/managed_execution_tests.out, evidence/checks/evidence_allowlist.out, evidence/checks/_managed.json, fixtures/live/managed/managed-3x-live-evidence.json, fixtures/live/verify_managed_live.py, ~/.local/share/ai-stack/routes/local-mode.yaml, evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json, git show --stat a34f92e, git log --oneline -3, git status --porcelain (vor/nach), frischer pytest-Lauf (370 passed, 2 skipped in 0.90s).
