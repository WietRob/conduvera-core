"""Phase E — local GPU/ODS admission gate for local routes.

ODS/AI-Stack is the authority for: active GPU mode, model loading, model
switching, rollback, route health, and GPU reservations. Conduvera requests a
capability (a local route); it never silently mutates ODS and never
overcommits the single local GPU.

Rules enforced by this gate:
  * If the job's model_binding route is a LOCAL route, dispatch must first
    verify the local lane is actually READY (correct ODS mode + llama-server
    healthy + served context not less than the contract advertises).
  * If not READY the attempt is HELD in the queue (visible) — never started
    optimistically, never silently cloud-fallbacked.
  * The scheduler serializes the local harness to one concurrent slot
    (matching llama-server --parallel 1).

States (match the goal Phase E):
  READY, WAITING_FOR_LOCAL_GPU, WAITING_FOR_MODEL_MODE, ROUTE_INCOMPATIBLE,
  LOCAL_UNAVAILABLE, CLOUD_FALLBACK_REQUIRES_POLICY
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.request
from pathlib import Path

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


def check(route: str, *,
          contract_path: Path | str = DEFAULT_CONTRACT,
          mode_file: Path | str = DEFAULT_MODE_FILE,
          llama_health: str = LLAMA_HEALTH,
          llama_props: str = LLAMA_PROPS) -> tuple[str, str]:
    """Return (state, reason). Pure read-only gate — never mutates ODS.

    A cloud route always returns (READY, not-a-local-route) because it does
    not consume the local GPU. A local route that is not READY returns one of
    the WAITING_*/ROUTE_INCOMPATIBLE/LOCAL_UNAVAILABLE states so the dispatcher
    holds it in the queue instead of starting it or falling back to cloud.
    """
    if not is_local_route(route):
        return READY, "not a local route; no local GPU admission needed"

    mode = _read_mode(Path(mode_file))
    expected_mode, served, slots = None, None, None
    try:
        import yaml  # local import keeps module import-light
        c = yaml.safe_load(open(contract_path))
        for r in c.get("routes", []):
            if r.get("route") == route or route in r.get("aliases", []):
                expected_mode = r.get("gpu_mode")
                served = r.get("served_context")
                slots = r.get("parallel_slots")
                break
    except Exception:
        pass

    status, _ = _http_get(llama_health)
    if status != 200:
        if not mode:
            return LOCAL_UNAVAILABLE, (
                f"ODS mode unknown and llama-server health={status}")
        return WAITING_FOR_LOCAL_GPU, (
            f"llama-server health={status} (mode={mode}); local lane not ready")

    if expected_mode and mode and expected_mode != mode:
        return WAITING_FOR_MODEL_MODE, (
            f"route {route} needs ODS mode '{expected_mode}' but active-mode is '{mode}'")

    if served:
        status2, body = _http_get(llama_props, timeout=5.0)
        if status2 == 200:
            try:
                nctx = json.loads(body)["default_generation_settings"]["n_ctx"]
                if nctx < int(served):
                    return ROUTE_INCOMPATIBLE, (
                        f"route advertises served={served} but llama-server n_ctx={nctx}")
            except Exception:
                pass

    return READY, (f"local route READY (mode={mode or '?':s}, served={served or '?'}, "
                   f"slots={slots or '?'})")


def retry_backoff_s(retries: int) -> float:
    """Small capped backoff so a held local attempt is not hot-looped."""
    return min(30.0, 5.0 * (2 ** retries))
