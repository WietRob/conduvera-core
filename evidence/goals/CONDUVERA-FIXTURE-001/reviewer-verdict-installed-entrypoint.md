# Reviewer-Verdikt: prove-and-wire-the-installed-buildroom-operator-entrypoint (DOD-11)

**REVIEWER-VERDIKT: BESTANDEN**

**COMMIT-SHA-GEPRÜFT:** `899dc88e733ce0aacab7e3a7b952e9f9562def1c` (Branch `task/goal-contract-fixture`, HEAD == geprüfter SHA, `git status --porcelain` leer vor Review; keine Drift während des Reviews; kein Merge — single parent `505e0c4a1f378f884f9f9a39f5394938ef3ae7f4`)

**Reviewer:** unabhängiger semantischer Reviewer (DOD-11), frische Session, read-only (einzige Schreib-Aktion: dieses Dokument + erlaubte Runtime-Trace-Läufe gemäß Task)

---

## BEGRÜNDUNG (pro Prüfpunkt, mit Referenzen)

### 1. IST-CALLGRAPH (DOD-01) — PASS
- `evidence/buildroom-callgraph-v1.json`: exakt 8 Caller inventarisiert (Operator manuell, Autopilot-Wrapper, freeze-watchdog, 4 Hermes-Cron, auto-build DISABLED), `running_buildroom_processes: []`, genau 1 aktiver Operator-Einstieg.
- Live-Verifikation: `~/.hermes/scripts/buildroom_loop.py` sha256 `3bc2ff6b…` == Repo-`legacy/buildroom/source/buildroom_loop.py` (3bc2ff6b) == Callgraph-Eintrag. `pgrep` (präzise Muster): 0 laufende Buildroom-Prozesse. `crontab -l`: freeze-watchdog `*/2` aktiv, Hash `7f2a763b…` == Callgraph. `hermes cron list`: buildroom-qa-verify / -daily-research / -weekly-dreamer / -daily-summary = active, buildroom-auto-build = **paused** (DISABLED); alle 4 Cron-Skript-Hashes (daa8215e, 3a9bb026, b7ce2ee1, 2b01f16d) == Callgraph. Dokumentierte Nicht-Aufrufer bestätigt.

### 2. INSTALLIERTER EINSTIEG (DOD-02) — PASS
- `curaops/buildroom/operator_entry.py` (NEU, 162 Zeilen): einziger installierter Operator-Einstieg; ruft `BuildroomExecutionDispatcher.dispatch()` genau **einmal** pro Invokation (Zeilen 103 bzw. 125, sich gegenseitig ausschließende Branches).
- `pyproject.toml:50` `[project.scripts] buildroom-operator = "curaops.buildroom.operator_entry:main"`; `~/.local/bin/buildroom-operator` existiert als Symlink → `.venv/bin/buildroom-operator` (Console-Script ruft `operator_entry.main`).
- Installierter Wrapper `~/.hermes/scripts/buildroom_autopilot_runner.sh` (Hash `16364b20…`, gewirete Version): Tick-Zeile 54 `$OPERATOR_ENTRY --project "$PROJECT" --live`; **kein** direkter `buildroom_loop.py`-Aufruf mehr (Zeile 26 definiert `LOOP` nur noch ungenutzt); Rollback-Hinweis Zeile 20.
- Backup `.bak-20260804-wired` existiert, sha256 `ec8db221…` == Repo-Original `legacy/buildroom/wrappers/buildroom_autopilot_runner.sh` (ec8db221).

### 3. LEGACY REAL (DOD-03) — PASS
- `dispatcher.py:501-539` `_run_legacy_entrypoint(live=…)`: Default isoliert (eigenes `tempfile.mkdtemp`-HOME, eigener State, kein Live-Drift); `live=True` = produktiver Tick via `subprocess.run([sys.executable, entry, "--project", "peekxd"])` gegen echten `~/.hermes`-State. Kein Marker: isolierter Lauf schreibt ausschließlich in tmp-Home.
- Frisch ausgeführt: `~/.local/bin/buildroom-operator --project peekxd` → `execution_path: legacy`, `status: legacy_completed`, `exit_code: 0`, `entrypoint: ~/.hermes/scripts/buildroom_loop.py` (echter Subprozess), `isolated_home: /tmp/buildroom-legacy-iso-*`, `state_phase: STOPPED_AFTER_CANARY_CHECK`, EXIT=0. `test_evidenz_b_operator_entry_legacy_real` (test_dispatcher.py:551) läuft grün.

