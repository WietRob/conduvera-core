# Reviewer-Verdikt — Semantisches Review (DOD-11)

Goal: close-core-adapter-seam-and-converge-canonical-ai-stack-architecture
Fixture: CONDUVERA-FIXTURE-001
Review-Typ: unabhängiges SEMANTISCHES Review (read-only, keine Mutation)
Review-HEAD (Working Tree): `791b50f` + uncommittete Änderungen an curaops/buildroom/fixture_runner.py, curaops/harness/gateway.py, curaops/harness/hermes_adapter.py, curaops/harness/registry.py (der tatsächlich ausgeführte Stand wurde reviewt)

---

REVIEWER-VERDIKT: APPROVE

---

## BEGRÜNDUNG

Semantische Verifikation aller fünf Prüfbereiche gegen den echten Code und die echten Artefakte — alle DOD-Behauptungen (01–07, 09, 12) sind im Code und in den Fixture-Artefakten belegt. Keine P1/P2-Findings. Zwei Advisory-Punkte (P3, dokumentarisch) — siehe FINDINGS.

### 1. Python-Call-Path (DOD-01/02) — VERIFIZIERT

**Adapter besitzt den vollständigen Lifecycle** (`curaops/harness/hermes_adapter.py`):
- Z.158–281 `start_session()`: erzeugt isoliertes HERMES_HOME (Z.225–226: `wt/hermes-home/profiles/fixture-live`), schreibt `config.yaml` mit `custom:litellm` + `workload/local` (Z.227–230, Template Z.487–501), spawnt `subprocess.Popen([hermes, "-z", prompt], start_new_session=True, stdin=DEVNULL)` (Z.237–245), erfasst PID/PGID/`create_time` via `os.getpgid` + `ps -o lstart=` (Z.246–255), gibt `SessionHandle` mit `trace_id` zurück (Z.257–268).
- Live-Flag sauber getrennt: Simulator-Modus (`live=false`, Z.190–222, schreibt nur Text-Artefakt, `pid=0`) vs. echter Spawn (`live=true`, Z.224ff.). Der Live-Run belegt den echten Zweig.
- Lifecycle-Methoden bedienen dieselbe Session über PID/PGID: `wait_for_completion` (Z.283–316), `status_session` (Z.318–353), `cancel_session` (SIGKILL eigene PGID, Z.355–389), `timeout_session` (SIGTERM→SIGKILL eigene PGID, Z.391–430), `collect_evidence` (Z.432–453).

**Runner ruft NUR `adapter.start_session()`** (`curaops/buildroom/fixture_runner.py`):
- Kein `subprocess`-Import im gesamten Modul (Z.22–37); einziger Spawn-Pfad ist der Adapter. `run()` ruft `start_session` (Z.162–172), danach ausschließlich Lifecycle-Folgeaufrufe am selben Adapter (`wait_for_completion` Z.216–218, `collect_evidence` Z.222). Trace wird korreliert und als `state/call-trace.json` geschrieben (Z.228–248).

**Trace-Korrelation über alle Artefakte — IDENTISCH**:
`goal_id=CONDUVERA-FIXTURE-001 → trace_id=TRACE-F12294E6B0 → task_id=TASK-33A4AB83 → attempt_id=ATT-569B98C4 → session_id=SES-B7BA56D2 → adapter_id=hermes → pid=1005751 → pgid=1005751 → route=workload/local → model_identity=openai/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf → evidence_event=fixture.run.completed`
konsistent in `fixtures/live/core-run/state/call-trace.json`, `core-run-evidence.json`, `evidence/TASK-33A4AB83/ATT-569B98C4-SES-B7BA56D2.json` (Events tragen dieselbe trace_id) und `goal-receipt.json`.

