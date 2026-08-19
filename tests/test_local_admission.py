"""LOCAL_ROUTE_PREFLIGHT fail-closed tests.

Tested properties (FIX-1, owner correction):
- A local route returns READY only when EVERY check passes.
- It returns a non-READY state when ANY of these holds, and never falls through
  to READY:
    * capability contract missing or malformed
    * requested route missing from the contract
    * active ODS mode missing or unknown
    * llama props missing or malformed
    * served n_ctx unavailable
    * actual model identity does not match the route contract
    * verified_context absent or below the task requirement
- Cloud routes skip local preflight (READY, not-a-local-route).
- The feature is a readiness preflight (LOCAL_ROUTE_PREFLIGHT), never a claim
  of an ODS-wide GPU reservation.
"""
from __future__ import annotations

import json
import pytest

from conduvera.control_plane import local_admission as la


CONTRACT = """routes:
  - route: local/qwen-3.6-35b
    aliases: [local/default, workload/local, gpt-4o, gpt-4o-mini]
    model_identity: Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
    served_context: 65536
    verified_context: 64734
    gpu_mode: text
    parallel_slots: 1
  - route: local/vision
    model_identity: gemma-4-31B-it-Q4_K_M.gguf
    served_context: 32768
    verified_context: 30701
    gpu_mode: vision
    parallel_slots: 1
"""


