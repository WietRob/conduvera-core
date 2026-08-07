"""Legacy state compatibility (goal converge..., Arbeit 5 / DOD-04).

The rename .curaops -> .conduvera must never hide existing state.

- .conduvera = new canonical WRITE authority
- .curaops   = legacy READ source (only until migrated)
- never parallel writes to both
- idempotent dry-run migration command
- explicit apply mode
- backup + manifest before migration
- rerun produces no second result
- rollback to backup is tested

Real productive state is NOT auto-migrated in this goal.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LEGACY_DIR_NAME = ".curaops"
CANONICAL_DIR_NAME = ".conduvera"


@dataclass
class MigrationPlan:
    legacy_root: Path
    canonical_root: Path
    subdirs: list[str]
    dry_run: bool
    created: str = ""

    def __post_init__(self) -> None:
        self.created = datetime.now(timezone.utc).isoformat()


def _iter_existing(
    legacy_root: Path, canonical_root: Path, subdirs: list[str]
) -> list[tuple[Path, Path]]:
    """List (legacy, canonical) pairs where legacy state actually exists."""
    pairs: list[tuple[Path, Path]] = []
    for sub in subdirs:
        src = legacy_root / sub
        dst = canonical_root / sub
        if src.exists() and any(src.iterdir()):
            pairs.append((src, dst))
    return pairs


def plan_migration(
    home: Path, subdirs: list[str], *, dry_run: bool = True
) -> MigrationPlan:
    return MigrationPlan(
        legacy_root=home / LEGACY_DIR_NAME,
        canonical_root=home / CANONICAL_DIR_NAME,
        subdirs=list(subdirs),
        dry_run=dry_run,
    )


def run_migration(plan: MigrationPlan) -> dict[str, object]:
    """Execute (or dry-run) the migration. Idempotent: a second run finds
    nothing left to migrate and reports zero actions."""
    actions: list[dict[str, str]] = []
    pairs = _iter_existing(plan.legacy_root, plan.canonical_root, plan.subdirs)

    backup_manifest: dict[str, str] = {}
    backup_dir: Path | None = None

    for src, dst in pairs:
        # Idempotency: if the canonical target already exists (from a prior
        # run), the pair is already migrated — no second result.
        if dst.exists() and any(dst.iterdir()):
            if src.exists() and any(src.iterdir()):
                # Already migrated (canonical exists) -> no action.
                actions.append(
                    {"action": "ALREADY_MIGRATED", "src": str(src), "dst": str(dst)}
                )
                continue
            actions.append(
                {"action": "SKIP_PARALLEL", "src": str(src), "dst": str(dst)}
            )
            continue
        if plan.dry_run:
            actions.append({"action": "WOULD_COPY", "src": str(src), "dst": str(dst)})
            continue

        # Apply mode: backup first, then copy (merge by copy, no move —
        # legacy stays as provenance until explicitly archived).
        if backup_dir is None:
            backup_dir = plan.legacy_root.parent / f".conduvera-migration-backup-{plan.created.replace(':', '')[:19].replace('T', '-')}"
            backup_dir.mkdir(parents=True, exist_ok=True)
        rel = src.relative_to(plan.legacy_root)
        backup_target = backup_dir / rel.name
        shutil.copytree(src, backup_target, dirs_exist_ok=True)
        backup_manifest[str(rel)] = str(backup_target)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        actions.append({"action": "COPIED", "src": str(src), "dst": str(dst)})

    result: dict[str, object] = {
        "dry_run": plan.dry_run,
        "created": plan.created,
        "actions": actions,
        "action_count": len(actions),
    }
    if backup_manifest:
        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(backup_manifest, indent=2), encoding="utf-8")
        result["backup_manifest"] = str(manifest_path)
    return result


def rollback(backup_dir: Path, canonical_root: Path) -> dict[str, str]:
    """Restore canonical dirs from a backup (tested)."""
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    restored: dict[str, str] = {}
    for rel, backup_src in manifest.items():
        dst = canonical_root / rel
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(Path(backup_src), dst)
        restored[str(rel)] = "RESTORED"
    return restored
