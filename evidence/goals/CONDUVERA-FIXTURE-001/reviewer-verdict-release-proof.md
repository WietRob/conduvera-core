# Reviewer-Verdikt — Release-Proof (DOD-09 / ARBEIT 6)

**REVIEWER-VERDIKT: BESTANDEN**

**COMMIT-SHA-GEPRÜFT:** `87e1296ca161b49f083fd707933be547c452b481` (Branch `task/goal-contract-fixture`)

**Review-Methode:** Unabhängiges semantisches Read-only-Review in frischer Session (kein Implementierungs-Kontext). Einzige Schreib-Aktion: dieses Verdikt-Dokument. `git status --porcelain` war vor den Prüfungen und nach den frischen Testläufen exakt leer.

---

## BEGRÜNDUNG (pro Prüfpunkt)

### 1. FINALER COMMIT — PASS
- `git rev-parse HEAD` = `87e1296ca161b49f083fd707933be547c452b481` (exakt, kein Typ-Expand), Branch `task/goal-contract-fixture`.
- `git status --porcelain` leer (vor und nach den Testläufen).
- `git show --stat HEAD`: Allowlist-Fix (`evidence/evidence-allowlist.yaml`, 5± Zeilen), Evidence (`evidence/checks/*_releaseproof.out` 4x, `fixtures/live/worktree-unavailable-v2/evidence/mxos-evidence-*.json` 3x), `evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json` (90±), `evidence/checks/_releaseproof.json`. Keine Produktcode-Änderung in diesem Commit.
- **Präzisierung (kein Finding):** `dispatcher.py` ist nicht Teil dieses Commits — die `~/.config`-Auflösung (ARBEIT 2) stammt aus dem Vorgänger-Commit `990b19a`. Entscheidend ist: Die final installierte Release-C-Quelle (site-packages) enthält die Auflösung nachweislich (siehe Prüfpunkt 2/3).

### 2. INSTALLIERTE RUNTIME (Release C) — PASS
- `readlink -f ~/.local/bin/buildroom-operator` → `~/.local/share/conduvera/releases/buildroom-operator/87e1296ca161b49f083fd707933be547c452b481/venv/bin/buildroom-operator` — KEIN `matrix-os-wt-*`-Worktree-Pfad.
- `current` → `87e1296…/venv` (C), `previous` → `990b19a…/venv` (B).
- `release-manifest.json` in `87e1296…/`: `git_commit: 87e1296ca161b49f083fd707933be547c452b481`, `wheel_sha256: f26383a8dcb877762a440d5509c3b28acd2236a470982e6b68d85c0a28c6ac0f` — `sha256sum` der Wheel-Datei stimmt exakt.
- `dispatcher.py` aus site-packages (`…/87e1296…/venv/lib/python3.12/site-packages/curaops/buildroom/dispatcher.py`): **0 Worktree-Referenzen** in der Datei.
- Ausführung: `~/.local/bin/buildroom-operator --project peekxd` → `{"execution_path":"legacy","status":"legacy_completed","entrypoint":"/home/roberto_schmidt/.hermes/scripts/buildroom_loop.py","exit_code":0,…}`, Exit 0.

### 3. PRODUKTIVE CONFIG (DOD-02) — PASS
- `~/.config/conduvera/buildroom-operator/dispatcher.yaml`: `execution_path: legacy`, `route: workload/local`, `canary_tasks: []` — **0 Worktree-Referenzen**.
- `~/.config/conduvera/buildroom-operator/dispatcher-canary.yaml`: `execution_path: managed_canary`, `canary_tasks: [t_c0a1, t_0c0a1e, t_0c0a1f]`, `route: workload/local`.
- Code: `DispatcherConfig.load()` in `dispatcher.py:139-163` — Priorität: explicit path → `CONDUVERA_BUILDROOM_DISPATCHER`-Env → `local_override` (`Path.home()/".config/conduvera/buildroom-operator/dispatcher.yaml"`, Zeile 147-148) → Package-Resource (`contracts/buildroom-execution-dispatcher.yaml`, Fallback `legacy`). `local_override` kommt **vor** der Package-Resource. Env-Var ist im Review-Prozess nicht gesetzt (kein Override aktiv).

