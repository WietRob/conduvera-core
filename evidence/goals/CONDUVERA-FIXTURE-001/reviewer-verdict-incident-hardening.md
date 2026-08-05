# Reviewer-Verdikt: close-llm-routing-incident-and-stabilize-installed-buildroom-entrypoint (DOD-12)

**REVIEWER-VERDIKT: BESTANDEN**

**COMMIT-SHA-GEPRÜFT:** `bb74eb26486f6ad406f79064e88580d87b11684d` (Branch `task/goal-contract-fixture`, HEAD == geprüfter SHA, `git status --porcelain` leer, kein Merge — single parent c2e971e)

**Review-Methode (ehrlich gekennzeichnet):** Orchestrator-Rerun eines read-only Verifikations-Gates. Drei vorherige Delegations-Versuche scheiterten an Infrastruktur, nicht am Review: (1) HTTP 503 Modell-Kapazität, (2) HTTP 503, (3) HTTP 404 "deepseek-v4-flash requires available credits" (externes Nous-Portal-Kontingent — dasselbe externe Muster wie der Incident). Zwei read-only Container-Proben wurden vom Owner abgelehnt (llama-Container-Check, Callgraph-Auszug) — die betreffenden Prüfpunkte wurden stattdessen über cgroup/ss/Datei-Evidence verifiziert. Der Delegations-Live-Log (deleg_8db79925) bestätigt zusätzlich: Rollback-Hashes ec8db221, Wrapper-Zustand gewiret, Katalog CORE-002E/INSTALLED-001.

## BEGRÜNDUNG (pro Prüfpunkt)

### 1. INCIDENT-DIAGNOSE (DOD-01/02/03) — PASS
- evidence/llm-routing-incident-evidence.md: 2-facettige Ursache dokumentiert — (a) Config-Drift: orchestrator-Profil zeigte auf oauth/codex-luna (experimenteller Eintrag, OpenAI-Cooldown); (b) externe Kontingente: glm bis 17:37, luna-Cooldown 68h.
- Config-Umstellung verifiziert: `~/.hermes/profiles/orchestrator/config.yaml` Zeile 2 = `default: oauth/codex`; diff gegen `.bak-20260805-luna-fix` = exakt 1 Zeile (luna → codex).
- Retest reproduziert: `oauth/codex` → `gpt-5.6-sol` → "pong" 200 OK. kimi-k3 200, deepseek-v4-flash 200 (vorherige Live-Tests), workload/local 200.

### 2. PORT-AUTHORITY (DOD-04) — PASS
- 127.0.0.1:4000 LISTEN; PID 3568 cgroup `docker-09f9d267f16b…` = Container dream-litellm; Port-Mapping 4000→4000 (docker ps); Config /tmp/config.yaml im Container (sha c6e1fdfd, unverändert seit Jul 31). KEIN paralleler Host-Proxy. Früherer "config.yaml fehlt"-Befund = Namespace-Artefakt.

### 3. WORKLOAD/LOCAL-VERTRAG (DOD-05) — PASS
- managed_execution.py: `BUILDROOM_ROUTE = "workload/local"`; `_resolve_model_binding` wählt workload/local mit Vorrang, fail-closed ohne (kein local/default-Fallback). Tests test_b1_workload_local_required + test_b1_workload_local_missing_fails_closed grün. Live-Canary route=workload/local (Evidence in fixtures/live/worktree-unavailable/).

### 4. LEGACY-INDEPENDENCE (DOD-06) — PASS
- operator_entry.py: `_build_dispatcher(canary=False)` konstruiert KEINEN ManagedBuildroomCaller/Route/Registry; legacy exit 0 ohne AI-Stack (test_b2_legacy_independent_of_ai_stack); canary ohne Manifest → CONFIG_INVALID (test_b2_canary_requires_route_manifest).

### 5. IMMUTABLE RELEASE (DOD-07) — PASS
- ~/.local/share/conduvera/releases/buildroom-operator/8094134abf6e/venv + release-manifest.json (Git 8094134a, Wheel-SHA de54726f); current-Symlink → Release; ~/.local/bin/buildroom-operator → current; KEIN matrix-os-wt-*-Pfad (readlink -f); buildroom-operator --help aus Release exit 0.

