"""
Pattern Learning Engine - Code Pattern Recognition
Extracted from CuraOps Framework (SW-REQ-079)

Learns patterns from code analysis findings and stores them for future use.
Reduces analysis costs by converting findings into reusable regex patterns.

Features:
- Learn patterns from code findings
- Store patterns in JSON library
- Match patterns against code
- Pattern confidence scoring
- Pattern prevalence tracking
"""

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CodeFinding:
    """A finding from code analysis."""
    description: str
    code_snippet: str
    severity: str = "MEDIUM"
    line_number: int = 0
    file_path: str = ""


@dataclass
class LearnedPattern:
    """A pattern learned from code findings."""
    id: str
    name: str
    regex: str
    severity: str
    description: str
    learned_from: str
    confidence: float
    occurrences: int = 0
    false_positives: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "LearnedPattern":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class PatternMatch:
    """Result of pattern matching."""
    pattern_id: str
    pattern_name: str
    file_path: str
    line_number: int
    matched_text: str
    severity: str
    confidence: float


class PatternLearningEngine:
    """
    Engine for learning and applying code patterns.
    
    Converts code findings into reusable regex patterns.
    Stores patterns in JSON for fast lookup.
    
    Example:
        >>> engine = PatternLearningEngine(Path("./patterns"))
        >>> finding = CodeFinding("Hardcoded password", 'password = "secret"')
        >>> pattern = engine.learn_from_finding(finding)
        >>> engine.store_pattern(pattern)
        >>> 
        >>> # Later: scan code
        >>> matches = engine.scan_file(Path("src/auth.py"))
    """
    
    def __init__(self, storage_dir: Path):
        """
        Initialize pattern learning engine.
        
        Args:
            storage_dir: Directory to store learned patterns
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.library_path = self.storage_dir / "learned_patterns.json"
        self.patterns: List[LearnedPattern] = []
        
        self._load_library()
        
        logger.info(f"PatternLearningEngine initialized: {self.storage_dir}")
    
    def _load_library(self):
        """Load pattern library from disk."""
        if not self.library_path.exists():
            self.patterns = []
            return
        
        try:
            with open(self.library_path, encoding="utf-8") as f:
                data = json.load(f)
            
            self.patterns = [LearnedPattern.from_dict(p) for p in data.get("patterns", [])]
            logger.info(f"Loaded {len(self.patterns)} patterns from library")
        
        except Exception as e:
            logger.error(f"Error loading pattern library: {e}")
            self.patterns = []
    
    def _save_library(self):
        """Save pattern library to disk."""
        try:
            data = {
                "patterns": [p.to_dict() for p in self.patterns],
                "version": "1.0.0",
                "last_updated": datetime.now().isoformat(),
            }
            
            with open(self.library_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            logger.error(f"Error saving pattern library: {e}")
    
    def learn_from_finding(self, finding: CodeFinding, source: str = "manual") -> Optional[LearnedPattern]:
        """
        Learn a pattern from a code finding.
        
        Args:
            finding: Code finding to learn from
            source: Source of the finding (e.g., "manual", "cursor-agent")
            
        Returns:
            LearnedPattern if pattern could be extracted, None otherwise
        """
        # Generate pattern name
        pattern_name = self._generate_pattern_name(finding.description)
        if not pattern_name:
            return None
        
        # Generate regex pattern
        regex_pattern = self._extract_regex(finding.code_snippet, finding.description)
        if not regex_pattern:
            return None
        
        # Calculate confidence
        confidence = self._calculate_confidence(finding.code_snippet, regex_pattern)
        
        # Generate unique ID
        pattern_id = self._generate_pattern_id()
        
        return LearnedPattern(
            id=pattern_id,
            name=pattern_name,
            regex=regex_pattern,
            severity=finding.severity,
            description=finding.description,
            learned_from=source,
            confidence=confidence,
        )
    
    def _generate_pattern_name(self, description: str) -> str:
        """Generate a pattern name from description."""
        description_lower = description.lower()
        
        # Security patterns
        if "password" in description_lower:
            return "hardcoded_password"
        if "api" in description_lower and "key" in description_lower:
            return "hardcoded_api_key"
        if "secret" in description_lower:
            return "hardcoded_secret"
        if "token" in description_lower:
            return "hardcoded_token"
        
        # GDPR/Privacy patterns
        if "email" in description_lower:
            return "exposed_email"
        if "pii" in description_lower or "personal" in description_lower:
            return "exposed_pii"
        if "log" in description_lower:
            return "sensitive_logging"
        if "encrypt" in description_lower:
            return "missing_encryption"
        
        # SQL patterns
        if "sql" in description_lower:
            return "sql_injection_risk"
        if "injection" in description_lower:
            return "injection_vulnerability"
        
        # Fallback
        words = [w for w in description_lower.split() if len(w) > 3][:2]
        return "_".join(words) if words else "unknown_pattern"
    
    def _extract_regex(self, code_snippet: str, description: str) -> str:
        """Extract regex pattern from code snippet."""
        description_lower = description.lower()
        
        # Hardcoded credentials
        if "password" in description_lower:
            return r'password\s*=\s*["\'].*["\']'
        if "api" in description_lower and "key" in description_lower:
            return r'api[_-]?key\s*=\s*["\'].*["\']'
        if "secret" in description_lower:
            return r'secret\s*=\s*["\'].*["\']'
        if "token" in description_lower:
            return r'token\s*=\s*["\'].*["\']'
        
        # Email pattern
        if "email" in description_lower:
            return r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        
        # Logging sensitive data
        if "log" in description_lower:
            return r"(print|log|logger)\s*\([^)]*\b(password|token|secret|ssn|email)\b[^)]*\)"
        
        # SQL injection
        if "sql" in description_lower:
            return r'(execute|query|raw)\s*\([^)]*["\'].*\+.*["\'][^)]*\)'
        
        # Try to extract from code snippet
        if code_snippet and len(code_snippet) < 200:
            match = re.search(r'(\w+)\s*=\s*["\']([^"\']+)["\']', code_snippet)
            if match:
                var_name = match.group(1)
                return rf'{var_name}\s*=\s*["\'].*["\']'
        
        # Fallback
        return r'[a-z_]+\s*=\s*["\'].*["\']'
    
    def _calculate_confidence(self, code_snippet: str, regex_pattern: str) -> float:
        """Calculate confidence score for pattern."""
        try:
            match = re.search(regex_pattern, code_snippet, re.IGNORECASE)
            if match:
                return 0.9
            return 0.6
        except re.error:
            return 0.0
    
    def _generate_pattern_id(self) -> str:
        """Generate unique pattern ID."""
        existing_ids = {p.id for p in self.patterns}
        counter = 1
        
        while True:
            pattern_id = f"LEARNED-{counter:03d}"
            if pattern_id not in existing_ids:
                return pattern_id
            counter += 1
    
    def store_pattern(self, pattern: LearnedPattern):
        """
        Store a learned pattern.
        
        Args:
            pattern: Pattern to store
        """
        # Check if similar pattern exists
        existing = next((p for p in self.patterns if p.name == pattern.name), None)
        
        if existing:
            # Update existing
            existing.occurrences += 1
            existing.last_seen = datetime.now().isoformat()
            existing.confidence = min(1.0, existing.confidence + 0.05)
            logger.info(f"Updated pattern: {existing.id} (occurrences: {existing.occurrences})")
        else:
            # Add new
            self.patterns.append(pattern)
            logger.info(f"Stored new pattern: {pattern.id} - {pattern.name}")
        
        self._save_library()
    
    def get_pattern(self, pattern_id: str) -> Optional[LearnedPattern]:
        """Get pattern by ID."""
        return next((p for p in self.patterns if p.id == pattern_id), None)
    
    def get_pattern_by_name(self, name: str) -> Optional[LearnedPattern]:
        """Get pattern by name."""
        return next((p for p in self.patterns if p.name == name), None)
    
    def scan_file(self, file_path: Path) -> List[PatternMatch]:
        """
        Scan a file for learned patterns.
        
        Args:
            file_path: Path to file to scan
            
        Returns:
            List of pattern matches
        """
        matches = []
        
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            for pattern in self.patterns:
                for line_num, line in enumerate(lines, 1):
                    try:
                        for match in re.finditer(pattern.regex, line, re.IGNORECASE):
                            matches.append(PatternMatch(
                                pattern_id=pattern.id,
                                pattern_name=pattern.name,
                                file_path=str(file_path),
                                line_number=line_num,
                                matched_text=match.group(0),
                                severity=pattern.severity,
                                confidence=pattern.confidence,
                            ))
                    except re.error:
                        continue
        
        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")
        
        return matches
    
    def scan_directory(self, directory: Path, file_pattern: str = "*.py") -> List[PatternMatch]:
        """
        Scan a directory for learned patterns.
        
        Args:
            directory: Directory to scan
            file_pattern: File pattern to match (default: *.py)
            
        Returns:
            List of pattern matches
        """
        all_matches = []
        
        for file_path in directory.rglob(file_pattern):
            matches = self.scan_file(file_path)
            all_matches.extend(matches)
        
        return all_matches
    
    def get_pattern_stats(self) -> Dict:
        """Get statistics about learned patterns."""
        if not self.patterns:
            return {
                "total_patterns": 0,
                "by_severity": {},
                "average_confidence": 0.0,
                "total_occurrences": 0,
            }
        
        by_severity = {}
        for p in self.patterns:
            by_severity[p.severity] = by_severity.get(p.severity, 0) + 1
        
        avg_confidence = sum(p.confidence for p in self.patterns) / len(self.patterns)
        total_occurrences = sum(p.occurrences for p in self.patterns)
        
        return {
            "total_patterns": len(self.patterns),
            "by_severity": by_severity,
            "average_confidence": avg_confidence,
            "total_occurrences": total_occurrences,
        }
    
    def suggest_patterns(self, code_snippet: str) -> List[Tuple[str, float]]:
        """
        Suggest patterns that might apply to code.
        
        Args:
            code_snippet: Code to check
            
        Returns:
            List of (pattern_name, confidence) tuples
        """
        suggestions = []
        
        for pattern in self.patterns:
            try:
                if re.search(pattern.regex, code_snippet, re.IGNORECASE):
                    suggestions.append((pattern.name, pattern.confidence))
            except re.error:
                continue
        
        # Sort by confidence
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return suggestions


# CLI Interface
def learn_pattern(storage_dir: str, description: str, code_snippet: str, severity: str = "MEDIUM") -> str:
    """CLI: Learn a new pattern from finding."""
    engine = PatternLearningEngine(Path(storage_dir))
    
    finding = CodeFinding(
        description=description,
        code_snippet=code_snippet,
        severity=severity,
    )
    
    pattern = engine.learn_from_finding(finding)
    if pattern:
        engine.store_pattern(pattern)
        return f"✅ Learned pattern: {pattern.id} - {pattern.name} (confidence: {pattern.confidence:.1%})"
    else:
        return "❌ Could not extract pattern"


def scan_code(storage_dir: str, file_path: str) -> str:
    """CLI: Scan file for learned patterns."""
    engine = PatternLearningEngine(Path(storage_dir))
    
    matches = engine.scan_file(Path(file_path))
    
    if not matches:
        return "✅ No patterns matched"
    
    lines = [f"⚠️  Found {len(matches)} matches:", ""]
    
    for match in matches:
        lines.append(f"  [{match.severity}] {match.pattern_name}")
        lines.append(f"    Line {match.line_number}: {match.matched_text[:50]}...")
        lines.append(f"    Confidence: {match.confidence:.1%}")
        lines.append("")
    
    return "\n".join(lines)


def list_patterns(storage_dir: str) -> str:
    """CLI: List all learned patterns."""
    engine = PatternLearningEngine(Path(storage_dir))
    
    stats = engine.get_pattern_stats()
    
    if stats["total_patterns"] == 0:
        return "📭 No patterns learned yet"
    
    lines = [
        f"📚 Pattern Library:",
        f"",
        f"Total Patterns: {stats['total_patterns']}",
        f"Average Confidence: {stats['average_confidence']:.1%}",
        f"Total Occurrences: {stats['total_occurrences']}",
        f"",
        f"By Severity:",
    ]
    
    for severity, count in stats["by_severity"].items():
        lines.append(f"  {severity}: {count}")
    
    lines.append("")
    lines.append("Patterns:")
    
    for pattern in engine.patterns:
        occ_str = f" ({pattern.occurrences}x)" if pattern.occurrences > 0 else ""
        lines.append(f"  • {pattern.id}: {pattern.name}{occ_str}")
    
    return "\n".join(lines)


def suggest(storage_dir: str, code_snippet: str) -> str:
    """CLI: Suggest patterns for code."""
    engine = PatternLearningEngine(Path(storage_dir))
    
    suggestions = engine.suggest_patterns(code_snippet)
    
    if not suggestions:
        return "📭 No pattern suggestions"
    
    lines = [f"💡 Pattern Suggestions:", ""]
    
    for name, confidence in suggestions[:5]:
        lines.append(f"  • {name} ({confidence:.1%})")
    
    return "\n".join(lines)


__all__ = [
    "PatternLearningEngine",
    "LearnedPattern",
    "CodeFinding",
    "PatternMatch",
]
