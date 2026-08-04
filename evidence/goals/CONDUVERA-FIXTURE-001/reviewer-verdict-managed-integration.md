# Reviewer-Verdikt — Goal integrate-buildroom-core-guards-into-real-caller (DOD-17)

REVIEWER-VERDIKT: **NICHT BESTANDEN**

COMMIT-SHA-GEPRÜFT: `e0e71abeb0506f87adf90845c5dbe6abcec900a2` (Branch `task/goal-contract-fixture`, HEAD exakt gleich; `git status --porcelain` exakt leer VOR und NACH allen Review-Aktionen)

GEPRÜFTER-TREE-UNVERÄNDERT: ja — einzige Schreib-Aktion ist dieses Verdikt-Dokument (untracked, nicht Teil des Commits; `git ls-files | grep -c reviewer-verdict-managed-integration` → 0)

---

## BEGRÜNDUNG (semantisch, pro Prüfpunkt)

### 1. Tatsächlicher Callgraph (Mandatory Order 1–10, Policy-before-spawn) — PASS
`curaops/buildroom/managed_execution.py` implementiert die Mandatory Order exakt in der geforderten Reihenfolge:
- (1) Task-Validierung: `managed_execution.py:164-165` (`ValueError("TASK_DESCRIPTION_REQUIRED")`)
- (2) TaskBinding erzeugen + `store_task_binding`: `managed_execution.py:172-180`
- (3) `binding_for_phase` zurücklesen + Identität prüfen (task_id UND board): `managed_execution.py:183-188` → sonst `TASK_BINDING_IDENTITY_MISMATCH`
- (4) `require_backend_enabled`: `managed_execution.py:200-202` — kommt NACH store (180) und VOR `start_session` (254): **Policy-before-spawn erfüllt**
- (5) Block VOR jedem Spawn bei disabled/unknown: `managed_execution.py:203-225` — `status="policy_blocked"`, `session_id=""`, keine PID/PGID, kein Gateway-Aufruf; Entscheidung als `BACKEND_DISABLED_BY_OWNER`/`UNKNOWN_BACKEND` strukturiert (206-212)
- (6) `start_session` via HarnessGatewayService: `managed_execution.py:254-264` (+ `await_completion` 287-289, öffentliche Contract-Methode)
- (7) LiteLLM-Pfad: Model-Binding aus Route-Manifest (`_resolve_model_binding` 411-426, `auth_domain=litellm`, selector `workload/local`) wird als `config["model_binding"]/["route"]` an die Session übergeben (259-263); kein direkter LiteLLM-/ai-stack-Aufruf im Caller
- (8) `collect_evidence` + MXOS-EVIDENCE: `managed_execution.py:308, 326, 446-464`
- (9) `observe_reconciliation`: `managed_execution.py:345-353` — im `execute()`-Pfad NACH collect_evidence, VOR persist_state
- (10) `persist_state`: `managed_execution.py:382` (und konsistent in allen Fehlerpfaden 224, 235, 280, 304, 323)

Kein `getattr`/privater Adapter-Zugriff im produktiven Pfad: `self._adapter`/`getattr` existieren ausschließlich in `_TestOnlyGateway` (`managed_execution.py:473-521`), explizit als „TEST-ONLY adapter wrapper (never used in the productive path)“ markiert (474-480); der produktive Pfad nutzt nur `self._gateway.start_session/await_completion/collect_evidence` (öffentliche Methoden).

### 2. State- und Evidence-Fluss (MXOS-EVIDENCE-Pflichtfelder) — PASS
- `fixtures/live/managed/run-0/managed-state.json`: `task_bindings` (Phase-Key BUILDER → TaskBinding), `call_trace`, `no_progress` (count/fingerprint/terminal_hold/threshold/root_blocker/task_binding) — alle vorhanden.
- `fixtures/live/managed/run-0/state/call-trace.json`: pid, pgid, create_time, route (`workload/local`), model_identity, execution_mode (`LIVE`), evidence_event (`buildroom.run.completed`).
- `fixtures/live/managed/run-0/evidence/mxos-evidence-ATT-D301BA87.json`: schema `MXOS-EVIDENCE-1.0.0`, goal_id, task_id, attempt_id, session_id, harness, producer, evidence, generated_at — alle DOD-11-Pflichtfelder; entspricht `_persist_evidence` (`managed_execution.py:452-462`).
- `EventEnvelope.create` mit bestehender MXOS-Hülle: `managed_execution.py:387-393`; `EVENT_TYPES` um `buildroom.attempt.bound/started/failed/policy_blocked` + `buildroom.run.completed` erweitert (`curaops/evidence/contract.py:49-56`) — gleiches Schema, KEIN neues Evidence-Schema.

