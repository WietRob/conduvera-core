# AGENTS.md — Conduvera Core (working name; formerly Matrix OS)

> Diese Datei ist die einzige aktive Harness-Bindungsquelle für den
> Goal-Execution-Contract (CONDUVERA-GOAL-1.0). Keine divergierenden Kopien.

## Goal-Execution-Contract (verbindlich für jede Session)

- Contract-ID: `CONDUVERA-GOAL-1.0`
- Maschinenlesbare SSoT: `contracts/goal-execution.v1.yaml`
- Schema: `contracts/goal-execution.v1.schema.json`
- Invarianten: `contracts/architecture-invariants.v1.yaml`
- Vorlage: `templates/goal-template.md`
- Validator: `conduvera goal lint <goal-file>` (fail-closed, exit 2 bei
  ungültigem Goal)

Contract-Hash: `sha256:d9824e6d3f2db5b8bc55a2e74c790a622f87b8bacc0b42e21c5a82f1619eb7ee`
(verifiziert 2026-08-03 via `conduvera goal hash`; bei Abweichung Session
BLOCKED melden).

## Arbeitsregel

- Fortschritt wird ausschließlich durch verifizierte Fähigkeiten gemessen.
- Keine Aussage DONE / READY / OPERATIONAL ohne vollständigen DoD-Nachweis
  und Abschluss-Receipt (`evidence/goals/<goal-id>/goal-receipt.json`).
- Architektur-Invarianten (11, siehe `contracts/architecture-invariants.v1.yaml`)
  müssen alle PASS sein; Verletzung = BLOCKED statt Improvisation.

## Autoritäten (Kurzform)

```text
Conduvera Core  = Task/Attempt/Session/Harness-Routing/Policies/Reviews/Evidence
Buildroom       = internes Ausführungs-/Arbeitsmodus-Modul in Conduvera Core
Hermes          = erster Harness (Adapter: curaops/harness/…, versioniert)
ODS             = alleinige Runtime-, Service-, Modell-, Ressourcen-Authority
LiteLLM         = Modell-Gateway (keine Task-Autorität)
BWS             = Secrets-Authority
Roberto_Brain   = menschliche SSoT
Repo-Verträge/Evidence = maschinenlesbare SSoT
```

## Harness-Bindings (eine Referenz für alle)

| Harness | Mechanismus | Referenz |
|---|---|---|
| Hermes | Repo-AGENTS.md (diese Datei) | Contract-ID + Pfad + Hash oben |
| Codex CLI | Repo-AGENTS.md (diese Datei) | dito |
| OpenCode | Repo-AGENTS.md (diese Datei) | dito |
| Pi | NUR Konfiguration/Template (`templates/pi-binding.md`), nicht starten | dito (Safety-Gate fehlt) |

## Bootstrap-Receipt (jede neue Session)

Beim Session-Start ein maschinenlesbares Receipt erzeugen (z. B.
`conduvera goal bootstrap`):

```json
{ "goal_contract": "CONDUVERA-GOAL-1.0",
  "contract_hash": "sha256:d9824e6d…eb7ee",
  "authority_map_version": "2026-08-01",
  "goal_id": "<current goal or null>",
  "loaded": true }
```

## Stop-Bedingungen (sofort BLOCKED)

- Ein laufender manueller Prozess müsste kontrolliert werden.
- Eine zweite Task-/Session-/Evidence-Authority entstünde.
- Ein privater Cross-Repo-Import wäre nötig.
- Ein destruktives State-Migrationsverfahren wäre nötig.
- ODS- oder Auth-Routing müsste außerhalb des genehmigten Scope geändert werden.
- Das E2E-Fixture ist nicht ohne Produktrepo-Mutation ausführbar.
