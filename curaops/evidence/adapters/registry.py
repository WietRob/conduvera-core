"""Registry for Matrix OS evidence adapters.

The registry is discovery metadata only. It does not execute external tools,
load external packages, or broaden the accepted event registry.
"""

from __future__ import annotations

from dataclasses import dataclass

from curaops.evidence import ValidationError
from curaops.evidence.adapters.agent_evidence_plane import AGENT_EVIDENCE_PLANE_EVENT_TYPES
from curaops.evidence.adapters.failure_loop import FAILURE_LOOP_EVENT_TYPES
from curaops.evidence.adapters.safety_guard import SAFETY_GUARD_EVENT_TYPES


@dataclass(frozen=True)
class AdapterDescriptor:
    """Discovery metadata for one Matrix OS evidence adapter."""

    adapter_id: str
    name: str
    source_project: str
    module_path: str
    docs_path: str
    input_contract: str
    supported_event_types: tuple[str, ...]
    cli_commands: tuple[str, ...]
    execution_mode: str
    production_status: str
    external_repo_policy: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable descriptor dictionary."""

        return {
            "adapter_id": self.adapter_id,
            "name": self.name,
            "source_project": self.source_project,
            "module_path": self.module_path,
            "docs_path": self.docs_path,
            "input_contract": self.input_contract,
            "supported_event_types": list(self.supported_event_types),
            "cli_commands": list(self.cli_commands),
            "execution_mode": self.execution_mode,
            "production_status": self.production_status,
            "external_repo_policy": self.external_repo_policy,
        }


_AGENT_EVIDENCE_PLANE_EVENT_ORDER = (
    "agent.run.started",
    "agent.run.completed",
    "agent.run.failed",
    "failure.observed",
)
_SAFETY_GUARD_EVENT_ORDER = (
    "safety_guard.check.completed",
    "safety_guard.action.allowed",
    "safety_guard.action.blocked",
    "safety_guard.approval.required",
)
_FAILURE_LOOP_EVENT_ORDER = ("failure.observed", "rule.proposed")

if set(_AGENT_EVIDENCE_PLANE_EVENT_ORDER) != AGENT_EVIDENCE_PLANE_EVENT_TYPES:
    raise RuntimeError("agent-evidence-plane registry metadata drift")
if set(_SAFETY_GUARD_EVENT_ORDER) != SAFETY_GUARD_EVENT_TYPES:
    raise RuntimeError("Safety Guard registry metadata drift")
if set(_FAILURE_LOOP_EVENT_ORDER) != FAILURE_LOOP_EVENT_TYPES:
    raise RuntimeError("failure-loop registry metadata drift")

_ADAPTERS: tuple[AdapterDescriptor, ...] = (
    AdapterDescriptor(
        adapter_id="agent-evidence-plane",
        name="agent-evidence-plane Thin Adapter",
        source_project="agent-evidence-plane",
        module_path="curaops.evidence.adapters.agent_evidence_plane",
        docs_path="docs/MATRIX_OS_AGENT_EVIDENCE_PLANE_ADAPTER.md",
        input_contract="agent-evidence-plane JSONL schema_version 0.1.0",
        supported_event_types=_AGENT_EVIDENCE_PLANE_EVENT_ORDER,
        cli_commands=(
            "python3 -m curaops.cli.main evidence convert-agent-plane INPUT.jsonl OUTPUT.jsonl",
        ),
        execution_mode="translation-only",
        production_status="local-contract-only / not-production-runtime",
        external_repo_policy="standalone; not vendored; not modified by Matrix OS",
    ),
    AdapterDescriptor(
        adapter_id="safety-guard",
        name="Safety Guard Adapter Contract",
        source_project="CuraOps Safety Guard",
        module_path="curaops.evidence.adapters.safety_guard",
        docs_path="docs/MATRIX_OS_SAFETY_GUARD_ADAPTER.md",
        input_contract="Safety Guard result JSONL schema_version safety-guard.result.v1",
        supported_event_types=_SAFETY_GUARD_EVENT_ORDER,
        cli_commands=(
            "python3 -m curaops.cli.main evidence convert-safety-guard INPUT.jsonl OUTPUT.jsonl",
        ),
        execution_mode="translation-only",
        production_status="local-contract-only / not-production-runtime",
        external_repo_policy="standalone; not vendored; not executed by Matrix OS",
    ),
    AdapterDescriptor(
        adapter_id="failure-loop",
        name="failure-driven-loop Thin Adapter",
        source_project="failure-driven-loop",
        module_path="curaops.evidence.adapters.failure_loop",
        docs_path="docs/MATRIX_OS_FAILURE_LOOP_ADAPTER.md",
        input_contract="failure-loop result JSONL schema_version failure-loop.result.v1",
        supported_event_types=_FAILURE_LOOP_EVENT_ORDER,
        cli_commands=(
            "python3 -m curaops.cli.main evidence convert-failure-loop INPUT.jsonl OUTPUT.jsonl",
        ),
        execution_mode="translation-only",
        production_status="local-contract-only / not-production-runtime",
        external_repo_policy="standalone; not vendored; not executed by Matrix OS",
    ),
)


def list_adapter_descriptors() -> tuple[AdapterDescriptor, ...]:
    """Return all registered Matrix OS evidence adapters."""

    return _ADAPTERS


def get_adapter_descriptor(adapter_id: str) -> AdapterDescriptor:
    """Return one adapter descriptor or fail closed for unknown ids."""

    for descriptor in _ADAPTERS:
        if descriptor.adapter_id == adapter_id:
            return descriptor
    raise ValidationError(f"unknown evidence adapter: {adapter_id}")
