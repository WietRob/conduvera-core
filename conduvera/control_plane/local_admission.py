"""LOCAL_ROUTE_PREFLIGHT — local-route readiness preflight + Control-Plane serialization.

NOT an ODS-wide GPU reservation or lease. ODS/AI-Stack is the sole authority
for GPU mode, model loading, switching, rollback, route health, and any real
GPU reservation. This module only OBSERVES the canonical route-capability
contract and the live ODS lane to answer one question: is this specific local
route READY to run a task right now? It never mutates ODS, never claims a GPU
lease, and does not control external/non-Conduvera consumers. Oversubscription
protection is provided by the Control-Plane scheduler serializing the local
harness to one concurrent slot (matching llama-server --parallel 1).

FAIL-CLOSED: for every local route, check() returns a non-READY state when ANY
of the following holds, and NO exception path may fall through to READY:
  * capability contract missing or malformed;
  * requested route missing from the contract;
  * active ODS mode missing or unknown;
  * llama props missing or malformed;
  * served n_ctx unavailable;
  * actual model identity does not match the route contract;
  * verified_context absent or below the task requirement.

States:
  READY, WAITING_FOR_LOCAL_GPU, WAITING_FOR_MODEL_MODE, ROUTE_INCOMPATIBLE,
  LOCAL_UNAVAILABLE, CLOUD_FALLBACK_REQUIRES_POLICY
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

# The feature is a local-route readiness preflight (never a GPU lease).
FEATURE = "LOCAL_ROUTE_PREFLIGHT"

READY = "READY"
WAITING_FOR_LOCAL_GPU = "WAITING_FOR_LOCAL_GPU"
WAITING_FOR_MODEL_MODE = "WAITING_FOR_MODEL_MODE"
ROUTE_INCOMPATIBLE = "ROUTE_INCOMPATIBLE"
LOCAL_UNAVAILABLE = "LOCAL_UNAVAILABLE"
CLOUD_FALLBACK_REQUIRES_POLICY = "CLOUD_FALLBACK_REQUIRES_POLICY"

# Canonical machine-readable route capability contract + ODS mode authority.
DEFAULT_CONTRACT = Path.home() / ".local/share/ai-stack/route-capabilities.yaml"
DEFAULT_MODE_FILE = Path.home() / ".local/share/ai-stack/active-mode"
LLAMA_HEALTH = "http://127.0.0.1:11434/health"
LLAMA_PROPS = "http://127.0.0.1:11434/props"
LLAMA_MODELS = "http://127.0.0.1:11434/v1/models"

# Local route namespace. workload/local + local/* + legacy local passthroughs.
LOCAL_ROUTE_MARKERS = ("workload/local", "local/", "gpt-4o", "gpt-4o-mini")


def is_local_route(route: str) -> bool:
    """True if the route consumes the local ODS/llama-server lane."""
    return any(route == m or (m.endswith("/") and route.startswith(m))
               for m in LOCAL_ROUTE_MARKERS)


def _http_get(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except Exception:
        return 0, b""


def _read_mode(mode_file: Path) -> str:
    try:
        return Path(mode_file).read_text().strip()
    except Exception:
        return ""


def _load_contract(contract_path: Path | str):
    """Return (routes, error). routes is None on missing/malformed; error is str."""
    try:
        import yaml  # local import keeps module import-light
        c = yaml.safe_load(open(contract_path))
        if not isinstance(c, dict) or not isinstance(c.get("routes"), list):
            return None, "capability contract missing or malformed"
        return c["routes"], ""
    except Exception as exc:  # noqa: BLE001 - fail closed on any read/parse error
        return None, f"capability contract missing or malformed: {exc}"


def _route_entry(routes, route: str):
    for r in routes:
        if r.get("route") == route or route in (r.get("aliases") or []):
            return r
    return None


def check(route: str, *,
          contract_path: Path | str = DEFAULT_CONTRACT,
          mode_file: Path | str = DEFAULT_MODE_FILE,
          llama_health: str = LLAMA_HEALTH,
          llama_props: str = LLAMA_PROPS,
          llama_models: str = LLAMA_MODELS,
          required_verified: int | None = None) -> tuple[str, str]:
    """LOCAL_ROUTE_PREFLIGHT: (state, reason). Read-only; never mutates ODS.

    A cloud route always returns (READY, not-a-local-route) because it does
    not consume the local GPU. A local route returns a non-READY state unless
    EVERY contract/live check passes (fail-closed — see module docstring).
    """
    if not is_local_route(route):
        return READY, "not a local route; no local route preflight needed"

    # 1. contract present + parseable
    routes, err = _load_contract(contract_path)
    if routes is None:
        return ROUTE_INCOMPATIBLE, err

    # 2. requested route present in the contract
    entry = _route_entry(routes, route)
    if entry is None:
        return ROUTE_INCOMPATIBLE, (
            f"requested route {route} missing from capability contract")

    # 3. active ODS mode present + known
    mode = _read_mode(Path(mode_file))
    if not mode:
        return LOCAL_UNAVAILABLE, "active ODS mode missing or unknown"

    # 4. llama-server health
    status, _ = _http_get(llama_health)
    if status != 200:
        return WAITING_FOR_LOCAL_GPU, (
            f"llama-server health={status} (mode={mode}); local lane not ready")

    # 5. llama props present + served n_ctx available
    status2, body = _http_get(llama_props, timeout=5.0)
    if status2 != 200 or not body:
        return ROUTE_INCOMPATIBLE, "llama props missing or malformed"
    try:
        nctx = int(json.loads(body)["default_generation_settings"]["n_ctx"])
    except Exception:  # noqa: BLE001
        return ROUTE_INCOMPATIBLE, "served n_ctx unavailable / props malformed"

    # 6. served n_ctx not less than the route contract advertises
    served = entry.get("served_context")
    if served:
        try:
            if nctx < int(served):
                return ROUTE_INCOMPATIBLE, (
                    f"route advertises served={served} but llama-server n_ctx={nctx}")
        except (TypeError, ValueError):
            return ROUTE_INCOMPATIBLE, f"contract served_context malformed: {served!r}"

    # 7. actual model identity matches the route contract
    status3, body3 = _http_get(llama_models, timeout=5.0)
    if status3 != 200 or not body3:
        return ROUTE_INCOMPATIBLE, "llama model identity unavailable"
    try:
        served_id = json.loads(body3)["data"][0]["id"]
    except Exception:  # noqa: BLE001
        return ROUTE_INCOMPATIBLE, "llama model identity malformed"
    expected = entry.get("model_identity")
    if expected:
        base = served_id.split("/")[-1]  # tolerate path prefixes on the id
        if expected not in base and base not in expected:
            return ROUTE_INCOMPATIBLE, (
                f"model identity mismatch: contract={expected!r} served={served_id!r}")

    # 8. ODS mode matches the route's expected mode
    expected_mode = entry.get("gpu_mode")
    if expected_mode and expected_mode != mode:
        return WAITING_FOR_MODEL_MODE, (
            f"route {route} needs ODS mode '{expected_mode}' but active-mode is '{mode}'")

    # 9. verified_context present and at least the task requirement
    verified = entry.get("verified_context")
    if verified is None:
        return ROUTE_INCOMPATIBLE, "verified_context absent from contract"
    try:
        if required_verified is not None and int(verified) < required_verified:
            return ROUTE_INCOMPATIBLE, (
                f"verified_context {verified} below required {required_verified}")
    except (TypeError, ValueError):
        return ROUTE_INCOMPATIBLE, f"contract verified_context malformed: {verified!r}"

    return READY, (f"LOCAL_ROUTE_PREFLIGHT READY (mode={mode}, served={served or '?'}, "
                   f"verified={verified}, slots={entry.get('parallel_slots') or '?'})")


def retry_backoff_s(retries: int) -> float:
    """Small capped backoff so a held local attempt is not hot-looped."""
    return min(30.0, 5.0 * (2 ** retries))
