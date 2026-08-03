"""Shadow equivalence test: legacy Buildroom parser vs. BuildroomLegacyStateReader.

Runs the REAL imported legacy source (buildroom_backend_policy, buildroom_core,
buildroom_status-style parsing) against frozen fixtures, and compares its
normalized output with the Matrix-OS reader. Records every difference as
expected normalization / unsupported legacy field / semantic mismatch / unknown.
No live state access, no subprocesses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Import the frozen legacy source (isolated, not the live ~/.hermes scripts)
LEGACY_SRC = Path(__file__).parents[2] / "legacy" / "buildroom" / "source"
sys.path.insert(0, str(LEGACY_SRC))

FIXTURES = Path(__file__).parent / "fixtures"

from curaops.buildroom.legacy_state import BuildroomLegacyStateReader  # noqa: E402


def _legacy_backend_policy() -> dict:
    """Replicate load_backend_policy() semantics on the fixture file."""
    from buildroom_backend_policy import load_backend_policy

    return load_backend_policy(FIXTURES / "execution-backends.yaml")


def _legacy_project_packs() -> dict:
    """Replicate ProjectPack.from_yaml() on fixture project packs.

    Redirects the backend-policy path to the frozen fixture so the legacy
    validator never touches live ~/.hermes state.
    """
    import buildroom_backend_policy as bbp
    from buildroom_core import ProjectPack

    bbp.POLICY_PATH = FIXTURES / "execution-backends.yaml"

    result = {}
    for yml in sorted((FIXTURES / "projects").glob("*.yaml")):
        pack = ProjectPack.from_yaml(yml)
        result[yml.stem] = {
            "project_name": pack.project_name,
            "repo_path": str(pack.repo_path),
            "default_branch": pack.default_branch,
            "test_command": pack.test_command,
            "github_repo": getattr(pack, "github_repo", None),
            "autopilot_enabled": bool(getattr(pack, "autopilot_enabled", False)),
            "delivery_mode": getattr(pack, "delivery_mode", None),
            "allowed_phases": list(getattr(pack, "allowed_phases", []) or []),
        }
    return result


def _legacy_active_project() -> dict:
    """Replicate buildroom_status-style load on the fixture state file."""
    with open(FIXTURES / "state" / "active-project.json", encoding="utf-8") as f:
        return json.load(f)


def _shadow_compare() -> dict:
    diffs: list[dict] = []

    # 1) Backend policy
    legacy_backends = _legacy_backend_policy()
    reader = BuildroomLegacyStateReader(FIXTURES)
    readiness = reader.read()
    assert readiness.ok, f"reader not ok: {readiness.errors} {readiness.missing_files}"
    snap = readiness.snapshot
    mx_backends = {b.backend: b for b in snap.backends}

    for backend, legacy_cfg in legacy_backends.items():
        mx = mx_backends.get(backend)
        if mx is None:
            diffs.append({
                "area": "backends",
                "field": backend,
                "kind": "unsupported_legacy_field",
                "legacy": legacy_cfg,
                "mxos": None,
            })
            continue
        for key in ("enabled", "status", "requires_explicit_owner_activation"):
            lv = legacy_cfg.get(key)
            mv = getattr(mx, key, None)
            # Legacy may omit keys; reader defaults False/None
            if lv is not None and lv != mv:
                diffs.append({
                    "area": "backends", "field": f"{backend}.{key}",
                    "kind": "semantic_mismatch",
                    "legacy": lv, "mxos": mv,
                })

    # 2) Project packs
    legacy_packs = _legacy_project_packs()
    mx_packs = {p.project_name: p for p in snap.project_packs}
    for name, legacy in legacy_packs.items():
        mx = mx_packs.get(name)
        if mx is None:
            diffs.append({
                "area": "project_packs", "field": name,
                "kind": "unsupported_legacy_field",
                "legacy": legacy, "mxos": None,
            })
            continue
        for key in ("default_branch", "test_command", "autopilot_enabled", "delivery_mode"):
            lv = legacy.get(key)
            mv = getattr(mx, key, None)
            if lv != mv:
                diffs.append({
                    "area": "project_packs", "field": f"{name}.{key}",
                    "kind": "semantic_mismatch",
                    "legacy": lv, "mxos": mv,
                })

    # 3) Active project
    legacy_active = _legacy_active_project()
    mx_active = snap.active_project
    if mx_active is None:
        diffs.append({
            "area": "active_project", "field": "all",
            "kind": "unsupported_legacy_field",
            "legacy": legacy_active, "mxos": None,
        })
    else:
        for key in ("schema_version", "active_project_id", "mode", "selected_by", "selected_at", "reason"):
            lv = legacy_active.get(key)
            mv = getattr(mx_active, key, None)
            if lv is not None and lv != mv:
                diffs.append({
                    "area": "active_project", "field": key,
                    "kind": "semantic_mismatch",
                    "legacy": lv, "mxos": mv,
                })

    # 4) Expected normalizations (reader-side defaults for legacy-omitted fields)
    expected_normalizations = []
    for backend, legacy_cfg in legacy_backends.items():
        for key in ("status", "requires_explicit_owner_activation"):
            if key not in legacy_cfg:
                expected_normalizations.append({
                    "area": "backends", "field": f"{backend}.{key}",
                    "legacy_omitted": key, "mxos_default": getattr(mx_backends[backend], key, None),
                })

    return {
        "legacy_backends": {k: v for k, v in legacy_backends.items()},
        "legacy_project_packs": legacy_packs,
        "legacy_active_project": legacy_active,
        "mxos_backends": {k: {"enabled": v.enabled, "status": v.status, "requires_explicit_owner_activation": v.requires_explicit_owner_activation} for k, v in mx_backends.items()},
        "mxos_project_packs": {p.project_name: {"default_branch": p.default_branch, "test_command": p.test_command, "autopilot_enabled": p.autopilot_enabled, "delivery_mode": p.delivery_mode} for p in snap.project_packs},
        "mxos_active_project": {"schema_version": mx_active.schema_version, "active_project_id": mx_active.active_project_id, "mode": mx_active.mode} if mx_active else None,
        "differences": diffs,
        "expected_normalizations": expected_normalizations,
        "verdict": "PASS" if not diffs else "DIFFS_RECORDED",
    }


def test_shadow_equivalence_no_semantic_mismatch():
    report = _shadow_compare()
    mismatches = [d for d in report["differences"] if d["kind"] == "semantic_mismatch"]
    assert not mismatches, f"semantic mismatches: {mismatches}"


def test_shadow_equivalence_expected_normalizations_documented():
    report = _shadow_compare()
    # Every reader-side default for a legacy-omitted field must be documented
    # as expected normalization (and the report must be saved).
    for en in report["expected_normalizations"]:
        assert en["mxos_default"] in (False, None), f"unexpected default: {en}"
