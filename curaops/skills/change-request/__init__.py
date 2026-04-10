"""
Change Request Service - CR Driven Development
Extracted from CuraOps Framework (SW-REQ-063)

Implements Change-Request-First workflow:
- Submit CR (Markdown)
- Status workflow: SUBMITTED → APPROVED → IN_PROGRESS → IMPLEMENTED → CLOSED
- Git-tracked changes/ directory
- Traceability Bible v3.1 compliant
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChangeRequestError(Exception):
    """Exception für Change-Request-Fehler."""
    pass


class ChangeRequestService:
    """
    FileSystem-basierte Change Request Service Implementation.
    
    Persistiert Change Requests als Markdown-Files im changes/ directory.
    Git-tracked für Audit-Trail.
    
    Directory Structure:
        changes/
        ├── CR-001.md  (Status: SUBMITTED)
        ├── CR-002.md  (Status: APPROVED)
        └── CR-003.md  (Status: IMPLEMENTED)
    
    Status Workflow:
        SUBMITTED → APPROVED → IN_PROGRESS → IMPLEMENTED → CLOSED
                ↘ REJECTED
    """
    
    # Valid CR statuses
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_APPROVED = "APPROVED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_IMPLEMENTED = "IMPLEMENTED"
    STATUS_CLOSED = "CLOSED"
    STATUS_REJECTED = "REJECTED"
    
    VALID_STATUSES = [
        STATUS_SUBMITTED,
        STATUS_APPROVED,
        STATUS_IN_PROGRESS,
        STATUS_IMPLEMENTED,
        STATUS_CLOSED,
        STATUS_REJECTED,
    ]
    
    # Valid status transitions
    VALID_TRANSITIONS = {
        STATUS_SUBMITTED: [STATUS_APPROVED, STATUS_REJECTED],
        STATUS_APPROVED: [STATUS_IN_PROGRESS, STATUS_REJECTED],
        STATUS_IN_PROGRESS: [STATUS_IMPLEMENTED, STATUS_REJECTED],
        STATUS_IMPLEMENTED: [STATUS_CLOSED, STATUS_IN_PROGRESS],
        STATUS_REJECTED: [STATUS_SUBMITTED],  # Can reopen
        STATUS_CLOSED: [],  # Terminal state
    }
    
    def __init__(self, changes_path: Optional[Path] = None, project_root: Optional[Path] = None):
        """
        Initialize Change Request Service.
        
        Args:
            changes_path: Path zum changes/ directory (default: ./changes)
            project_root: Project root for relative path resolution
        """
        if changes_path is None:
            changes_path = Path("changes")
        
        self.changes_path = Path(changes_path)
        self.project_root = project_root or Path.cwd()
        
        # Ensure changes/ directory exists
        self.changes_path.mkdir(parents=True, exist_ok=True)
        
        # CR-Counter (für ID-Generierung)
        self._cr_counter = self._get_next_cr_number()
        
        logger.info(f"ChangeRequestService initialized: {self.changes_path}")
    
    def _get_next_cr_number(self) -> int:
        """Holt nächste freie CR-Nummer."""
        existing_numbers = []
        
        if self.changes_path.exists():
            for file in self.changes_path.glob("CR-*.md"):
                try:
                    num = int(file.stem.split("-")[1])
                    existing_numbers.append(num)
                except (IndexError, ValueError):
                    continue
        
        return max(existing_numbers, default=0) + 1
    
    def _generate_cr_id(self) -> str:
        """Generiert eindeutige CR-ID (CR-XXX)."""
        cr_id = f"CR-{self._cr_counter:03d}"
        self._cr_counter += 1
        return cr_id
    
    def _generate_markdown(
        self,
        cr_id: str,
        title: str,
        description: str,
        status: str,
        timestamp: str,
        requirement_refs: Optional[List[str]] = None,
    ) -> str:
        """Generiert Markdown-Content für CR-File."""
        
        req_section = ""
        if requirement_refs:
            req_section = "\n".join([f"- {ref}" for ref in requirement_refs])
        else:
            req_section = "- (TBD)"
        
        markdown_template = f"""# {cr_id}: {title}

