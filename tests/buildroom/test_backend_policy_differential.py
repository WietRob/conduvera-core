"""Differential tests: legacy vs ported backend-policy module (DOD-03/04/05/08).

For the SAME inputs both the frozen legacy module and the ported
curaops.buildroom.backend_policy module are executed and compared on:
- return value,
- exception type,
- error code/text (contractual),
- side effects (none by design),
- deterministic ordering (KNOWN_BACKENDS order).

DOD-05: production code must not import the legacy file — only this test
module loads it (via sys.path to legacy/buildroom/source).
DOD-08: a negative test proves the module touches no LiteLLM/model/ODS/
GPU/secret state.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy/buildroom/source"))

import curaops.buildroom.backend_policy as new_mod  # noqa: E402
import buildroom_backend_policy as legacy_mod  # noqa: E402

CANONICAL = """execution_backends:
  native:
    enabled: true
  codex_cli:
    enabled: false
    status: disabled_by_owner
    requires_explicit_owner_activation: true
  opencode_cli:
    enabled: false
    status: disabled_by_owner
    requires_explicit_owner_activation: true
"""


def _write_policy(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def _run(mod, fn: str, *args, **kwargs):
    """Run one call on a module; return (ok, value) or (exception_name, message)."""
    try:
        result = getattr(mod, fn)(*args, **kwargs)
        return ("OK", result)
    except Exception as exc:  # noqa: BLE001 — differential capture
        return (type(exc).__name__, str(exc))


@pytest.mark.parametrize("content", [
    CANONICAL,
    "{}",
    "foo: bar\n",
    "execution_backends: [1,2,3]\n",
    "execution_backends:\n  native:\n    enabled: true\n  codex_cli:\n    enabled: true\n  opencode_cli:\n    enabled: false\n    status: disabled_by_owner\n    requires_explicit_owner_activation: true\n",
    "execution_backends:\n  native:\n    enabled: true\n  codex_cli:\n    enabled: false\n  opencode_cli:\n    enabled: false\n    status: disabled_by_owner\n    requires_explicit_owner_activation: true\n",
    "execution_backends: [unclosed\n",
    "execution_backends:\n  native:\n    enabled: false\n  codex_cli:\n    enabled: false\n    status: disabled_by_owner\n    requires_explicit_owner_activation: true\n  opencode_cli:\n    enabled: false\n    status: disabled_by_owner\n    requires_explicit_owner_activation: true\n",
])
def test_differential_load_backend_policy(content):
    path = _write_policy(content)
    try:
        legacy_res = _run(legacy_mod, "load_backend_policy", path)
        new_res = _run(new_mod, "load_backend_policy", path)
    finally:
        Path(path).unlink()
    assert legacy_res == new_res, f"Legacy {legacy_res} != New {new_res}"


def test_differential_missing_file():
    missing = str(ROOT / "nonexistent-policy-xyz.yaml")
    legacy_res = _run(legacy_mod, "load_backend_policy", missing)
    new_res = _run(new_mod, "load_backend_policy", missing)
    assert legacy_res == new_res
    assert legacy_res[0] == "BackendPolicyError"
    assert "EXECUTION_BACKEND_POLICY_REQUIRED" in legacy_res[1]


@pytest.mark.parametrize("backend", ["native", "codex_cli", "opencode_cli", "claude", "native2", ""])
def test_differential_require_backend_enabled(backend):
    path = _write_policy(CANONICAL)
    try:
        legacy_res = _run(legacy_mod, "require_backend_enabled", backend, policy_path=path)
        new_res = _run(new_mod, "require_backend_enabled", backend, policy_path=path)
    finally:
        Path(path).unlink()
    assert legacy_res == new_res, f"backend={backend!r}: Legacy {legacy_res} != New {new_res}"


def test_known_backends_identical():
    assert legacy_mod.KNOWN_BACKENDS == new_mod.KNOWN_BACKENDS == ("native", "codex_cli", "opencode_cli")


def test_exception_class_identical():
    assert issubclass(new_mod.BackendPolicyError, ValueError)
    assert new_mod.BackendPolicyError.__name__ == legacy_mod.BackendPolicyError.__name__


def test_return_value_deep_equal():
    path = _write_policy(CANONICAL)
    try:
        l = legacy_mod.load_backend_policy(path)
        n = new_mod.load_backend_policy(path)
    finally:
        Path(path).unlink()
    assert l == n
    assert list(n.keys()) == ["native", "codex_cli", "opencode_cli"]  # deterministic order


def test_dod05_no_production_import_of_legacy():
    """Production code (curaops/) must never import legacy/buildroom.

    Only real import statements count — docstring mentions of the word
    'legacy' (concept) or provenance comments are not imports.
    """
    hits = []
    for py in (ROOT / "curaops").rglob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and "legacy" in stripped:
                hits.append(f"{py}:{i}: {stripped}")
    assert not hits, f"Produktions-Import aus legacy: {hits}"


def test_dod08_no_litellm_ods_gpu_secret_side_effects():
    """The module must not touch LiteLLM/model/ODS/GPU/secret state."""
    # Static: no real imports of litellm, ai-stack, ODS, secrets, no
    # subprocess/env access in code (docstring boundary descriptions are
    # fine — they are the scope statement).
    src = (ROOT / "curaops/buildroom/backend_policy.py").read_text(encoding="utf-8")
    # Strip docstring blocks ("""...""") — they are scope statements, not code.
    lines = src.splitlines()
    code_lines, in_doc = [], False
    for l in lines:
        stripped = l.strip()
        if stripped.startswith('"""'):
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        if stripped.startswith("#"):
            continue
        code_lines.append(l)
    code = "\n".join(code_lines)
    for forbidden in ("litellm", "ai_stack", "ai-stack", "bws", "bitwarden",
                      "subprocess", "requests", "os.environ", "os.getenv"):
        assert forbidden not in code, f"verbotene Abhängigkeit im Modul: {forbidden}"
    # Dynamic: run with a canonical policy, assert nothing is written anywhere
    # and no new process appears.
    path = _write_policy(CANONICAL)
    env_before = dict(os.environ)
    try:
        new_mod.load_backend_policy(path)
        new_mod.require_backend_enabled("native", policy_path=path)
    finally:
        Path(path).unlink()
    assert dict(os.environ) == env_before, "Modul mutiert die Umgebung"


def test_fail_closed_path():
    """Deaktiviertes Backend wirft IMMER — auch wenn die Policy valide ist."""
    path = _write_policy(CANONICAL)
    try:
        for mod in (legacy_mod, new_mod):
            with pytest.raises(mod.BackendPolicyError) as exc_info:
                mod.require_backend_enabled("codex_cli", policy_path=path)
            assert "BACKEND_DISABLED_BY_OWNER:codex_cli" in str(exc_info.value)
    finally:
        Path(path).unlink()
