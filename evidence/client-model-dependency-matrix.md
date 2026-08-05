# Client-Abhängigkeits-Matrix — Model-Alias-Nutzung (2026-08-05)

Schema: client-model-dependency-matrix.v1
Zweck: ARBEIT 1 des Goals "close-model-picker-curation" — wer nutzt welche
Aliase, bevor irgendetwas geändert wird. Read-only erfasst.

## Clients

| Client | Konfigurationsquelle | Modell-Alias | Rolle |
|---|---|---|---|
| Hermes default-Profil | ~/.hermes/profiles/default/config.yaml | oauth/codex | model.default |
| Hermes orchestrator-Profil | ~/.hermes/profiles/orchestrator/config.yaml | oauth/codex | model.default |
| OpenCode | ~/.config/opencode/opencode.json | litellm/oauth/codex | model |
| OpenCode | ~/.config/opencode/opencode.json | litellm/cloud/glm-standard | small_model |
| Buildroom Dispatcher (produktiv) | ~/.config/conduvera/buildroom-operator/dispatcher.yaml | workload/local | route-Vertrag |
| Buildroom Canary | ~/.config/conduvera/buildroom-operator/dispatcher-canary.yaml | workload/local | route-Vertrag |

## Kernbefund (Owner-Feedback 2026-08-05)

cloud/* UND provider/* parallel sind die unbegründete Doppelstruktur.
OpenCode nutzt NOCH cloud/glm-standard (small_model) — cloud/* kann NICHT
pauschal entfernt werden, sondern braucht Migration. Die "12 aktiven Routen"
der dokumentierten früheren Architektur (local/default, cloud/deepseek,
cloud/glm-standard, cloud/glm-strong, oauth/codex, ...) sind teilweise noch
in realer Nutzung.

## LiteLLM-Katalog (46 Modelle, unverändert — Backend-Bestandsschutz)

- cloud/ (12): alte Benutzer-Konvention — deepseek, glm-4.5/4.6/4.7/5-turbo/
  5.2/standard/strong, kimi/kimi-coding-fast/k3/k3-256k
- local/ (1): local/default
- oauth/ (8): codex + codex-luna/sol/spark/terra + gpt-5.4/-mini/5.5
- provider/ (18): präzisere Struktur — deepseek/v4-flash/v4-pro,
  kimi/coding/k3/k3-256k, openai/gpt-5.5/luna/sol/spark/terra,
  zai/glm-4.5/4.5-air/4.6/4.7/5/5-turbo/5.1/5.2
- workload/ (7): architect/builder/fast/local/long-context/research/reviewer

## Design-Entscheidung (aus Owner-Feedback)

- MODEL_ROUTE_CATALOG: unverändert erhalten, keine pauschale Löschung
- MODEL_PICKER_UX: jetzt korrigieren (Standardansicht kuratiert,
  Advanced/Enter-custom für alle übrigen Routen)
- Kuratierte Standardansicht: nur Owner-approved Hauptmodelle und
  gewünschte Varianten, sauber nach Provider gruppiert
- Technische/interne Routen (workload/*, lokale Betriebsaliasse,
  Kompatibilitätsaliasse) im normalen Picker ausblenden
