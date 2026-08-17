"""Phase E — local GPU/ODS admission gate tests (LOCAL-ADMISSION-V1).

Tested properties:
- A local route returns READY only when ODS mode matches, llama-server is
  healthy, and served context >= the route-capability contract advertises.
- A blocked local route returns a concrete non-READY state (WAITING_FOR_LOCAL_GPU,
  WAITING_FOR_MODEL_MODE, ROUTE_INCOMPATIBLE, LOCAL_UNAVAILABLE) and never a
  silent cloud fallback.
- Cloud routes skip local admission (READY, not-a-local-route).
- The retry backoff is capped and monotonic.

Architecture flow: dispatch_claimed -> local_admission.check() reads the
canonical route-capability contract (~/.local/share/ai-stack/route-capabilities.yaml)
and the ODS active-mode file, plus live llama-server health/props. ODS stays
the authority; Conduvera only observes it.
"""
from __future__ import annotations

import pytest

from conduvera.control_plane import local_admission as la


def _write(path, text: str) -> str:
    path.write_text(text)
    return str(path)


CONTRACT = """routes:
  - route: local/qwen-3.6-35b
    aliases: [local/default, workload/local, gpt-4o, gpt-4o-mini]
    served_context: 65536
    gpu_mode: text
    parallel_slots: 1
  - route: local/vision
    served_context: 32768
    gpu_mode: vision
    parallel_slots: 1
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    contract = _write(tmp_path / "contract.yaml", CONTRACT)
    mode = _write(tmp_path / "mode", "text")
    def set_http(health_code, n_ctx=None):
        def _fake(url: str, timeout: float = 3.0):
            if "/health" in url:
                return health_code, b"ok"
            if "/props" in url:
                body = b"{}"
                if n_ctx is not None:
                    body = ('{"default_generation_settings":{"n_ctx":%d}}' % n_ctx).encode()
                return (200, body) if health_code == 200 else (0, b"")
            return (0, b"")
        monkeypatch.setattr(la, "_http_get", _fake)
    return {"contract": contract, "mode": mode, "set_http": set_http}


def test_local_route_ready(env):
    env["set_http"](200, n_ctx=65536)
    state, reason = la.check("workload/local", contract_path=env["contract"],
                             mode_file=env["mode"])
    assert state == la.READY
    assert "65536" in reason and "slots=1" in reason


def test_cloud_route_skips_admission(env):
    env["set_http"](0)  # even if llama is down, a cloud route is READY
    state, reason = la.check("provider/openai/gpt-5.6-sol",
                             contract_path=env["contract"], mode_file=env["mode"])
    assert state == la.READY and "not a local route" in reason


def test_llama_down_waiting_local_gpu(env):
    env["set_http"](503)
    state, reason = la.check("workload/local", contract_path=env["contract"],
                             mode_file=env["mode"])
    assert state == la.WAITING_FOR_LOCAL_GPU


def test_llama_down_unknown_mode_local_unavailable(env, tmp_path):
    env["set_http"](0)
    mode = _write(tmp_path / "mode", "")
    state, reason = la.check("workload/local", contract_path=env["contract"],
                             mode_file=mode)
    assert state == la.LOCAL_UNAVAILABLE


def test_wrong_ods_mode_waiting_model_mode(env, tmp_path):
    env["set_http"](200, n_ctx=32768)
    mode = _write(tmp_path / "mode", "vision")
    state, reason = la.check("workload/local", contract_path=env["contract"],
                             mode_file=mode)
    assert state == la.WAITING_FOR_MODEL_MODE


def test_served_less_than_contract_route_incompatible(env):
    env["set_http"](200, n_ctx=32768)  # text mode but backend only 32K < 65536
    state, reason = la.check("workload/local", contract_path=env["contract"],
                             mode_file=env["mode"])
    assert state == la.ROUTE_INCOMPATIBLE


def test_is_local_route():
    assert la.is_local_route("workload/local")
    assert la.is_local_route("local/default")
    assert la.is_local_route("local/vision")
    assert la.is_local_route("gpt-4o")
    assert not la.is_local_route("provider/openai/gpt-5.6-sol")
    assert not la.is_local_route("cloud/glm-standard")


def test_retry_backoff_capped_monotonic():
    assert la.retry_backoff_s(1) == 10.0
    assert la.retry_backoff_s(2) == 20.0
    assert la.retry_backoff_s(20) == 30.0  # capped
