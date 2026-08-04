# Reviewer-Verdikt — wire-canonical-buildroom-entrypoint-and-pilot-brain-runtime-on-real-task (DOD-13)

REVIEWER-VERDIKT: TEILBESTANDEN

BEGRÜNDUNG:

Unabhängiger, frischer Read-only-Review im exakten Commit-Zustand. 7 von 8 Kernpunkten
frisch verifiziert PASS; Kernpunkt 6 (Suite 399/0) ist im Commit-Zustand deterministisch
VERLETZT (1 Test-Fail, in d336ee9 selbst eingeführt).

1. LEGACY REAL ISOLIERT — PASS
   - curaops/buildroom/dispatcher.py:369-394: Auflösung der echten buildroom_loop.py
     (produktive Installation `~/.hermes/scripts/buildroom_loop.py` zuerst, dann
     `legacy/buildroom/source/buildroom_loop.py`); :402-421 `_run_legacy_entrypoint`
     führt buildroom_loop.py `--legacy-peekxd` in isoliertem HOME aus.
   - fixtures/live/rollback/rollback-evidence.json: `legacy_real_executed: true`,
     `exit_code: 0`, `entrypoint: /home/roberto_schmidt/.hermes/scripts/buildroom_loop.py`,
     `managed_calls_after_rollback: 0`, `verdict: PASS`.
   - evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json, wired_dod_matrix DOD-04:
     `result: PASS`, check `legacy_real_ausgefuehrt` (Subprozess, isoliertes
     HOME/HERMES_HOME, PHASE_ALREADY_TERMINAL, kein legacy_delegated-Ersatz).

2. KEIN DUAL-SPAWN / ATOMARE LEASE — PASS
   - dispatcher.py:249 (O_CREAT|O_EXCL — genau EIN Gewinner), :267 `fcntl.flock(...LOCK_EX)`
     (Reclaim-Lock serialisiert unlink+create), :280 `os.open(lease, O_CREAT|O_EXCL|O_WRONLY, 0o600)`,
     :300 LOCK_UN, :457 flock automatisch frei bei Prozess-Exit.
   - tests/buildroom/test_dispatcher.py:389-427 `test_arbeit5_atomic_lease_multiprocess`:
     Event-Halte-Semantik (Docstring :392-395; Worker halten Lease bis `release.wait`,
     :409-411), 4 konkurrierende Prozesse, `assert wins.count(True) == 1` / `count(False) == 3`
     (:426-427). Kein Dual-Spawn-Pfad (managed_canary nur für allowlistete IDs,
     dispatcher.py:26-28, MODES-Docstring; non-canary -> legacy).

3. CONFIG IN contracts/ OHNE FIXTURES-DEFAULT — PASS (mit Minor-Finding)
   - contracts/buildroom-execution-dispatcher.yaml existiert:
     `buildroom.execution_path: legacy`, `canary_tasks: []`.
   - dispatcher.py:60 `_PACKAGE_DISPATCHER = "contracts/buildroom-execution-dispatcher.yaml"`;
     :102/:120 Package-Resource bzw. repo-relative contracts/; load()-Docstring
     "never fixtures by default"; Auflösung explicit -> CONDUVERA_BUILDROOM_DISPATCHER ->
     Paketressource -> legacy (missing -> legacy, konservativ).
   - grep "fixtures/buildroom" in dispatcher.py: genau 1 Treffer, Zeile 30 im Modul-Docstring
     (nicht produktiv). Kein fixtures-Default im ausführbaren Code.
   - goal-receipt.json wired_dod_matrix DOD-07: `result: PASS`, check
     `config_nicht_fixtures_ungueltig_blockt` (kanonische Config; CONFIG_INVALID bei
     invalid mode / invalid canary id beim Laden).

4. CANARY 3/3 — PASS
   - fixtures/live/dispatcher-canary/dispatcher-3x-canary-evidence.json: 3 Runs, alle
     `status: completed`, `response: CONDUVERA_FIXTURE_OK`, `response_exact: true`,
     `clean: true`, `leases_left: 0`; Abschlussfelder `all_exact: true`,
     `all_completed: true`, `zombies: []`, `orphans: []`, `pgid_all_empty: true`,
     `foreign_process_changed: false`, `all_leases_released: true`,
     `verdict: "PASS 3/3 CANARY"`.

5. BRAIN-PILOT — PASS (frisch ausgeführt, CONDUVERA_BRAIN_ROOT=Roberto_Brain-Vault)
   - `brain doctor`: 0 errors (2 WARN: Git dirty, 3 source-YAML-Warnungen — keine Fehler).
   - `brain context --topic "Buildroom Migration Matrix Authority_Map Conduvera_System_Feature_Catalog
     Buildroom_AI_Stack_Contract dispatcher legacy managed canary" --max-tokens 12000`:
     Output enthält alle 4 Pflichtquellen —
     Authority_Map.md, Conduvera_System_Feature_Catalog.md, Buildroom_AI_Stack_Contract.md,
     Buildroom_Migration_Matrix.md (20_Areas/Dev_Infrastructure/...).
   - `brain index rebuild`: `native_yaml_errors: 0` (Rebuilt: 165 native docs, 2145 source
     docs; 3 source_yaml_warnings ausschließlich in 99_Sources_READONLY/Fremdquellen).