### 3. No-Progress im realen Caller — PASS
`observe_reconciliation` wird im `execute()`-Pfad nach `collect_evidence` aufgerufen (`managed_execution.py:345-353`), nicht nur separat. Threshold-Semantik 1→2→3 mit `terminal_hold = count >= threshold` (`curaops/buildroom/no_progress.py:90-93`), bei Hold `status=HOLD_FOR_BOSS`, `blocker=REPEATED_NO_PROGRESS`, `root_blocker=<ursprünglicher blocker>` (114-117); `NEW_EVIDENCE`-Reset bei gesetztem evidence_fingerprint (74-88). Belegt durch `tests/buildroom/test_managed_execution.py::test_d_no_progress_threshold_sequence` (1→2→3, r3 status hold, 176-186) und `test_e_progress_reset` (count=0, reset_reason NEW_EVIDENCE, 191-200) — beide grün.

### 4. Authority-Grenzen — PASS
- Keine neue Registry/State-Store/Evidence-Schema im Caller; State über `state_path`, Evidence über MXOS-EVIDENCE-1.0.0, Events über EventEnvelope.create.
- Kein impliziter GPU-Moduswechsel, keine litellm/ai_stack/bws/subprocess/os.environ-Mutation im Caller (Grep-Audit: keine Treffer; `ai-stack` nur als read-only `Path.home()/".local/share/ai-stack/routes/local-mode.yaml"`-Lesezugriff, `managed_execution.py:430-435`; `litellm` nur als `auth_domain`-String).
- Beide `except Exception`-Blöcke fail-closed: `_resolve_model_binding` → `None` → `MODEL_BINDING_UNAVAILABLE` (229-236); `_model_identity_from_manifest` → `""` → im LIVE-Modus `MODEL_IDENTITY_UNVERIFIED` (310-324). Kein Swallow-and-continue.
- FixtureRunner bleibt separater Seam (keine Referenz im Modul).
- `OPERATIONAL_PRODUCTION = NOT_YET` im Receipt (`goal-receipt.json` status_components); missing_gate „OPERATIONAL_PRODUCTION (kein Cutover)“ bei `managed_execution_caller` und `real_buildroom_execution_path` in system-capabilities.yaml.

### 5. LIVE-Beweis (DOD-16) — PASS
`fixtures/live/managed/managed-3x-live-evidence.json`: verdict `PASS 3/3 LIVE`; alle Runs `status=completed`, `response_exact=true` (CONDUVERA_FIXTURE_OK), `pgid_remaining=0`, `zombies: []`, `orphans: []`, `foreign_process_changed=false`, `same_semantic_state=true`.
**Echte Modellidentität aus Live-Manifest (kreuzgeprüft, nicht aus Fixture-Metadaten):**
- Live-Manifest `~/.local/share/ai-stack/routes/local-mode.yaml` (existiert, lesbar): Route `workload/local` → `upstream_model: openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`.
- Committete Identität in allen 3 Runs/call-traces: exakt `openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` — identisch mit dem Live-Manifest-Wert.
- Fixture-Manifest `fixtures/ods/route-manifest.fixture.yaml` enthält nur `model: fixture-model-local` — die committete Identität KANN dort nicht herkommen.
- Code-Pfad: `_model_identity_from_manifest` liest ZUERST das Live-Manifest (430-435); LIVE-Modus erzwingt Nicht-Leere (310-324). Zusätzlicher Beleg: `model_binding.model` im Evidence ist bewusst `fixture-model-local`, während `model_identity` die Live-Identität ist — die beiden Quellen sind klar getrennt.

### 6. Tests — NICHT BESTANDEN (P1)
- `uv run python -m pytest -q -p no:cacheprovider tests/buildroom/test_managed_execution.py` → **14 passed in 0.11s** — stimmt mit `evidence/checks/managed_execution_tests.out` (14 passed in 0.12s; Count identisch, Timing-Drift ±0.01s) überein.
- `uv run python -m pytest -q -p no:cacheprovider` (volle Suite) → **1 failed, 369 passed, 2 skipped in 1.09s** — stimmt NICHT mit `evidence/checks/regression_full_managed.out` („370 passed, 2 skipped in 0.90s“) überein. Der einzige Fehler ist reproduzierbar (isoliert erneut ausgeführt: `test_all_evidence_files_are_allowlisted` failed): `tests/test_evidence_allowlist.py:73` meldet 8 committete managed-Live-Artefakte, die nicht von `evidence/evidence-allowlist.yaml` abgedeckt sind (siehe Findings P1).
- sha256-Crosscheck: `sha256sum evidence/checks/regression_full_managed.out` = `4d880e20…` und `managed_execution_tests.out` = `a3a035c0…` — beide stimmen EXAKT mit `evidence/checks/_managed.json` überein (die .out-Dateien wurden nach ihrem Erzeugungslauf nicht verändert); das Problem ist also eine **stale Evidence**: Der committete 370er-Lauf beschreibt einen Baum OHNE die managed-Fixtures (bzw. vor deren Allowlist-Ergänzung) und ist auf dem finalen Commit nicht reproduzierbar.

