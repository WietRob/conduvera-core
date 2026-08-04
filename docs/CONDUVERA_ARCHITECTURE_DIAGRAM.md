# Conduvera / ODS / AI-Stack — Kanonisches Architekturdiagramm

> EIN kanonisches Diagramm (CONDUVERA-GOAL-1.0 / close-core-adapter-seam).
> Status: 2026-08-03. Authorities siehe Authority_Map.md; UI-Konsolidierung
> siehe UI_Consolidation.md. Dieses Diagramm ist maschinenlesbar als
> `docs/architecture.mmd` gespiegelt.

## Mermaid (aktueller Ist-Stand inkl. Browser-/Access-Ebene)

```mermaid
flowchart TD
    subgraph USER["User / Console / Workspace"]
        U1["Owner (CLI/Console)"]
        U2["Browser (aktuelle Access-Ebene)"]
    end

    subgraph CORE["Conduvera Core (Control Plane)"]
        C1["Tasks/Attempts/Sessions"]
        C2["Policies/Approvals"]
        C3["Evidence (MXOS-EVIDENCE-1.0.0)"]
        C4["Harness Gateway (eine Registry-Authority)"]
        B1["internes Buildroom-Modul"]
        B2["backend_policy (Execution-Backend-Entscheidung, LIVE_PROVEN)"]
        B3["BuildroomExecutionDispatcher (legacy | managed_canary)"]
        B4["ManagedBuildroomCaller (produktionsnaher Caller, LIVE_PROVEN)"]
        C1 --- C2 --- C3 --- C4
        C4 --> B1
    end

    subgraph HARNESS["Harness Plane (Adapter-gebunden)"]
        H1["Hermes (hermes-adapter.v1)"]
        H2["OpenCode CLI"]
        H3["Codex CLI (≠ Codex OAuth)"]
        H4["Pi (PI_START_BLOCKED)"]
        C4 --> H1
        C4 --> H2
        C4 --> H3
        C4 -. config/template only .-> H4
    end

    subgraph MODEL["Model Plane (LiteLLM)"]
        M1["LiteLLM Gateway :4000"]
        M2["workload/local (nur text-Modus)"]
        M3["Hermes/OpenCode -> LiteLLM oauth/codex-* -> CLIProxyAPI -> geteilter Codex-OAuth-Broker"]
        H1 --> M1
        H2 --> M1
        M1 --> M2
    end

    subgraph CODEXROUTE["Codex CLI eigene Auth-/Backend-Route"]
        C1["Codex CLI Harness"]
        C2["~/.codex eigener Auth-Store (kein LiteLLM-OAuth)"]
        C3["direkter Backend-Pfad"]
        H3 --> C1
        C1 --> C2
        C2 --> C3
    end

    subgraph ODS["ODS / ai-stack (Runtime-/GPU-/Service-Authority)"]
        O1["ai-stack model use (EINZIGE Moduswechsel-Schnittstelle)"]
        O2["llama-server :8080 (GPU, text-Modus)"]
        O3["CLIProxyAPI (nur OAuth-Broker)"]
        O4["Cloud Provider (nur vision/cloud)"]
        O5["ComfyUI / Qdrant+TEI / Whisper+Kokoro / n8n / Search / Langfuse (ODS-Capabilities)"]
        O1 --> O2
        M2 --> O2
        O3 --> O4
        O5 -. Capability-Adapter .-> C3
    end

    subgraph EVID["Evidence / Telemetry / Secrets"]
        E1["MXOS-EVIDENCE-1.0.0 (einziges Schema)"]
        E2["Telemetry (Langfuse)"]
        E3["BWS (einzige Secrets-Authority)"]
        C3 --> E1
        C3 -.-> E2
        H1 -.-> E3
    end

    subgraph UI_AKT["Aktuelle Browser-/Access-Ebene (IST, 2026-08-03)"]
        UI1["ODS Dream Dashboard :3001 (Betreiber/Setup; Auth ≠ Open WebUI; kein Modellwechsel)"]
        UI2["Open WebUI :3000 (eigenes Auth; BLOCKED_AUTH_RECOVERY; Browser-E2E NOT_PROVEN)"]
        UI3["ODS-Hermes :9120 (healthy ≠ autorisierter Browserzugang; dream-session/Owner Card)"]
        UI4["n8n :5678 (separates Login; Owner registriert)"]
        UI5["OpenCode :3003 (Host-Systemd-Service, keine UI-Auth-Änderung)"]
        UI1 --> ODS
        UI2 --> M1
        UI3 --> H1
        UI4 --> O5
        UI5 --> H2
    end

    subgraph UI_ZUK["Zukünftige Console-/Workspace-Ebene (ZIEL, design_draft)"]
        Z1["Conduvera Console (Operator/Control)"]
        Z2["Conduvera Workspace (Arbeit; Basis NOT_DECIDED — ersetzt Open WebUI NOCH NICHT)"]
        Z1 --> CORE
        Z2 --> H1
        Z2 -. Deep-Links .-> UI1
        Z2 -. Deep-Links .-> UI4
        Z2 -. Deep-Links .-> UI5
    end
```