### 4. WORKTREE-UNAVAILABLE (DOD-03) — PASS (nur Evidence verifiziert, kein Worktree-Umbenennen wiederholt)
3/3 Canary-Evidence in `fixtures/live/worktree-unavailable-v2/evidence/`:
- `mxos-evidence-ATT-B3E40C07.json` → task `t_c0a1`, `status: completed`, `ok: true`, `handle.route: workload/local`, `model_binding.selector: workload/local`, `exitcode: 0`
- `mxos-evidence-ATT-F7196502.json` → task `t_0c0a1e`, completed, route `workload/local`, exitcode 0
- `mxos-evidence-ATT-3FC15A4F.json` → task `t_0c0a1f`, completed, route `workload/local`, exitcode 0
Zusätzlicher Beleg: installierte Runtime-Quelle aus site-packages (Prüfpunkt 2) funktioniert ohne Worktree.

### 5. RELEASE-ROLLBACK (DOD-04/05/06) — PASS
- Drei Release-Verzeichnisse, **alle** mit `venv/` + `matrix_os-0.1.0-py3-none-any.whl` + `release-manifest.json` IM versionierten Verzeichnis: `8094134abf6e…` (A), `990b19a3dd9a…` (B), `87e1296ca161…` (C).
- Wheel-SHAs exakt == Manifeste: A `de54726f5fb4…` ✓, B `88d9290a6a2d…` ✓, C `f26383a8dcb8…` ✓ (alle per `sha256sum` frisch berechnet).
- `current`→C, `previous`→B (Symlinks).
- Receipt `releaseproof_dod_matrix` DOD-04/05/06 = PASS: atomar B→A (Wheel-SHA de54726f == Manifest, Match True), A lief (Legacy exit 0 + Canary completed), atomar A→B erneut, 0 Prozesse/Leases. Physische `fixtures/live/rollback/rollback-evidence.json`: `rollback_resolve` → `path_after: legacy`, `legacy_real_executed: true`, `leases_left: 0`, `verdict: PASS`.

### 6. HERMES-CLIENT (DOD-01) — PASS
- `diff ~/.hermes/profiles/orchestrator/config.yaml.bak-20260805-luna-fix ~/.hermes/profiles/orchestrator/config.yaml` = **exakt 1 Zeile**: Backup `default: oauth/codex-luna` → live `default: oauth/codex`.
- Backup-Datei existiert (`config.yaml.bak-20260805-luna-fix`, 378 B, 05.08. 09:38).
- **Session-Beweis (echt):** Hermes-Session-DB zeigt Session `20260805_103731_0360bb` (05.08.2026 10:37): User-Prompt „Antworte mit exakt einem Wort: PONG" → Antwort „PONG", **model: `oauth/codex`** (der neue Default nach dem Fix). Das ist der echte Prompt-Nachweis; kein erneuter LLM-Call durchgeführt (Task-Vorgabe).
- Aktiver Gateway PID 300958 läuft seit `Di Aug 4 13:51:07 2026` — d.h. **vor** dem Config-Fix (05.08. 09:38); er hält den alten Default im Speicher, ein neuer Prozess lädt frisch (belegt durch die Session 10:37 mit `oauth/codex`).
- Hinweis: Direkte `state.db`-SQL-Abfrage wurde vom Owner während des Reviews blockiert; der Session-Nachweis wurde stattdessen über die Hermes-Session-DB (read-only `session_search`) erbracht.