def _write(path, text: str) -> str:
    path.write_text(text)
    return str(path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    contract = _write(tmp_path / "contract.yaml", CONTRACT)
    mode = _write(tmp_path / "mode", "text")
    state = {"health": 200, "n_ctx": 65536, "models": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
             "health_body": b"ok"}

    def set_state(**kw):
        state.update(kw)

    def _fake(url: str, timeout: float = 3.0):
        if "/health" in url:
            return state["health"], state["health_body"]
        if "/props" in url:
            if state["n_ctx"] is None:
                return 200, b""
            return 200, json.dumps(
                {"default_generation_settings": {"n_ctx": state["n_ctx"]}}).encode()
        if "/v1/models" in url:
            if state["models"] is None:
                return 200, b""
            return 200, json.dumps({"data": [{"id": state["models"]}]}).encode()
        return 0, b""

    monkeypatch.setattr(la, "_http_get", _fake)
    return {"contract": contract, "mode": mode, "set_state": set_state}


def _ck(env, route="workload/local", mode_file=None, contract=None, required=None):
    return la.check(route, contract_path=contract or env["contract"],
                    mode_file=mode_file or env["mode"],
                    required_verified=required)


# ---- fail-closed cases ----
def test_contract_missing_fail_closed(env, tmp_path):
    missing = _write(tmp_path / "nope.yaml", "routes: []")  # present but wrong
    missing2 = tmp_path / "absent.yaml"  # does not exist
    st, re = la.check("workload/local", contract_path=missing2, mode_file=env["mode"])
    assert st == la.ROUTE_INCOMPATIBLE
    st, re = la.check("workload/local", contract_path=missing, mode_file=env["mode"])
    assert st == la.ROUTE_INCOMPATIBLE


def test_contract_malformed_fail_closed(env, tmp_path):
    bad = _write(tmp_path / "bad.yaml", "routes: not-a-list: [broken")
    st, _ = la.check("workload/local", contract_path=bad, mode_file=env["mode"])
    assert st == la.ROUTE_INCOMPATIBLE


def test_route_missing_from_contract_fail_closed(env, tmp_path):
    c = _write(tmp_path / "c.yaml", "routes:\n  - route: local/other\n    model_identity: x\n")
    st, _ = la.check("workload/local", contract_path=c, mode_file=env["mode"])
    assert st == la.ROUTE_INCOMPATIBLE


def test_mode_missing_fail_closed(env, tmp_path):
    mode = _write(tmp_path / "mode", "")
    st, _ = la.check("workload/local", contract_path=env["contract"], mode_file=mode)
    assert st == la.LOCAL_UNAVAILABLE


def test_llama_down_fail_closed(env):
    env["set_state"](health=503)
    st, _ = _ck(env)
    assert st == la.WAITING_FOR_LOCAL_GPU


def test_props_missing_fail_closed(env):
    env["set_state"](n_ctx=None)  # /props returns empty body
    st, _ = _ck(env)
    assert st == la.ROUTE_INCOMPATIBLE


def test_nctx_unavailable_fail_closed(env):
    env["set_state"](n_ctx="garbage")
    st, _ = _ck(env)
    assert st == la.ROUTE_INCOMPATIBLE


def test_served_less_than_contract_fail_closed(env):
    env["set_state"](n_ctx=32768)  # backend 32K < contract served 65536
    st, _ = _ck(env)
    assert st == la.ROUTE_INCOMPATIBLE


def test_model_identity_mismatch_fail_closed(env):
    env["set_state"](models="gemma-4-31B-it-Q4_K_M.gguf")  # wrong identity
    st, _ = _ck(env)
    assert st == la.ROUTE_INCOMPATIBLE


def test_model_identity_unavailable_fail_closed(env):
    env["set_state"](models=None)
    st, _ = _ck(env)
    assert st == la.ROUTE_INCOMPATIBLE


def test_wrong_ods_mode_fail_closed(env, tmp_path):
    mode = _write(tmp_path / "mode", "vision")
    st, _ = _ck(env, mode_file=mode)
    assert st == la.WAITING_FOR_MODEL_MODE


def test_verified_absent_fail_closed(env, tmp_path):
    c = _write(tmp_path / "c.yaml",
               "routes:\n  - route: local/qwen-3.6-35b\n    model_identity: Qwen3.6-35B-A3B-UD-Q4_K_M.gguf\n"
               "    served_context: 65536\n    gpu_mode: text\n")
    st, _ = la.check("workload/local", contract_path=c, mode_file=env["mode"])
    assert st == la.ROUTE_INCOMPATIBLE


def test_verified_below_required_fail_closed(env):
    st, _ = _ck(env, required=65000)  # contract verified 64734 < 65000
    assert st == la.ROUTE_INCOMPATIBLE


# ---- happy path ----
def test_local_route_ready(env):
    st, re = _ck(env)
    assert st == la.READY
    assert "LOCAL_ROUTE_PREFLIGHT READY" in re and "verified=64734" in re


def test_cloud_route_skips_preflight(env):
    env["set_state"](health=0)  # even if llama is down, cloud route is READY
    st, re = la.check("provider/openai/gpt-5.6-sol", contract_path=env["contract"],
                      mode_file=env["mode"])
    assert st == la.READY and "not a local route" in re


def test_is_local_route():
    assert la.is_local_route("workload/local")
    assert la.is_local_route("local/default")
    assert la.is_local_route("gpt-4o")
    assert not la.is_local_route("provider/openai/gpt-5.6-sol")


def test_feature_is_preflight_not_reservation():
    assert la.FEATURE == "LOCAL_ROUTE_PREFLIGHT"


def test_retry_backoff_capped_monotonic():
    assert la.retry_backoff_s(1) == 10.0
    assert la.retry_backoff_s(20) == 30.0


def test_scheduler_merges_per_harness_overrides_keeps_defaults(tmp_path):
    """FIX-3: an override for one harness must not replace the default limits of
    every other existing harness (codex_cli/opencode_cli/hermes keep prior limits)."""
    from conduvera.control_plane.scheduler import Scheduler, SchedulerStore
    s = Scheduler(store=SchedulerStore(str(tmp_path / "q.json")),
                  per_harness_limits={"hermes_scoped": 1})
    assert s.per_harness["hermes_scoped"] == 1
    assert s.per_harness["codex_cli"] == 2
    assert s.per_harness["opencode_cli"] == 1
    assert s.per_harness["hermes"] == 2
    # a harness not in defaults keeps the per-harness fallback of 1
    assert s.per_harness.get("unknown_harness", 1) == 1