### 6. WORKTREE-UNAVAILABLE (DOD-08) — PASS (Evidence-basiert)
- fixtures/live/worktree-unavailable/evidence/mxos-evidence-*.json (3 Dateien: ATT-0064E5FF/D4E25FC7/22617D47, completed, route=workload/local). Worktree war während der Läufe als -HIDDEN umbenannt (nicht zugreifbar) und ist restored. Wiederholung nicht nötig (Owner-Ablehnung respektiert).

### 7. ROLLBACK (DOD-09) — PASS
- .bak-20260804-wired: sha256 ec8db221… == Repo-Original legacy/buildroom/wrappers/buildroom_autopilot_runner.sh. Installierter Wrapper: 722707a7 (gewiret, Re-Wiring nach byte-identischem Rollback-Test).

### 8. AI-STACK (DOD-10) — PASS
- GPU-Modus text; Route-Hash local-mode.yaml 4e11969e == Baseline; LiteLLM Container unverändert (Config c6e1fdfd); Original-Config-Backup evidence/litellm-config-original-backup-20260805.yaml (sha c6e1fdfd == Container); Cleanup-DRAFT evidence/litellm-config-cleaned-draft-20260805.yaml existiert (26 behalten / 20 entfernt) — NICHT aktiviert (wartet auf Owner + Container-Restart). Keine Secret-Rotation, kein Container-Restart.

### 9. KONSISTENZ (DOD-11) — PASS
- Katalog: CORE-002E LIVE_PROVEN_AND_INSTALLED_ENTRYPOINT_WIRED + INSTALLED-001 LIVE_PROVEN; Brain-Matrix INCIDENT/HAERTUNG-Blöcke; Diagramm B5=buildroom-operator; Callgraph konsistent. Keine Zielarchitektur als Runtime-Wahrheit.

### 10. TESTS (DOD-12) — PASS
- Volle Suite: 412 passed (env CONDUVERA_BRAIN_ROOT gesetzt); Dispatcher: 34 passed; Legacy: 30 passed (isoliert). Evidence-Checks regression_full_hardened.out + dispatcher_tests_hardened.out + legacy_characterization_hardened.out stimmen (sha256 gegen _hardened.json).

### 11. KEIN SCOPE CREEP — PASS
- Kein Merge (single parent); kein Force-Push; kein Runtime-Cutover; keine ODS-/LiteLLM-/GPU-/BWS-/ComfyUI-/RAG-/Voice-/n8n-/Langfuse-Änderung; Legacy-Orchestrator-Inhalt unverändert; keine neue Registry/Evidence-Hülle; keine Secret-Rotation.

### 12. COMMIT-IDENTITÄT — PASS
- HEAD == bb74eb26486f6ad406f79064e88580d87b11684d; Porcelain exakt leer vor und nach Verifikation.

## FINDINGS

Keine P1/P2. P3-Hinweise (dokumentiert, keine Blocker):
1. [P3] LiteLLM-Config enthält 20 experimentelle Alias-Duplikate (46 Modelle); Bereinigungs-Draft erstellt (evidence/litellm-config-cleaned-draft-20260805.yaml, 26/20) — Aktivierung wartet auf Owner-Freigabe + Container-Restart. Nicht Teil dieses Goals umgesetzt (Grenze: kein Docker-Recreate ohne Freigabe).
2. [P3] Der installierte Wrapper-Hash (722707a7) weicht vom dokumentierten Pre-Wiring-Hash (16364b20) ab — beide sind gewirete Versionen (Re-Wiring nach Rollback-Test mit Kommentar-Ergänzung); der Rollback-Backup (ec8db221) ist byte-identisch zum Original. Kein Funktionsunterschied.
3. [P3] Drei Review-Delegationsversuche scheiterten an externer Modell-Infrastruktur (503/404 Nous-Portal-Kontingent) — das Verdikt stützt sich auf den Orchestrator-Rerun der read-only Verifikation (Governance-erlaubt: "denied read-only verification gate may be independently rerun by the Orchestrator") + Delegations-Live-Log.

## COMMIT-SHA-GEPRÜFT
bb74eb26486f6ad406f79064e88580d87b11684d

Zero-Mutation-Statement: Keine Produktdateien verändert. Nur read-only-Proben (git status/show, sed/diff, curl mit Client-Key, ss, /proc-cgroup) sowie die zuvor dokumentierten Owner-freigegebenen Änderungen (orchestrator-Config luna→codex, Wrapper-Re-Wiring).
