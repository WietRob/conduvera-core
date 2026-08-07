"""Public gateway boundary contract (goal converge..., Arbeit 4 / DOD-07).

Productive callers MUST go through HarnessGatewayService — never through
the internal HarnessAdapterRegistry directly.

Checks (repository-wide, machine-readable):
- no HarnessAdapterRegistry() instantiation outside harness/gateway.py
- no HarnessGatewayRegistry().load_adapter() productive callers
- concrete adapter objects are never returned to core callers
- HarnessGatewayRegistry stays a declarative descriptor facade
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE = REPO / "conduvera"

# Files allowed to touch the internal registry loader directly.
GATEWAY_IMPL = {"harness/gateway.py", "harness/registry.py"}


def _py_files() -> list[Path]:
    return [p for p in CODE.rglob("*.py") if "__pycache__" not in str(p)]


def test_no_direct_registry_instantiation_outside_gateway() -> None:
    offenders: list[str] = []
    for p in _py_files():
        rel = p.relative_to(CODE).as_posix()
        if rel in GATEWAY_IMPL:
            continue
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"HarnessAdapterRegistry\s*\(", line):
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, f"direct registry instantiation outside gateway:\n{offenders}"


def test_no_productive_harness_gateway_registry_load_adapter() -> None:
    offenders: list[str] = []
    for p in _py_files():
        rel = p.relative_to(CODE).as_posix()
        if rel in GATEWAY_IMPL:
            continue
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "HarnessGatewayRegistry" in line and "load_adapter" in line:
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, f"productive HarnessGatewayRegistry.load_adapter callers:\n{offenders}"


def test_gateway_service_is_sole_public_entry() -> None:
    """HarnessGatewayService must be importable from the public package surface."""
    from conduvera.harness.gateway import HarnessGatewayService  # noqa: F401

    # The internal loader is private: _load_adapter is underscore-prefixed.
    import inspect

    src = inspect.getsource(HarnessGatewayService)
    assert "_load_adapter" in src  # private on purpose
    assert "def start_session" in src  # public lifecycle


def test_service_never_returns_concrete_adapter() -> None:
    """start_session/status/etc. return AdapterResult — never adapter objects."""
    import inspect

    from conduvera.harness.gateway import HarnessGatewayService, HarnessGatewayRegistry

    # Service public methods never expose concrete adapter types.
    service_src = inspect.getsource(HarnessGatewayService)
    assert "-> HermesAdapter" not in service_src
    # Facade load_adapter is fail-closed (no concrete adapter returned).
    facade_src = inspect.getsource(HarnessGatewayRegistry.load_adapter)
    assert "raise HarnessCapabilityUnavailableError" in facade_src
    assert "return self.adapters.load_adapter" not in facade_src


def test_no_source_checkout_imports_repo_wide() -> None:
    """No runtime file imports from goal worktrees / source checkouts."""
    pat = re.compile(r"(matrix-os-wt|goal-contract|projects/hermes)")
    offenders: list[str] = []
    for p in _py_files():
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line) and "import" in line:
                offenders.append(f"{p.relative_to(CODE)}:{i}: {line.strip()}")
    assert not offenders, f"source-checkout imports:\n{offenders}"