6. SUITE 399/0 — NICHT BESTANDEN (einziger verletzter Kernpunkt)
   - Frischer Lauf `uv run python -m pytest -q --no-header -p no:cacheprovider` im exakten
     Commit-Zustand (HEAD d336ee9, Porcelain leer vor und nach dem Lauf):
     **1 failed, 395 passed, 3 skipped** (1.19s).
   - Fail: tests/test_evidence_allowlist.py::test_all_evidence_files_are_allowlisted (Z.73).
     Der Test prüft committete Dateien (`git ls-tree HEAD`) unter fixtures/live gegen
     evidence/evidence-allowlist.yaml allowed_patterns. 4 in d336ee9 committete Dateien
     haben KEINEN Allowlist-Eintrag:
       - fixtures/live/rollback/canary-run/evidence/mxos-evidence-ATT-5F959753.json
       - fixtures/live/rollback/canary-run/managed-state.json
       - fixtures/live/rollback/dispatcher-canary.yaml
       - fixtures/live/rollback/dispatcher-legacy.yaml
     Die Rollback-Sektion der Allowlist enthält nur `verify_rollback_evidence.py` und
     `rollback-evidence.json`. Die Dateien existierten im Parent bbc5c61 NICHT
     (`git ls-tree -r bbc5c61 -- fixtures/live/rollback/` leer) und wurden in d336ee9
     hinzugefügt (git diff --stat bbc5c61 d336ee9: +47/+48/+15/+4/+2 Zeilen) —
     der Fehler wurde exakt im zu reviewenden Commit eingeführt. Deterministisch,
     umgebungsunabhängig (nur git ls-tree + YAML gelesen).
   - 3 Skips: erwartete Brain-Konsistenz-/Vault-Skips ohne CONDUVERA_BRAIN_ROOT im
     Suite-Env (test_ui_access_plane.py:83-90; test_architecture_consistency.py:122,141)
     — kein Fehler, konsistent mit früherem Review-Lauf.
   - Der behauptete Zustand "399 passed, 0 failed" ist im exakten Commit-Zustand NICHT
     reproduzierbar.

7. DIAGRAMM-KANTEN — PASS
   - tests/test_architecture_consistency.py:213 `def test_dod12_diagram_shows_real_call_path_edges`.
   - docs/architecture.mmd:23 `B3 -->|managed_canary| B4`.

8. COMMIT-IDENTITÄT — PASS
   - `git rev-parse HEAD` == d336ee929f3210a78893cf852d35502c0f560d62 (exakt, kein
     Short-SHA, kein Typ-Expand).
   - Branch task/goal-contract-fixture; `git rev-list --parents -n 1 HEAD`:
     genau 1 Parent bbc5c617ad29236ed3992236fa80ac0b99bbbea1, kein Merge-Commit.
   - `git status --porcelain`: leer VOR dem Review und NACH Suite-/Brain-Proben
     (Null-Mutation des Repos bestätigt; brain-Proben schreiben nur in den Vault-Index).

FINDINGS:
1. [P1] Suite-Gate verletzt im Review-Commit d336ee9:
   tests/test_evidence_allowlist.py::test_all_evidence_files_are_allowlisted schlägt
   deterministisch fehl; 4 in d336ee9 committete Rollback-Evidence-Dateien
   (fixtures/live/rollback/canary-run/evidence/mxos-evidence-ATT-5F959753.json,
   fixtures/live/rollback/canary-run/managed-state.json,
   fixtures/live/rollback/dispatcher-canary.yaml,
   fixtures/live/rollback/dispatcher-legacy.yaml) fehlen in
   evidence/evidence-allowlist.yaml allowed_patterns. Ergebnis: 1 failed, 395 passed,
   3 skipped — erwartet laut Goal: 399 passed, 0 failed. Minimalbehebung: die 4
   Artefaktpfade als allowed_patterns ergänzen (oder in Source-/Doku-Pfade umklassifizieren),
   dann Suite erneut ausführen.
2. [P3] Irreführender Modul-Docstring: curaops/buildroom/dispatcher.py:30 nennt
   "fixtures/buildroom/execution-dispatcher.yaml" als CONFIG-Quelle, während der
   produktive Code aus contracts/ lädt (dispatcher.py:60 _PACKAGE_DISPATCHER).
   Kein produktiver fixtures-Default, aber Doku widerspricht dem Code.

COMMIT-SHA-GEPRÜFT: d336ee929f3210a78893cf852d35502c0f560d62

Reviewer-Hinweis: Frühere Review-Versuche (HTTP-503-Abbruch) behaupteten
"399 passed, 2 skipped"; dieser unabhängige Frischlauf im exakten Commit-Zustand
(HEAD == d336ee9, sauberes Porcelain) widerlegt dies: der Allowlist-Fail ist
zustandsfest und reproduzierbar. Zwei frühere Abbruch-Versuche sind damit als
Verdikt-Grundlage nicht tragfähig; dieses Verdikt basiert ausschließlich auf dem
frischen, unabhängig ausgeführten Nachweis.

Zero-Mutation-Statement: Es wurden keine Produktdateien verändert.
Ausgeführt wurden ausschließlich read-only-Proben (git show/ls-tree/status,
grep/read, pytest mit -p no:cacheprovider) sowie die explizit beauftragten
Brain-Proben (doctor/context/index rebuild — schreiben nur in den Vault-Index,
nicht ins Repo). git status --porcelain war vor und nach allen Proben leer.
