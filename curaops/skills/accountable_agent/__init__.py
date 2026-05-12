"""
Accountable Agent Service — Accountable Agent Layer v2.1.0

Thin accountability layer on top of Compliance Change Control v2.0.0.

Captures agent identity, context, and intent for AI-assisted changes.
Ensures mandatory accountability links (CR + requirements) are present.
Generates evidence packets for audit trail.

v2.1.0 additions (HIGH blocker fixes):
- Formal state machine with transition guards (Accountable Agent Layer process §C)
- Bugfix-specific blocking rules consumed from Compliance Change Control (Accountable Agent Layer rules §3.1, §7.1)
- pre_flight_check() session gate (Accountable Agent Layer rules §5.1 and process §D.1)
- reset() transition support (Accountable Agent Layer process §C.3)

Dependencies:
    - change-request (Compliance Change Control v2.0.0): CR lifecycle, validation, evidence
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

from curaops.skills.change_request import (
    CRStatus,
    ChangeRequestService,
    verify_evidence_file,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class AccountabilityError(Exception):
    """Raised when accountability requirements are not met."""
    pass


class MissingMandatoryLinkError(AccountabilityError):
    """Raised when mandatory CR or requirement link is missing."""
    pass


class InvalidACTransitionError(AccountabilityError):
    """Raised when an AccountableChange state transition is not allowed.

    B-PROCESS §C.2: Only transitions in the matrix are valid.
    B-PROCESS §G.2: Exit code 3 for invalid transition.
    """
    pass


# ── State Machine ───────────────────────────────────────────────────────


class ACStatus(Enum):
    """Accountable Change states — B-PROCESS §C.1.

    | State    | Code | Definition                          |
    |----------|------|--------------------------------------|
    | PENDING  | P    | Created, awaiting validation         |
    | LINKED   | L    | CR linked, requirements present      |
    | VALIDATED| V    | Validation passed                    |
    | BLOCKED  | B    | Validation failed, work stopped      |
    """
    PENDING = "pending"
    LINKED = "linked"
    VALIDATED = "validated"
    BLOCKED = "blocked"


# Transition matrix — B-PROCESS §C.2
#
#   From → To  | P | L | V | B |
#   -----------|---|---|---|---|
#   P          | - | Y | N | Y |
#   L          | N | - | Y | Y |
#   V          | N | N | - | N |
#   B          | Y | N | N | - |
#
_VALID_AC_TRANSITIONS: Dict[str, Set[str]] = {
    "pending":   {"linked", "blocked"},
    "linked":    {"validated", "blocked"},
    "validated": set(),           # terminal
    "blocked":   {"pending"},     # reset only
}


# ── Data Classes ────────────────────────────────────────────────────────


@dataclass
class AgentContext:
    """Captures agent identity and execution context."""
    agent_id: str
    agent_name: str
    model: str
    tools_used: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    platform: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentContext":
        return cls(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            model=data["model"],
            tools_used=list(data.get("tools_used") or []),
            session_id=data.get("session_id"),
            platform=data.get("platform"),
        )


@dataclass
class ChangeIntent:
    """Captures the intent and scope of an AI-assisted change."""
    description: str
    change_type: str  # e.g., "feature", "bugfix", "refactor", "test"
    files_affected: List[str] = field(default_factory=list)
    estimated_impact: Optional[str] = None
    justification: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeIntent":
        return cls(
            description=data["description"],
            change_type=data["change_type"],
            files_affected=list(data.get("files_affected") or []),
            estimated_impact=data.get("estimated_impact"),
            justification=data.get("justification"),
        )


@dataclass
class AccountableChange:
    """
    Complete accountable change record.
    Links agent context + change intent to CR + requirements.
    """
    accountable_id: str
    agent_context: AgentContext
    change_intent: ChangeIntent
    cr_id: Optional[str] = None
    requirement_refs: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, linked, validated, blocked
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    evidence_path: Optional[str] = None
    block_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accountable_id": self.accountable_id,
            "agent_context": self.agent_context.to_dict(),
            "change_intent": self.change_intent.to_dict(),
            "cr_id": self.cr_id,
            "requirement_refs": self.requirement_refs,
            "status": self.status,
            "created_at": self.created_at,
            "evidence_path": self.evidence_path,
            "block_reason": self.block_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountableChange":
        return cls(
            accountable_id=data["accountable_id"],
            agent_context=AgentContext.from_dict(data["agent_context"]),
            change_intent=ChangeIntent.from_dict(data["change_intent"]),
            cr_id=data.get("cr_id"),
            requirement_refs=list(data.get("requirement_refs") or []),
            status=data.get("status", "pending"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            evidence_path=data.get("evidence_path"),
            block_reason=data.get("block_reason"),
        )


# ── Valid ID Patterns ───────────────────────────────────────────────────

_VALID_ID_PATTERNS = [
    re.compile(r"^SW-REQ-\d+$"),
    re.compile(r"^SYS-REQ-\d+$"),
    re.compile(r"^SW-ARCH-\d+$"),
    re.compile(r"^SEC-REQ-\d+$"),
    re.compile(r"^REQ-\d+$"),
    re.compile(r"^[A-Z]+-REQ-[A-Z]+-\d+$"),  # e.g. SW-REQ-AUTH-001
]


# ── Service ─────────────────────────────────────────────────────────────


class AccountableAgentService:
    """
    Service for managing accountable AI-assisted changes.
    Thin layer on top of ChangeRequestService (C core v2.0.0).

    Per C-RULES §7, this consumes the C core's public API:
      - ChangeRequestService for CR lifecycle
      - CREvidenceGenerator for evidence generation
      - VerificationService for verification case management

    State machine per B-PROCESS §C:
      P → L (link), L → V (validate), P/L → B (block), B → P (reset)
    """

    # Mandatory fields for accountability
    MANDATORY_LINKS = ["cr_id", "requirement_refs"]

    def __init__(
        self,
        project_root: Optional[Path] = None,
        changes_path: Optional[Path] = None,
        evidence_dir: Optional[Path] = None,
    ):
        self.project_root = project_root or Path.cwd()
        changes_dir = changes_path or self.project_root / "changes"
        self.evidence_dir = evidence_dir or changes_dir / "evidence"

        # Ensure directories exist
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # Initialize C core services (v2.0.0 API)
        self.cr_service = ChangeRequestService(
            changes_dir=changes_dir,
            evidence_dir=self.evidence_dir,
        )

        # Track accountable changes in a small on-disk store so CLI commands
        # can register in one process and validate/evidence in later commands.
        self.accountable_dir = changes_dir / "accountable"
        self.accountable_dir.mkdir(parents=True, exist_ok=True)
        self._accountable_changes: Dict[str, AccountableChange] = {}
        self._load_accountable_changes()

        logger.info(f"AccountableAgentService initialized: {self.project_root}")

    # ── Persistence ─────────────────────────────────────────────────────

    def _accountable_path(self, accountable_id: str) -> Path:
        return self.accountable_dir / f"{accountable_id}.json"

    def _load_accountable_changes(self) -> None:
        """Load persisted accountable changes for process-to-process CLI use."""
        for path in sorted(self.accountable_dir.glob("AC-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                ac = AccountableChange.from_dict(data)
                self._accountable_changes[ac.accountable_id] = ac
            except Exception as exc:
                logger.warning("Skipping invalid accountable change %s: %s", path, exc)

    def _save_accountable_change(self, ac: AccountableChange) -> Path:
        self.accountable_dir.mkdir(parents=True, exist_ok=True)
        path = self._accountable_path(ac.accountable_id)
        path.write_text(json.dumps(ac.to_dict(), indent=2), encoding="utf-8")
        return path

    # ── State Machine ──────────────────────────────────────────────────

    def _can_transition(self, ac: AccountableChange, new_status: str) -> bool:
        """Check if transition is allowed per B-PROCESS §C.2."""
        allowed = _VALID_AC_TRANSITIONS.get(ac.status, set())
        return new_status in allowed

    def _transition(
        self,
        ac: AccountableChange,
        new_status: str,
        reason: str = "",
    ) -> None:
        """Execute state transition with guard check.

        Raises:
            InvalidACTransitionError: if transition not in matrix
        """
        if not self._can_transition(ac, new_status):
            raise InvalidACTransitionError(
                f"Cannot transition {ac.status} → {new_status} "
                f"for {ac.accountable_id}"
            )
        ac.status = new_status
        if new_status == "blocked" and reason:
            ac.block_reason = reason
        elif new_status != "blocked":
            ac.block_reason = None

    def reset(self, accountable_id: str) -> AccountableChange:
        """Reset a blocked AccountableChange back to pending (B→P).

        B-PROCESS §C.3: B → P via reset(), developer addresses blocking issue.

        Args:
            accountable_id: The blocked accountable change to reset

        Returns:
            Updated AccountableChange with status='pending'

        Raises:
            AccountabilityError: if AC not found
            InvalidACTransitionError: if AC is not in blocked state
        """
        if accountable_id not in self._accountable_changes:
            raise AccountabilityError(
                f"Unknown accountable change: {accountable_id}"
            )

        ac = self._accountable_changes[accountable_id]
        self._transition(ac, "pending", reason="Developer reset")
        self._save_accountable_change(ac)
        logger.info(f"Reset {accountable_id}: blocked → pending")
        return ac

    # ── ID Validation ──────────────────────────────────────────────────

    @staticmethod
    def _is_valid_id_format(ref_id: str) -> bool:
        """Validate requirement ID format against known patterns."""
        return any(p.match(ref_id) for p in _VALID_ID_PATTERNS)

    # ── Bugfix-Specific Checks ─────────────────────────────────────────

    def _check_bugfix_blocking(
        self,
        cr,
        requirement_refs: List[str],
    ) -> tuple:
        """Bugfix-specific blocking/warning rules consumed from C.

        B-RULES §3.1 (hard blocks), §3.2 (warnings).
        B-RULES §7.1: B consumes bugfix semantics from C, not separate.

        Returns:
            (blocks_list, warnings_list)
        """
        from curaops.skills.change_request import (
            ChangeType,
            RequirementLinkageType,
        )

        blocks: List[str] = []
        warnings: List[str] = []

        # Only apply if CR change_type is bugfix
        if cr.change_type != ChangeType.BUGFIX:
            return blocks, warnings

        # BLOCK: Bugfix without SW-REQ linkage (C-RULES §9.1)
        has_sw_req = any(
            ref.startswith("SW-REQ") for ref in requirement_refs
        )
        if not has_sw_req:
            blocks.append(
                "Bugfix CR has no SW-REQ linkage (C-RULES §9.1)"
            )

        # BLOCK: Bugfix new_ref SW-REQ not APPROVED (C-RULES §9.3)
        if cr.requirement_linkage_type == RequirementLinkageType.NEW_REF:
            blocks.append(
                "Bugfix new SW-REQ not APPROVED (C-RULES §9.3)"
            )

        # BLOCK: Bugfix at IMPLEMENTED+ without VerificationCases
        # (C-RULES §9.4)
        if cr.status.value in ("implemented", "verified", "closed"):
            if not cr.affected_verifications:
                blocks.append(
                    "Bugfix at IMPLEMENTED with no VerificationCases "
                    "(C-RULES §9.4)"
                )

        # WARN: No regression VerificationCase at IN_PROGRESS
        if cr.status.value == "in_progress":
            if not cr.affected_verifications:
                warnings.append(
                    "No regression VerificationCase linked "
                    "(required at IMPLEMENTED)"
                )

        # WARN: Root-cause category not documented
        if not cr.root_cause_category:
            warnings.append(
                "Root-cause category not documented "
                "(recommended for non-safety)"
            )

        return blocks, warnings

    # ── Pre-Flight Check ───────────────────────────────────────────────

    def pre_flight_check(
        self,
        cr_id: str,
        requirement_refs: List[str],
        change_type: str = "feature",
        impact_level: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Pre-flight gate — checks before ANY AI work starts.

        B-RULES §5.1, §6: Blocks AI changes without CR + requirement linkage.
        B-PROCESS §D.1: Intervention Point 1.

        Checks:
            - CR exists in changes/
            - CR.status = APPROVED
            - Requirement refs present (min 1)
            - ID formats valid
            - Impact classification consistent
            - Bugfix-specific rules from C (B-RULES §3.1, §7.1)

        Returns:
            Dict with 'passed' (bool), 'blocks' (list), 'warnings' (list)
        """
        blocks: List[str] = []
        warnings: List[str] = []

        # Check 1: CR exists
        try:
            cr = self.cr_service.get_cr(cr_id)
        except FileNotFoundError:
            blocks.append(f"CR {cr_id} does not exist in changes/")
            return {"passed": False, "blocks": blocks, "warnings": warnings}
        except Exception as e:
            blocks.append(f"Cannot load CR {cr_id}: {e}")
            return {"passed": False, "blocks": blocks, "warnings": warnings}

        # Check 2: CR status = APPROVED (B-RULES §3.1)
        if cr.status != CRStatus.APPROVED:
            blocks.append(
                f"CR {cr_id} status is {cr.status.value}, must be APPROVED"
            )

        # Check 3: Requirement refs present (min 1)
        if not requirement_refs:
            blocks.append(
                "No requirement refs. Minimum SW-REQ required."
            )

        # Check 4: ID format validation (B-RULES §3.1)
        invalid_ids = [
            ref for ref in requirement_refs
            if not self._is_valid_id_format(ref)
        ]
        if invalid_ids:
            blocks.append(f"Invalid ID format: {invalid_ids}")

        # Check 5: Impact classification consistency (B-RULES §3, §4)
        if impact_level:
            has_sys = "SYS" in impact_level
            has_arch = "ARCH" in impact_level
            has_sys_req = any(
                ref.startswith("SYS-REQ") for ref in requirement_refs
            )
            has_sw_arch = any(
                ref.startswith("SW-ARCH") for ref in requirement_refs
            )

            if has_sys and not has_sys_req:
                blocks.append(
                    "SYS impact detected but no SYS-REQ linked"
                )
            if has_arch and not has_sw_arch:
                blocks.append(
                    "ARCH impact detected but no SW-ARCH linked"
                )

        # Check 6: Bugfix-specific blocking rules from C
        # (B-RULES §3.1, §7.1)
        bugfix_blocks, bugfix_warnings = self._check_bugfix_blocking(
            cr, requirement_refs
        )
        blocks.extend(bugfix_blocks)
        warnings.extend(bugfix_warnings)

        passed = len(blocks) == 0
        return {"passed": passed, "blocks": blocks, "warnings": warnings}

    # ── Registration ───────────────────────────────────────────────────

    def register_accountable_change(
        self,
        agent_context: AgentContext,
        change_intent: ChangeIntent,
        cr_id: Optional[str] = None,
        requirement_refs: Optional[List[str]] = None,
        strict: bool = True,
    ) -> AccountableChange:
        """
        Register an accountable change attempt.

        In strict mode with cr_id provided, the pre-flight gate runs
        automatically (B-RULES §5.1, B-PROCESS §D.1). If the gate fails,
        registration is blocked with MissingMandatoryLinkError.

        Args:
            agent_context: Who/what is making the change
            change_intent: What is being changed and why
            cr_id: Optional existing CR to link
            requirement_refs: Optional requirement IDs to link
            strict: If True, fail if mandatory links are missing

        Returns:
            AccountableChange record

        Raises:
            MissingMandatoryLinkError: If strict=True and links missing or
                pre-flight gate fails
        """
        accountable_id = f"AC-{uuid.uuid4().hex[:8].upper()}"

        # Validate mandatory links
        missing = []
        if not cr_id:
            missing.append("cr_id")
        if not requirement_refs:
            missing.append("requirement_refs")

        if strict and missing:
            raise MissingMandatoryLinkError(
                f"Accountable change {accountable_id} blocked: "
                f"missing mandatory links: {', '.join(missing)}. "
                f"Agent: {agent_context.agent_name}, "
                f"Intent: {change_intent.description[:50]}..."
            )

        # Pre-flight gate (B-RULES §5.1): when strict and CR provided,
        # run the full pre-flight check before accepting registration.
        if strict and cr_id and requirement_refs:
            pf = self.pre_flight_check(
                cr_id=cr_id,
                requirement_refs=requirement_refs,
                change_type=change_intent.change_type,
            )
            if not pf["passed"]:
                raise MissingMandatoryLinkError(
                    f"Pre-flight gate BLOCKED for {accountable_id}: "
                    f"{'; '.join(pf['blocks'])}"
                )

        accountable_change = AccountableChange(
            accountable_id=accountable_id,
            agent_context=agent_context,
            change_intent=change_intent,
            cr_id=cr_id,
            requirement_refs=requirement_refs or [],
            status="linked" if (cr_id and requirement_refs) else "pending",
        )

        self._accountable_changes[accountable_id] = accountable_change
        self._save_accountable_change(accountable_change)

        logger.info(f"Registered accountable change: {accountable_id}")
        return accountable_change

    def link_to_cr(
        self,
        accountable_id: str,
        cr_id: str,
    ) -> AccountableChange:
        """Link an accountable change to an existing CR.

        Transitions PENDING → LINKED if requirement_refs present.
        Uses state machine guard — raises if not PENDING.

        Raises:
            AccountabilityError: if AC not found
            InvalidACTransitionError: if transition not allowed
        """
        if accountable_id not in self._accountable_changes:
            raise AccountabilityError(
                f"Unknown accountable change: {accountable_id}"
            )

        ac = self._accountable_changes[accountable_id]
        ac.cr_id = cr_id

        # Update status via state machine
        if ac.requirement_refs:
            self._transition(ac, "linked")
        else:
            logger.info(
                f"CR linked but no requirement_refs yet — "
                f"staying {ac.status}"
            )

        logger.info(f"Linked {accountable_id} to CR {cr_id}")
        self._save_accountable_change(ac)
        return ac

    def validate_accountability(
        self,
        accountable_id: str,
        check_traceability: bool = True,
    ) -> Dict[str, Any]:
        """
        Validate an accountable change has all required links and evidence.

        Uses state machine for transitions:
            LINKED → VALIDATED (all checks pass)
            PENDING/LINKED → BLOCKED (blocking condition)

        Args:
            accountable_id: The accountable change ID
            check_traceability: Whether to validate via C core validator

        Returns:
            Validation result dict with status and details
        """
        if accountable_id not in self._accountable_changes:
            return {
                "valid": False,
                "error": f"Unknown accountable change: {accountable_id}",
            }

        ac = self._accountable_changes[accountable_id]
        issues = []

        # Check mandatory links
        if not ac.cr_id:
            issues.append("Missing CR link")
        if not ac.requirement_refs:
            issues.append("Missing requirement references")

        # Check CR exists and is valid (via C core v2.0.0)
        traceability_result = None
        cr_obj = None
        if check_traceability and ac.cr_id:
            try:
                cr = self.cr_service.get_cr(ac.cr_id)
                cr_obj = cr
                approved_or_later = {
                    CRStatus.APPROVED,
                    CRStatus.IN_PROGRESS,
                    CRStatus.IMPLEMENTED,
                    CRStatus.VERIFIED,
                    CRStatus.CLOSED,
                }
                if cr.status not in approved_or_later:
                    issues.append(
                        f"CR {ac.cr_id} status is {cr.status.value}, must be APPROVED or later"
                    )
                # Validate CR has no blocking issues
                cr_issues = self.cr_service.validate_cr(ac.cr_id)
                blocking = [
                    i for i in cr_issues if i["severity"] == "BLOCKING"
                ]
                if blocking:
                    for b in blocking:
                        issues.append(f"CR validation: {b['message']}")
                traceability_result = {
                    "cr_id": ac.cr_id,
                    "cr_status": cr.status.value,
                    "blocking_issues": len(blocking),
                    "total_issues": len(cr_issues),
                }
            except FileNotFoundError:
                issues.append(f"Linked CR {ac.cr_id} does not exist")
            except Exception as e:
                issues.append(f"Traceability validation failed: {e}")

        # Bugfix-specific checks consumed from C
        # (B-RULES §3.1, §7.1)
        if cr_obj is not None:
            bugfix_blocks, _ = self._check_bugfix_blocking(
                cr_obj, ac.requirement_refs
            )
            issues.extend(bugfix_blocks)

        is_valid = len(issues) == 0

        # Transition via state machine
        if is_valid:
            if ac.status in ("pending", "linked"):
                self._transition(ac, "validated")
        else:
            if ac.status in ("pending", "linked"):
                self._transition(ac, "blocked", reason="; ".join(issues))
            # Terminal states (validated/blocked from other paths)
            # are not transitioned further per §C.2 matrix

        self._save_accountable_change(ac)

        return {
            "valid": is_valid,
            "accountable_id": accountable_id,
            "cr_id": ac.cr_id,
            "requirement_refs": ac.requirement_refs,
            "issues": issues,
            "traceability": traceability_result,
        }

    def _linked_cr_for(self, ac: AccountableChange):
        """Load the linked Compliance Change Control CR if available."""
        if not ac.cr_id:
            return None
        try:
            return self.cr_service.get_cr(ac.cr_id)
        except Exception as exc:
            logger.warning("Could not load linked CR %s: %s", ac.cr_id, exc)
            return None

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return getattr(value, "value", value)

    def _bugfix_context_for(self, ac: AccountableChange, cr: Any) -> Optional[Dict[str, Any]]:
        """Build bugfix metadata from the linked C CR without duplicating C lifecycle."""
        if ac.change_intent.change_type != "bugfix":
            return None

        regression_ids = list(getattr(cr, "affected_verifications", []) or []) if cr else []
        warnings: List[str] = []
        if not regression_ids:
            warnings.append("No regression VerificationCase linked (required at IMPLEMENTED)")

        return {
            "change_type": "bugfix",
            "requirement_linkage_type": self._enum_value(getattr(cr, "requirement_linkage_type", None)) if cr else None,
            "root_cause_category": self._enum_value(getattr(cr, "root_cause_category", None)) if cr else None,
            "escalation_triggers_met": [],
            "regression_verification_ids": regression_ids,
            "regression_verification_semantics": (
                "linked_from_cr_affected_verifications"
                if regression_ids
                else "no_regression_verification_linked_on_cr"
            ),
            "warnings": warnings,
        }

    def _referenced_c_evidence_for(self, ac: AccountableChange) -> Dict[str, Any]:
        """Generate/reference C evidence explicitly, or record why unavailable."""
        if not ac.cr_id:
            return {
                "available": False,
                "cr_evidence_path": None,
                "integrity_verified": False,
                "hash": None,
                "verification": None,
                "unavailable_reason": "no linked CR",
            }
        try:
            cr_evidence_path = self.cr_service.generate_evidence(ac.cr_id)
            verification = verify_evidence_file(cr_evidence_path)
            if verification["valid"]:
                return {
                    "available": True,
                    "cr_evidence_path": str(cr_evidence_path),
                    "integrity_verified": True,
                    "hash": verification["stored_hash"],
                    "verification": verification,
                    "unavailable_reason": None,
                }
            return {
                "available": False,
                "cr_evidence_path": str(cr_evidence_path),
                "integrity_verified": False,
                "hash": verification.get("stored_hash"),
                "verification": verification,
                "unavailable_reason": verification.get("reason") or "integrity_verification_failed",
            }
        except Exception as exc:
            logger.warning(f"Could not generate CR evidence: {exc}")
            return {
                "available": False,
                "cr_evidence_path": None,
                "integrity_verified": False,
                "hash": None,
                "verification": None,
                "unavailable_reason": str(exc),
            }

    def generate_accountability_evidence(
        self,
        accountable_id: str,
        output_format: str = "json",
    ) -> str:
        """
        Generate evidence packet for an accountable change.
        Combines agent context, change intent, CR linkage, validation results,
        linked C evidence, and bugfix metadata required by AAL docs.

        Args:
            accountable_id: The accountable change ID
            output_format: "json" or "markdown"

        Returns:
            Path to generated evidence file
        """
        if accountable_id not in self._accountable_changes:
            raise AccountabilityError(
                f"Unknown accountable change: {accountable_id}"
            )

        ac = self._accountable_changes[accountable_id]

        # Validate first
        validation = self.validate_accountability(accountable_id)
        cr = self._linked_cr_for(ac)
        referenced_c_evidence = self._referenced_c_evidence_for(ac)
        cr_evidence = referenced_c_evidence["cr_evidence_path"]

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        evidence_filename = f"{accountable_id}_{timestamp}.{output_format if output_format == 'json' else 'md'}"
        evidence_file = self.evidence_dir / evidence_filename

        accountable_change = ac.to_dict()
        accountable_change["accountability_links"] = {
            "cr_id": ac.cr_id,
            "requirement_refs": ac.requirement_refs,
        }
        if cr:
            accountable_change["linked_cr_metadata"] = {
                "change_type": self._enum_value(cr.change_type),
                "requirement_linkage_type": self._enum_value(cr.requirement_linkage_type),
                "root_cause_category": self._enum_value(cr.root_cause_category),
                "regression_verification_ids": list(cr.affected_verifications or []),
                "status": self._enum_value(cr.status),
            }
        bugfix_context = self._bugfix_context_for(ac, cr)
        accountable_change["bugfix_context"] = bugfix_context

        # Build evidence packet
        evidence = {
            "schema_version": "AAL-1.0.0",
            "accountable_change": accountable_change,
            "bugfix_context": bugfix_context,
            "validation": validation,
            "referenced_c_evidence": referenced_c_evidence,
            # Backward-compatible alias used by older docs/code.
            "cr_evidence_path": cr_evidence,
            "evidence_chain": {
                "this_evidence": str(evidence_file),
                "linked_cr": str(self.project_root / "changes" / f"{ac.cr_id}.md") if ac.cr_id else None,
                "linked_cr_evidence": cr_evidence,
                "chain_integrity": "verified" if referenced_c_evidence["integrity_verified"] else "incomplete",
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "service_version": "B-2.1.0",
        }

        # Write evidence file
        if output_format == "json":
            with open(evidence_file, "w") as f:
                json.dump(evidence, f, indent=2)
        else:
            with open(evidence_file, "w") as f:
                f.write(self._format_evidence_markdown(evidence))

        ac.evidence_path = str(evidence_file)
        self._save_accountable_change(ac)
        logger.info(f"Generated evidence: {evidence_file}")

        return str(evidence_file)

    def _format_evidence_markdown(self, evidence: Dict[str, Any]) -> str:
        """Format evidence as markdown report."""
        ac = evidence["accountable_change"]
        val = evidence["validation"]

        lines = [
            "# Accountability Evidence Report",
            "",
            f"**Accountable ID:** {ac['accountable_id']}",
            f"**Generated:** {evidence['generated_at']}",
            f"**Service Version:** {evidence['service_version']}",
            "",
            "## Agent Context",
            "",
            f"- **Agent ID:** {ac['agent_context']['agent_id']}",
            f"- **Agent Name:** {ac['agent_context']['agent_name']}",
            f"- **Model:** {ac['agent_context']['model']}",
            (
                f"- **Tools Used:** "
                f"{', '.join(ac['agent_context']['tools_used'])}"
            ),
            f"- **Session ID:** {ac['agent_context'].get('session_id', 'N/A')}",
            "",
            "## Change Intent",
            "",
            f"- **Type:** {ac['change_intent']['change_type']}",
            f"- **Description:** {ac['change_intent']['description']}",
            (
                f"- **Files Affected:** "
                f"{', '.join(ac['change_intent']['files_affected'])}"
            ),
            f"- **Justification:** "
            f"{ac['change_intent'].get('justification', 'N/A')}",
            "",
            "## Accountability Links",
            "",
            f"- **CR ID:** {ac['cr_id'] or 'NOT LINKED'}",
            (
                f"- **Requirements:** "
                f"{', '.join(ac['requirement_refs']) if ac['requirement_refs'] else 'NONE'}"
            ),
            f"- **Status:** {ac['status']}",
            "",
            "## Validation Results",
            "",
            f"- **Valid:** {'✅ YES' if val['valid'] else '❌ NO'}",
        ]

        if val.get("issues"):
            lines.extend(["", "### Issues", ""])
            for issue in val["issues"]:
                lines.append(f"- ❌ {issue}")

        if ac.get("block_reason"):
            lines.extend(["", f"**Block Reason:** {ac['block_reason']}"])

        lines.extend([
            "",
            "## Evidence Chain",
            "",
            f"- This accountable change: `{ac['accountable_id']}`",
            (
                f"- Linked CR: `{ac['cr_id']}`"
                if ac['cr_id']
                else "- Linked CR: NONE"
            ),
            f"- CR Evidence: `{evidence.get('cr_evidence_path', 'N/A')}`",
        ])

        return "\n".join(lines)


# ── Convenience functions for CLI/API usage ──────────────────────────


def submit_change_request(
    project_path: str,
    title: str,
    description: str,
    requirement_refs=None,
    impact_level: str = "SW",
    justification: str = "",
):
    """
    Create and submit a CR using the C core v2.0.0 API.

    Returns dict with cr_id, title, status (mirrors legacy return shape).
    """
    changes_dir = Path(project_path) / "changes"
    evidence_dir = changes_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    svc = ChangeRequestService(
        changes_dir=changes_dir,
        evidence_dir=evidence_dir,
    )

    # Create in DRAFT, then submit
    cr = svc.create_cr(
        title=title,
        requester="accountable-agent",
        problem=description,
        justification=justification or description,
        impact_level=[impact_level],
        requirement_refs=requirement_refs or [],
    )
    cr = svc.submit_cr(cr.id)

    return {
        "cr_id": cr.id,
        "title": cr.title,
        "status": cr.status.value,
    }


def create_accountable_change(
    project_path: str,
    agent_id: str,
    agent_name: str,
    model: str,
    change_description: str,
    change_type: str,
    cr_id: Optional[str] = None,
    requirement_refs: Optional[List[str]] = None,
    tools_used: Optional[List[str]] = None,
    files_affected: Optional[List[str]] = None,
    strict: bool = True,
) -> Dict[str, Any]:
    """
    High-level function to create an accountable change.

    Returns:
        Dict with accountable_change and status
    """
    service = AccountableAgentService(project_root=Path(project_path))

    agent_context = AgentContext(
        agent_id=agent_id,
        agent_name=agent_name,
        model=model,
        tools_used=tools_used or [],
    )

    change_intent = ChangeIntent(
        description=change_description,
        change_type=change_type,
        files_affected=files_affected or [],
    )

    try:
        accountable_change = service.register_accountable_change(
            agent_context=agent_context,
            change_intent=change_intent,
            cr_id=cr_id,
            requirement_refs=requirement_refs,
            strict=strict,
        )

        return {
            "success": True,
            "accountable_id": accountable_change.accountable_id,
            "status": accountable_change.status,
            "cr_id": accountable_change.cr_id,
            "requirement_refs": accountable_change.requirement_refs,
        }
    except MissingMandatoryLinkError as e:
        return {
            "success": False,
            "error": str(e),
            "blocked": True,
        }


def validate_accountable_change(
    project_path: str,
    accountable_id: str,
) -> Dict[str, Any]:
    """Validate an accountable change exists and meets requirements."""
    service = AccountableAgentService(project_root=Path(project_path))
    return service.validate_accountability(accountable_id)


def generate_accountability_report(
    project_path: str,
    accountable_id: str,
    output_format: str = "json",
) -> Dict[str, Any]:
    """Generate evidence report for an accountable change."""
    service = AccountableAgentService(project_root=Path(project_path))

    try:
        evidence_path = service.generate_accountability_evidence(
            accountable_id, output_format
        )
        return {
            "success": True,
            "evidence_path": evidence_path,
            "format": output_format,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


__all__ = [
    # State Machine
    "ACStatus",
    "InvalidACTransitionError",
    # Data Classes
    "AgentContext",
    "ChangeIntent",
    "AccountableChange",
    # Service
    "AccountableAgentService",
    # Errors
    "AccountabilityError",
    "MissingMandatoryLinkError",
    # Convenience functions
    "submit_change_request",
    "create_accountable_change",
    "validate_accountable_change",
    "generate_accountability_report",
]
