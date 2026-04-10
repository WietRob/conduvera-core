"""
Accountable Agent Service - Context B Implementation
Thin accountability layer on top of Compliance-CR (Context C)

Captures agent identity, context, and intent for AI-assisted changes.
Ensures mandatory accountability links (CR + requirements) are present.
Generates evidence packets for audit trail.

Dependencies:
    - change-request (Context C): CR creation, requirement linking, evidence
    - aspice-link-manager: Traceability validation
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Import C core services - use importlib to handle non-package imports
import sys
import importlib.util

# Load change_request module
change_request_path = Path(__file__).parent.parent / "change-request" / "__init__.py"
spec_cr = importlib.util.spec_from_file_location("change_request", change_request_path)
change_request = importlib.util.module_from_spec(spec_cr)
sys.modules["change_request"] = change_request
spec_cr.loader.exec_module(change_request)

# Load aspice_link_manager module
aspice_path = Path(__file__).parent.parent / "aspice-link-manager" / "__init__.py"
spec_alm = importlib.util.spec_from_file_location("aspice_link_manager", aspice_path)
aspice_link_manager = importlib.util.module_from_spec(spec_alm)
sys.modules["aspice_link_manager"] = aspice_link_manager
spec_alm.loader.exec_module(aspice_link_manager)

ChangeRequestService = change_request.ChangeRequestService
# Note: submit_change_request is a method, not a standalone function
generate_cr_evidence = change_request.generate_cr_evidence
validate_cr_traceability = change_request.validate_cr_traceability
ASPICELinkManager = aspice_link_manager.ASPICELinkManager

# Wrapper function for convenience
def submit_change_request(project_path: str, title: str, description: str, requirement_refs=None):
    """Wrapper to create CR using ChangeRequestService."""
    service = ChangeRequestService(
        changes_path=Path(project_path) / "changes",
        project_root=Path(project_path),
    )
    return service.submit_change_request(
        title=title,
        description=description,
        requirement_refs=requirement_refs,
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AccountabilityError(Exception):
    """Raised when accountability requirements are not met."""
    pass


class MissingMandatoryLinkError(AccountabilityError):
    """Raised when mandatory CR or requirement link is missing."""
    pass


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
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
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


class AccountableAgentService:
    """
    Service for managing accountable AI-assisted changes.
    Thin layer on top of ChangeRequestService (C core).
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
        self.changes_path = changes_path or self.project_root / "changes"
        self.evidence_dir = evidence_dir or self.project_root / "changes" / "evidence"
        
        # Ensure directories exist
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize C core services
        self.cr_service = ChangeRequestService(
            changes_path=self.changes_path,
            project_root=self.project_root,
        )
        
        # Track accountable changes in memory (could persist to file)
        self._accountable_changes: Dict[str, AccountableChange] = {}
        
        logger.info(f"AccountableAgentService initialized: {self.project_root}")
    
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
        
        Args:
            agent_context: Who/what is making the change
            change_intent: What is being changed and why
            cr_id: Optional existing CR to link
            requirement_refs: Optional requirement IDs to link
            strict: If True, fail if mandatory links are missing
            
        Returns:
            AccountableChange record
            
        Raises:
            MissingMandatoryLinkError: If strict=True and links missing
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
        
        accountable_change = AccountableChange(
            accountable_id=accountable_id,
            agent_context=agent_context,
            change_intent=change_intent,
            cr_id=cr_id,
            requirement_refs=requirement_refs or [],
            status="linked" if (cr_id and requirement_refs) else "pending",
        )
        
        self._accountable_changes[accountable_id] = accountable_change
        
        logger.info(f"Registered accountable change: {accountable_id}")
        return accountable_change
    
    def link_to_cr(
        self,
        accountable_id: str,
        cr_id: str,
    ) -> AccountableChange:
        """Link an accountable change to an existing CR."""
        if accountable_id not in self._accountable_changes:
            raise AccountabilityError(f"Unknown accountable change: {accountable_id}")
        
        ac = self._accountable_changes[accountable_id]
        ac.cr_id = cr_id
        
        # Update status
        if ac.requirement_refs:
            ac.status = "linked"
        
        logger.info(f"Linked {accountable_id} to CR {cr_id}")
        return ac
    
    def validate_accountability(
        self,
        accountable_id: str,
        check_traceability: bool = True,
    ) -> Dict[str, Any]:
        """
        Validate an accountable change has all required links and evidence.
        
        Args:
            accountable_id: The accountable change ID
            check_traceability: Whether to validate against ASPICE Link Manager
            
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
        
        # Check CR exists
        if ac.cr_id:
            cr_file = self.changes_path / f"{ac.cr_id}.md"
            if not cr_file.exists():
                issues.append(f"Linked CR {ac.cr_id} does not exist")
        
        # Check traceability via C core
        traceability_result = None
        if check_traceability and ac.cr_id and ac.requirement_refs:
            try:
                traceability_result = validate_cr_traceability(
                    str(self.project_root), ac.cr_id
                )
            except Exception as e:
                issues.append(f"Traceability validation failed: {e}")
        
        is_valid = len(issues) == 0
        ac.status = "validated" if is_valid else "blocked"
        if not is_valid:
            ac.block_reason = "; ".join(issues)
        
        return {
            "valid": is_valid,
            "accountable_id": accountable_id,
            "cr_id": ac.cr_id,
            "requirement_refs": ac.requirement_refs,
            "issues": issues,
            "traceability": traceability_result,
        }
    
    def generate_accountability_evidence(
        self,
        accountable_id: str,
        output_format: str = "json",
    ) -> str:
        """
        Generate evidence packet for an accountable change.
        Combines agent context, change intent, CR linkage, and validation results.
        
        Args:
            accountable_id: The accountable change ID
            output_format: "json" or "markdown"
            
        Returns:
            Path to generated evidence file
        """
        if accountable_id not in self._accountable_changes:
            raise AccountabilityError(f"Unknown accountable change: {accountable_id}")
        
        ac = self._accountable_changes[accountable_id]
        
        # Validate first
        validation = self.validate_accountability(accountable_id)
        
        # Get CR evidence if available
        cr_evidence = None
        if ac.cr_id:
            try:
                cr_evidence_path = generate_cr_evidence(
                    str(self.project_root), ac.cr_id, output_format
                )
                cr_evidence = cr_evidence_path
            except Exception as e:
                logger.warning(f"Could not generate CR evidence: {e}")
        
        # Build evidence packet
        evidence = {
            "accountable_change": ac.to_dict(),
            "validation": validation,
            "cr_evidence_path": cr_evidence,
            "generated_at": datetime.now().isoformat(),
            "service_version": "B-0.1.0",
        }
        
        # Write evidence file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_format == "json":
            evidence_file = self.evidence_dir / f"{accountable_id}_{timestamp}.json"
            with open(evidence_file, "w") as f:
                json.dump(evidence, f, indent=2)
        else:
            evidence_file = self.evidence_dir / f"{accountable_id}_{timestamp}.md"
            with open(evidence_file, "w") as f:
                f.write(self._format_evidence_markdown(evidence))
        
        ac.evidence_path = str(evidence_file)
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
            f"- **Tools Used:** {', '.join(ac['agent_context']['tools_used'])}",
            f"- **Session ID:** {ac['agent_context'].get('session_id', 'N/A')}",
            "",
            "## Change Intent",
            "",
            f"- **Type:** {ac['change_intent']['change_type']}",
            f"- **Description:** {ac['change_intent']['description']}",
            f"- **Files Affected:** {', '.join(ac['change_intent']['files_affected'])}",
            f"- **Justification:** {ac['change_intent'].get('justification', 'N/A')}",
            "",
            "## Accountability Links",
            "",
            f"- **CR ID:** {ac['cr_id'] or 'NOT LINKED'}",
            f"- **Requirements:** {', '.join(ac['requirement_refs']) if ac['requirement_refs'] else 'NONE'}",
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
            f"- Linked CR: `{ac['cr_id']}`" if ac['cr_id'] else "- Linked CR: NONE",
            f"- CR Evidence: `{evidence.get('cr_evidence_path', 'N/A')}`",
        ])
        
        return "\n".join(lines)


# Convenience functions for CLI/API usage

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
    
    Args:
        project_path: Path to project root
        agent_id: Unique agent identifier
        agent_name: Human-readable agent name
        model: AI model used
        change_description: What is being changed
        change_type: Type of change (feature, bugfix, etc.)
        cr_id: Optional existing CR to link
        requirement_refs: Optional requirement IDs
        tools_used: List of tools the agent used
        files_affected: List of files being modified
        strict: Fail if mandatory links missing
        
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
    "AccountableAgentService",
    "AgentContext",
    "ChangeIntent",
    "AccountableChange",
    "AccountabilityError",
    "MissingMandatoryLinkError",
    "create_accountable_change",
    "validate_accountable_change",
    "generate_accountability_report",
]
