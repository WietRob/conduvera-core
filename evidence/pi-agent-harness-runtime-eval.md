# Pi Agent Harness — Runtime Evaluation (PR-S Option B live)

**Status:** PI_RUNTIME_EVALUATION_COMPLETE (live proof via Control Plane)
**Basis:** conduvera-core d6fd814d693c8eee45788b692b58115b95969022
**Pi:** @earendil-works/pi-coding-agent 0.84.1 (global npm install)
**Sandbox-Contract:** Control-Plane-Isolation (systemd-scope, Fingerprint-
  Ownership, Worktree-Isolation, EXTERNAL-Non-Adoption) — live bewiesen im
  Buildroom Operational Pilot.

## Zusammenfassung

Die frühere PR-S-Evaluation (Entscheid C: "nur Konzepte borgen") ist
überholt. Mit dem durchsetzbaren Sandbox-Contract ist **Option B**
("Matrix OS adapts Pi as runtime backend") jetzt live bewiesen — Pi läuft
als vollwertiger vierter Harness hinter dem Conduvera Control Plane.

## Pi-CLI-Inventar (verifiziert, nicht nur dokumentiert)

```
pi --version                      0.84.1
pi --model <pattern>              Modellwahl ("provider/id", optional :thinking)
pi --print, -p                    Nicht-interaktiver Modus (Prozess + Exit)
pi --mode text|json|rpc           Ausgabe-Modi
pi --offline                      Startup-Netzwerk deaktiviert
pi --list-models [search]         Modell-Liste
pi --api-key <key>                Key-Übergabe (env, nie persistiert)
```

Provider: OpenAI-kompatibel via `~/.pi/agent/models.json` (baseUrl, api,
apiKey, models, compat). Lokale LiteLLM-Route (127.0.0.1:4000) als
`litellm-local`-Provider konfiguriert — **keine Route-/Auth-/ODS-Änderung**.

## Sandbox-Contract (der durchsetzbare Blocker)

Pi-Tools (read/bash/edit/write) werden durch die Control-Plane-Isolation
eingeschränkt:
- jeder MANAGED Pi-Prozess läuft in einem transienten user systemd scope
  (KillMode=control-group, eigenes Unit/Scope-Identity) — kein Signal auf
  Fremdprozesse;
- dedizierter Git-Worktree aus exaktem Base-Commit — kein Write aufs
  Base-Checkout;
- Fingerprint-Ownership (pid+start_time+boot_id) — PID-Reuse -> LOST, nie
  Fremdprozess-Kontrolle;
- EXTERNAL_* Sessions: nie adoptiert/signalisiert;
- Timeout-Kette SIGTERM -> grace -> SIGKILL nur auf eigenen Scope.

## Live-Proof (via Control Plane)

```
PI-EVAL-10 (P10): submit -> queue -> auto-dispatch -> Pi-Session
  session mxs_1c05aab3e231429f  state COMPLETED  exit 0
  harness pi_cli  scope conduvera-mxs_1c05aab3e231429f.scope
  worktree …/PI-EVAL-10-P10  base d6fd814d693c
  stdout (5 bytes): 'PONG\n'  (echte lokale-Modell-Antwort, sha256 erfasst)
```

Multi-Harness mit Pi: PI-EVAL-3 (Pi, COMPLETED) + Hermes-Job (RUNNING)
parallel — Capacity-2-Dispatch mit Pi als Harness.

## Wichtige Befunde / Pitfalls

1. **npx-Cache-Konflikt (ENOTEMPTY):** mehrere parallele `npx --yes`
   Instanzen kollidieren am npx-Cache (`~/.npm/_npx/<id>`). Fix: Pi global
   installieren (`npm install -g @earendil-works/pi-coding-agent`) und den
   Adapter direkt auf `pi`-Binary zeigen (kein npx-Wrapper).
2. **Prompt-Injection:** `dispatch_claimed` reichte früher `prompt:""` an
   den Adapter (Sicherheits-Redaction). Pi braucht den echten Prompt. Fix:
   Prompt in-memory pro Attempt halten (`_pending_prompts`), nie persistiert,
   beim Dispatch injizieren. Store hält nur den content hash.
3. **API-Key aus Service-Env:** der Daemon bekommt LITELLM_KEY via
   EnvironmentFile; der Pi-Adapter liest LITELLM_API_KEY -> LITELLM_KEY ->
   LITELLM_MASTER_KEY -> OPENAI_API_KEY und übergibt `--api-key` (env-only,
   nie geloggt).
4. **Pi-spezifisch:** `--print` (nicht interaktiv) + `--offline` sind
   entscheidend für nicht-interaktiven Managed-Betrieb. `--mode json`
   verfügbar für strukturierte Ausgabe.
5. **Scope-Debugging:** über den Service lief Pi mit 0-byte-Output, obwohl
   der Direkt-Adapter-Test PONG lieferte — Ursache war die Prompt-Redaction
   im dispatch-Pfad (nicht der Scope).

## Adapter-Modularität (H)

Pi ist als `pi_cli`-Adapter in `conduvera/harness/adapters` registriert
(version `conduitvera-scope-adapter.v1`). Core-Start ohne Adapter bleibt
graceful (CAPABILITY_UNAVAILABLE). Kein neues Adapter-Release, kein
Version-Bump, keine Canonicality-/Provenance-Änderung.

## Registry-Erweiterung

```
pi_cli:
  enabled: true
  module: conduvera.harness.adapters
  entry_point: pi_cli_adapter
  version: conduitvera-scope-adapter.v1
  contract: CONTROL-PLANE-V1
  isolation: systemd-user-scope
  note: Pi Agent Harness CLI (print mode, local LiteLLM provider via
        ~/.pi/agent/models.json; sandbox = control-plane isolation contract)
```

## Nächster Schritt (nicht in diesem Eval)

- Pi `--mode json`/rpc für strukturierte Evidence;
- Pi-spezifische Evidence-Adapter (Pi-Session-JSONL -> MXOS-EVIDENCE-1.0.0)
  nur als separater fokussierter PR;
- Pi-Extensions/Skills-Evaluation als eigenständiges Thema.
