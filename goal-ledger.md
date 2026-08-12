# Goal Ledger — close-conduvera-operational-activity-workspace-v1
ACCEPTANCE_CONTRACT_VERSION = 1.0

## Rebaseline (2026-08-12)
- core local==GH: ef4f5c0978dfff5aae89e85ab890d45f69d8e844
- adapter d1cedd219478 · platform ed3b951701d4 (unverändert)
- core branch main · porcelain 0 · fixture HEAD 8cb595f3 tree ec3f64c0 porcelain 0
- service unit SHA256 8f3744abaf99bed640d87b3752d026a0c2603fae4588dd74c196c1a5a343e2ab
- service: active, concurrency 2, HTTP 8791, WorkingDir ~/projects/matrix-os
- doctor True · harnesses hermes_scoped/codex_cli/opencode_cli/hermes
- canonical state ~/.local/state/conduvera (NIE von Acceptance genutzt)
- tests 370 (Baseline) → jetzt 375+ durch Closure-Änderungen

## Immutable DoD (19 Zeilen, evtl. Änderungen nur per Owner-Amendment)
DOD-01..DOD-19 wie Vertrag §8. Keine Ersatzbeweise, keine Abschwächung.

## Workstreams
- WS-A Rebaseline+Ledger: DONE
- WS-B Graphical Submit: IN PROGRESS (Fixture-Harness + Registry-Gating fertig)
- WS-C Retry same-job: DONE (retry_job neuer Attempt desselben Jobs, idempotent)
- WS-D Evidence lifecycle: TODO (persistenter EvidenceStore + fail-closed)
- WS-E Operator actions + UI resilience: TODO (Retry-UI + Disconnect)
- WS-F Restart/reconcile exactly-once: EXISTS (zu verifizieren live)
- WS-G Acceptance runner + Browser journey: TODO
- Acceptance-only Harness: DONE (acceptance_fixture, env-gated)

## Deviations/Recovered
- ruff --fix verursachte 40 Drive-bys -> revertet (nur geplante Dateien behalten),
  ruff danach ohne --fix nur auf meinen Dateien.

## Nächste Aktion
1. EvidenceStore (WS-D): persistent, EvidenceBundle schema, fail-closed invalid
2. UI Submit-Formular + Retry/Actions (WS-B/E)
3. Acceptance-Runner (WS-G)
4. Live-Isolated-Service + Browser-Acceptance-Journey (Steps 0-13)
5. Final Acceptance Bundle + Report
