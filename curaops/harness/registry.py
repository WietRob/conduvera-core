"""Harness adapter protocol + registry loader (CONDUVERA-GOAL-1.0).

Core must never import a concrete adapter. This module defines:

- HarnessAdapterProtocol: the public, versioned contract every harness
  adapter implements (including await_completion and execution_mode).
- ExecutionMode: SIMULATION vs LIVE — never a silent default.
- AdapterErrorCode: structured fail-closed error codes.
- HarnessAdapterRegistry: INTERNAL implementation-detail loader, owned by
  the single public entry point HarnessGatewayService (gateway.py). Core/
  Runner/CLI must NOT use this class directly.

Fail-closed rules:
- registry entry missing            -> CAPABILITY_UNAVAILABLE (no adapter)
- registry entry disabled           -> CAPABILITY_UNAVAILABLE (disabled)
- adapter module physically absent  -> CAPABILITY_UNAVAILABLE (unavailable),
                                       Core still starts (no ImportError)
- no hidden fallback: a missing adapter never silently maps to another one.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from curaops.control.adapters.base import AdapterResult


class HarnessCapabilityUnavailableError(Exception):
    """Structured fail-closed error for missing/disabled/unavailable adapters."""

    def __init__(self, adapter_id: str, reason: str):
        self.adapter_id = adapter_id
        self.reason = reason
        self.code = "CAPABILITY_UNAVAILABLE"
        super().__init__(f"{adapter_id}: {reason}")


class ExecutionMode(str, Enum):
    """Execution mode — never a silent default.

    SIMULATION: deterministic, no real process/model; may NEVER satisfy
        operational/live gates.
    LIVE: real managed process via the real ODS/LiteLLM path; the only mode
        the productive Core path accepts.
    """

    SIMULATION = "SIMULATION"
    LIVE = "LIVE"

    @classmethod
    def require(cls, value: Any) -> "ExecutionMode":
        """Coerce and validate; fail closed on unknown/empty values."""
        if isinstance(value, ExecutionMode):
            return value
        if isinstance(value, str):
            for m in cls:
                if m.value == value.upper():
                    return m
        raise ValueError(f"Unknown execution mode: {value!r} (must be SIMULATION|LIVE)")


class AdapterErrorCode(str, Enum):
    """Structured fail-closed error codes for adapter/lifecycle results."""

    ADAPTER_PROTOCOL_ERROR = "ADAPTER_PROTOCOL_ERROR"
    MODEL_IDENTITY_UNVERIFIED = "MODEL_IDENTITY_UNVERIFIED"
    SESSION_WAIT_FAILED = "SESSION_WAIT_FAILED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    PROCESS_FINGERPRINT_MISMATCH = "PROCESS_FINGERPRINT_MISMATCH"


@runtime_checkable
class HarnessAdapterProtocol(Protocol):
    """Public versioned adapter contract (hermes-adapter.v1 compatible)."""

    name: str
    adapter_version: str

    def health_check(self) -> AdapterResult: ...

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: dict[str, Any],
    ) -> AdapterResult: ...

    def status_session(self, session_id: str) -> AdapterResult: ...

    def cancel_session(self, session_id: str) -> AdapterResult: ...

    def timeout_session(self, session_id: str) -> AdapterResult: ...

    def await_completion(
        self, session_id: str, timeout_policy: dict[str, Any] | None = None
    ) -> AdapterResult:
        """Block until the managed session finishes or the policy expires.

        timeout_policy keys (optional): wait_s, grace_s. Returns a structured
        AdapterResult (success + status in detail). Never raises on a managed
        session wait; foreign sessions are never touched.
        """
        ...

    def collect_evidence(self, session_id: str) -> dict[str, Any]: ...


@dataclass
class AdapterRegistration:
    """One entry of the versioned harness registry."""

    adapter_id: str
    enabled: bool
    module: str
    entry_point: str
    version: str = ""


# -- Config resolution: explicit path -> controlled env -> package resource ----

_REGISTRY_ENV_VAR = "CONDUVERA_HARNESS_REGISTRY"
_PACKAGE_REGISTRY = "contracts/harness-registry.yaml"


def resolve_registry_path(
    explicit: str | Path | None = None,
) -> Path:
    """Resolve the registry config deterministically (never Path.cwd()).

    Priority:
      1. explicit path (caller-supplied, e.g. fixtures/harness-registry.yaml)
      2. CONDUVERA_HARNESS_REGISTRY env var (controlled)
      3. package resource contracts/harness-registry.yaml (installed)
    Raises FileNotFoundError if none exists (fail closed, no cwd fallback).
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    env_val = os.environ.get(_REGISTRY_ENV_VAR, "").strip()
    if env_val:
        candidates.append(Path(env_val).expanduser())
    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    # Package resource (importlib.resources) — installed environment.
    try:
        pkg_res = resources.files("curaops.harness") / _PACKAGE_REGISTRY
        if pkg_res.is_file():
            return Path(str(pkg_res))
        # Fall back to the repo-relative package file when running from source.
        repo_rel = Path(__file__).resolve().parent.parent.parent / "contracts" / "harness-registry.yaml"
        if repo_rel.is_file():
            return repo_rel.resolve()
    except Exception:
        pass
    raise FileNotFoundError(
        f"harness registry not resolvable (explicit={explicit!r}, env={_REGISTRY_ENV_VAR!r})"
    )


