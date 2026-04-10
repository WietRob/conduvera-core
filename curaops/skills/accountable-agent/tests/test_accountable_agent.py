"""
Tests for Accountable Agent Service (Context B)
Tests the thin accountability layer on top of Compliance-CR (Context C)
"""

import json
import sys
import unittest
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "change-request"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "aspice-link-manager"))

# Import after path setup - use importlib to handle non-package imports
import importlib.util

# Load accountable_agent module directly
aa_path = Path(__file__).parent.parent / "__init__.py"
spec_aa = importlib.util.spec_from_file_location("accountable_agent", aa_path)
accountable_agent = importlib.util.module_from_spec(spec_aa)
sys.modules["accountable_agent"] = accountable_agent
spec_aa.loader.exec_module(accountable_agent)

from accountable_agent import (
    AccountableAgentService,
    AgentContext,
    ChangeIntent,
    AccountableChange,
    AccountabilityError,
    MissingMandatoryLinkError,
    create_accountable_change,
    validate_accountable_change,
    generate_accountability_report,
    submit_change_request,  # Wrapper function from B layer
)


class TestAccountableAgentService(unittest.TestCase):
    """Test Accountable Agent Service core functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(__file__).parent / "test_workspace"
        self.test_dir.mkdir(exist_ok=True)
        
        # Create changes directory
        self.changes_dir = self.test_dir / "changes"
        self.changes_dir.mkdir(exist_ok=True)
        
        # Create evidence directory
        self.evidence_dir = self.changes_dir / "evidence"
        self.evidence_dir.mkdir(exist_ok=True)
        
        self.service = AccountableAgentService(
            project_root=self.test_dir,
            changes_path=self.changes_dir,
            evidence_dir=self.evidence_dir,
        )
        
        # Sample agent context
        self.agent_context = AgentContext(
            agent_id="test-agent-001",
            agent_name="TestAgent",
            model="claude-sonnet-4",
            tools_used=["file_edit", "terminal", "web_search"],
            session_id="session-123",
        )
        
        # Sample change intent
        self.change_intent = ChangeIntent(
            description="Fix authentication bug in login flow",
            change_type="bugfix",
            files_affected=["src/auth.py", "tests/test_auth.py"],
            justification="Security vulnerability reported in issue #42",
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_register_accountable_change_with_all_links(self):
        """B-TEST-001: Register accountable change with CR and requirements."""
        # First create a CR (using wrapper from B layer)
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Fix auth bug",
            description="Fix login vulnerability",
            requirement_refs=["SW-REQ-001", "SEC-REQ-005"],
        )
        cr_id = cr_result["cr_id"]
        
        # Now register accountable change
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001", "SEC-REQ-005"],
        )
        
        self.assertIsNotNone(ac.accountable_id)
        self.assertTrue(ac.accountable_id.startswith("AC-"))
        self.assertEqual(ac.cr_id, cr_id)
        self.assertEqual(ac.requirement_refs, ["SW-REQ-001", "SEC-REQ-005"])
        self.assertEqual(ac.status, "linked")
        self.assertIsNone(ac.block_reason)
    
    def test_register_accountable_change_strict_missing_links_blocked(self):
        """B-TEST-002: Strict mode blocks changes with missing mandatory links."""
        with self.assertRaises(MissingMandatoryLinkError) as context:
            self.service.register_accountable_change(
                agent_context=self.agent_context,
                change_intent=self.change_intent,
                cr_id=None,  # Missing
                requirement_refs=None,  # Missing
                strict=True,
            )
        
        error_msg = str(context.exception)
        self.assertIn("blocked", error_msg.lower())
        self.assertIn("missing mandatory links", error_msg)
        self.assertIn("cr_id", error_msg)
        self.assertIn("requirement_refs", error_msg)
    
    def test_register_accountable_change_non_strict_allows_missing_links(self):
        """B-TEST-003: Non-strict mode allows registration with missing links."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id=None,
            requirement_refs=None,
            strict=False,
        )
        
        self.assertEqual(ac.status, "pending")
        self.assertIsNone(ac.block_reason)
    
    def test_validate_accountability_valid(self):
        """B-TEST-004: Validate passes when all mandatory links present."""
        # Create CR first (using wrapper from B layer)
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Fix auth bug",
            description="Fix login vulnerability",
            requirement_refs=["SW-REQ-001"],
        )
        cr_id = cr_result["cr_id"]
        
        # Register and validate
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id=cr_id,
            requirement_refs=["SW-REQ-001"],
        )
        
        result = self.service.validate_accountability(ac.accountable_id)
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["accountable_id"], ac.accountable_id)
        self.assertEqual(result["cr_id"], cr_id)
        self.assertEqual(len(result["issues"]), 0)
    
    def test_validate_accountability_missing_cr_blocked(self):
        """B-TEST-005: Validation fails when CR doesn't exist."""
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id="CR-NONEXISTENT",
            requirement_refs=["SW-REQ-001"],
            strict=False,  # Allow registration
        )
        
        result = self.service.validate_accountability(ac.accountable_id)
        
        self.assertFalse(result["valid"])
        self.assertIn("does not exist", str(result["issues"]))
        self.assertEqual(ac.status, "blocked")
    
    def test_validate_accountability_missing_requirements_blocked(self):
        """B-TEST-006: Validation fails when requirements missing."""
        # Create CR without requirements (using wrapper from B layer)
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Fix auth bug",
            description="Fix login vulnerability",
            requirement_refs=[],
        )
        cr_id = cr_result["cr_id"]
        
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id=cr_id,
            requirement_refs=[],  # Empty
            strict=False,
        )
        
        result = self.service.validate_accountability(ac.accountable_id)
        
        self.assertFalse(result["valid"])
        self.assertIn("Missing requirement references", result["issues"])
    
    def test_generate_accountability_evidence_json(self):
        """B-TEST-007: Generate JSON evidence packet."""
        # Setup (using wrapper from B layer)
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Fix auth bug",
            description="Fix login vulnerability",
            requirement_refs=["SW-REQ-001"],
        )
        
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id=cr_result["cr_id"],
            requirement_refs=["SW-REQ-001"],
        )
        
        # Generate evidence
        evidence_path = self.service.generate_accountability_evidence(
            ac.accountable_id, output_format="json"
        )
        
        # Verify file exists
        self.assertTrue(Path(evidence_path).exists())
        
        # Verify content
        with open(evidence_path) as f:
            evidence = json.load(f)
        
        self.assertEqual(evidence["accountable_change"]["accountable_id"], ac.accountable_id)
        self.assertEqual(evidence["accountable_change"]["agent_context"]["agent_name"], "TestAgent")
        self.assertEqual(evidence["accountable_change"]["change_intent"]["change_type"], "bugfix")
        self.assertEqual(evidence["validation"]["valid"], True)
        self.assertEqual(evidence["service_version"], "B-0.1.0")
    
    def test_generate_accountability_evidence_markdown(self):
        """B-TEST-008: Generate Markdown evidence report."""
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Fix auth bug",
            description="Fix login vulnerability",
            requirement_refs=["SW-REQ-001"],
        )
        
        ac = self.service.register_accountable_change(
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id=cr_result["cr_id"],
            requirement_refs=["SW-REQ-001"],
        )
        
        evidence_path = self.service.generate_accountability_evidence(
            ac.accountable_id, output_format="markdown"
        )
        
        self.assertTrue(Path(evidence_path).exists())
        self.assertTrue(evidence_path.endswith(".md"))
        
        with open(evidence_path) as f:
            content = f.read()
        
        self.assertIn("# Accountability Evidence Report", content)
        self.assertIn(ac.accountable_id, content)
        self.assertIn("TestAgent", content)
        self.assertIn("claude-sonnet-4", content)
    
    def test_agent_context_to_dict(self):
        """B-TEST-009: AgentContext serializes correctly."""
        ctx = AgentContext(
            agent_id="agent-123",
            agent_name="Claude",
            model="claude-opus",
            tools_used=["read", "write"],
            session_id="sess-456",
            platform="test",
        )
        
        d = ctx.to_dict()
        self.assertEqual(d["agent_id"], "agent-123")
        self.assertEqual(d["agent_name"], "Claude")
        self.assertEqual(d["model"], "claude-opus")
        self.assertEqual(d["tools_used"], ["read", "write"])
        self.assertEqual(d["session_id"], "sess-456")
        self.assertEqual(d["platform"], "test")
    
    def test_change_intent_to_dict(self):
        """B-TEST-010: ChangeIntent serializes correctly."""
        intent = ChangeIntent(
            description="Add feature",
            change_type="feature",
            files_affected=["a.py", "b.py"],
            estimated_impact="high",
            justification="Customer request",
        )
        
        d = intent.to_dict()
        self.assertEqual(d["description"], "Add feature")
        self.assertEqual(d["change_type"], "feature")
        self.assertEqual(d["files_affected"], ["a.py", "b.py"])
        self.assertEqual(d["estimated_impact"], "high")
        self.assertEqual(d["justification"], "Customer request")
    
    def test_accountable_change_to_dict(self):
        """B-TEST-011: AccountableChange serializes correctly."""
        ac = AccountableChange(
            accountable_id="AC-TEST123",
            agent_context=self.agent_context,
            change_intent=self.change_intent,
            cr_id="CR-001",
            requirement_refs=["REQ-001"],
            status="validated",
        )
        
        d = ac.to_dict()
        self.assertEqual(d["accountable_id"], "AC-TEST123")
        self.assertEqual(d["cr_id"], "CR-001")
        self.assertEqual(d["status"], "validated")
        self.assertEqual(d["agent_context"]["agent_name"], "TestAgent")
        self.assertEqual(d["change_intent"]["change_type"], "bugfix")


