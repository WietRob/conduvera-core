"""
ASPICE Link Manager - Traceability Management
Simplified version extracted from CuraOps Framework (SW-REQ-094)

Manages bidirectional traceability links between requirements, code, and tests.
Uses JSON for metadata (no YAML dependency).

Features:
- Parse requirement documents with JSON frontmatter
- Update bidirectional links (forward + backward)
- Verify link consistency
- Generate traceability reports
- <5min SLA for link updates
"""

import json
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Requirement:
    """Requirement document data model."""
    id: str
    title: str
    description: str = ""
    refined_from: List[str] = None
    refined_in: List[str] = None
    validated_by: List[str] = None
    implemented_in: List[str] = None
    file_path: str = ""
    
    def __post_init__(self):
        if self.refined_from is None:
            self.refined_from = []
        if self.refined_in is None:
            self.refined_in = []
        if self.validated_by is None:
            self.validated_by = []
        if self.implemented_in is None:
            self.implemented_in = []


@dataclass
class LinkUpdateResult:
    """Result of link update operation."""
    success: bool
    updated_count: int
    errors: List[str]
    updated_files: List[str]


class ASPICELinkManager:
    """
    Manage ASPICE traceability links.
    
    Works with Markdown files that have JSON frontmatter:
    
    ```json
    {
      "id": "SW-REQ-001",
      "title": "User Authentication",
      "refined_from": ["SYS-REQ-001"],
      "refined_in": ["SW-REQ-002"],
      "validated_by": ["TEST-001"]
    }
    ```
    
    Rest of document...
    """
    
    def __init__(self, root_dir: Optional[Path] = None):
        """
        Initialize ASPICE Link Manager.
        
        Args:
            root_dir: Root directory for requirement documents
        """
        if root_dir is None:
            root_dir = Path.cwd()
        self.root_dir = Path(root_dir)
        
        # Default search directories
        self.search_dirs = [
            self.root_dir / "requirements",
            self.root_dir / "architecture",
            self.root_dir / "tests",
            self.root_dir / "src",
        ]
        
        logger.info(f"ASPICELinkManager initialized: {self.root_dir}")
    
    def parse_document(self, file_path: Path) -> Optional[Requirement]:
        """
        Parse requirement document with JSON frontmatter.
        
        Format:
        ```json
        {"id": "SW-REQ-001", "title": "...", "refined_from": [...]}
        ```
        
        Rest of document...
        
        Args:
            file_path: Path to document
            
        Returns:
            Requirement object or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            
            # Extract JSON frontmatter (```json ... ```)
            match = re.search(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
            if not match:
                logger.warning(f"No JSON frontmatter in {file_path}")
                return None
            
            json_text = match.group(1).strip()
            data = json.loads(json_text)
            
            if "id" not in data or "title" not in data:
                logger.warning(f"Missing required fields in {file_path}")
                return None
            
            return Requirement(
                id=data["id"],
                title=data["title"],
                description=data.get("description", ""),
                refined_from=data.get("refined_from", []),
                refined_in=data.get("refined_in", []),
                validated_by=data.get("validated_by", []),
                implemented_in=data.get("implemented_in", []),
                file_path=str(file_path),
            )
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None
    
    def find_document(self, doc_id: str) -> Optional[Path]:
        """
        Find document by ID.
        
        Args:
            doc_id: Document ID (e.g., "SW-REQ-001")
            
        Returns:
            Path to document or None if not found
        """
        for search_dir in self.search_dirs:
            if not search_dir.exists():
                continue
            
            for md_file in search_dir.rglob("*.md"):
                doc = self.parse_document(md_file)
                if doc and doc.id == doc_id:
                    return md_file
        
        return None
    
    def update_bidirectional_links(self, changed_file: Path) -> LinkUpdateResult:
        """
        Update bidirectional links for changed document.
        
        If doc A has B in refined_in, then B should have A in refined_from.
        
        Args:
            changed_file: Path to changed document
            
        Returns:
            LinkUpdateResult with update status
        """
        errors = []
        updated_files = []
        updated_count = 0
        
        try:
            doc = self.parse_document(changed_file)
            if doc is None:
                return LinkUpdateResult(
                    success=False,
                    updated_count=0,
                    errors=[f"Could not parse {changed_file}"],
                    updated_files=[],
                )
            
            # Update forward links (refined_in)
            for target_id in doc.refined_in:
                target_file = self.find_document(target_id)
                if target_file:
                    if self._add_backlink(target_file, doc.id, "refined_from"):
                        updated_files.append(str(target_file))
                        updated_count += 1
                else:
                    errors.append(f"Target document {target_id} not found")
            
            # Update backward links (refined_from)
            for source_id in doc.refined_from:
                source_file = self.find_document(source_id)
                if source_file:
                    if self._add_backlink(source_file, doc.id, "refined_in"):
                        updated_files.append(str(source_file))
                        updated_count += 1
                else:
                    errors.append(f"Source document {source_id} not found")
            
            # Update validation links
            for test_id in doc.validated_by:
                test_file = self.find_document(test_id)
                if test_file:
                    if self._add_backlink(test_file, doc.id, "validates"):
                        updated_files.append(str(test_file))
                        updated_count += 1
            
            return LinkUpdateResult(
                success=len(errors) == 0,
                updated_count=updated_count,
                errors=errors,
                updated_files=updated_files,
            )
        
        except Exception as e:
            logger.error(f"Error updating links for {changed_file}: {e}")
            return LinkUpdateResult(
                success=False,
                updated_count=updated_count,
                errors=[str(e)],
                updated_files=updated_files,
            )
    
    def _add_backlink(self, target_file: Path, source_id: str, field_name: str) -> bool:
        """
        Add backlink to target file's JSON frontmatter.
        
        Args:
            target_file: File to update
            source_id: ID to add
            field_name: Field name (e.g., "refined_from")
            
        Returns:
            True if added, False if already present or error
        """
        try:
            content = target_file.read_text(encoding="utf-8")
            
            # Extract JSON frontmatter
            match = re.search(r"(```json\s*\n)(.*?)(\n```)", content, re.DOTALL)
            if not match:
                return False
            
            json_text = match.group(2).strip()
            data = json.loads(json_text)
            
            # Initialize field if not present
            if field_name not in data:
                data[field_name] = []
            
            if not isinstance(data[field_name], list):
                logger.warning(f"Field '{field_name}' is not a list in {target_file}")
                return False
            
            # Add if not already present
            if source_id in data[field_name]:
                return False
            
            data[field_name].append(source_id)
            
            # Write back
            new_json = json.dumps(data, indent=2)
            new_content = content[:match.start()] + f"```json\n{new_json}\n```" + content[match.end():]
            
            target_file.write_text(new_content, encoding="utf-8")
            logger.info(f"Added {field_name} link {source_id} to {target_file}")
            return True
        
        except Exception as e:
            logger.error(f"Error adding backlink to {target_file}: {e}")
            return False
    
    def verify_links(self, file_path: Path) -> List[str]:
        """
        Verify link consistency for document.
        
        Checks:
        - Forward links exist
        - Backward links are reciprocal
        
        Args:
            file_path: Path to document
            
        Returns:
            List of consistency errors (empty if all consistent)
        """
        errors = []
        
        doc = self.parse_document(file_path)
        if doc is None:
            return [f"Could not parse {file_path}"]
        
        # Verify forward links exist
        for target_id in doc.refined_in:
            if not self.find_document(target_id):
                errors.append(
                    f"Forward link {target_id} (refined_in) points to non-existent document"
                )
        
        # Verify backward links are reciprocal
        for source_id in doc.refined_from:
            source_file = self.find_document(source_id)
            if source_file:
                source_doc = self.parse_document(source_file)
                if source_doc and doc.id not in source_doc.refined_in:
                    errors.append(
                        f"Backward link {source_id} (refined_from) is not reciprocal: "
                        f"{source_id} does not have {doc.id} in refined_in"
                    )
        
        # Verify forward links are reciprocal
        for target_id in doc.refined_in:
            target_file = self.find_document(target_id)
            if target_file:
                target_doc = self.parse_document(target_file)
                if target_doc and doc.id not in target_doc.refined_from:
                    errors.append(
                        f"Forward link {target_id} (refined_in) is not reciprocal: "
                        f"{target_id} does not have {doc.id} in refined_from"
                    )
        
        return errors
    
    def generate_traceability_matrix(self) -> Dict:
        """
        Generate traceability matrix for all documents.
        
        Returns:
            Dict with traceability data
        """
        matrix = {
            "generated_at": datetime.now().isoformat(),
            "requirements": [],
            "links": {},
            "coverage": {},
        }
        
        all_docs = []
        for search_dir in self.search_dirs:
            if not search_dir.exists():
                continue
            for md_file in search_dir.rglob("*.md"):
                doc = self.parse_document(md_file)
                if doc:
                    all_docs.append(doc)
        
        # Build matrix
        for doc in all_docs:
            matrix["requirements"].append({
                "id": doc.id,
                "title": doc.title,
                "file": doc.file_path,
            })
            
            matrix["links"][doc.id] = {
                "refined_from": doc.refined_from,
                "refined_in": doc.refined_in,
                "validated_by": doc.validated_by,
                "implemented_in": doc.implemented_in,
            }
        
        # Calculate coverage
        total = len(all_docs)
        with_tests = sum(1 for d in all_docs if d.validated_by)
        with_impl = sum(1 for d in all_docs if d.implemented_in)
        
        matrix["coverage"] = {
            "total_requirements": total,
            "with_tests": with_tests,
            "with_implementation": with_impl,
            "test_coverage": with_tests / total if total > 0 else 0,
            "impl_coverage": with_impl / total if total > 0 else 0,
        }
        
        return matrix
    
    def save_traceability_matrix(self, output_file: Path = None) -> Path:
        """
        Save traceability matrix to JSON file.
        
        Args:
            output_file: Output file path (default: root_dir/traceability_matrix.json)
            
        Returns:
            Path to saved file
        """
        if output_file is None:
            output_file = self.root_dir / "traceability_matrix.json"
        
        matrix = self.generate_traceability_matrix()
        output_file.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
        
        logger.info(f"Traceability matrix saved: {output_file}")
        return output_file


# CLI Interface
def update_links(project_path: str, doc_id: str = None) -> str:
    """CLI: Update bidirectional links for document(s)."""
    manager = ASPICELinkManager(root_dir=Path(project_path))
    
    if doc_id:
        # Update specific document
        doc_file = manager.find_document(doc_id)
        if not doc_file:
            return f"❌ Document {doc_id} not found"
        
        result = manager.update_bidirectional_links(doc_file)
        if result.success:
            return f"✅ Updated {result.updated_count} links for {doc_id}"
        else:
            return f"⚠️ Updated {result.updated_count} links with errors: {', '.join(result.errors)}"
    else:
        # Update all documents
        total_updated = 0
        errors = []
        
        for search_dir in manager.search_dirs:
            if not search_dir.exists():
                continue
            for md_file in search_dir.rglob("*.md"):
                result = manager.update_bidirectional_links(md_file)
                total_updated += result.updated_count
                errors.extend(result.errors)
        
        if errors:
            return f"⚠️ Updated {total_updated} links with {len(errors)} errors"
        else:
            return f"✅ Updated {total_updated} links successfully"


def verify_links(project_path: str, doc_id: str = None) -> str:
    """CLI: Verify link consistency."""
    manager = ASPICELinkManager(root_dir=Path(project_path))
    
    if doc_id:
        doc_file = manager.find_document(doc_id)
        if not doc_file:
            return f"❌ Document {doc_id} not found"
        
        errors = manager.verify_links(doc_file)
        if errors:
            error_list = "\n".join(f"  - {e}" for e in errors)
            return f"⚠️ {doc_id} has {len(errors)} consistency issues:\n{error_list}"
        else:
            return f"✅ {doc_id} links are consistent"
    else:
        # Verify all
        all_errors = []
        for search_dir in manager.search_dirs:
            if not search_dir.exists():
                continue
            for md_file in search_dir.rglob("*.md"):
                doc = manager.parse_document(md_file)
                if doc:
                    errors = manager.verify_links(md_file)
                    if errors:
                        all_errors.extend([f"{doc.id}: {e}" for e in errors])
        
        if all_errors:
            error_list = "\n".join(f"  - {e}" for e in all_errors[:10])
            return f"⚠️ Found {len(all_errors)} consistency issues:\n{error_list}"
        else:
            return "✅ All links are consistent"


def generate_matrix(project_path: str) -> str:
    """CLI: Generate traceability matrix."""
    manager = ASPICELinkManager(root_dir=Path(project_path))
    output_file = manager.save_traceability_matrix()
    
    matrix = manager.generate_traceability_matrix()
    coverage = matrix["coverage"]
    
    return f"""✅ Traceability matrix generated: {output_file}

📊 Coverage Report:
   Total Requirements: {coverage['total_requirements']}
   With Tests: {coverage['with_tests']} ({coverage['test_coverage']:.1%})
   With Implementation: {coverage['with_implementation']} ({coverage['impl_coverage']:.1%})
"""


__all__ = ["ASPICELinkManager", "Requirement", "LinkUpdateResult"]