### 7. MODELLKATALOG (DOD-07) — PASS
- `evidence/litellm-config-cleaned-draft-20260805.yaml`, Zeile 1: `# STATUS: NOT_APPROVED / QUARANTINED (Owner 2026-08-05) — NICHT aktivieren, NICHT anwenden.`
- `evidence/model-alias-catalog-v1.json`: **46 Modelle**, 5 Familien über `provider_family`: codex 13, zai 15, kimi 7, deepseek 3, local 8 (= 46). Top-Level `status: READ_ONLY_INVENTORY — KEINE Aktivierung, KEINE Entfernung ohne Owner`; `note` enthält die Owner-Anforderung (Codex-Varianten sol/terra/luna/spark/5.4-mini sowie Z.AI-/DeepSeek-Varianten dürfen nicht pauschal entfernt werden).
- LiteLLM-Container **nicht aktiviert/neugestartet**: `dream-litellm` StartedAt `2026-07-31T05:36:51Z`, running — kein Restart am 05.08.

### 8. AI-STACK (DOD-10) — PASS
- GPU im Text-Mode aktiv: NVIDIA RTX 5090 Laptop, 22106/24463 MiB belegt.
- Route-Hash `~/.local/share/ai-stack/routes/local-mode.yaml` = `4e11969eea21…` — Präfix **4e11969e** ✓.
- `dream-litellm` unverändert: StartedAt 31.07., Host-Mount `~/dream-server/config/litellm/local.yaml` (SHA `c65cd000fcfd…`) ist **byte-identisch** mit `/app/config.yaml` im Container. Host-LiteLLM-Prozess PID 3568 läuft seit 31.07. 07:36.
- Keine Secret-/Service-Mutation erkennbar (keine neuen Prozesse, keine Container-Neustarts, Commit enthält keine Secrets).
- Hinweis: Die Task-Angabe „Config c6e1fdfd" konnte keiner auffindbaren Datei zugeordnet werden; die gemessene dream-litellm-Config hat SHA `c65cd000fcfde…` (Host-Mount == Container). Kein Anzeichen einer Mutation, daher kein Finding — nur Dokumentations-Drift in der Task-Angabe.

