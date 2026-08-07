# Side-Effect-Inventar (rc3-goal, DOD-11)

## Self-Improvement-/Konfig-Diffs
| Datei | Vorher-Hash | Nachher-Hash | Grund | Entscheid |
|---|---|---|---|---|
| ~/.hermes/config.yaml | 9a4495e227eee844 (delegation.model=qwen, provider=litellm) | 70103569f3e3b6bb (= Backup, model/provider leer) | Review-Provider-Fallback (RC2) | ZURÜCKGESETZT — nicht behalten; separater Vorschlag: config-fallback-vorschlag.md |
| config.yaml.bak-rc2-review | — | unverändert | Backup | behalten (Backup) |

## Temporäre Artefakte (außerhalb aller Repos)
- /tmp/rc3-build.py — Release-Builder (fail-closed)
- /tmp/core-2026-08-07-rc3-staging (weg — atomar nach releases/core/rc3 gemovt)
- /tmp/rc3-removal-copy, /tmp/rc2-removal-copy — Removal-Test-Kopien
- /tmp/rc2-wt-final, /tmp/rc3-wt — Hermes-Fake-Worktrees (PONG-Tests)

## Legitime Goal-Arbeit
- Adapter-Repo: 0.1.2 (Provenance-Korrektur, keine Funktion)
- goal-contract evidence/rc-v3/: Tree-Manifest, Config-Vorschlag, Receipts

## Invarianz (verifiziert)
- RC1: core-wheel 0a6e1ae5 unverändert
- RC2: core-wheel eeb659be unverändert
- Produktiv-Release: 1b9c1de2 unverändert
- current-Symlink: keiner (unverändert)
- ODS: text · LiteLLM: 1c3d2b96 · Prozesse: 0
