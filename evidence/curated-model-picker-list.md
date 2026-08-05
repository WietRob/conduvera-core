# Kuratierte Picker-Standardansicht für litellm (2026-08-05)

Schema: curated-model-picker-list.v1
Zweck: MODEL_PICKER_UX — Standardansicht des Model Pickers für den litellm-
Provider auf Owner-approved Hauptmodelle + gewünschte Varianten reduzieren.
Die 46 LiteLLM-Routen bleiben ALLE erhalten (Backend-Bestandsschutz,
MODEL_ROUTE_CATALOG unverändert). Advanced/Enter-custom bleibt für alle
übrigen Routen erreichbar.

## Auswahlkriterien (aus Owner-Feedback 2026-08-05)

- Nur Owner-approved Hauptmodelle und gewünschte Varianten
- Codex-Varianten sol/terra/luna/spark/5.4-mini: behalten (reale Upstream-
  Modelle, auch wenn Rollen-Zuordnung nicht belegt)
- Z.AI-/DeepSeek-/Kimi-Varianten: behalten
- workload/* (architect/builder/fast/long-context/research/reviewer):
  AUSGEBLENDET (intern für Agentensteuerung, nicht manuelle Auswahl)
- Kompatibilitäts-Dubletten (cloud/* vs provider/* parallel): nur EINE
  Konvention pro Modell in der Standardansicht
- oauth/*-Transport-Routen: die Modellvarianten bleiben sichtbar (sol/terra/
  luna/spark/5.4-mini), nicht die kryptischen Transportnamen

## Kuratierte Liste (Standardansicht — Reihenfolge = Anzeige)

Codex:
  oauth/codex            (GPT-5.6 Sol — Hauptmodell, verifiziert 200)
  oauth/codex-terra      (GPT-5.6 Terra)
  oauth/codex-luna       (GPT-5.6 Luna — aktuell Cooldown, Owner-Variante)
  oauth/codex-spark      (Codex Spark)
  oauth/gpt-5.4-mini     (GPT-5.4 Mini)

Z.AI / GLM:
  cloud/glm-5.2
  cloud/glm-5-turbo
  cloud/glm-4.6

DeepSeek:
  provider/deepseek/v4-pro
  provider/deepseek/v4-flash   (verifiziert 200)

Kimi:
  cloud/kimi-k3               (verifiziert 200)
  cloud/kimi-k3-256k

Lokal:
  local/default               (Lokal — Qwen 3.6 35B)

= 13 Modelle in der Standardansicht (statt 46)

## Bewusst NICHT in der Standardansicht

- workload/* (7): interne Agenten-Routen, nicht manuell wählbar
- provider/openai/* (5): Alias-Dubletten der oauth/*-Varianten
- provider/zai/* (8): Alias-Dubletten der cloud/glm-*
- provider/kimi/coding, cloud/kimi-coding-fast: Spezial-/Subscription-Routen
- cloud/glm-standard, cloud/glm-strong: Kompatibilitäts-Aliasse (OpenCode
  small_model nutzt cloud/glm-standard — bleibt technisch erhalten!)
- cloud/glm-4.5, cloud/glm-4.7: ältere Varianten (Advanced erreichbar)
- oauth/gpt-5.4, oauth/gpt-5.5: nicht gewünschte Varianten
- cloud/deepseek, cloud/kimi, cloud/kimi-coding-fast: Kompatibilitäts-Aliasse

## Umsetzung

providers.litellm.models in den Hermes-Profil-Configs (default + orchestrator)
als Liste der 13 kuratierten Routen. Kein Hermes-Code-Change. Kein LiteLLM-
Config-Eingriff. Kein Container-Restart. Backup vor Änderung.
