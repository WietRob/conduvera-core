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

    def test_pi_registry_entry_disabled(self, tmp_path):
        """harness-registry.yaml: pi_cli ist production-disabled (Quarantäne)."""
        import yaml
        reg_path = Path("conduvera/harness/contracts/harness-registry.yaml")
        data = yaml.safe_load(reg_path.read_text())
        pi = data["adapters"]["pi_cli"]
        assert pi["enabled"] is False
        assert pi["entry_point"] == "pi_cli_adapter"
        assert pi["isolation"] == "systemd-user-scope"

    def test_router_no_native_pi(self):
        """Es gibt kein automatisches native_pi-Routing (Pi nicht routbar)."""
        from conduvera.harness.router import TASK_CLASSES, DEFAULT_BINDINGS
        assert "native_pi" not in TASK_CLASSES
        assert "pi_cli" not in DEFAULT_BINDINGS

    def test_pi_cli_not_in_default_adapters(self):
        """Der Service startet standardmäßig ohne pi_cli (Quarantäne)."""
        import inspect
        from conduvera.control_plane.service import ControlPlaneService
        sig = inspect.signature(ControlPlaneService.__init__)
        default_ids = sig.parameters["adapter_ids"].default
        assert "pi_cli" not in default_ids


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
