# Unabhängiges semantisches Final-Review (DOD-H14) — Härtungs-Goal

- Goal: `harden-core-adapter-seam-before-any-buildroom-port` (CONDUVERA-FIXTURE-001)
- Reviewer: frischer unabhängiger semantischer Reviewer (kein Implementierungskontext)
- Review-Objekt: EXAKT Commit `c6ffc487659050d59edeba2a1fc66f33a7082b2c` auf Branch `task/goal-contract-fixture`
- Vorgänger-Review `deleg_24dbe73c` (reviewer-verdict-semantic.md) gilt NICHT für diesen Commit
  (wurde vor Zombie-/Wait-Fix und finalem Run-Skript erstellt; siehe correction_note im goal-receipt.json)
- Review-Modus: read-only; einzige Schreib-Aktion ist dieses Verdikt-Dokument

---

REVIEWER-VERDIKT: APPROVE

COMMIT-SHA-GEPRÜFT: c6ffc487659050d59edeba2a1fc66f33a7082b2c

---

## BEGRÜNDUNG (semantisch, pro Prüfpunkt)

Commit-Identität: `git rev-parse HEAD` = `c6ffc487659050d59edeba2a1fc66f33a7082b2c` (exakter
Full-SHA, kein Kurz-SHA, kein Worktree-Drift), Branch `task/goal-contract-fixture`. Der
Commit-Diff (git show --stat) entspricht der Commit-Message: 5 Produktdateien, 2 Doku-Dateien,
Tests, Evidence-Artefakte, 39 Runtime-Artefakt-Deletions. Kein Buildroom-Port, kein
`run_buildroom_fixture.py`, kein Cutover im Diff.

**1. ADAPTERVERTRAG (DOD-01/02) — PASS**
- `curaops/harness/gateway.py:331-476`: `HarnessGatewayService` ist der einzige öffentliche
  Entry Point mit `load_adapter` (Z.375), `start_session` (Z.389), `status_session` (Z.415),
  `cancel_session` (Z.425), `timeout_session` (Z.435), `await_completion` (Z.445),
  `collect_evidence` (Z.463) und `execution_mode`-Property (Z.474-476).
- `curaops/buildroom/fixture_runner.py`: `run()` (Z.110-291) kennt NUR `self._gateway`
  (Z.169, 204, 222, 295, 311) — kein konkreter Adapter-Import, kein `getattr` im produktiven
  Pfad, kein privates Feld (`_task_timeout_s`, `_sessions`, `_handle`), kein broad-except.
  `_TestOnlyGateway` (Z.543-591) ist explizit „TEST-ONLY ... never used in the productive
  path" markiert und wird nur bei Test-Injection (Z.96-99) verwendet. Assertion-Tests:
  `tests/buildroom/test_hardening.py::test_dod01_*` (Z.42-60) und `test_dod02_*` (Z.62-76).
- `curaops/harness/hermes_adapter.py`: `await_completion` als Vertragsmethode (Z.429-509,
  auch im Protocol `registry.py:103-112`); `_fingerprint_ok` vor jedem Signal; `_build_hermes_env`
  (Z.107-125) mit Allowlist. Nur `HermesAdapter.start_session()` spawnt Hermes (Z.291-299).

**2. FAIL-CLOSED (DOD-03) — PASS**
- Strukturierte Codes in `curaops/harness/registry.py:70-77` (AdapterErrorCode) und
  `:36-43` (HarnessCapabilityUnavailableError): ADAPTER_PROTOCOL_ERROR (gateway.py Z.412/422/
  432/442/470), MODEL_IDENTITY_UNVERIFIED (fixture_runner.py Z.232), SESSION_WAIT_FAILED
  (gateway.py Z.460, hermes_adapter.py Z.507), CAPABILITY_UNAVAILABLE (gateway.py Z.384/404,
  registry.py Z.216-238), PROCESS_FINGERPRINT_MISMATCH (hermes_adapter.py Z.461/539/586/633).
- Kein stilles Fehler-Masking: alle `except Exception`-Pfade enden in strukturierten
  AdapterResult/Codes oder gewollten Endzuständen (killpg auf bereits beendete PGID).
  (Anmerkung P3: mehrzeilige `except Exception:\n pass` existieren wörtlich, siehe FINDINGS.)

**3. REGISTRY (DOD-03) — PASS**
- `registry.py:134-167`: `resolve_registry_path` = explicit → `CONDUVERA_HARNESS_REGISTRY` →
  Package-Resource; kein `Path.cwd()`-Fallback (am Ende `FileNotFoundError`, fail-closed).
  Negativ-Tests: `test_hardening.py::test_dod03_no_cwd_fallback_when_nothing_configured`
  (Z.103-110), `test_dod03_runner_without_registry_fails_closed` (Z.113-122).
- `HarnessAdapterRegistry` (registry.py:170-239) ist als INTERN dokumentiert; grep über
  `curaops/` zeigt keine direkte Nutzung außerhalb gateway.py/registry.py (fixture_runner.py
  referenziert sie nur im Docstring, Z.63). Fixture-Registry `fixtures/harness-registry.yaml`:
  hermes enabled; codex_cli/opencode_cli disabled_by_owner (fail-closed).