### 9. KONSISTENZ (DOD-10) — PASS
- `goal-receipt.json`: `overall_status: TEILBESTANDEN`, `OVERALL_GOAL: TEILBESTANDEN`, `INDEPENDENT_SEMANTIC_REVIEW: PENDING` (vor diesem Verdikt), `RELEASE_ROLLBACK: LIVE_PROVEN`, `DURABLE_MANAGED_CANARY_INSTALLATION: LIVE_PROVEN`, `ACTIVE_HERMES_CLIENT_RELOAD: LIVE_PROVEN`, `LITELLM_CLEANUP_DRAFT: NOT_APPROVED`, `GENERAL_MANAGED_CUTOVER: NOT_STARTED`, `OPERATIONAL_PRODUCTION: NOT_YET`.
- Brain-Vault `Buildroom_Migration_Matrix.md:202-216` (STATUSKORREKTUR-2, 2026-08-05, Owner): deckungsgleich (OVERALL_GOAL = TEILBESTANDEN, INDEPENDENT_SEMANTIC_REVIEW = PENDING, RELEASE_ROLLBACK = LIVE_PROVEN A/B 8094134a↔990b19a atomar SHA-geprüft, LLM_ROUTING_INCIDENT = RESOLVED mit oauth/codex-Umstellung); im Vault **committet** (letzter Commit `2c87a73` „brain: Statuskorrektur-2 — … Review PENDING", porcelain leer).
- Kein Widerspruch zwischen Repo-Receipt, DOD-Matrix und Brain-Matrix.

### 10. TESTS (DOD-08) — PASS (frisch reproduziert)
- `CONDUVERA_BRAIN_ROOT="/home/roberto_schmidt/Dokumente/Obsidian Vaults/Roberto_Brain/20_Areas/Dev_Infrastructure/ODS_Integration" uv run python -m pytest -q --no-header -p no:cacheprovider` → **412 passed in 1.36s** (0 failed).
- `PYTHONPATH=legacy/buildroom/source uv run python -m pytest -q --no-header -p no:cacheprovider legacy/buildroom/tests/test_buildroom_cycle49_preflight.py legacy/buildroom/tests/test_buildroom_task_binding_cycle49.py` → **30 passed in 0.04s** (0 failed).
- Evidence-Hash-Manifest-Cross-Check: alle 4 `.out`-Dateien exakt == `_releaseproof.json`-Einträge (regression_full `fc2daf99…`, dispatcher_tests `0acf2c70…`, legacy_characterization `670684a4…`, allowlist `c2cba0e5…`) — kein Tampering, Artefakte nicht nachträglich umgeschrieben.

### 11. KEIN SCOPE CREEP — PASS
- Kein Merge in der Spitzen-Historie (die 3 gefundenen Merge-Commits `e5b7e9b`, `80cd916`, `0e1fd99` sind alt/aus anderen Themensträngen); Reflog zeigt ausschließlich sequentielle `commit:`-Einträge (kein reset/rebase/amend/Force-Push-Indiz).
- `git diff --stat HEAD^ HEAD -- legacy/` = leer (Legacy-Inhalt unverändert durch den Review-Commit).
- Commit-Dateiliste nur: Evidence (checks, live-evidence, receipt), Allowlist-Fix, `_releaseproof.json` — keine ODS-/LiteLLM-/GPU-/BWS-/ComfyUI-/RAG-/Voice-/n8n-/Langfuse-Änderung, keine Secret-Rotation, kein Container-Restart.
- Kein Worktree-Pfad in produktiver Config (`~/.config/…`), Env (keine CONDUVERA/BUILDROOM-Variablen gesetzt) oder Release-Artefakten (grep `matrix-os-wt` über alle produktiven Artefakte: 0 Treffer).

---

## FINDINGS

1. **[P3 – Hinweis]** Zentrales `~/.local/share/conduvera/releases/buildroom-operator/release-manifest.json` (Basisverzeichnis) referenziert noch Release A (`git_commit: 8094134a…`, `installed_at: 2026-08-05T09:28:50`) und wurde nach dem Rollback/Upgrade auf C nicht aktualisiert. Die bindenden Manifeste je Release-Verzeichnis sind korrekt (verifiziert). Empfehlung: zentrales Manifest aktualisieren oder als Legacy-Artefakt kennzeichnen.
2. **[P3 – Hinweis]** Task-Angabe „LiteLLM Config c6e1fdfd" nicht reproduzierbar; Ist-Hash der produktiven dream-litellm-Config (Host-Mount `local.yaml`, byte-identisch mit Container) ist `c65cd000fcfde…`. Kein Hinweis auf unautorisierte Mutation — nur Dokumentations-Drift.
3. **[P3 – Hinweis]** Direkte `state.db`-Abfrage wurde vom Owner während des Reviews blockiert; Session-Nachweis für `20260805_103731_0360bb` stattdessen über die Hermes-Session-DB (read-only `session_search`) erbracht (model `oauth/codex`, Antwort „PONG") — Beweis vollständig.

Keine P1/P2-Findings.

---

## FREIGABE-UMFANG (was dieses Verdikt NICHT freigibt)

Das Verdikt bestätigt DOD-09 (unabhängiges semantisches Review) für den exakten Commit `87e1296ca161b49f083fd707933be547c452b481` und damit die DOD-01..08/10-Statuskomponenten des Goals „close-buildroom-release-proof-gaps-and-preserve-model-catalog". Es **UNLOCKT NICHT**: `OPERATIONAL_PRODUCTION` (NOT_YET), `GENERAL_MANAGED_CUTOVER` (NOT_STARTED), `LITELLM_CLEANUP_DRAFT` (NOT_APPROVED — wartet auf Owner-Freigabe + Container-Restart), und der `OVERALL_GOAL` bleibt **TEILBESTANDEN** bis zur Owner-Bestätigung.

---

**GEPRÜFTER-TREE-UNVERÄNDERT:** `git status --porcelain` nach dem Schreiben dieses Verdikts zeigt ausschließlich die autorisierte Schreib-Aktion selbst (`?? evidence/goals/CONDUVERA-FIXTURE-001/reviewer-verdict-release-proof.md`, untracked); die Datei ist nicht getrackt (`git ls-files` → 0 Treffer). HEAD unverändert `87e1296ca161b49f083fd707933be547c452b481`.
