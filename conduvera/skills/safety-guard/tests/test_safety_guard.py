"""
Tests for Safety Guard Skill
"""

import pytest
from pathlib import Path
import sys
import os

# Add skill to path
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/safety-guard"))

from __init__ import SafetyGuard, SafetyGuardError


class TestSafetyGuard:
    """Test Safety Guard functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        self.guard = SafetyGuard()
        self.test_project = Path("/tmp/test_safety_guard_project")
        self.test_project.mkdir(parents=True, exist_ok=True)
    
    def teardown_method(self):
        """Cleanup after each test."""
        import shutil
        if self.test_project.exists():
            shutil.rmtree(self.test_project)
    
    def test_empty_path_raises_error(self):
        """AC1: Empty path should raise SafetyGuardError."""
        with pytest.raises(SafetyGuardError, match="KRITISCH: Path ist leer"):
            self.guard.validate_path("")
        
        with pytest.raises(SafetyGuardError, match="KRITISCH: Path ist None"):
            self.guard.validate_path(None)
    
    def test_relative_path_raises_error(self):
        """AC2: Relative path should raise SafetyGuardError."""
        with pytest.raises(SafetyGuardError, match="KRITISCH: Pfad.*ist relativ"):
            self.guard.validate_path("relative/path")
        
        with pytest.raises(SafetyGuardError, match="KRITISCH: Pfad.*ist relativ"):
            self.guard.validate_path("../parent/path")
    
    def test_absolute_path_allowed(self):
        """AC2: Absolute path should be valid."""
        result = self.guard.validate_path("/tmp/test_absolute")
        assert result == Path("/tmp/test_absolute").resolve()
    
    def test_current_directory_raises_error(self):
        """AC3: Current directory should raise SafetyGuardError."""
        cwd = str(Path.cwd())
        with pytest.raises(SafetyGuardError, match="KRITISCH: Pfad.*zeigt auf Current-Directory"):
            self.guard.validate_path(cwd)
    
    def test_protected_git_raises_error(self):
        """AC4: Protected path .git should raise SafetyGuardError."""
        with pytest.raises(SafetyGuardError, match="🛑 GE BLOCKT.*Geschützter Pfad"):
            self.guard.validate_path("/home/user/projects/.git/config", operation="write")
    
    def test_protected_production_raises_error(self):
        """AC4: Protected path production/ should raise SafetyGuardError."""
        with pytest.raises(SafetyGuardError, match="🛑 GE BLOCKT.*Geschützter Pfad"):
            self.guard.validate_path("/production/database.sql", operation="delete")
    
    def test_project_boundary_check(self):
        """AC5: Path outside project should raise SafetyGuardError."""
        guard_with_project = SafetyGuard(project_root="/tmp/test_safety_guard_project")
        
        with pytest.raises(SafetyGuardError, match="KRITISCH: Pfad.*verlässt Projekt-Grenzen"):
            guard_with_project.validate_path("/outside/project/path")
    
    def test_project_boundary_inside_allowed(self):
        """AC5: Path inside project should be valid."""
        guard_with_project = SafetyGuard(project_root="/tmp")
        
        result = guard_with_project.validate_path("/tmp/inside/project")
        assert result == Path("/tmp/inside/project").resolve()
    
    def test_check_safety_returns_tuple(self):
        """Test check_safety returns (bool, str) tuple."""
        is_safe, message = self.guard.check_safety("/tmp/safe_path")
        assert is_safe == True
        assert "sicher" in message
        
        is_safe, message = self.guard.check_safety("")
        assert is_safe == False
        assert "KRITISCH" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