**4. SIMULATION/LIVE (DOD-04) — PASS**
- `registry.py:46-67`: `ExecutionMode.SIMULATION|LIVE`; `require()` wirft bei leer/unbekannt
  (kein stiller Default); Test `test_dod04_execution_mode_never_silent_default` (Z.128-136).
- Gateway-Default LIVE (gateway.py:349; Test Z.151-153); SIMULATION spawnt keinen Prozess
  (hermes_adapter.py Z.243-277) und erfüllt nie Live-Gates. Mode in Events (fixture_runner.py
  Z.166/276), Trace (Z.255), Receipt (FixtureRunResult.execution_mode Z.55). Produktiver Pfad
  `fixtures/live/run_core_fixture.py` erzwingt `ExecutionMode.LIVE`.

**5. PROZESSSICHERHEIT (DOD-05/06/07) — PASS**
- `_fingerprint_ok` (PID + `ps -o lstart=`-create_time) vor await_completion (Z.457),
  status_session (Z.535), cancel_session (Z.582), timeout_session (Z.629); Mismatch →
  PROCESS_FINGERPRINT_MISMATCH, kein Signal (Test `test_dod05_fingerprint_mismatch_no_signal`,
  Z.159-189, inkl. „Process must still be alive").
- Timeout: SIGTERM → 3s Grace → SIGKILL nur wenn `_pgid_members` nicht leer (Z.636-649);
  `pgid_remaining` im Result (Z.659). Zombie-/Wait-Fix: waitpid(WNOHANG)-Reap vor
  Liveness-Check (Z.356-371, 467-495).
- `fixtures/live/run5/live-5x-evidence.json`: verdict „PASS 5/5", alle responses exakt
  `CONDUVERA_FIXTURE_OK`, `pgid_remaining: 0` überall, `zombies: []`, `orphans: []`,
  `pgid_all_empty: true`, `foreign_process_changed: false`. Verifiziert durch
  `fixtures/live/verify_5x_live.py`.

**6. ENV-ALLOWLIST (DOD-08) — PASS**
- `_ENV_ALLOWLIST` (hermes_adapter.py Z.88-104) und `_build_hermes_env` (Z.107-125): nur
  PATH/HOME/HERMES_*/LITELLM_API_KEY/Locale + neutrale Runtime-Felder (USER/LOGNAME/SHELL/TERM);
  keine Secret-Kandidaten. Test `test_dod08_env_allowlist_drops_foreign_secrets`
  (test_hardening.py Z.195-205): AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN, SESSION_COOKIE werden
  verworfen, LITELLM_API_KEY redacted referenziert.

**7. PORTABILITÄT (DOD-09/10) — PASS**
- `tests/test_ui_access_plane.py:19-22, 87-90`: `CONDUVERA_BRAIN_ROOT` aus Env, Default
  `/nonexistent/...`, `pytest.skip` wenn ungesetzt; keine `/home/roberto`-Hardcodes.
- `fixtures/ods/route-manifest.fixture.yaml`: deterministisch (`fixture-model-local/default`),
  kein Qwen, kein `/home/`; Test `test_dod10_*` (Z.211-230). Live-Snapshot
  `fixtures/live/core-run/route-snapshot/route-manifest.snapshot.yaml`: Qwen-Identität,
  `live_manifest_sha256`, `active_mode: text`, `generated_at`.

**8. EVIDENCE-HYGIENE (DOD-11) — PASS (mit P3-Advisory, siehe FINDINGS)**
- c6ffc48-Diff: KEINE state.db, KEINE HERMES_HOME-Verzeichnisse, KEINE Caches, KEINE
  request_dumps, KEINE Secrets hinzugefügt; 39 Runtime-Artefakte (state.db, hermes-home/
  profiles/*, request_dump_*.json, stderr.txt, mxfix_*.response.txt, auth.lock, SOUL.md,
  tool_discovery_cache.json) wurden ENTFERNT. Neu hinzugefügt nur Allowlist: call-trace.json,
  Evidence-JSON, Route-Snapshot, live-5x-evidence.json, Receipt, Review-Verdikte, Tests, Doku.
- `.gitignore` (Z.60-79) ignoriert hermes-home/**, state.db, auth.lock, cache/,
  .skills_prompt_snapshot.json, SOUL/MEMORY/USER.md, stderr.txt, *.response.txt, worktrees/,
  *.db. Lücke: nacktes `response.txt` (ohne Präfix) wird nicht gematcht → siehe FINDINGS.

**9. DIAGRAMM (DOD-12) — PASS**
- `docs/CONDUVERA_ARCHITECTURE_DIAGRAM.md` + `docs/architecture.mmd`: Codex CLI (H3) →
  `~/.codex` eigener Auth-Store (C2) → direkter Backend-Pfad (C3), getrennt vom
  Hermes/OpenCode-Pfad → LiteLLM `oauth/codex-*` → CLIProxyAPI als geteilter Broker (M3);
  KEIN Ausdruck „native Codex-CLI-Route (OAuth)" (Diagramm-MD Z.105 verneint ihn explizit).
  Capability-Fluss: Core/Harness → Capability-Adapter → ComfyUI/RAG/Voice/n8n UND Capability →
  MXOS-EVIDENCE (Z.117). Workspace `NOT_DECIDED` ohne Festbindung (Z.92/115/122). .mmd
  konsistent gespiegelt (Z.20/31/37-44).

**10. STATUSWAHRHEIT — PASS**
- `evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json` Z.6-16: CORE_INTERNAL_MANAGED_HERMES_SLICE
  = LIVE_PROVEN_CANDIDATE, _OPERATIONAL = NOT_YET, FINAL_COMMIT_SEMANTIC_REVIEW = NOT_PROVEN
  (bis zu diesem Verdikt), REAL_BUILDROOM_EXECUTION_PATH = NOT_PROVEN, BUILDROOM_ABSORPTION =
  NOT_STARTED, LIVE_RUNTIME_CUTOVER = NOT_STARTED, CORE_ADAPTER_SEAM = RELEASE_CANDIDATE_LIVE_PROVEN,
  OPERATIONAL_PRODUCTION = NOT_YET, FULL_SYSTEM = TEILBESTANDEN. DOD-H14 = PENDING (Z.248-251);
  correction_note (Z.181) deklariert korrekt, dass das alte APPROVE nicht für diesen Commit gilt.
- `fixtures/live/core-run/state/call-trace.json`: `execution_mode: LIVE`, Kette
  goal→task→attempt→session→adapter→pid→pgid→route→model→evidence_event korreliert mit
  `evidence/goals/.../ATT-86CA8923-SES-101E8A39.json`.

Test-Evidence: `evidence/checks/regression_full_harden.out` = 266 passed, 1 skipped;
`evidence/checks/hardening_tests.out` = 14 passed (exitcode 0 in goal-receipt Z.264-283).
Tests wurden statisch geprüft (read-only; nicht neu ausgeführt).

---

## FINDINGS

1. **[P3 — Evidence-Hygiene, nicht blockierend]** 14 Runtime-Artefakte `response.txt`
   (`fixtures/live/live-run-001..007/response.txt`, `run1..run7/response.txt`) liegen im
   Commit-Tree (seit 39c308e, NICHT Teil des c6ffc48-Diffs). Inhalt: alte Fixture-Responses
   (z. B. „HTTP 400: No connected db." oder leer) — KEINE Secrets. Ursache: `.gitignore`
   matcht nur `fixtures/live/**/*.response.txt` (Z.75), nicht nacktes `response.txt`.
   Empfehlung (nächster Hygiene-Commit, nicht Blocker für c6ffc48): Muster
   `fixtures/live/**/response.txt` ergänzen und die 14 Dateien aus dem Tree entfernen —
   dann ist die Allowlist-Behauptung auch tree-weit exakt.
2. **[P3 — Wörtliche Commit-Behauptung, nicht blockierend]** Mehrzeilige
   `except Exception:\n pass` existieren in `registry.py:163-164` (Package-Resource-Fallback,
   endet in FileNotFoundError = fail-closed), `fixture_runner.py:417-418` (führt zu leerer
   Identity → in LIVE MODEL_IDENTITY_UNVERIFIED = fail-closed) und `hermes_adapter.py:308/405/426`
   (create_time="" bzw. False/[] → Fingerprint/Kill-Entscheidung fail-closed). Semantik ist
   durchgehend fail-closed, KEIN stilles Verschlucken mit Erfolgsvortäuschung; die wörtliche
   Aussage „keine except Exception: pass" in der Commit-Message ist jedoch nicht exakt.
   Empfehlung: Behauptung in der Commit-Message präzisieren („kein stilles Fehler-Masking").
3. **[Beobachtung, kein Finding]** `fixtures/live/run5/run-0..4/`-Evidence + `verify_5x_live.py`
   belegen die 5 Live-Läufe konsistent. `uv.lock` ist untracked im Worktree (nicht Teil des
   Commits; DOD-H15 „worktree clean" bleibt PENDING bis zum Abschluss des Goals).

---

## Geltung

Dieses APPROVE gilt NUR für Commit `c6ffc487659050d59edeba2a1fc66f33a7082b2c`. Damit wird
FINAL_COMMIT_SEMANTIC_REVIEW von NOT_PROVEN auf APPROVED gesetzt (Receipt-Aktualisierung durch
den Orchestrator). CORE_INTERNAL_MANAGED_HERMES_SLICE_OPERATIONAL bleibt NOT_YET, bis
REAL_BUILDROOM_EXECUTION_PATH/BUILDROOM_ABSORPTION/LIVE_RUNTIME_CUTOVER eigenständig bewiesen
sind. Kein OPERATIONAL-Status aus diesem Review ableiten.
