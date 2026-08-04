# Behaviour-Matrix: buildroom_backend_policy (Legacy → Neu, DOD-01/04)

Quelle: legacy/buildroom/source/buildroom_backend_policy.py (58 Zeilen,
frozen, SOURCE_MANIFEST sha256 c17ed5a491b17800aa1056443da24d6f2f8843287e0c735a3d77d3e6ea0f9ac8)

## Öffentliche API (vollständig inventarisiert)

- Konstante: `POLICY_PATH = Path.home() / ".hermes/buildroom/execution-backends.yaml"`
- Konstante: `KNOWN_BACKENDS = ("native", "codex_cli", "opencode_cli")`
- Exception: `BackendPolicyError(ValueError)`
- `load_backend_policy(path=POLICY_PATH) -> dict[str, dict[str, Any]]`
- `require_backend_enabled(backend, *, policy_path=POLICY_PATH) -> dict[str, Any]`

## Importe (nur stdlib + yaml)

pathlib.Path, typing.Any, yaml. KEINE Cross-Module-Imports.

## Caller (Legacy, NICHT portiert in diesem Goal)

- legacy/buildroom/source/buildroom_core.py (Z.16/197/342/629)
- legacy/buildroom/source/buildroom_execution.py (Z.25/236)
- legacy/buildroom/tests/test_buildroom_cycle49_preflight.py (Z.5/149-152:
  test_external_cli_backends_remain_blocked)

## Side Effects

- KEINE: liest nur die Policy-Datei; schreibt nichts, mutiert keinen State,
  kein Netzwerk, kein Modell-/ODS-/Secret-Zugriff.
- Runtime-Befund: der Default-Pfad ~/.hermes/buildroom/execution-backends.yaml
  EXISTIERT live (kanonisch: native enabled, codex_cli/opencode_cli
  disabled_by_owner + requires_explicit_owner_activation: true) — die
  Live-Runtime-Konfiguration entspricht der erwarteten Policy.

## Verhaltensfälle (Eingabe → Legacy-Ergebnis, empirisch verifiziert)

| # | Eingabe | Legacy-Ergebnis |
|---|---------|-----------------|
| 1 | Datei fehlt (expliziter nicht-existenter Pfad) | BackendPolicyError "EXECUTION_BACKEND_POLICY_REQUIRED" |
| 2 | Kanonische Policy (native true, beide disabled) | dict in KNOWN_BACKENDS-Reihenfolge |
| 3 | require_backend_enabled("native") | {"enabled": True} |
| 4 | require_backend_enabled("codex_cli"/"opencode_cli") | BackendPolicyError "BACKEND_DISABLED_BY_OWNER:<backend>" |
| 5 | require_backend_enabled("unbekannt") | BackendPolicyError "UNKNOWN_BACKEND:<backend>" |
| 6 | leere Policy {} | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 7 | Policy ohne execution_backends-Key | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 8 | execution_backends kein dict (list/str) | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 9 | Backend-Menge ≠ KNOWN_BACKENDS | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 10 | native ≠ {"enabled": True} | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 11 | codex/opencode enabled nicht False | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 12 | codex/opencode status ≠ disabled_by_owner | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 13 | codex/opencode requires_explicit_owner_activation ≠ True | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 14 | YAML-Invalid / OSError | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 15 | Entry kein dict / enabled kein bool | BackendPolicyError "EXECUTION_BACKEND_POLICY_INVALID" |
| 16 | Default-/Fallback: require ohne policy_path nutzt POLICY_PATH | (live: kanonische Policy → native OK) |
| 17 | fail-closed: require auf deaktiviertem Backend wirft IMMER | (Fall 4) |

## Deterministische Reihenfolge

load_backend_policy gibt Backends in KNOWN_BACKENDS-Reihenfolge zurück
(native, codex_cli, opencode_cli) — nicht in YAML-Reihenfolge.

## Konfigurationsquellen

Nur die YAML-Datei unter POLICY_PATH bzw. explizitem policy_path. Keine
Env-Variablen, keine CLI-Args, kein Netzwerk.
