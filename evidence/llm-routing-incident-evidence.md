# LLM-Routing-Incident — Diagnose-Evidence (2026-08-05)

Schema: llm-routing-incident.v1
Goal: close-llm-routing-incident-and-stabilize-installed-buildroom-entrypoint

## Timeline (absolute Zeitstempel, aus Container-Logs)

| Zeit (UTC) | Ereignis |
|---|---|
| 2026-07-30T12:00:51Z | ERSTER 429 model_cooldown gpt-5.6-luna (reset 136h) — Cooldown begann bereits am 30.07. |
| 2026-08-05T07:25:29Z | Aktueller luna-429: reset 68h6m (Cooldown durch wiederholte Versuche verlängert) |
| 2026-08-05T09:2x | Reproduktion: oauth/codex-luna -> 429; cloud/glm-4.6 -> 429 (reset 17:37:31) |
| 2026-08-05T09:2x | Gegenprobe: kimi-k3 -> 200 OK; oauth/codex -> 200; workload/local -> 200 |

## Client-Callgraph (IST)

| Client | Provider | Modell | Base-URL | Auth-Quelle | Status |
|---|---|---|---|---|---|
| Hermes default-Profil | custom:litellm | oauth/codex | 127.0.0.1:4000/v1 | LITELLM_API_KEY env | 200 OK |
| Hermes orchestrator-Profil | custom:litellm | oauth/codex-luna | 127.0.0.1:4000/v1 | LITELLM_API_KEY env | 429 (extern) |
| OpenCode (PID 1732, host) | — | — | — | — | läuft, Port 3003 |
| Buildroom Managed Canary | workload/local | Qwen3.6-35B | llama-server (Container) | — | 200 OK, 3/3 |
| CLIProxyAPI (Container) | codex | oauth/* | — | OAuth | — |

## Port-/Prozess-Authority 127.0.0.1:4000 (A2)

- Eindeutiger Owner: Container **dream-litellm** (cgroup docker-09f9d267f16b,
  PID 3568, Start 2026-07-31T05:36:51Z, Container seit 5 Tagen healthy)
- Port-Mapping 127.0.0.1:4000->4000/tcp (docker ps)
- geladene Config: /tmp/config.yaml IM CONTAINER (sha256 c6e1fdfd…, seit
  Jul 31 unverändert)
- KEIN paralleler Host-LiteLLM: der Host-`ls /tmp/config.yaml`-Fehlschlag
  war ein Namespace-Artefakt (Datei liegt im Container-Namespace)
- Ergebnis: EINE eindeutige Runtime-Authority. Kein ungeklärter Dual-Proxy.

## Ursache (A4)

EXTERNE Provider-Kontingente, KEIN lokaler Fehler:
1. oauth/codex-luna: OpenAI-Codex model_cooldown für gpt-5.6-luna,
   reset_seconds 245218 (~68h), code=model_cooldown — server-seitig verhängt
2. cloud/glm-4.6: Z.AI "Usage limit reached for 5 hour", reset
   2026-08-05T17:37:31Z — Token-Kontingent des externen Kontos
3. kimi-k3: 200 OK (freigegeben, Owner-Korrektur bestätigt)
4. workload/local + oauth/codex: 200 OK (lokale + sol-Pfade grün)

Lokale Reparatur NICHT möglich (extern); keine lokale Infrastruktur
umgebaut. Alle lokalen Pfade (LiteLLM, llama-server, Container, Ports)
sind grün.

## Beweise

- Container-Logs dream-litellm (--timestamps): erste 429 2026-07-30T12:00:51Z
- Live-Test-Calls (Authorization: Bearer $LITELLM_API_KEY):
  luna 429, glm 429, kimi 200, codex 200, workload/local 200
- ss -tln: 127.0.0.1:4000 LISTEN; cgroup-Zuordnung aller Kandidaten
- docker inspect dream-litellm: Port-Mapping + Status healthy

## Status

LLM_ROUTING_INCIDENT = RESOLVED (als externe Störung bewiesen;
lokale Pfade grün; Nutzer-Clients mit freigegebenen Modellen funktionieren)
