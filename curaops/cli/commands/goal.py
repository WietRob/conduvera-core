"""CONDUVERA-GOAL-1.0 goal lint command.

Validates a goal file against the goal-execution.v1 schema and the
architecture invariants. Fail-closed: any missing required field,
missing DoD, missing verification, or invariant violation ends with a
structured error and a non-zero exit code.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="goal", help="CONDUVERA-GOAL-1.0 goal contract validation")
console = Console()

CONTRACT_ID = "CONDUVERA-GOAL-1.0"
CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA_PATH = CONTRACT_PATH / "goal-execution.v1.schema.json"
INVARIANTS_PATH = CONTRACT_PATH / "architecture-invariants.v1.yaml"

REQUIRED_INVARIANTS = [
    "exactly_one_control_plane",
    "buildroom_is_internal_module",
    "ods_is_runtime_authority",
    "bws_is_secrets_authority",
    "harnesses_are_replaceable",
    "capabilities_are_adapter_bound",
    "no_private_cross_repo_imports",
    "no_second_evidence_schema",
    "no_parallel_state_writer",
    "adapters_are_removable",
    "products_remain_standalone",
]


class GoalValidationError(Exception):
    """Structured goal validation failure (fail-closed)."""

    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "contract_id": CONTRACT_ID,
            "error": {"code": self.code, "message": self.message, "field": self.field},
        }


def contract_hash() -> str:
    """Content hash of the canonical contract YAML (bindings reference this)."""
    yaml_text = (CONTRACT_PATH / "goal-execution.v1.yaml").read_text(encoding="utf-8")
    return "sha256:" + hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()


def _normalize_goal_id(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _load_goal(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise GoalValidationError("GOAL_NOT_FOUND", f"goal file not found: {path}", "goal_file")
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise GoalValidationError("GOAL_PARSE_ERROR", f"cannot parse goal file: {exc}", "goal_file") from exc
    if not isinstance(data, dict):
        raise GoalValidationError("GOAL_NOT_OBJECT", "goal file must contain a YAML/JSON mapping")
    return data


def validate_goal_file(path: Path) -> dict[str, Any]:
    """Validate a goal file; raises GoalValidationError on failure."""
    data = _load_goal(path)

    # 1) Schema-level required fields
    required = [
        "goal_id", "title", "architekturposition", "scope", "non_goals",
        "definition_of_done", "verifikation", "rollback", "modularitaet",
        "architektur_invarianten", "stop_bedingungen", "abschluss_evidence",
    ]
    missing = [f for f in required if f not in data or data[f] in (None, "", [], {})]
    if missing:
        raise GoalValidationError(
            "MISSING_REQUIRED_FIELD",
            f"missing required field(s): {', '.join(missing)}",
            missing[0],
        )

    # 2) Contract identity
    contract = data.get("contract") or {}
    if contract.get("id") != CONTRACT_ID:
        raise GoalValidationError(
            "CONTRACT_MISMATCH", f"contract.id must be {CONTRACT_ID}", "contract.id"
        )

    # 3) Normalized goal_id
    goal_id = _normalize_goal_id(data["goal_id"])
    import re
    if not re.match(r"^CONDUVERA-[A-Z0-9-]{3,64}$", goal_id):
        raise GoalValidationError(
            "INVALID_GOAL_ID",
            f"goal_id '{goal_id}' does not match CONDUVERA-<BEREICH>-<NNN>",
            "goal_id",
        )

    # 4) Architecture position
    pos = data["architekturposition"]
    pos_map = {
        "control_plane": "conduvera_core",
        "execution_module": "buildroom_internal",
        "runtime_authority": "ods",
        "secrets_authority": "bws",
    }
    for key, expected in pos_map.items():
        if pos.get(key) != expected:
            raise GoalValidationError(
                "ARCHITECTURE_POSITION_MISMATCH",
                f"architekturposition.{key} must be '{expected}', got '{pos.get(key)}'",
                f"architekturposition.{key}",
            )

    # 5) DoD: at least one entry, each with id/beschreibung/verifikation
    dod = data["definition_of_done"]
    if not isinstance(dod, list) or len(dod) < 1:
        raise GoalValidationError("DOD_MISSING", "definition_of_done must contain at least one entry")
    for i, item in enumerate(dod):
        if not isinstance(item, dict):
            raise GoalValidationError("DOD_INVALID", f"definition_of_done[{i}] must be an object", "definition_of_done")
        for sub in ("id", "beschreibung", "verifikation"):
            if not item.get(sub):
                raise GoalValidationError(
                    "DOD_INCOMPLETE",
                    f"definition_of_done[{i}] missing '{sub}'",
                    f"definition_of_done[{i}].{sub}",
                )

    # 6) Verification: at least one entry
    if not isinstance(data["verifikation"], list) or len(data["verifikation"]) < 1:
        raise GoalValidationError("VERIFICATION_MISSING", "verifikation must contain at least one entry")

    # 7) Invariants: all 11 required must be referenced
    declared = set(str(i) for i in data["architektur_invarianten"])
    missing_inv = [inv for inv in REQUIRED_INVARIANTS if inv not in declared]
    if missing_inv:
        raise GoalValidationError(
            "INVARIANT_MISSING",
            f"missing architecture invariant(s): {', '.join(missing_inv)}",
            "architektur_invarianten",
        )
    unknown_inv = [inv for inv in declared if inv not in set(REQUIRED_INVARIANTS)]
    if unknown_inv:
        raise GoalValidationError(
            "INVARIANT_UNKNOWN",
            f"unknown architecture invariant(s): {', '.join(sorted(unknown_inv))}",
            "architektur_invarianten",
        )

    # 8) Modularity: must declare standalone products / no vendoring / public contracts
    mod = data["modularitaet"]
    for key in ("products_standalone", "no_vendoring", "adapters_use_public_contracts"):
        if mod.get(key) is not True:
            raise GoalValidationError(
                "MODULARITY_VIOLATION", f"modularitaet.{key} must be true", f"modularitaet.{key}"
            )

    # 9) Evidence path must point into evidence/goals/
    if not str(data["abschluss_evidence"]).startswith("evidence/goals/"):
        raise GoalValidationError(
            "EVIDENCE_PATH_INVALID",
            "abschluss_evidence must start with 'evidence/goals/'",
            "abschluss_evidence",
        )

    # 10) Non-goals + stop conditions present
    if not isinstance(data["non_goals"], list) or len(data["non_goals"]) < 1:
        raise GoalValidationError("NON_GOALS_MISSING", "non_goals must contain at least one entry")
    if not isinstance(data["stop_bedingungen"], list) or len(data["stop_bedingungen"]) < 1:
        raise GoalValidationError("STOP_CONDITIONS_MISSING", "stop_bedingungen must contain at least one entry")

    return {
        "ok": True,
        "goal_id": goal_id,
        "contract_id": CONTRACT_ID,
        "contract_hash": contract_hash(),
        "title": data["title"],
        "dod_count": len(dod),
        "verification_count": len(data["verifikation"]),
        "invariants": sorted(declared),
        "schema_path": str(SCHEMA_PATH),
    }


@app.command("lint")
def goal_lint(
    goal_file: Path = typer.Argument(..., help="Path to the goal file (YAML or JSON)"),
) -> None:
    """Validate a goal file against CONDUVERA-GOAL-1.0 (fail-closed)."""
    try:
        result = validate_goal_file(goal_file)
    except GoalValidationError as exc:
        console.print(f"[bold red]GOAL INVALID[/bold red] ({exc.code})")
        console.print(f"  {exc.message}")
        if exc.field:
            console.print(f"  field: {exc.field}")
        console.print(json.dumps(exc.to_dict(), indent=2))
        raise typer.Exit(code=2)

    table = Table(title="CONDUVERA-GOAL-1.0 — valid")
    table.add_column("Feld")
    table.add_column("Wert")
    table.add_row("goal_id", result["goal_id"])
    table.add_row("contract_id", result["contract_id"])
    table.add_row("contract_hash", result["contract_hash"])
    table.add_row("DoD-Einträge", str(result["dod_count"]))
    table.add_row("Verifikationen", str(result["verification_count"]))
    table.add_row("Invarianten", ", ".join(result["invariants"]))
    console.print(table)
    console.print(f"OK: goal_id={result['goal_id']} contract_hash={result['contract_hash']}")


@app.command("hash")
def goal_hash() -> None:
    """Print the canonical contract hash (for harness bindings)."""
    console.print(contract_hash())


def main() -> None:
    app()
