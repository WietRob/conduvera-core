"""Harness adapter protocol + registry loader (CONDUVERA-GOAL-1.0).

Core must never import a concrete adapter. This module defines:

- HarnessAdapterProtocol: the public, versioned contract every harness
  adapter implements.
- HarnessAdapterRegistry: the versioned entry-point layer that loads
  adapters by id from contracts/harness-registry.yaml.
- Dynamic import by entry point: the adapter module is imported ONLY when
  the registry entry is present AND enabled.

Fail-closed rules:
- registry entry missing            -> CAPABILITY_UNAVAILABLE (no adapter)
- registry entry disabled           -> CAPABILITY_UNAVAILABLE (disabled)
- adapter module physically absent  -> CAPABILITY_UNAVAILABLE (unavailable),
                                       Core still starts (no ImportError)
- no hidden fallback: a missing adapter never silently maps to another one.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
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

    def collect_evidence(self, session_id: str) -> dict[str, Any]: ...


@dataclass
class AdapterRegistration:
    """One entry of the versioned harness registry."""

    adapter_id: str
    enabled: bool
    module: str
    entry_point: str
    version: str = ""


class HarnessAdapterRegistry:
    """Versioned adapter registry (contracts/harness-registry.yaml).

    Runtime adapter loader component of the SINGLE registry authority
    (HarnessGatewayRegistry, DOD-03). Not an independent second registry —
    it is owned by the gateway registry and resolves adapter entry points
    for the same harness ids the gateway declares.
    """

    def __init__(self, registry_path: str | Path | None = None):
        self.registry_path = (
            Path(registry_path).expanduser().resolve()
            if registry_path
            else Path.cwd() / "contracts" / "harness-registry.yaml"
        )

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
        """Dynamically load an adapter.

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
