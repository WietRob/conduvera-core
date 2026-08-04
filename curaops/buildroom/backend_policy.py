"""Internal Buildroom execution-backend policy module (Conduvera Core).

Ported 1:1 from the frozen legacy component
`legacy/buildroom/source/buildroom_backend_policy.py` (sha256
c17ed5a491b17800aa1056443da24d6f2f8843287e0c735a3d77d3e6ea0f9ac8,
58 lines) — behaviour-preserving differential parity is proven by
`tests/buildroom/test_backend_policy_differential.py`.

SCOPE (hard boundary):
- This module decides ONLY which execution backend is allowed.
- It does NOT own: model routing, provider routing, GPU modes, ODS
  service lifecycle, credentials, task/session authority.
- LiteLLM stays the model gateway; ODS/ai-stack stays the
  runtime/GPU/service authority; BWS stays the secrets authority;
  HarnessGatewayService stays the single harness-lifecycle boundary.

PUBLIC CONTRACT (small, documented):
- `POLICY_PATH`          default policy file (owner home)
- `KNOWN_BACKENDS`       the three canonical backend ids
- `BackendPolicyError`   ValueError subclass, fail-closed
- `load_backend_policy(path=POLICY_PATH) -> dict[str, dict[str, Any]]`
- `require_backend_enabled(backend, *, policy_path=POLICY_PATH) -> dict[str, Any]`

No production code imports the legacy file; only the differential tests
load legacy and new side by side.
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