class TestConvenienceFunctions(unittest.TestCase):
    """Test high-level convenience functions."""
    
    def setUp(self):
        self.test_dir = Path(__file__).parent / "test_workspace_funcs"
        self.test_dir.mkdir(exist_ok=True)
        (self.test_dir / "changes").mkdir(exist_ok=True)
    
    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_create_accountable_change_success(self):
        """B-TEST-012: High-level create function works with links."""
        # First create a CR (using wrapper from B layer)
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Test CR",
            description="Test",
            requirement_refs=["REQ-001"],
        )
        
        result = create_accountable_change(
            project_path=str(self.test_dir),
            agent_id="agent-001",
            agent_name="TestBot",
            model="gpt-4",
            change_description="Fix bug",
            change_type="bugfix",
            cr_id=cr_result["cr_id"],
            requirement_refs=["REQ-001"],
            tools_used=["shell", "edit"],
            files_affected=["main.py"],
        )
        
        self.assertTrue(result["success"])
        self.assertTrue(result["accountable_id"].startswith("AC-"))
        self.assertEqual(result["status"], "linked")
    
    def test_create_accountable_change_strict_blocked(self):
        """B-TEST-013: High-level create function blocks on missing links."""
        result = create_accountable_change(
            project_path=str(self.test_dir),
            agent_id="agent-001",
            agent_name="TestBot",
            model="gpt-4",
            change_description="Fix bug",
            change_type="bugfix",
            cr_id=None,
            requirement_refs=None,
            strict=True,
        )
        
        self.assertFalse(result["success"])
        self.assertTrue(result["blocked"])
        self.assertIn("missing mandatory links", result["error"])


