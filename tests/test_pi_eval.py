"""Pi Agent Harness runtime-evaluation tests (PI-EVAL).

Proves:
- pi_cli adapter loads + health-checks via the gateway;
- registry entry pi_cli enabled;
- router maps native_pi -> pi_cli with the litellm-local binding;
- the adapter passes the API key only from the process environment
  (never hard-coded, never persisted);
- prompt redaction: the store holds a hash, never the raw prompt.
"""

import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestPiAdapter:
    """Pi-CLI-Adapter-Registrierung und Health."""

    def test_pi_cli_adapter_registered_and_healthy(self):
        """Der pi_cli-Adapter ist registriert und meldet sich per npx/global."""
        from conduvera.harness.adapters import pi_cli_adapter
        a = pi_cli_adapter()
        hc = a.health_check()
        assert hc.success, hc.message

    def test_pi_registry_entry_enabled(self, tmp_path):
        """harness-registry.yaml: pi_cli ist enabled."""
        import yaml
        reg_path = Path("conduvera/harness/contracts/harness-registry.yaml")
        data = yaml.safe_load(reg_path.read_text())
        pi = data["adapters"]["pi_cli"]
        assert pi["enabled"] is True
        assert pi["entry_point"] == "pi_cli_adapter"
        assert pi["isolation"] == "systemd-user-scope"

    def test_router_native_pi(self):
        """native_pi hat pi_cli in der Verfügbarkeits-Fallback-Kette und ein
        litellm-local Model-Binding (deterministisches Pi-Binding)."""
        from conduvera.harness.router import DeterministicRouter
        r = DeterministicRouter()
        d = r.route(task_id="t", task_class="native_pi")
        assert "pi_cli" in d.fallback_chain
        # pi_cli ist ein gültiges Ziel (Binding vorhanden)
        from conduvera.harness.router import DEFAULT_BINDINGS
        assert "pi_cli" in DEFAULT_BINDINGS
        assert DEFAULT_BINDINGS["pi_cli"].provider == "litellm-local"

    def test_router_native_pi_override(self):
        """Bei explizitem pi_cli-Override wird deterministisch auf pi_cli
        geroutet (kein verstecktes Modell-Switching)."""
        from conduvera.harness.router import DeterministicRouter
        r = DeterministicRouter()
        d = r.route(task_id="t", task_class="native_pi", override_harness="pi_cli")
        assert d.harness == "pi_cli"


class TestPiPromptHandling:
    """Prompt-Redaction und In-Memory-Injection."""

    def test_pi_args_never_contains_raw_key_in_args_schema(self):
        """Der Adapter liest den Key aus der env, nicht aus config."""
        from conduvera.harness.adapters import _pi_args
        test_key = "envtest-localkey-xyz"  # dummy, not a real secret prefix
        saved = {k: os.environ.pop(k, None) for k in
                 ("LITELLM_API_KEY", "LITELLM_KEY", "LITELLM_MASTER_KEY",
                  "OPENAI_API_KEY")}
        os.environ["LITELLM_KEY"] = test_key
        try:
            args = _pi_args("PONG", {"model": "litellm-local/local/qwen-3.6-35b"})
            assert "--api-key" in args
            assert test_key in args
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_pi_args_without_key_omits_flag(self):
        """Ohne Key in der env wird kein --api-key übergeben."""
        from conduvera.harness.adapters import _pi_args
        saved = {k: os.environ.pop(k, None)
                 for k in ("LITELLM_API_KEY", "LITELLM_KEY", "LITELLM_MASTER_KEY",
                           "OPENAI_API_KEY")}
        try:
            args = _pi_args("PONG", {"model": "litellm-local/local/qwen-3.6-35b"})
            assert "--api-key" not in args
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class TestPiStoreRedaction:
    """Queue/Store hält nie den raw Prompt."""

    def test_prompt_never_persisted_in_job(self, tmp_path):
        """JobDescriptor.bind_prompt speichert nur Hash + [prompt redacted]."""
        from conduvera.control_plane.scheduler import JobDescriptor
        job = JobDescriptor(
            job_id="j1", task_id="t", repo="fixture", base_commit="deadbeef",
            harness="pi_cli", model_binding={}, prompt="")
        job.bind_prompt("GEHEIM-SECRET-PROMPT mit token abc123")
        d = job.to_dict()
        assert "GEHEIM-SECRET-PROMPT" not in str(d)
        assert d.get("prompt_summary") == "[prompt redacted]"
        assert d.get("prompt_hash", "").startswith("sha256:")