## Invarianten im Diagramm (verifiziert, 2026-08-03)

| Invariante | Darstellung |
|---|---|
| Codex CLI ≠ Codex OAuth | Codex CLI (H3) → ~/.codex eigener Auth-Store (C2) → direkter Backend-Pfad (C3); Hermes/OpenCode → LiteLLM oauth/codex-* → CLIProxyAPI (geteilter Broker, M3); KEIN Ausdruck „native Codex-CLI-Route (OAuth)" |
| Buildroom/Conduvera wechseln NIE implizit GPU-Modi | O1 ist einzige Schnittstelle; kein Pfeil CORE→O1 außer via ODS-Runbook |
| `ai-stack model use` ist die einzige Moduswechsel-Schnittstelle | O1 explizit; Dashboard (UI1) hat KEINEN Modellwechsel-Pfeil |
| `workload/local` existiert nur im text-Modus | M2 mit „nur text-Modus" annotiert |
| ODS bleibt Runtime-Authority | ODS-Subgraph umschließt llama-server/CLIProxyAPI/Capabilities |
| BWS bleibt Secrets-Authority | E3 einzige Secrets-Quelle |
| Dashboard-Auth ≠ Open-WebUI-Auth | UI1 vs. UI2 getrennt annotiert |
| Owner Card/dream-session für ODS-Hermes | UI3 annotiert |
| OpenCode als Host-Service | UI5 annotiert |
| n8n mit separatem Login | UI4 annotiert |
| Conduvera Workspace ersetzt Open WebUI NOCH NICHT | Z2 annotiert (NOT_DECIDED; keine Festbindung an Hermes oder Open WebUI) |
| Browser-UI-E2E getrennt von Backend-E2E | UI-Ebene (UI_AKT) vs. Core/Backend getrennt |
| Capability-Fluss | Core/Harness → Capability-Adapter → ComfyUI/RAG/Voice/n8n/… UND Capability → MXOS-EVIDENCE (Evidence-Fluss explizit) |

## Statuswahrheit (UI/Access, 2026-08-03)

```text
CONDUVERA_WORKSPACE_IMPLEMENTATION_BASIS = NOT_DECIDED
OPEN_WEBUI_CURRENT_ACCESS               = BLOCKED_AUTH_RECOVERY
OPEN_WEBUI_BROWSER_E2E                  = NOT_PROVEN
ODS-HERMES_HEALTHY                      = SERVICE_HEALTH (nicht Browser autorisiert)
DREAM_DASHBOARD                         = SERVICE_HEALTH + AUTHENTICATED_BROWSER (Owner)
N8N_OWNER_REGISTERED                    = AUTHENTICATED_BROWSER (Owner)
OPENCODE_UI                             = SERVICE_HEALTH (Host-Service)
BACKEND_E2E                             = bewiesen (Core→Adapter→LiteLLM→Qwen)
```