### 4. CANARY 3/3 VIA INSTALLIERTEM EINSTIEG (DOD-04) — PASS
- `fixtures/live/installed-entry/evidence/`: genau 3 Dateien — ATT-BE8A3555 (t_c0a1), ATT-0BEECCD8 (t_0c0a1e), ATT-A5B4D702 (t_0c0a1f); alle `schema: MXOS-EVIDENCE-1.0.0`, `status: completed`, `exitcode: 0`, `ok: true`, `model_binding.model: openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, `api_base: http://llama-server:8080/v1`, `route: local/default`, `execution_mode: LIVE`, eigene Sessions/PIDs.
- `state/call-trace.json`: t_0c0a1f, TRACE-AC0044ECAD, `model_identity: openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, `evidence_event: buildroom.run.completed`.
- 0 verbleibende Leases: `~/.hermes/buildroom/dispatcher/leases/` enthält nur persistente 0-Byte-`.reclaim`-Locks (korrekt, siehe Prüfpunkt 5), keine `.lease.json`. 0 laufende Prozesse.

### 5. KEIN PARALLELER START (DOD-05) — PASS
- `dispatcher.py:344` `os.open(…, O_CREAT|O_EXCL|O_WRONLY)` = atomare Lease; Reclaim-Pfad durch persistenten flock-Reclaim-Lock serialisiert (Zeilen 289-298); **Reclaim-Lock-Datei wird bewusst nie gelöscht** (Zeilen 371-375, dokumentiert den Multiprocess-Race — der im Review-Skill bekannte flock/unlink-Trap ist vermieden).
- `test_evidenz_d_canary_same_attempt_no_parallel` (test_dispatcher.py:608): zweiter Acquire derselben Attempt-ID blockt. `test_arbeit5_atomic_lease_multiprocess` (Zeile 389): 4 Worker mit Event-gehaltenen Leases → genau 1 True / 3 False.

### 6. LEASE-FINGERPRINT (DOD-06) — PASS
- `dispatcher.py:90-113` `_process_fingerprint()`: PID + Boot-ID (`/proc/sys/kernel/random/boot_id`) + Create-Time-Ticks (`/proc/<pid>/stat` Feld 22); Lease enthält alle drei (Zeilen 350-360).
- PID-Reuse-Schutz (Zeilen 305-338): gleiche PID + abweichende Create-Time oder Boot-ID → stale; Reclaim nur durch denselben `task_id` (Zeile 339); fremde Leases werden weder beendet noch freigegeben (`_release_attempt_lease` Zeile 384: nur eigener PID).
- `test_evidenz_f_*` 3 Tests (Zeilen 478/497/518): Fingerprint in Lease, PID-Reuse mit lebender PID 1 + falscher Create-Time → stale/reclaimbar, Fremd-Lease unangetastet.

### 7. PACKAGE (DOD-07) — PASS
- `pyproject.toml:60-61` `[tool.setuptools.package-data] curaops = ["contracts/*.yaml", "contracts/*.json", "harness/contracts/*.yaml"]`.
- `curaops/contracts/buildroom-execution-dispatcher.yaml` byte-identisch zu `contracts/…` (cmp OK); `curaops/harness/contracts/harness-registry.yaml` byte-identisch zu `fixtures/harness-registry.yaml` (cmp OK).
- Frisch ausgeführt: `uv build` → `dist/matrix_os-0.1.0-py3-none-any.whl`; Wheel enthält `curaops/contracts/buildroom-execution-dispatcher.yaml` UND `curaops/harness/contracts/harness-registry.yaml` (zipfile-Verifikation). `dist/` ist in `.gitignore` (Zeile 9), nichts committet.
- Frische venv `/tmp/review-fresh-venv` (außerhalb des Repos): `DispatcherConfig.load()` aus `/tmp` → `execution_path: legacy` (Package-Resource, kein Repo-Fallback). Ungültige Config (`execution_path: BOGUS`) → `CONFIG_INVALID` ohne Spawn. `test_evidenz_e_config_in_wheel` + `test_evidenz_e_package_data_mirrors_canonical` + `test_evidenz_b_operator_entry_binary_exists`: 3 passed frisch.

### 8. ROLLBACK (DOD-08) — PASS
- `.bak-20260804-wired` sha256 `ec8db221…` == Repo-Original-Wrapper (ec8db221). `/tmp/autopilot-before.sha256` (Pre-Wiring-Snapshot, 07:51) listet den installierten Wrapper als ec8db221 — die `sha256sum -c`-Meldung „GESCHEITERT" ist **erwartet**: installiert ist jetzt die gewirete Version (16364b20), das .bak repräsentiert byte-identisch den Originalzustand. Rollback-Pfad dokumentiert (Wrapper Zeile 20: `cp .bak-20260804-wired` zurück).

### 9. AI-STACK (DOD-09) — PASS
- GPU text: NVIDIA RTX 5090 Laptop (22106 MiB belegt). LiteLLM: Port 4000 lauschend, PID **3568** (`/usr/bin/python3.13 /usr/bin/litellm --config /tmp/config.yaml --port 4000`, seit Jul 31). Route-Hash `~/.local/share/ai-stack/routes/local-mode.yaml` = `4e11969e…` == Baseline. llama-server PID 3645 (Qwen3.6-35B-A3B-UD-Q4_K_M.gguf, Port 8080) bestätigt die live Modell-Identität der Canaries. Commit-Diff enthält keine AI-Stack-/Secret-/Service-Dateien → keine Mutation.

### 10. KONSISTENZ (DOD-10) — PASS
- Katalog `evidence/goals/CONDUVERA-FIXTURE-001/system-capabilities.yaml`:581-631 — CORE-002E `LIVE_PROVEN_AND_INSTALLED_ENTRYPOINT_WIRED` (missing_gate: OPERATIONAL_PRODUCTION, kein Cutover), INSTALLED-001 `LIVE_PROVEN` (missing_gate: General Managed Cutover NOT_STARTED).
- Diagramm: B5 in `docs/architecture.mmd` UND `docs/CONDUVERA_ARCHITECTURE_DIAGRAM.md` = „Operator Entry (buildroom-operator, installiert)".
- Brain-Matrix `Buildroom_Migration_Matrix.md` (Brain-Vault, separates Git): committet in `209e549` (2026-08-05), Block „DISPATCHER … CORE-002E = LIVE_PROVEN_AND_INSTALLED_ENTRYPOINT_WIRED (2026-08-05) … INSTALLED-001 = LIVE_PROVEN … .bak-20260804-wired ec8db221" — identisch zum Repo-Katalog. Callgraph zeigt denselben Pfad (B5 → dispatcher → legacy|managed).
- `goal-receipt.json`: `installed_dod_matrix.DOD-11.result = PENDING` (vor diesem Verdikt), status_components konsistent zur Commit-Message (OPERATIONAL_PRODUCTION NOT_YET, RELEASE_CANDIDATE YES, FULL_SYSTEM TEILBESTANDEN).

### 11. TESTS (DOD-11) — PASS
- Frisch ausgeführt auf exakt 899dc88e: `CONDUVERA_BRAIN_ROOT=… uv run python -m pytest -q --no-header -p no:cacheprovider` → **408 passed, 0 failed** (in 1.59s; committed .out: 408 passed — Zahl exakt).
- Frisch: `PYTHONPATH=legacy/buildroom/source uv run python -m pytest … test_buildroom_cycle49_preflight.py test_buildroom_task_binding_cycle49.py` → **30 passed, 0 failed** (0.03s, == committed).
- sha256-Cross-Check: alle 5 `.out` (regression_full_installed acc3ffbf, dispatcher_tests_installed 2c7c8a68, legacy_characterization_installed 4f79869c, hardening_installed 75dd5011, allowlist_installed c2cba0e5) matchen exakt `evidence/checks/_installed.json` — keine nachträgliche Manipulation.

### 12. INSTALLIERTER RUNTIME-TRACE — PASS
- `~/.local/bin/buildroom-operator --project peekxd` (legacy, isoliert): exit 0, `legacy_completed`, echter buildroom_loop.py-Subprozess.
- `CONDUVERA_BUILDROOM_DISPATCHER=fixtures/buildroom/execution-dispatcher-canary.yaml ~/.local/bin/buildroom-operator --canary t_c0a1`: `managed_canary`, `completed`, ATT-396463A6, session mxfix_7062764a9c3d, `route=local/default`, `model=openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`, exit 0. Frische Evidence `~/.hermes/buildroom/dispatcher/evidence/mxos-evidence-ATT-396463A6.json` (MXOS-EVIDENCE-1.0.0, completed, ok:true) — **nicht committet** (`git ls-files`: 0 Treffer; `git status --porcelain` danach leer).

### 13. KEIN SCOPE-CREEP — PASS
- Commit: 26 Dateien (+963/−40), single parent, kein Merge. `git diff 505e0c4a..HEAD -- legacy/` = **leer** (Legacy-Inhalt unverändert). Keine ODS-/LiteLLM-/GPU-/BWS-/ComfyUI-/RAG-/Voice-/n8n-/Langfuse-Dateien; keine neue Registry/Evidence-Hülle (nutzt bestehendes `curaops.harness.registry` + `curaops.evidence.contract`); kein Runtime-Cutover (missing_gates dokumentiert); kein Force-Push lokal nachweisbar (linearer Einzel-Eltern-Commit). Einzige neue Installed-Evidence: die 3 mxos-evidence + call-trace, allowlist-konform (`evidence/evidence-allowlist.yaml` +3 Zeilen).

### 14. COMMIT-IDENTITÄT — PASS
- `git rev-parse HEAD` == `899dc88e733ce0aacab7e3a7b952e9f9562def1c` vor und nach dem Review; `git merge-base --is-ancestor` OK; `git diff --name-status <sha> HEAD` leer (keine Drift). `git status --porcelain` leer vor dem Review und nach dem Canary-Trace; nach diesem Verdikt nur die neue untracked Verdict-Datei (erwartet, nicht committet, nicht tracked).

---

## FINDINGS

Keine P1/P2. P3-Hinweise (approvable, kein Blocker):

1. **P3 – Callgraph beschreibt Autopilot im Pre-Wiring-Zustand**: `evidence/buildroom-callgraph-v1.json` (generated_at 05:48 UTC) dokumentiert den Autopilot-Caller mit `runtime_path: python3 $LOOP --project peekxd` und Hash ec8db221 — das ist der IST-Snapshot **vor** der Wiring (Wiring-Installation 07:55, Symlink mtime 07:55, .bak 07:51). Der installierte Wrapper hat heute Hash 16364b20 und ruft `$OPERATOR_ENTRY --live`. Keine Falschaussage (Snapshot korrekt datiert und als IST-Aufnahme markiert), aber die Notes sind ohne Zeitkontext missverständlich.
2. **P3 – `handle.model_identity` in den 3 committeten mxos-evidence-Dateien ist leer** (`""`), während `model_binding.model` (Qwen…) und `call-trace.json`/`final_status` die Modell-Identität korrekt führen. Kosmetisch; Quelle der Wahrheit (`model_binding` aus der Route) ist korrekt und live verifiziert.
3. **P3 – Brain-Vault hat weitere uncommittete Dateien** (Agent_Fleet.md, Current_Status.md, Dev_System.md, Profile_Routing.md, Capability_Strengthening_Design.md) — fremde parallele Arbeit, nicht Teil dieses Goals; die für DOD-10 relevante `Buildroom_Migration_Matrix.md` ist committet (209e549).
4. **P3 – `/tmp/autopilot-before.sha256` „GESCHEITERT"**: erwartetes Ergebnis der aktiven Wiring (siehe Prüfpunkt 8), kein Fehler — der Pre-Wiring-Eintrag ec8db221 == .bak == Repo-Original beweist die Rollback-Byte-Identität.

---

## FREIGABE-UMFANG

Dieses BESTANDEN bestätigt: Ist-Callgraph, installierter Einstieg (genau einmal Dispatcher), Legacy real (isoliert + --live), Canary 3/3 via installiertem Einstieg, atomare Lease + Fingerprint, Package-Nachweis, Rollback-Pfad, AI-Stack-Invarianz, Katalog/Diagramm/Matrix/Callgraph-Konsistenz, 408/0 + 30/0 frisch, installierter Runtime-Trace, kein Scope-Creep, Commit-Identität.

**NICHT freigegeben** (bleiben NOT_YET/NOT_STARTED): OPERATIONAL_PRODUCTION (kein Runtime-Cutover), General Managed Cutover (NOT_STARTED), Buildroom-Absorption (PARTIAL), vollständige System-Freigabe (FULL_SYSTEM TEILBESTANDEN).

---

**GEPRÜFTER-TREE-UNVERÄNDERT:** ja (nur untracked Verdict-Datei nach Review; `git ls-files | grep -c reviewer-verdict-installed-entrypoint` → 0)
