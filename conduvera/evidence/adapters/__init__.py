"""Matrix OS evidence adapters for external evidence producers."""

from conduvera.evidence.adapters.agent_evidence_plane import (
    AGENT_EVIDENCE_PLANE_EVENT_TYPES,
    convert_agent_evidence_plane_jsonl,
    translate_agent_evidence_plane_event,
)
from conduvera.evidence.adapters.failure_loop import (
    FAILURE_LOOP_EVENT_TYPES,
    convert_failure_loop_jsonl,
    translate_failure_loop_result,
)
from conduvera.evidence.adapters.registry import (
    AdapterDescriptor,
    get_adapter_descriptor,
    list_adapter_descriptors,
)
from conduvera.evidence.adapters.safety_guard import (
    SAFETY_GUARD_EVENT_TYPES,
    convert_safety_guard_jsonl,
    translate_safety_guard_result,
)

__all__ = [
    "AGENT_EVIDENCE_PLANE_EVENT_TYPES",
    "FAILURE_LOOP_EVENT_TYPES",
    "SAFETY_GUARD_EVENT_TYPES",
    "AdapterDescriptor",
    "convert_agent_evidence_plane_jsonl",
    "convert_failure_loop_jsonl",
    "convert_safety_guard_jsonl",
    "get_adapter_descriptor",
    "list_adapter_descriptors",
    "translate_agent_evidence_plane_event",
    "translate_failure_loop_result",
    "translate_safety_guard_result",
]