class TestEndToEndWorkflow(unittest.TestCase):
    """B-TEST-E2E: End-to-end accountable change workflow."""
    
    def setUp(self):
        self.test_dir = Path(__file__).parent / "test_e2e"
        self.test_dir.mkdir(exist_ok=True)
        (self.test_dir / "changes").mkdir(exist_ok=True)
        (self.test_dir / "changes" / "evidence").mkdir(exist_ok=True)
    
    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_full_accountable_workflow(self):
        """
        B-TEST-E2E-001: Full workflow - CR creation → Accountable registration →
        Validation → Evidence generation
        """
        # Step 1: Create CR with requirements (C core via B wrapper)
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Implement user authentication",
            description="Add OAuth2 login flow",
            requirement_refs=["SW-REQ-AUTH-001", "SEC-REQ-002"],
        )
        self.assertEqual(cr_result["status"], "SUBMITTED")
        cr_id = cr_result["cr_id"]
        
        # Step 2: Register accountable change (B layer)
        service = AccountableAgentService(project_root=self.test_dir)
        
        agent_context = AgentContext(
            agent_id="claude-code-001",
            agent_name="Claude Code",
            model="claude-sonnet-4",
            tools_used=["file_edit", "terminal", "web_search"],
            session_id="sess-abc-123",
            platform="matrix-os",
        )
        
        change_intent = ChangeIntent(
            description="Implement OAuth2 authentication handler",
            change_type="feature",
            files_affected=["src/auth/oauth2.py", "tests/test_oauth2.py"],
            justification="Required by SW-REQ-AUTH-001",
        )
        
        ac = service.register_accountable_change(
            agent_context=agent_context,
            change_intent=change_intent,
            cr_id=cr_id,
            requirement_refs=["SW-REQ-AUTH-001", "SEC-REQ-002"],
        )
        
        self.assertEqual(ac.status, "linked")
        self.assertEqual(ac.cr_id, cr_id)
        
        # Step 3: Validate accountability
        validation = service.validate_accountability(ac.accountable_id)
        self.assertTrue(validation["valid"])
        self.assertEqual(len(validation["issues"]), 0)
        
        # Step 4: Generate evidence
        evidence_path = service.generate_accountability_evidence(
            ac.accountable_id, output_format="json"
        )
        
        with open(evidence_path) as f:
            evidence = json.load(f)
        
        # Verify evidence chain
        self.assertEqual(evidence["accountable_change"]["cr_id"], cr_id)
        self.assertEqual(
            evidence["accountable_change"]["requirement_refs"],
            ["SW-REQ-AUTH-001", "SEC-REQ-002"]
        )
        self.assertTrue(evidence["validation"]["valid"])
    
    def test_blocked_workflow_missing_requirements(self):
        """
        B-TEST-E2E-002: Blocked workflow - missing requirements should block
        """
        service = AccountableAgentService(project_root=self.test_dir)
        
        # Create CR but don't pass requirements to accountable change
        cr_result = submit_change_request(
            str(self.test_dir),
            title="Fix bug",
            description="Fix",
            requirement_refs=["REQ-001"],
        )
        
        agent_context = AgentContext(
            agent_id="agent-001",
            agent_name="Test Agent",
            model="gpt-4",
            tools_used=["edit"],
        )
        
        change_intent = ChangeIntent(
            description="Fix critical bug",
            change_type="bugfix",
            files_affected=["bug.py"],
        )
        
        # Register without requirements (non-strict)
        ac = service.register_accountable_change(
            agent_context=agent_context,
            change_intent=change_intent,
            cr_id=cr_result["cr_id"],
            requirement_refs=[],  # Empty!
            strict=False,
        )
        
        # Validation should fail
        validation = service.validate_accountability(ac.accountable_id)
        self.assertFalse(validation["valid"])
        self.assertIn("Missing requirement references", validation["issues"])
        self.assertEqual(ac.status, "blocked")


if __name__ == "__main__":
    unittest.main()
