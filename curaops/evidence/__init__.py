"""Matrix OS evidence backbone adapter contract.

This package is the Matrix OS harness-side contract only. It does not import,
copy, or run the separately maintainable agent-evidence-plane project.
"""

from curaops.evidence.contract import (
    ADAPTER_EVENT_TYPES,
    CORE_EVENT_TYPES,
    EVENT_TYPES,
    SCHEMA_VERSION,
    EventEnvelope,
    EvidenceProducer,
    ValidationError,
)
from curaops.evidence.store import (
    EvidenceStore,
    default_event_store_path,
    summarize_event_stream,
    validate_event_stream,
)

__all__ = [
    "ADAPTER_EVENT_TYPES",
    "CORE_EVENT_TYPES",
    "EVENT_TYPES",
    "SCHEMA_VERSION",
    "EventEnvelope",
    "EvidenceProducer",
    "EvidenceStore",
    "ValidationError",
    "default_event_store_path",
    "summarize_event_stream",
    "validate_event_stream",
]