**Live-Evidence unabhängig gegen den Disk-Stand geprüft**:
- `core-run-evidence.json`: `response=CONDUVERA_FIXTURE_OK`, `response_exact=true`, `pid==pgid==1005751`, `process_group_isolation=true` ✓
- `response_sha256=c8a786ca...` stimmt mit `sha256sum` der tatsächlichen Datei `worktrees/SES-B7BA56D2/mxfix_3fc5b40f8c79.response.txt` exakt überein; Inhalt ist exakt `CONDUVERA_FIXTURE_OK\n` ✓
- `pid==pgid` beweist `start_new_session=True` (eigene Prozessgruppe) aus dem Adapter-Code ✓
- `config.yaml` unter dem adapter-generierten Pfad (`hermes-home/profiles/fixture-live`) entspricht exakt `_FIXTURE_CONFIG_TEMPLATE` (inkl. vom echten Hermes-Prozess beim Start ergänztem `_config_version: 33`) ✓
- `agent.log` derselben HERMES_HOME zeigt echten Hermes-CLI-Start („Plugin discovery complete: 55 found, 48 enabled") — kein Simulator-Artefakt ✓

### 2. Registry-Authority (DOD-03) — VERIFIZIERT

- `curaops/harness/gateway.py` Z.206–262: `HarnessGatewayRegistry` ist die SINGLE Authority; besitzt den Runtime-Loader als Komponente (`self.adapters = HarnessAdapterRegistry(...)`, Z.237–239) und delegiert `load_adapter` an sie (Z.253–262). Keine zweite unabhängige Registry.
- `curaops/harness/registry.py` Z.79–86: `HarnessAdapterRegistry` ist ausdrücklich als Komponente der Gateway-Authority dokumentiert, nicht als eigenständige zweite Registry. Fail-closed-Logik (CAPABILITY_UNAVAILABLE statt ImportError, Z.118–153) intakt.
- Test `tests/buildroom/test_core_internal_seam.py::test_dod03_single_registry_authority` (Z.163–179) belegt die Komponenten-Beziehung.

### 3. Ledger-/State-Authority (DOD-04) — VERIFIZIERT

- `fixture_runner.py::_load_ledger()` (Z.409–434): `schema=conduvera.ledger.v1`, `ledger_scope=test_fixture`, `bound_to=curaops.harness.gateway.HarnessGatewayRegistry` — Defaults in jeder Rückgabebranche (Datei vorhanden, Fehlerfall, Datei fehlt).
- Es existiert KEIN `state/run-ledger.json` — der Runner schreibt das Ledger nie (nur Lesen in `reconcile()`/`state_ledger()`). Das ist stärker als gefordert: kein geschriebener paralleler State, kein produktiver State-Writer. Test `test_dod04_ledger_test_fixture_scope` (Z.184–225) belegt die Defaults.

### 4. AI-Stack-Architekturdiagramm (DOD-07 + UI-Gate) — VERIFIZIERT

`docs/CONDUVERA_ARCHITECTURE_DIAGRAM.md` (Z.10–91) und maschinenlesbare Spiegelung `docs/architecture.mmd` (inhaltlich identisch, ASCII-normalisiert) enthalten vollständig:
- **Ebenen:** Control Plane (CORE, Z.17–25), Harness Plane (HARNESS, Z.27–36), Model Plane (MODEL/LiteLLM, Z.38–46), ODS Runtime (ODS/ai-stack, Z.48–58), Capabilities (O5, Z.53), Evidence/Telemetry/Secrets (EVID inkl. BWS E3, Z.60–67).
- **Aktuelle Browser-Ebene (IST):** UI1 Dashboard :3001 (Auth ≠ Open WebUI, kein Modellwechsel), UI2 Open WebUI :3000 (BLOCKED_AUTH_RECOVERY, Browser-E2E NOT_PROVEN), UI3 ODS-Hermes :9120 (healthy ≠ autorisierter Browserzugang), UI4 n8n :5678 (separates Login), UI5 OpenCode :3003 (Host-Systemd-Service) — Z.69–80.
- **Zukünftige Console-/Workspace-Ebene (ZIEL):** Z1 Conduvera Console, Z2 Conduvera Workspace mit `NOT_DECIDED` und „ersetzt Open WebUI NOCH NICHT" — Z.82–90.
- **Invarianten** (Z.93–108): Codex CLI ≠ Codex OAuth (H3→M3 getrennt, CLIProxyAPI O3 nur Broker), `ai-stack model use` einzige Moduswechsel-Schnittstelle (O1 explizit, Dashboard ohne Modellwechsel-Pfeil), `workload/local` nur text-Modus (M2 annotiert), BWS einzige Secrets-Authority (E3), Statuswahrheitstabelle Z.110–121 (NOT_DECIDED/BLOCKED_AUTH_RECOVERY/NOT_PROVEN korrekt).

### 5. Statuswahrheit im Receipt — VERIFIZIERT

`evidence/goals/CONDUVERA-FIXTURE-001/goal-receipt.json` status_components (Z.6–15):
- `CORE_INTERNAL_ADAPTER_MANAGED_RUN: PASS` — gerechtfertigt: der Adapter startet die Session wirklich selbst (Popen in hermes_adapter.py Z.237–245, belegt durch Disk-Artefakte: adapter-generierte config.yaml, pid==pgid, echter agent.log, exakte Antwort).
- `REAL_BUILDROOM_EXECUTION_PATH: NOT_PROVEN` — wahrheitsgemäß: kein reproduzierbares Buildroom-Eintrittsskript im Repo; die Execution lief über Test/adhoc-Pfad.
- `BUILDROOM_ABSORPTION: NOT_STARTED`, `LIVE_RUNTIME_CUTOVER: NOT_STARTED` — korrekt.
- `GESAMT: TEILBESTANDEN` — konsistent mit `DOD-11: PENDING` und `DOD-12`-Note „OPERATIONAL erst nach DOD-01..11"; KEIN OPERATIONAL beansprucht. `correction_note` (Z.176) dokumentiert die vorherige NOT_PROVEN-Korrektur und den nun belegten Adapter-Start — konsistent.

---

## FINDINGS

Keine P1/P2. Zwei Advisory-Punkte (P3, nicht blockierend, dokumentarisch):

1. **Call-Path-Beschreibung vereinfacht (P3):** `core-run-evidence.json` Z.4 und `goal-receipt.json` Z.25 beschreiben den Pfad als „FixtureRunner → HarnessGatewayRegistry → HermesAdapter.start_session()". Tatsächlich instanziiert `fixture_runner.py` Z.85–88 `HarnessAdapterRegistry` direkt (die Komponente des Gateway, nicht das Gateway-Objekt). Die Single-Authority ist dadurch NICHT verletzt (eine Registry-Klasse), aber die wörtliche Pfadbeschreibung ist unpräzise. Empfehlung: künftig „FixtureRunner → HarnessAdapterRegistry (Komponente von HarnessGatewayRegistry) → HermesAdapter.start_session()" formulieren.

2. **Kein reproduzierbares Live-Run-Skript (P3):** Der Live-Run `core-run-001` ist über einen ad-hoc/Test-Pfad entstanden; ein `fixtures/live/core-run/run_core_fixture.py` o.ä. würde `REAL_BUILDROOM_EXECUTION_PATH` beweisbar machen. Das Receipt weist dafür korrekt NOT_PROVEN aus — kein aktueller Wahrheitsfehler, sondern ein Ausblick für die nächste Slice.

---

## CALL-PATH-VERIFIKATION

Verifizierter realer Pfad (gegen Code + Disk-Artefakte):

```
FixtureRunner.run()                                  fixture_runner.py Z.102–270
  └─ HarnessAdapterRegistry.load_adapter("hermes")   fixture_runner.py Z.84–88 (Komponente von HarnessGatewayRegistry, gateway.py Z.237–262)
  └─ HermesAdapter.start_session(live=true)          hermes_adapter.py Z.158–281
       ├─ HERMES_HOME=worktrees/SES-B7BA56D2/hermes-home/profiles/fixture-live  (belegt: config.yaml existiert, Z.225–230)
       ├─ subprocess.Popen(["hermes","-z",prompt], start_new_session=True)      (Z.237–245; belegt: pid==pgid==1005751)
       ├─ PID/PGID/create_time erfasst → SessionHandle(trace_id=TRACE-F12294E6B0) (Z.246–268)
       └─ Hermes CLI → LiteLLM :4000 (custom:litellm) → workload/local → Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
            → Antwort CONDUVERA_FIXTURE_OK (exakt, SHA-256 c8a786ca… verifiziert)
  └─ wait_for_completion + collect_evidence (Z.216–222)
  └─ Trace-Kette goal→trace→task→attempt→session→adapter→pid→pgid→route→model_identity→evidence_event
       → state/call-trace.json (Z.228–248) + MXOS-EVIDENCE-1.0.0 Event-Envelope
```

Querverbindung der Korrelations-IDs ist über vier Artefakte (call-trace.json, core-run-evidence.json, MXOS-Evidence, goal-receipt.json) fehlerfrei. Registry-Authority, Ledger-Scope, Architekturdiagramm (inkl. UI-Ebenen und Invarianten) und Statuswahrheit sind wie oben belegt.