**Status:** {status}
**Created:** {timestamp.split("T")[0]}
**Requester:** (TBD)
**Priority:** (TBD)

## Description

{description}

## Requirement References

{req_section}

## Impact Analysis

*(To be filled during review)*

**Impacted Levels:**
- [ ] US (User Stories)
- [ ] SYS (System Requirements)
- [ ] ARCH (Architecture)
- [ ] SW (Software Requirements)
- [ ] CODE (Implementation)

**Impacted Requirements:**
- (TBD)

**Impacted Files:**
- (TBD)

**Estimated Effort:**
- (TBD)

## Approval

*(To be filled by Tech-Lead/PO)*

**Approved by:** (TBD)
**Approval date:** (TBD)
**Decision:** (PENDING)

## Implementation

*(To be filled during implementation)*

**Implementation started:** (TBD)
**Assigned to:** (TBD)

**Git Commits:**
- (TBD)

**Changed Requirements:**
- (TBD)

**Changed Files:**
- (TBD)

## Verification

*(To be filled after implementation)*

**Tests added/modified:**
- (TBD)

**Test results:**
- (TBD)

**Verification date:** (TBD)

## Traceability

**Related Requirements:**
- (TBD)

**Related ADRs:**
- (TBD)

**Related Tests:**
- (TBD)

