# Config-Vorschlag (separat, NICHT in diesem Goal entschieden)

## Kontext
Während des RC2-Reviews (2026-08-07) waren alle Cloud-Provider gedrosselt
(nous HTTP 503, codex HTTP 429, Weekly/Monthly-Limits). Das Review lief
danach erfolgreich über die ODS-lokale Inferenz
(`local/qwen-3.6-35b` via `custom:litellm`).

## Temporär eingeführte globale Änderung (JETZT ZURÜCKGESETZT)
```yaml
delegation:
  model: 'local/qwen-3.6-35b'    # war: '' (erbt Session-Modell)
  provider: 'custom:litellm'     # war: ''
```
Zurückgesetzt auf `model: ''` / `provider: ''` (exakt wie Backup
config.yaml.bak-rc2-review). Finaler Config-Hash: 70103569f3e3b6bb.

## Vorschlag (Owner entscheidet separat)
Option A: delegation.provider = custom:litellm DAUERHAFT setzen, damit
Subagenten nie an den Session-Provider gebunden sind (Resilienz gegen
Provider-Ausfälle).
Option B: Bei Ausfall manuell wie geschehen umstellen (Status quo).

## Empfehlung (keine Entscheidung)
Option A erhöht die Robustheit unabhängiger Reviews — die delegierten
Subagenten sind Funktionsarbeit (wir testen Funktionen, nicht Modelle).
