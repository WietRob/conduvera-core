# Conduvera Gesamtarchitektur — IST HEUTE / ZIELBILD (Rebaseline-Audit 2026-08-07)

Status-Marker: [LIVE] LIVE_PROVEN · [RC] RELEASE_CANDIDATE · [PART] PARTIAL
· [SVC] SERVICE_HEALTHY_NOT_E2E · [DESIGN] DESIGNED_ONLY · [BLOCK] BLOCKED
· [SCAF] SCAFFOLD_ONLY

## IST HEUTE (bewiesen durch Audit A1-A5, Repo-Head e5b7e9b/2d6641e)

```text
                         [LIVE] Roberto_Brain (Knowledge/Context-Plane)
                           |  brain doctor OK, 2310 docs; REPO_TRUTH via
                           |  99_Sources_READONLY (conduvera-harness Symlink)
                           v
   [LIVE] ODS / ai-stack  <--- LiteLLM [LIVE] 55 Routen ---> Provider (DeepSeek/Z.AI/OpenAI/...)
   (Runtime/GPU/Service)        |  (Model Gateway, cd61881d)
                                |
   [PART] Conduvera Core  (matrix-os e5b7e9b + goal-contract 2d6641e)
   ├─ [RC] Harness Gateway Service + Registry (hermes enabled; codex/opencode disabled_by_owner)
   │        ├─ [PART] Hermes Adapter (hermes_adapter.py 757Z, einziger echter Adapter)
   │        ├─ [SCAF] OpenCode Adapter (opencode.py tmux ALT; canary-only)
   │        ├─ [SCAF] Codex Adapter (Registry-Eintrag disabled_by_owner)
   │        └─ [BLOCK] Pi Adapter (PR_S_PI Evaluation; PI_START_BLOCKED, MXOS-SAFETY-1 fehlt)
   ├─ [PART] Buildroom (internes Modul; dispatcher.py Pfadwahl, managed_execution,
   │          fixture_runner; legacy frozen als Provenance 61 Dateien)
   ├─ [REUSED] Evidence Backbone MXOS-EVIDENCE-1.0.0 (contract.py, store, reporting)
   ├─ [PART] Reports/Operator-Status (operator_status.py aus Events)
   ├─ [REUSED] Route Plan (route_plan.py, viewer, panel, picker — display-only)
   ├─ [SUPERSEDED] Control-Layer ALT (curaops/control registry/eventlog/gates — ARCHIVE)
   ├─ [SUPERSEDED] AI-Gateway ALT (control/gateway — abgeloest durch LiteLLM)
   ├─ [SCAF] MCP-Server (mcp_server.py, Zed-Fokus, keine Runtime-Integration)
   └─ [SCAF] Editor-Scaffolding (scaffolding.py, EditorSurfaceDescriptor deklarativ)

   [DESIGN] PeekXD -> Conduvera Operator (kein Adapter, nur ToolDescriptor
            future-capability-descriptor-only; MXOS-SAFETY-1 design_draft;
            4/4 P0-Gaps offen: R1/R2/R4/R5)

   [REUSED] Matrix UI (Textual-App src/core/app.py: 14 Views, 16 Widgets)
            ├─ startbar (Import verifiziert), aber NICHT an Conduvera-State
            │  angeschlossen (liest changes/evidence/events.jsonl — existiert nicht)
            └─ Panels: RoutePlan/OperatorStatus/Git/Docker/DB/Terminal/Monitoring

   [LIVE] Hermes (6a5e51d) — Profile orchestrieren Worker; Kanban-Capability-Routing
   [SVC] OpenCode serve :3003 (Host-Systemd) · [LIVE] CLIProxyAPI (OAuth-Broker)
   [LIVE] Brain V1.1 (REPO_TRUTH-Contract geschlossen)

Auth-Grenzen IST: Hermes per-Profil-auth; LiteLLM LITELLM_MASTER_KEY;
CLIProxyAPI OAuth; Secrets-Authority = BWS (Bitwarden Secrets) [LIVE]
```

## ZIELBILD (abgeleitet, KEIN neuer Neubau vor Audit-Abschluss)

```text
   [ZIEL] Conduvera Core = kanonische Control Plane
   ├─ [ZIEL] Harness Gateway Service = einziger Lifecycle-Einstieg
   │          (Hermes LIVE; OpenCode/Codex/Pi je NUR als installierte
   │           Adapter-Artefakte via Registry — Produktgrenze belegt)
   ├─ [ZIEL] Buildroom = internes Modul (Canary-Cutover nach Equivalenz)
   ├─ [ZIEL] Evidence MXOS-EVIDENCE-1.0.0 = einzige Evidence-Autorität
   ├─ [ZIEL] Operator-Console = Option C (dünner Owner-Launcher über
   │          bestehende Reader: captain dashboard + matrix-cli harness status)
   └─ [ZIEL] PeekXD-Operator-Adapter NACH MXOS-SAFETY-1 + Gap-Audit-P0
   (R1-R5 geschlossen) — Evidence-Adapter, kein Runtime-Import

   Grenzen (unveränderlich):
   Roberto_Brain=Knowledge · Conduvera Core=Control · Buildroom=internes
   Execution-Modul · Hermes/OpenCode/Codex/Pi=Harnesses · LiteLLM=Model
   Gateway · ODS=Runtime/Lifecycle · Secrets=BWS
```

## NÄCHSTER IMPLEMENTIERUNGSSLICE (genau einer, evidence-basiert)

```text
SLICE: HARNESS-001-REBALANCE — Conduvera-State-Anschluss der Owner-Sicht
  Basis: A3-Befund (UI liest nicht-existenten Pfad changes/evidence/events.jsonl
  statt .curaops/control/events.jsonl) + A2 (HarnessGatewayService ist
  RELEASE_CANDIDATE in goal-contract, aber nicht im Core-Repo e5b7e9b)

  Capability: Owner-Console-Slice (dünner Launcher, Option C)
  Evidenz: A3 Punkt 5 (Anschlussweg: default_event_store_path() + Mini-Adapter
  ControlEvent->EventEnvelope) + captain dashboard liest bereits echten State
  Scope: (a) HarnessGatewayService + Registry aus goal-contract in den
  Core-Zweig zurückführen (PORT C04/C07/C13), (b) OperatorStatus-Panel an
  .curaops/control/events.jsonl anschließen, (c) 1 Launcher-Modul
  Status: PARTIAL -> RELEASE_CANDIDATE
  KEIN neuer UI-Neubau (DOD-05); keine Runtime-Mutation in diesem Goal
```
