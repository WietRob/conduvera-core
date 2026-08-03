#!/usr/bin/env python3
"""Canonical Owner execution-backend policy for Hermes Buildroom.

Adapter implementations remain available as dormant compatibility code, but
this policy is checked before command construction or process creation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

POLICY_PATH = Path.home() / ".hermes/buildroom/execution-backends.yaml"
KNOWN_BACKENDS = ("native", "codex_cli", "opencode_cli")


class BackendPolicyError(ValueError):
    """Raised when backend policy is missing, invalid, or disables a backend."""


def load_backend_policy(path: str | Path = POLICY_PATH) -> dict[str, dict[str, Any]]:
    policy_path = Path(path).expanduser().resolve()
    if not policy_path.exists() or not policy_path.is_file():
        raise BackendPolicyError("EXECUTION_BACKEND_POLICY_REQUIRED")
    try:
        data = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID") from exc
    backends = data.get("execution_backends")
    if not isinstance(backends, dict) or set(backends) != set(KNOWN_BACKENDS):
        raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID")
    for name in KNOWN_BACKENDS:
        entry = backends.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("enabled"), bool):
            raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID")
    if backends["native"] != {"enabled": True}:
        raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID")
    for name in ("codex_cli", "opencode_cli"):
        entry = backends[name]
        if entry.get("enabled") is not False:
            raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID")
        if entry.get("status") != "disabled_by_owner":
            raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID")
        if entry.get("requires_explicit_owner_activation") is not True:
            raise BackendPolicyError("EXECUTION_BACKEND_POLICY_INVALID")
    return {name: dict(backends[name]) for name in KNOWN_BACKENDS}


def require_backend_enabled(backend: str, *, policy_path: str | Path = POLICY_PATH) -> dict[str, Any]:
    policy = load_backend_policy(policy_path)
    if backend not in policy:
        raise BackendPolicyError(f"UNKNOWN_BACKEND:{backend}")
    entry = policy[backend]
    if not entry["enabled"]:
        raise BackendPolicyError(f"BACKEND_DISABLED_BY_OWNER:{backend}")
    return dict(entry)
