"""
Tests for Agent Session Manager
"""

import pytest
import shutil
import time
from pathlib import Path
import sys
import os

# Add skill to path
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/session-manager"))

from __init__ import AgentSessionManager, Session, SessionExchange


class TestAgentSessionManager:
    """Test Agent Session Manager functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        self.test_dir = Path("/tmp/test_session_manager")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.manager = AgentSessionManager(storage_dir=self.test_dir)
    
    def teardown_method(self):
        """Cleanup after each test."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_create_session(self):
        """AC1: Create session generates ID and saves to disk."""
        session = self.manager.create_session(
            agent="cursor",
            model="claude-sonnet",
            prompt="Refactor auth module",
        )
        
        assert session.session_id.startswith("sess_")
        assert session.agent == "cursor"
        assert session.model == "claude-sonnet"
        assert session.status == "active"
        
        # Verify file was created
        session_file = self.test_dir / f"{session.session_id}.json"
        assert session_file.exists()
    
    def test_load_session(self):
        """AC2: Load session retrieves saved session."""
        # Create and save session
        session = self.manager.create_session(
            agent="vscode",
            model="gpt-4",
            prompt="Add feature X",
        )
        session_id = session.session_id
        
        # Load it back
        loaded = self.manager.load_session(session_id)
        
        assert loaded is not None
        assert loaded.session_id == session_id
        assert loaded.agent == "vscode"
        assert loaded.prompt == "Add feature X"
    
    def test_load_nonexistent_session(self):
        """AC3: Load non-existent session returns None."""
        loaded = self.manager.load_session("sess_nonexistent_12345")
        assert loaded is None
    
    def test_append_exchange(self):
        """AC4: Append exchange adds to history."""
        session = self.manager.create_session(
            agent="cli",
            model="haiku",
            prompt="Fix bug",
        )
        
        success = self.manager.append_exchange(
            session_id=session.session_id,
            task="Analyze code",
            outcome="Found issue in line 42",
            tokens=150,
        )
        
        assert success == True
        
        # Verify
        loaded = self.manager.load_session(session.session_id)
        assert len(loaded.history) == 1
        assert loaded.history[0]["task"] == "Analyze code"
        assert loaded.history[0]["tokens"] == 150
    
    def test_append_exchange_nonexistent(self):
        """AC5: Append to non-existent session returns False."""
        success = self.manager.append_exchange(
            session_id="sess_nonexistent",
            task="Test",
            outcome="Result",
        )
        assert success == False
    
    def test_update_status(self):
        """AC6: Update status changes session status."""
        session = self.manager.create_session(
            agent="cursor",
            model="opus",
            prompt="Test task",
        )
        
        success = self.manager.update_status(session.session_id, "completed")
        
        assert success == True
        
        loaded = self.manager.load_session(session.session_id)
        assert loaded.status == "completed"
    
    def test_update_metadata(self):
        """AC7: Update metadata adds key-value pair."""
        session = self.manager.create_session(
            agent="test",
            model="test-model",
            prompt="Test",
        )
        
        success = self.manager.update_metadata(
            session_id=session.session_id,
            key="cost",
            value=0.05,
        )
        
        assert success == True
        
        loaded = self.manager.load_session(session.session_id)
        assert loaded.metadata["cost"] == 0.05
    
    def test_list_sessions(self):
        """AC8: List sessions returns all sessions."""
        # Create multiple sessions
        self.manager.create_session(agent="cursor", model="m1", prompt="Task 1")
        time.sleep(0.01)  # Ensure different timestamps
        self.manager.create_session(agent="vscode", model="m2", prompt="Task 2")
        time.sleep(0.01)
        self.manager.create_session(agent="cli", model="m3", prompt="Task 3")
        
        sessions = self.manager.list_sessions()
        
        assert len(sessions) == 3
    
    def test_list_sessions_filter_by_agent(self):
        """AC9: List sessions filters by agent."""
        self.manager.create_session(agent="cursor", model="m1", prompt="Task 1")
        self.manager.create_session(agent="vscode", model="m2", prompt="Task 2")
        self.manager.create_session(agent="cursor", model="m3", prompt="Task 3")
        
        sessions = self.manager.list_sessions(agent="cursor")
        
        assert len(sessions) == 2
        assert all(s.agent == "cursor" for s in sessions)
    
    def test_list_sessions_filter_by_status(self):
        """AC10: List sessions filters by status."""
        s1 = self.manager.create_session(agent="a", model="m", prompt="p1")
        s2 = self.manager.create_session(agent="a", model="m", prompt="p2")
        self.manager.update_status(s2.session_id, "completed")
        
        sessions = self.manager.list_sessions(status="completed")
        
        assert len(sessions) == 1
        assert sessions[0].session_id == s2.session_id
    
    def test_get_session_stats(self):
        """AC11: Get session statistics."""
        self.manager.create_session(agent="cursor", model="m1", prompt="p1")
        self.manager.create_session(agent="cursor", model="m2", prompt="p2")
        self.manager.create_session(agent="vscode", model="m3", prompt="p3")
        
        # Add exchanges
        s = self.manager.create_session(agent="cli", model="m4", prompt="p4")
        self.manager.append_exchange(s.session_id, "Task", "Outcome")
        self.manager.append_exchange(s.session_id, "Task2", "Outcome2")
        
        stats = self.manager.get_session_stats()
        
        assert stats["total_sessions"] == 4
        assert stats["by_agent"]["cursor"] == 2
        assert stats["by_agent"]["vscode"] == 1
        assert stats["total_exchanges"] == 2
    
    def test_search_sessions(self):
        """AC12: Search sessions by prompt content."""
        self.manager.create_session(agent="a", model="m", prompt="Refactor auth module")
        self.manager.create_session(agent="a", model="m", prompt="Add payment feature")
        self.manager.create_session(agent="a", model="m", prompt="Fix database bug")
        
        results = self.manager.search_sessions("auth")
        
        assert len(results) == 1
        assert "auth" in results[0].prompt.lower()
    
    def test_delete_session(self):
        """AC13: Delete session removes file."""
        session = self.manager.create_session(agent="a", model="m", prompt="p")
        session_id = session.session_id
        
        success = self.manager.delete_session(session_id)
        
        assert success == True
        assert self.manager.load_session(session_id) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