---
*Generated by ChangeRequestService v1.0*
"""
        return markdown_template.strip()
    
    def _parse_cr_markdown(self, markdown_content: str, cr_id: str) -> dict:
        """Parsed Markdown-Content zu CR-Metadata dict."""
        # Extract title from first line: # CR-001: Title
        title_match = re.search(r"^# CR-\d+: (.+)$", markdown_content, re.MULTILINE)
        title = title_match.group(1) if title_match else "Unknown"
        
        # Extract status: **Status:** SUBMITTED
        status_match = re.search(r"\*\*Status:\*\* (\w+)", markdown_content)
        status = status_match.group(1) if status_match else self.STATUS_SUBMITTED
        
        # Extract created date: **Created:** 2025-10-09
        created_match = re.search(r"\*\*Created:\*\* ([\d-]+)", markdown_content)
        created = created_match.group(1) if created_match else datetime.now().date().isoformat()
        
        # Extract description
        description_match = re.search(
            r"## Description\s+(.+?)\s+## Impact Analysis",
            markdown_content,
            re.DOTALL,
        )
        description = description_match.group(1).strip() if description_match else ""
        
        return {
            "cr_id": cr_id,
            "title": title,
            "description": description,
            "status": status,
            "created": created,
            "file_path": str(self.changes_path / f"{cr_id}.md"),
        }
    
    def submit_change_request(
        self, 
        title: str, 
        description: str,
        requirement_refs: Optional[List[str]] = None,
    ) -> dict:
        """
        Submittet neuen Change Request.
        
        Args:
            title: CR-Title
            description: CR-Description
            requirement_refs: List of requirement IDs (e.g., ["SW-REQ-001", "SYS-REQ-042"])
            
        Returns:
            dict: CR-Metadata (cr_id, title, description, status, created, file_path, requirement_refs)
        """
        # Validate inputs
        if not title or not title.strip():
            raise ChangeRequestError("Title cannot be empty")
        
        if not description or not description.strip():
            raise ChangeRequestError("Description cannot be empty")
        
        # Generate CR-ID
        cr_id = self._generate_cr_id()
        timestamp = datetime.now().isoformat()
        
        # Generate Markdown
        markdown_content = self._generate_markdown(
            cr_id, title, description, self.STATUS_SUBMITTED, timestamp, requirement_refs
        )
        
        # Persist as Markdown
        md_file = self.changes_path / f"{cr_id}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        logger.info(f"CR submitted: {cr_id} - {title}")
        
        return {
            "cr_id": cr_id,
            "title": title,
            "description": description,
            "status": self.STATUS_SUBMITTED,
            "created": timestamp.split("T")[0],
            "file_path": str(md_file),
            "requirement_refs": requirement_refs or [],
        }
    
    def get_pending_requests(self) -> List[dict]:
        """Holt alle pending Change Requests (Status: SUBMITTED)."""
        return self.get_requests_by_status(self.STATUS_SUBMITTED)
    
    def get_requests_by_status(self, status: str) -> List[dict]:
        """Holt alle CRs mit gegebenem Status."""
        crs = []
        
        if not self.changes_path.exists():
            return []
        
        for md_file in self.changes_path.glob("CR-*.md"):
            try:
                with open(md_file, encoding="utf-8") as f:
                    content = f.read()
                
                cr_id = md_file.stem
                cr_data = self._parse_cr_markdown(content, cr_id)
                
                if cr_data["status"] == status:
                    crs.append(cr_data)
            
            except Exception as e:
                logger.error(f"Failed to load CR {md_file}: {e}")
                continue
        
        # Sort by created date (oldest first)
        crs.sort(key=lambda cr: cr.get("created", ""))
        
        return crs
    
    def get_all_requests(self) -> List[dict]:
        """Holt alle Change Requests (alle Status)."""
        crs = []
        
        if not self.changes_path.exists():
            return []
        
        for md_file in self.changes_path.glob("CR-*.md"):
            try:
                with open(md_file, encoding="utf-8") as f:
                    content = f.read()
                
                cr_id = md_file.stem
                cr_data = self._parse_cr_markdown(content, cr_id)
                crs.append(cr_data)
            
            except Exception as e:
                logger.error(f"Failed to load CR {md_file}: {e}")
                continue
        
        # Sort by created date (oldest first)
        crs.sort(key=lambda cr: cr.get("created", ""))
        
        return crs
    
    def process_change_request(self, cr_id: str, new_status: Optional[str] = None) -> dict:
        """
        Processed Change Request (ändert Status).
        
        Args:
            cr_id: CR-ID (z.B. "CR-001")
            new_status: Neuer Status (default: APPROVED)
            
        Returns:
            dict: {"success": bool, "cr_id": str, "status": str, "error": str}
        """
        md_file = self.changes_path / f"{cr_id}.md"
        
        if not md_file.exists():
            return {"success": False, "error": f"CR {cr_id} not found"}
        
        # Load CR-Markdown
        try:
            with open(md_file, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return {"success": False, "error": f"Failed to load CR {cr_id}: {e}"}
        
        # Parse current status
        current_status_match = re.search(r"\*\*Status:\*\* (\w+)", content)
        current_status = current_status_match.group(1) if current_status_match else self.STATUS_SUBMITTED
        
        # Determine new status
        if new_status is None:
            new_status = self.STATUS_APPROVED
        
        if new_status not in self.VALID_STATUSES:
            return {"success": False, "error": f"Invalid status: {new_status}"}
        
        # Validate transition
        if new_status != current_status and new_status not in self.VALID_TRANSITIONS.get(current_status, []):
            valid_next = ", ".join(self.VALID_TRANSITIONS.get(current_status, []))
            return {
                "success": False,
                "error": f"Invalid transition: {current_status} → {new_status}. Valid: {valid_next}"
            }
        
        # Update status in Markdown
        updated_content = re.sub(
            r"\*\*Status:\*\* \w+",
            f"**Status:** {new_status}",
            content,
        )
        
        # Add timestamp if moving to IN_PROGRESS
        if new_status == self.STATUS_IN_PROGRESS:
            timestamp = datetime.now().isoformat().split("T")[0]
            updated_content = re.sub(
                r"\*\*Implementation started:\*\* \(TBD\)",
                f"**Implementation started:** {timestamp}",
                updated_content,
            )
        
        # Add approval date if moving to APPROVED
        if new_status == self.STATUS_APPROVED:
            timestamp = datetime.now().isoformat().split("T")[0]
            updated_content = re.sub(
                r"\*\*Approval date:\*\* \(TBD\)",
                f"**Approval date:** {timestamp}",
                updated_content,
            )
            updated_content = re.sub(
                r"\*\*Decision:\*\* \(PENDING\)",
                "**Decision:** APPROVED",
                updated_content,
            )
        
        # Save updated Markdown
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(updated_content)
        
        logger.info(f"CR status updated: {cr_id} → {new_status}")
        
        return {"success": True, "cr_id": cr_id, "status": new_status}
    
    def get_cr_status(self, cr_id: str) -> dict:
        """
        Holt Status eines Change Requests.
        
        Args:
            cr_id: CR-ID (z.B. "CR-001")
            
        Returns:
            dict: CR-Metadata oder {"success": False, "error": str}
        """
        md_file = self.changes_path / f"{cr_id}.md"
        
        if not md_file.exists():
            return {"success": False, "error": f"CR {cr_id} not found"}
        
        try:
            with open(md_file, encoding="utf-8") as f:
                content = f.read()
            
            cr_data = self._parse_cr_markdown(content, cr_id)
            return {"success": True, **cr_data}
        
        except Exception as e:
            return {"success": False, "error": f"Failed to load CR {cr_id}: {e}"}


# CLI Interface
def submit_cr(project_path: str, title: str, description: str) -> str:
    """CLI: Submit new Change Request."""
    service = ChangeRequestService(changes_path=Path(project_path) / "changes")
    
    try:
        cr = service.submit_change_request(title, description)
        return f"✅ {cr['cr_id']} submitted: {cr['title']}\n   File: {cr['file_path']}"
    except ChangeRequestError as e:
        return f"🛑 Error: {e}"


def list_crs(project_path: str, status: str = None) -> str:
    """CLI: List Change Requests."""
    service = ChangeRequestService(changes_path=Path(project_path) / "changes")
    
    if status:
        crs = service.get_requests_by_status(status)
    else:
        crs = service.get_all_requests()
    
    if not crs:
        return "📭 No Change Requests found"
    
    lines = [f"📋 {len(crs)} Change Requests:", ""]
    
    for cr in crs:
        status_emoji = {
            "SUBMITTED": "📤",
            "APPROVED": "✅",
            "IN_PROGRESS": "🔄",
            "IMPLEMENTED": "💻",
            "CLOSED": "🏁",
            "REJECTED": "❌",
        }.get(cr["status"], "⚪")
        
        lines.append(f"{status_emoji} {cr['cr_id']}: {cr['title']}")
        lines.append(f"   Status: {cr['status']} | Created: {cr['created']}")
        lines.append("")
    
    return "\n".join(lines)


def update_cr(project_path: str, cr_id: str, new_status: str) -> str:
    """CLI: Update Change Request status."""
    service = ChangeRequestService(changes_path=Path(project_path) / "changes")
    
    result = service.process_change_request(cr_id, new_status)
    
    if result["success"]:
        return f"✅ {cr_id} updated to {result['status']}"
    else:
        return f"🛑 Error: {result['error']}"


def show_cr(project_path: str, cr_id: str) -> str:
    """CLI: Show Change Request details."""
    service = ChangeRequestService(changes_path=Path(project_path) / "changes")
    
    result = service.get_cr_status(cr_id)
    
    if not result["success"]:
        return f"🛑 Error: {result['error']}"
    
    lines = [
        f"📋 {result['cr_id']}: {result['title']}",
        f"",
        f"Status: {result['status']}",
        f"Created: {result['created']}",
        f"File: {result['file_path']}",
        f"",
        f"Description:",
        f"{result['description'][:200]}...",
    ]
    
    return "\n".join(lines)


def generate_cr_evidence(project_path: str, cr_id: str, output_format: str = "json") -> str:
    """CLI: Generate machine-readable evidence for CR state.
    
    Args:
        project_path: Path to project root
        cr_id: Change Request ID (e.g., "CR-001")
        output_format: Output format (json, markdown)
        
    Returns:
        Path to generated evidence file or error message
    """
    import json
    from datetime import datetime
    
    service = ChangeRequestService(changes_path=Path(project_path) / "changes")
    
    # Get CR status
    result = service.get_cr_status(cr_id)
    if not result["success"]:
        return f"🛑 Error: {result['error']}"
    
    # Load full CR content
    cr_file = Path(project_path) / "changes" / f"{cr_id}.md"
    if not cr_file.exists():
        return f"🛑 Error: CR file not found: {cr_file}"
    
    full_content = cr_file.read_text(encoding="utf-8")
    
    # Extract requirement references
    req_refs = []
    req_section_match = re.search(r"## Requirement References\n+((?:- .+\n)+)", full_content)
    if req_section_match:
        req_lines = req_section_match.group(1).strip().split("\n")
        req_refs = [line.strip("- ").strip() for line in req_lines if line.strip() and not line.strip().startswith("(TBD)")]
    
    # Build evidence structure
    evidence = {
        "cr_id": result["cr_id"],
        "title": result["title"],
        "status": result["status"],
        "created": result["created"],
        "file_path": str(result["file_path"]),
        "description": result["description"],
        "requirement_references": req_refs,
        "evidence_generated_at": datetime.now().isoformat(),
        "evidence_format": "compliance-cr-v1.0",
    }
    
    # Write evidence file
    output_dir = Path(project_path) / "changes" / "evidence"
    output_dir.mkdir(exist_ok=True)
    
    if output_format == "json":
        output_file = output_dir / f"{cr_id}_evidence.json"
        output_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    else:
        output_file = output_dir / f"{cr_id}_evidence.md"
        md_content = f"""# Evidence: {cr_id}

