# Goal-Vorlage (CONDUVERA-GOAL-1.0)

> Vorlage für neue Goals. Pflichtfelder laut `contracts/goal-execution.v1.schema.json`.
> Ein Goal ohne DoD oder ohne Verifikation wird vom Validator abgelehnt (fail-closed).

```yaml
contract:
  id: CONDUVERA-GOAL-1.0
  schema_version: "1.0"

goal_id: CONDUVERA-XXX-001        # Muster: CONDUVERA-<BEREICH>-<NNN>
title: "Einzeiliger Titel"

architekturposition:
  control_plane: conduvera_core
  execution_module: buildroom_internal
  runtime_authority: ods
  secrets_authority: bws

scope:
  - "was in diesem Goal getan wird"

non_goals:
  - "was explizit NICHT getan wird"

definition_of_done:
  - id: DoD-01
    beschreibung: "…"
    verifikation: "… (Test-/Nachweismethode)"
  # mindestens 1; jede Zeile testbar

verifikation:
  - "Verifikationsplan: konkrete Kommandos/Tests"

rollback:
  - "Rückrollplan"

modularitaet:
  products_standalone: true
  no_vendoring: true
  adapters_use_public_contracts: true

architektur_invarianten:
  - exactly_one_control_plane
  - buildroom_is_internal_module
  - ods_is_runtime_authority
  - bws_is_secrets_authority
  - harnesses_are_replaceable
  - capabilities_are_adapter_bound
  - no_private_cross_repo_imports
  - no_second_evidence_schema
  - no_parallel_state_writer
  - adapters_are_removable
  - products_remain_standalone

stop_bedingungen:
  - "…"

abschluss_evidence: evidence/goals/CONDUVERA-XXX-001/goal-receipt.json
```

## Hinweise

- Validator: `conduvera goal lint <goal-file>` — gibt bei Erfolg
  normalisierte Goal-ID + Contract-Hash aus.
- Abschluss: `evidence/goals/<goal-id>/goal-receipt.json` mit allen
  DoD-Ergebnissen, Evidence-Pfaden, Invarianten und Rollback-Verifikation.