class HarnessAdapterRegistry:
    """INTERNAL implementation-detail adapter loader.

    Owned exclusively by HarnessGatewayService (gateway.py) — the single
    public entry point. Core/Runner/CLI must not instantiate this class
    directly (DOD-03); use HarnessGatewayService.from_registry(...).
    """

    def __init__(self, registry_path: str | Path | None = None):
        self.registry_path = resolve_registry_path(registry_path)

    def _load(self) -> dict[str, AdapterRegistration]:
        try:
            data = yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            return {}
        raw = data.get("adapters", data)
        out: dict[str, AdapterRegistration] = {}
        if isinstance(raw, dict):
            for adapter_id, cfg in raw.items():
                if not isinstance(cfg, dict):
                    continue
                out[adapter_id] = AdapterRegistration(
                    adapter_id=str(adapter_id),
                    enabled=bool(cfg.get("enabled", False)),
                    module=str(cfg.get("module", "")),
                    entry_point=str(cfg.get("entry_point", "")),
                    version=str(cfg.get("version", "")),
                )
        return out

    def registrations(self) -> dict[str, AdapterRegistration]:
        return self._load()

    def load_adapter(self, adapter_id: str) -> Any:
        """Dynamically load an adapter (internal — call via gateway service).

        Raises HarnessCapabilityUnavailableError (never ImportError) for:
        - missing registry entry,
        - disabled entry,
        - physically missing adapter module,
        - missing entry-point attribute,
        - module that does not implement the protocol.
        """
        reg = self._load().get(adapter_id)
        if reg is None:
            raise HarnessCapabilityUnavailableError(
                adapter_id, "no registry entry (CAPABILITY_UNAVAILABLE)"
            )
        if not reg.enabled:
            raise HarnessCapabilityUnavailableError(
                adapter_id, "adapter disabled in harness-registry.yaml (fail-closed)"
            )
        if not reg.module or not reg.entry_point:
            raise HarnessCapabilityUnavailableError(
                adapter_id, "registry entry incomplete (module/entry_point missing)"
            )
        try:
            module = importlib.import_module(reg.module)
            adapter_cls = getattr(module, reg.entry_point)
            adapter = adapter_cls() if callable(adapter_cls) else adapter_cls
        except (ImportError, AttributeError) as exc:
            raise HarnessCapabilityUnavailableError(
                adapter_id, f"adapter module/entry point unavailable: {exc}"
            ) from exc
        if not isinstance(adapter, HarnessAdapterProtocol):
            raise HarnessCapabilityUnavailableError(
                adapter_id, "adapter does not implement HarnessAdapterProtocol"
            )
        return adapter
