"""Bootstrap receipt for CONDUVERA-GOAL-1.0 sessions.

Every new session (Hermes/Codex/OpenCode) may produce a machine-readable
receipt at bootstrap: goal_contract, contract_hash, authority_map_version,
goal_id, loaded=true. This module is import-only (no side effects) and
provides a CLI command `conduvera goal bootstrap`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from curaops.cli.commands.goal import CONTRACT_ID, CONTRACT_PATH, contract_hash

app = typer.Typer(name="bootstrap", help="CONDUVERA-GOAL-1.0 bootstrap receipt")
console = Console()

AUTHORITY_MAP_VERSION = "2026-08-01"


def bootstrap_receipt(goal_id: str | None = None) -> dict[str, Any]:
    """Build the machine-readable bootstrap receipt."""
    return {
        "goal_contract": CONTRACT_ID,
        "contract_hash": contract_hash(),
        "authority_map_version": AUTHORITY_MAP_VERSION,
        "goal_id": goal_id,
        "loaded": True,
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def find_goal_id(cwd: Path | None = None) -> str | None:
    """Locate the nearest goal.yaml under evidence/goals/ (best effort)."""
    base = (cwd or Path.cwd())
    for p in sorted(base.rglob("goal*.yaml")) + sorted(base.rglob("goal*.json")):
        if "evidence/goals" in str(p):
            return p.parent.name
    return None


@app.command()
def receipt(
    goal_id: str | None = typer.Option(None, "--goal-id", help="Explicit goal id"),
    output: Path | None = typer.Option(None, "--output", help="Write receipt to file"),
) -> None:
    """Produce the bootstrap receipt (loaded=true) for the current session."""
    gid = goal_id or find_goal_id()
    receipt_data = bootstrap_receipt(gid)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt_data, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"Receipt geschrieben: {output}")
    else:
        console.print(json.dumps(receipt_data, indent=2, ensure_ascii=False))
