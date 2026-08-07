"""
Compliance Change Control — Public API.

This package provides the canonical C core implementation.

Consumed by:
  - conduvera.cli.commands.cr  (CLI)
  - conduvera.skills.accountable_agent  (B layer, future)
"""

from .models import (
    ChangeRequest,
    ChangeType,
    CRStatus,
    ImpactLevel,
    RequirementLinkageType,
    RootCauseCategory,
    SafetyImpact,
    VerificationCase,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)
from .state_machine import (
    CRStateMachine,
    InvalidTransitionError,
    MissingFieldsError,
)
from .validation import CRValidator
from .evidence import (
    CREvidenceGenerator,
    SCHEMA_VERSION as EVIDENCE_SCHEMA_VERSION,
    verify_evidence_file,
)
from .persistence import CRPersistence, VCPersistence
from .service import ChangeRequestService, VerificationService

__all__ = [
    # Models
    "ChangeRequest",
    "ChangeType",
    "CRStatus",
    "ImpactLevel",
    "RequirementLinkageType",
    "RootCauseCategory",
    "SafetyImpact",
    "VerificationCase",
    "VerificationResult",
    "VerificationStatus",
    "VerificationType",
    # State Machine
    "CRStateMachine",
    "InvalidTransitionError",
    "MissingFieldsError",
    # Validation
    "CRValidator",
    # Evidence
    "CREvidenceGenerator",
    "EVIDENCE_SCHEMA_VERSION",
    "verify_evidence_file",
    # Persistence
    "CRPersistence",
    "VCPersistence",
    # Services
    "ChangeRequestService",
    "VerificationService",
]
