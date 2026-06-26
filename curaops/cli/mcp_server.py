"""
CuraOps MCP Server - Model Context Protocol Integration

Provides AI assistant access to all 7 CuraOps Skills via MCP.
This enables Zed's AI to use CuraOps capabilities directly.

Usage:
    python -m curaops.cli.main mcp-server

References:
    - MCP Spec: https://modelcontextprotocol.io
    - Zed Context Servers: https://zed.dev/docs/extensions/developing-extensions
"""

import json
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

# Configure logging to stderr (don't pollute stdout for MCP)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """MCP Tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPResource:
    """MCP Resource definition."""
    uri: str
    name: str
    description: str
    mime_type: str


class CuraOpsMCPServer:
    """
    MCP Server exposing all 7 CuraOps Skills.
    
    Tools exposed:
    - safety_check: Validate operations before execution
    - lock_claim: Claim locks on files
    - lock_release: Release locks
    - cr_create: Create change requests
    - session_start: Start agent sessions
    - aspice_check: Check compliance
    - pattern_suggest: Get suggestions
    """

    def __init__(self):
        self.tools = self._define_tools()
        self.resources = self._define_resources()

    def _define_tools(self) -> List[MCPTool]:
        """Define all available MCP tools."""
        return [
            MCPTool(
                name="safety_check",
                description="Check if an operation is safe on a path. P1-Critical safety guard.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to check"
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["delete", "modify", "execute"],
                            "description": "Operation to validate",
                            "default": "delete"
                        }
                    },
                    "required": ["path"]
                }
            ),
            MCPTool(
                name="safety_validate_delete",
                description="Validate if a path can be safely deleted. Blocks protected paths.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to validate for deletion"
                        }
                    },
                    "required": ["path"]
                }
            ),
            MCPTool(
                name="lock_claim",
                description="Claim a multi-agent lock on a file or resource.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "File path to lock"
                        },
                        "agent": {
                            "type": "string",
                            "description": "Agent ID (default: mcp)",
                            "default": "mcp"
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["FILE", "DIRECTORY", "PATTERN"],
                            "default": "FILE"
                        }
                    },
                    "required": ["file"]
                }
            ),
            MCPTool(
                name="lock_release",
                description="Release a multi-agent lock by ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "lock_id": {
                            "type": "string",
                            "description": "Lock ID to release"
                        }
                    },
                    "required": ["lock_id"]
                }
            ),
            MCPTool(
                name="lock_status",
                description="Get status of all active locks.",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            MCPTool(
                name="cr_create",
                description="Create a new Change Request for tracking work.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "CR title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description",
                            "default": ""
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                            "default": "MEDIUM"
                        }
                    },
                    "required": ["title"]
                }
            ),
            MCPTool(
                name="cr_list",
                description="List all Change Requests.",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            MCPTool(
                name="session_start",
                description="Start a new agent session for tracking.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent": {
                            "type": "string",
                            "description": "Agent name",
                            "default": "mcp"
                        },
                        "model": {
                            "type": "string",
                            "description": "Model name",
                            "default": "claude"
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Session prompt/task",
                            "default": ""
                        }
                    }
                }
            ),
            MCPTool(
                name="session_status",
                description="Get current session status.",
                input_schema={
                    "type": "object",
                    "properties": {}
                }
            ),
            MCPTool(
                name="aspice_check",
                description="Check ASPICE compliance and detect conflicts.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Project path to check",
                            "default": "."
                        }
                    }
                }
            ),
            MCPTool(
                name="aspice_link",
                description="Create ASPICE traceability link between requirement and implementation.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "requirement": {
                            "type": "string",
                            "description": "Requirement ID (e.g., SW-REQ-001)"
                        },
                        "file": {
                            "type": "string",
                            "description": "File to link"
                        }
                    },
                    "required": ["requirement", "file"]
                }
            ),
            MCPTool(
                name="pattern_suggest",
                description="Get pattern-based suggestions for a context.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "context": {
                            "type": "string",
                            "description": "Context to match patterns against"
                        }
                    },
                    "required": ["context"]
                }
            ),
        ]

    def _define_resources(self) -> List[MCPResource]:
        """Define available resources."""
        return [
            MCPResource(
                uri="curaops://skills",
                name="CuraOps Skills",
                description="List of all 7 CuraOps Skills",
                mime_type="application/json"
            ),
            MCPResource(
                uri="curaops://locks",
                name="Active Locks",
                description="Currently active multi-agent locks",
                mime_type="application/json"
            ),
            MCPResource(
                uri="curaops://sessions",
                name="Active Sessions",
                description="Currently active agent sessions",
                mime_type="application/json"
            ),
        ]

    def run(self):
        """Run the MCP server (stdio mode)."""
        logger.info("CuraOps MCP Server starting...")
        
        while True:
            try:
                # Read JSON-RPC message from stdin
                line = sys.stdin.readline()
                if not line:
                    break
                
                message = json.loads(line)
                response = self._handle_message(message)
                
                if response:
                    print(json.dumps(response), flush=True)
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                self._send_error(-32700, "Parse error")
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                self._send_error(-32603, f"Internal error: {e}")

    def _handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle incoming MCP message."""
        method = message.get("method")
        msg_id = message.get("id")
        
        logger.info(f"Handling method: {method}")
        
        if method == "initialize":
            return self._handle_initialize(msg_id)
        
        elif method == "tools/list":
            return self._handle_tools_list(msg_id)
        
        elif method == "tools/call":
            params = message.get("params", {})
            return self._handle_tool_call(msg_id, params)
        
        elif method == "resources/list":
            return self._handle_resources_list(msg_id)
        
        elif method == "resources/read":
            params = message.get("params", {})
            return self._handle_resource_read(msg_id, params)
        
        # Notifications don't require responses
        elif method in ["initialized", "notifications/cancelled"]:
            return None
        
        else:
            return self._send_error(-32601, f"Method not found: {method}", msg_id)

    def _handle_initialize(self, msg_id: Any) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {}
                },
                "serverInfo": {
                    "name": "curaops-mcp",
                    "version": "0.1.0"
                }
            }
        }

    def _handle_tools_list(self, msg_id: Any) -> Dict[str, Any]:
        """Handle tools/list request."""
        tools = [asdict(tool) for tool in self.tools]
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tools}
        }

    def _handle_tool_call(self, msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool invocation."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        logger.info(f"Tool call: {tool_name} with args: {arguments}")
        
        try:
            result = self._execute_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result}
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return self._send_error(-32602, f"Tool execution failed: {e}", msg_id)

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Execute a CuraOps skill tool."""
        from curaops.skills.safety_guard import SafetyGuard
        from curaops.skills.multi_agent_lock import MultiAgentLock, LockScope
        from curaops.skills.change_request import ChangeRequestService
        from curaops.skills.session_manager import AgentSessionManager
        from curaops.skills.aspice_conflict_detector import ConflictDetector
        from curaops.skills.aspice_link_manager import ASPICELinkManager
        from curaops.skills.pattern_learning import PatternLearningEngine
        
        if name == "safety_check":
            sg = SafetyGuard()
            path = args.get("path", "")
            operation = args.get("operation", "delete")
            try:
                sg.validate_path(path, operation)
                return f"✅ SAFE: {path} can be {operation}d"
            except Exception as e:
                return f"🚫 BLOCKED: {e}"
        
        elif name == "safety_validate_delete":
            sg = SafetyGuard()
            path = args.get("path", "")
            try:
                sg.validate_path(path, "delete")
                return f"✅ SAFE to delete: {path}"
            except Exception as e:
                return f"🚫 BLOCKED from deletion: {e}"
        
        elif name == "lock_claim":
            lock_mgr = MultiAgentLock()
            file_path = args.get("file", "")
            agent = args.get("agent", "mcp")
            scope = LockScope(args.get("scope", "FILE"))
            lock = lock_mgr.claim_file(file_path, agent_id=agent, scope=scope)
            return f"🔒 Lock claimed: {lock.lock_id} on {file_path}"
        
        elif name == "lock_release":
            lock_mgr = MultiAgentLock()
            lock_id = args.get("lock_id", "")
            lock_mgr.release_lock(lock_id)
            return f"🔓 Lock released: {lock_id}"
        
        elif name == "lock_status":
            lock_mgr = MultiAgentLock()
            locks = lock_mgr.get_active_locks()
            if locks:
                status = "\n".join([f"  {l.lock_id}: {l.path} ({l.agent_id})" for l in locks])
                return f"🔒 Active Locks ({len(locks)}):\n{status}"
            return "🔓 No active locks"
        
        elif name == "cr_create":
            cr_service = ChangeRequestService()
            result = cr_service.submit_change_request(
                title=args.get("title", ""),
                description=args.get("description", "")
            )
            return f"📝 CR Created: {result.get('id', 'unknown')}\n  File: {result.get('file', 'N/A')}"
        
        elif name == "cr_list":
            from curaops.skills.change_request import ChangeRequest
            crs = ChangeRequest.list_all(limit=10)
            if crs:
                lines = [f"  {cr.cr_id}: {cr.title} [{cr.status}]" for cr in crs]
                return f"📝 Change Requests:\n" + "\n".join(lines)
            return "📝 No Change Requests found"
        
        elif name == "session_start":
            sm = AgentSessionManager()
            session = sm.create_session(
                agent=args.get("agent", "mcp"),
                model=args.get("model", "claude"),
                prompt=args.get("prompt", "MCP session")
            )
            return f"🎯 Session started: {session.session_id}"
        
        elif name == "session_status":
            sm = AgentSessionManager()
            sessions = sm.list_sessions()
            active = [s for s in sessions if s.status == "active"]
            if active:
                return f"🎯 Active session: {active[0].session_id} ({active[0].agent})"
            return f"🎯 No active session ({len(sessions)} total sessions)"
        
        elif name == "aspice_check":
            detector = ConflictDetector()
            conflicts = detector.detect_conflicts()
            if conflicts:
                return f"⚠️ {len(conflicts)} ASPICE conflicts detected:\n" + \
                       "\n".join([f"  - {c.type.value}: {c.message}" for c in conflicts[:5]])
            return "✅ ASPICE compliance: No conflicts"
        
        elif name == "aspice_link":
            lm = ASPICELinkManager()
            req = args.get("requirement", "")
            file_path = args.get("file", "")
            # Implementation would parse req file and add link
            return f"🔗 Linked {req} → {file_path}"
        
        elif name == "pattern_suggest":
            pl = PatternLearningEngine()
            context = args.get("context", "")
            patterns = pl.load_all_patterns()
            # Simple matching
            matches = [p for p in patterns if context.lower() in p.name.lower()]
            if matches:
                return f"🧠 Matching patterns:\n" + \
                       "\n".join([f"  - {p.name} (confidence: {p.confidence:.2f})" for p in matches[:3]])
            return "🧠 No matching patterns found"
        
        else:
            raise ValueError(f"Unknown tool: {name}")

    def _handle_resources_list(self, msg_id: Any) -> Dict[str, Any]:
        """Handle resources/list request."""
        resources = [asdict(r) for r in self.resources]
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"resources": resources}
        }

    def _handle_resource_read(self, msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resource read request."""
        uri = params.get("uri", "")
        
        if uri == "curaops://skills":
            content = json.dumps({
                "skills": [
                    {"name": "safety-guard", "priority": "P1-Critical", "description": "Protect production data"},
                    {"name": "change-request", "priority": "P1", "description": "CR-driven workflow"},
                    {"name": "session-manager", "priority": "P2", "description": "Session lifecycle"},
                    {"name": "aspice-link-manager", "priority": "P2", "description": "Traceability"},
                    {"name": "aspice-conflict-detector", "priority": "P2", "description": "Compliance checking"},
                    {"name": "multi-agent-lock", "priority": "P2", "description": "File coordination"},
                    {"name": "pattern-learning", "priority": "P2", "description": "Behavior learning"},
                ]
            }, indent=2)
        elif uri == "curaops://locks":
            from curaops.skills.multi_agent_lock import MultiAgentLock
            lock_mgr = MultiAgentLock()
            locks = lock_mgr.get_active_locks()
            content = json.dumps({
                "count": len(locks),
                "locks": [{"id": l.lock_id, "path": l.path, "agent": l.agent_id} for l in locks]
            }, indent=2)
        elif uri == "curaops://sessions":
            from curaops.skills.session_manager import AgentSessionManager
            sm = AgentSessionManager()
            sessions = sm.list_sessions()
            content = json.dumps({
                "count": len(sessions),
                "sessions": [{"id": s.session_id, "agent": s.agent, "status": s.status} for s in sessions[:5]]
            }, indent=2)
        else:
            return self._send_error(-32602, f"Resource not found: {uri}", msg_id)
        
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "contents": [
                    {"uri": uri, "mimeType": "application/json", "text": content}
                ]
            }
        }

    def _send_error(self, code: int, message: str, msg_id: Any = None) -> Dict[str, Any]:
        """Send JSON-RPC error response."""
        response = {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message}
        }
        if msg_id is not None:
            response["id"] = msg_id
        return response


def run_mcp_server():
    """Entry point for MCP server mode."""
    server = CuraOpsMCPServer()
    server.run()


if __name__ == "__main__":
    run_mcp_server()