### 7. Kein Scope-Creep — PASS
Semantischer YAML-Diff (vorher/nachher, geladen per yaml.safe_load) von `evidence/goals/CONDUVERA-FIXTURE-001/system-capabilities.yaml`: genau 4 geänderte + 1 neue Komponente von 36, alle anderen 30 unverändert:
- `buildroom_backend_policy_slice`: PARITY_PROVEN_NOT_INTEGRATED → **INTEGRATED_AND_LIVE_PROVEN** (missing_gate aktualisiert)
- `buildroom_no_progress_slice`: → **INTEGRATED_AND_LIVE_PROVEN**
- `buildroom_task_binding_slice`: → **INTEGRATED_AND_LIVE_PROVEN**
- `real_buildroom_execution_path`: NOT_PROVEN → **LIVE_PROVEN** (missing_gate bleibt OPERATIONAL_PRODUCTION; proof aktualisiert)
- NEU: `managed_execution_caller` (CORE-002D, LIVE_PROVEN, missing_gate OPERATIONAL_PRODUCTION)
- KEIN vierter Helper-Port, kein Merge/Cutover. `tests/test_architecture_consistency.py:62-66` erweitert die gültigen Status um `INTEGRATED_AND_LIVE_PROVEN` (konsistent, isoliert grün: 6 passed, 1 skipped).

### 8. Commit-Identität (DOD-18) — PASS
`git rev-parse HEAD` == `e0e71abeb0506f87adf90845c5dbe6abcec900a2`; `git branch --show-current` == `task/goal-contract-fixture`; `git status --porcelain` exakt leer (vor und nach den Review-Testläufen, `-p no:cacheprovider`); `git show --stat` == 20 Dateien, 1622 insertions, 18 deletions, exakt die in der Aufgabe genannten (managed_execution.py neu, test_managed_execution.py neu, verify_managed_live.py neu, 3× Live-Evidence-Bündel, Katalog, Receipt, contract.py EVENT_TYPES).

---

## FINDINGS

- **P1 — Evidence-Hygiene-Gate verletzt auf exaktem Commit (volle Suite rot, committete Regression-Evidence nicht reproduzierbar):**
  Der Commit fügt 8 Artefakte unter `fixtures/live/managed/**` hinzu, ohne `evidence/evidence-allowlist.yaml` (zuletzt in 7040ad5 geändert, in diesem Commit unverändert) zu erweitern:
  1. `fixtures/live/managed/managed-3x-live-evidence.json`
  2. `fixtures/live/managed/run-0/managed-state.json`
  3. `fixtures/live/managed/run-1/managed-state.json`
  4. `fixtures/live/managed/run-2/managed-state.json`
  5. `fixtures/live/managed/run-0/evidence/mxos-evidence-ATT-D301BA87.json`
  6. `fixtures/live/managed/run-1/evidence/mxos-evidence-ATT-E30372FB.json`
  7. `fixtures/live/managed/run-2/evidence/mxos-evidence-ATT-E4A3AEF9.json`
  8. `fixtures/live/verify_managed_live.py`
  (Die 3 `call-trace.json` matchen zufällig das Muster `fixtures/live/**/state/call-trace.json`, da fnmatch-`*` auch `/` matcht; die evidence-Muster verlangen dagegen eine weitere Ebene unter `evidence/` und matchen deshalb nicht.)
  → `tests/test_evidence_allowlist.py:73` failed; volle Suite frisch: **1 failed, 369 passed, 2 skipped** vs. committet „370 passed, 2 skipped“; `evidence/checks/regression_full_managed.out` ist damit stale; Receipt-Claim `EVIDENCE_HYGIENE_GATE = PASS` (`evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json`) ist auf diesem Commit falsch; Commit-Message-Claim „Tests: 370 passed + 2 skipped gesamt“ ebenfalls nicht reproduzierbar.
  **Fix (nächste Builder-Runde):** `evidence/evidence-allowlist.yaml` um `fixtures/live/managed/**` (bzw. die konkreten Muster) erweitern, volle Suite erneut laufen lassen (erwartet 370 passed, 2 skipped), `regression_full_managed.out` + `_managed.json`-sha256 + Receipt (EVIDENCE_HYGIENE_GATE) neu committen, dann erneutes Review auf dem neuen exakten SHA.

- **P3 (Kosmetik, nicht blockierend):** `load_backend_policy` wird in `curaops/buildroom/managed_execution.py:48` importiert, aber nie aufgerufen (unused import; `require_backend_enabled` lädt die Policy intern).

---

## Scope des Verdikts

Das Verdikt **NICHT BESTANDEN** betrifft ausschließlich den P1 der Evidence-Hygiene/Test-Wahrheit auf diesem exakten Commit. Der semantische Kern (Callgraph, Policy-before-spawn, State-/Evidence-Fluss, No-Progress, Authority-Grenzen, LIVE-Beweis mit echter Modellidentität, kein Scope-Creep, Commit-Identität) ist unabhängig verifiziert und erfüllt. Das Verdikt bestätigt ausdrücklich NICHT: OPERATIONAL_PRODUCTION (bleibt NOT_YET bis separate Cutover-/Absorptions-Beweise existieren).