**CR:** {evidence['title']}  
**Status:** {evidence['status']}  
**Generated:** {evidence['evidence_generated_at']}

## Requirement References

"""
        for ref in req_refs:
            md_content += f"- {ref}\n"
        md_content += f"""
## Description

{evidence['description']}

---
*Generated by ChangeRequestService*
"""
        output_file.write_text(md_content, encoding="utf-8")
    
    return f"✅ Evidence generated: {output_file}"


def validate_cr_traceability(project_path: str, cr_id: str) -> str:
    """CLI: Validate CR traceability against ASPICE Link Manager.
    
    Args:
        project_path: Path to project root
        cr_id: Change Request ID
        
    Returns:
        Validation report
    """
    service = ChangeRequestService(changes_path=Path(project_path) / "changes")
    
    result = service.get_cr_status(cr_id)
    if not result["success"]:
        return f"🛑 Error: {result['error']}"
    
    # Load full CR content
    cr_file = Path(project_path) / "changes" / f"{cr_id}.md"
    if not cr_file.exists():
        return f"🛑 Error: CR file not found: {cr_file}"
    
    full_content = cr_file.read_text(encoding="utf-8")
    
    # Extract requirement references (filter out placeholders)
    req_refs = []
    req_section_match = re.search(r"## Requirement References\n+((?:- .+\n)+)", full_content)
    if req_section_match:
        req_lines = req_section_match.group(1).strip().split("\n")
        req_refs = [
            ref for ref in [line.strip("- ").strip() for line in req_lines if line.strip()]
            if ref and ref != "(TBD)" and not ref.startswith("(")
        ]
    
    if not req_refs:
        return f"⚠️  {cr_id}: No requirement references found\n   Add requirements to enable traceability validation"
    
    # Try to import and use ASPICE Link Manager
    try:
        from curaops.skills.aspice_link_manager import ASPICELinkManager
        
        link_mgr = ASPICELinkManager(root_dir=Path(project_path))
        
        lines = [f"🔗 Traceability Validation for {cr_id}:", ""]
        lines.append(f"Requirement References: {len(req_refs)}")
        lines.append("")
        
        all_valid = True
        for req_id in req_refs:
            doc_file = link_mgr.find_document(req_id)
            if doc_file:
                lines.append(f"✅ {req_id}: Found at {doc_file.relative_to(project_path)}")
            else:
                lines.append(f"❌ {req_id}: NOT FOUND in project")
                all_valid = False
        
        lines.append("")
        if all_valid:
            lines.append("✅ All requirement references validated successfully")
        else:
            lines.append("⚠️  Some requirements not found — check requirement IDs or update links")
        
        return "\n".join(lines)
        
    except ImportError:
        return f"📋 {cr_id} has {len(req_refs)} requirement references:\n" + "\n".join([f"  - {ref}" for ref in req_refs]) + "\n\n⚠️  ASPICE Link Manager not available for validation"


__all__ = [
    "ChangeRequestService",
    "ChangeRequestError",
    "generate_cr_evidence",
    "validate_cr_traceability",
]
