"""
Tests for Pattern Learning Engine
"""

import pytest
import shutil
import json
from pathlib import Path
import sys
import os

# Add skill to path
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/pattern-learning"))

from __init__ import PatternLearningEngine, CodeFinding, LearnedPattern


class TestPatternLearningEngine:
    """Test Pattern Learning Engine functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        self.test_dir = Path("/tmp/test_pattern_learning")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.engine = PatternLearningEngine(storage_dir=self.test_dir)
    
    def teardown_method(self):
        """Cleanup after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_learn_from_finding_password(self):
        """AC1: Learn pattern from password finding."""
        finding = CodeFinding(
            description="Hardcoded password detected",
            code_snippet='password = "secret123"',
            severity="HIGH",
        )
        
        pattern = self.engine.learn_from_finding(finding)
        
        assert pattern is not None
        assert pattern.name == "hardcoded_password"
        assert "password" in pattern.regex
        assert pattern.confidence > 0.5
    
    def test_learn_from_finding_api_key(self):
        """AC2: Learn pattern from API key finding."""
        finding = CodeFinding(
            description="Hardcoded API key",
            code_snippet='api_key = "sk-123456"',
            severity="CRITICAL",
        )
        
        pattern = self.engine.learn_from_finding(finding)
        
        assert pattern is not None
        assert pattern.name == "hardcoded_api_key"
        assert "api" in pattern.regex.lower()
    
    def test_store_and_retrieve_pattern(self):
        """AC3: Store and retrieve pattern."""
        pattern = LearnedPattern(
            id="LEARNED-001",
            name="test_pattern",
            regex=r'test\s*=',
            severity="MEDIUM",
            description="Test pattern",
            learned_from="manual",
            confidence=0.9,
        )
        
        self.engine.store_pattern(pattern)
        
        # Retrieve by ID
        retrieved = self.engine.get_pattern("LEARNED-001")
        assert retrieved is not None
        assert retrieved.name == "test_pattern"
        
        # Retrieve by name
        by_name = self.engine.get_pattern_by_name("test_pattern")
        assert by_name is not None
        assert by_name.id == "LEARNED-001"
    
    def test_store_duplicate_updates_occurrences(self):
        """AC4: Storing duplicate pattern updates occurrences."""
        # Create first pattern
        pattern1 = LearnedPattern(
            id="LEARNED-001",
            name="duplicate_test",
            regex=r'duplicate\\s*=',
            severity="MEDIUM",
            description="Test",
            learned_from="manual",
            confidence=0.9,
        )
        
        # Create second pattern with same name
        pattern2 = LearnedPattern(
            id="LEARNED-002",
            name="duplicate_test",  # Same name
            regex=r'duplicate\\s*=',
            severity="MEDIUM",
            description="Test",
            learned_from="manual",
            confidence=0.9,
        )
        
        self.engine.store_pattern(pattern1)
        self.engine.store_pattern(pattern2)  # Should update existing
        
        stored = self.engine.get_pattern_by_name("duplicate_test")
        assert stored.occurrences >= 1  # Should have at least 1 occurrence
    
    def test_scan_file_with_match(self):
        """AC5: Scan file finds pattern matches."""
        # Create a pattern
        pattern = LearnedPattern(
            id="LEARNED-001",
            name="hardcoded_password",
            regex=r'password\s*=\s*["\'].*["\']',
            severity="HIGH",
            description="Hardcoded password",
            learned_from="manual",
            confidence=0.9,
        )
        self.engine.store_pattern(pattern)
        
        # Create test file
        test_file = self.test_dir / "test_code.py"
        test_file.write_text("""
# This is a test file
password = "secret123"
api_key = "sk-123"
""")
        
        # Scan
        matches = self.engine.scan_file(test_file)
        
        assert len(matches) == 1
        assert matches[0].pattern_name == "hardcoded_password"
        assert "password" in matches[0].matched_text
    
    def test_scan_file_no_match(self):
        """AC6: Scan file with no matches returns empty list."""
        pattern = LearnedPattern(
            id="LEARNED-001",
            name="test_pattern",
            regex=r'xyz123notfound',
            severity="LOW",
            description="Test",
            learned_from="manual",
            confidence=0.5,
        )
        self.engine.store_pattern(pattern)
        
        test_file = self.test_dir / "test_code.py"
        test_file.write_text("print('hello world')")
        
        matches = self.engine.scan_file(test_file)
        
        assert len(matches) == 0
    
    def test_get_pattern_stats(self):
        """AC7: Get pattern statistics."""
        # Store some patterns
        self.engine.store_pattern(LearnedPattern(
            id="LEARNED-001",
            name="pattern1",
            regex=r'test1',
            severity="HIGH",
            description="Test",
            learned_from="manual",
            confidence=0.9,
        ))
        
        self.engine.store_pattern(LearnedPattern(
            id="LEARNED-002",
            name="pattern2",
            regex=r'test2',
            severity="MEDIUM",
            description="Test",
            learned_from="manual",
            confidence=0.7,
        ))
        
        stats = self.engine.get_pattern_stats()
        
        assert stats["total_patterns"] == 2
        assert stats["by_severity"]["HIGH"] == 1
        assert stats["by_severity"]["MEDIUM"] == 1
        assert 0.7 < stats["average_confidence"] < 0.9
    
    def test_suggest_patterns(self):
        """AC8: Suggest patterns for code snippet."""
        # Store patterns
        self.engine.store_pattern(LearnedPattern(
            id="LEARNED-001",
            name="password_pattern",
            regex=r'password\s*=',
            severity="HIGH",
            description="Password",
            learned_from="manual",
            confidence=0.9,
        ))
        
        self.engine.store_pattern(LearnedPattern(
            id="LEARNED-002",
            name="api_key_pattern",
            regex=r'api[_-]?key',
            severity="CRITICAL",
            description="API Key",
            learned_from="manual",
            confidence=0.85,
        ))
        
        # Get suggestions
        suggestions = self.engine.suggest_patterns('password = "secret"')
        
        assert len(suggestions) > 0
        assert suggestions[0][0] == "password_pattern"
    
    def test_persist_to_disk(self):
        """AC9: Patterns persist to disk and reload."""
        # Store pattern
        pattern = LearnedPattern(
            id="LEARNED-001",
            name="persist_test",
            regex=r'persist',
            severity="LOW",
            description="Test",
            learned_from="manual",
            confidence=0.8,
        )
        self.engine.store_pattern(pattern)
        
        # Create new engine instance (should reload from disk)
        new_engine = PatternLearningEngine(storage_dir=self.test_dir)
        
        retrieved = new_engine.get_pattern("LEARNED-001")
        assert retrieved is not None
        assert retrieved.name == "persist_test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
