# CuraOps Architecture: Matrix OS + Hermes Integration

**Version:** 1.0.0  
**Date:** 2026-04-07  
**Status:** Phase 1 Complete (7/7 Skills) | Phase 2 Design  
**Authors:** Rob + Hermes Agent

---

## 1. Executive Summary

CuraOps is a **CR-driven development framework** that combines:
- **Matrix OS**: Terminal User Interface (TUI) for session management
- **Hermes Agent**: AI-powered execution engine with 7 specialized skills
- **ASPICE Compliance**: Full traceability from requirements to code

**Key Principle:** *Separation of Concerns*
- Matrix OS = **Control Plane** (What should happen?)
- Hermes = **Execution Plane** (How is it executed?)

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER (Developer)                               │
│                              ────────────────                               │
│                         Zed Editor / Terminal                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Matrix OS (Python/Textual)                           │
│                        ─────────────────────────                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Matrix Rain  │  │ File Browser │  │   Terminal   │  │   Process    │   │
│  │    (UI)      │  │   (Widget)   │  │  (PTY-based) │  │   Monitor    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CuraOps Integration Layer                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │ Session      │  │ Workflow     │  │   Agent Coordinator      │  │   │
│  │  │ Manager      │  │ State Mach.  │  │   (Hermes Bridge)        │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Python Import (Same Process)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Hermes Agent (Python)                                │
│                        ─────────────────────                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        CuraOps Skills (7)                           │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │  Safety  │ │  Change  │ │  ASPICE  │ │ Pattern  │ │  Session │  │   │
│  │  │  Guard   │ │ Request  │ │  Link    │ │ Learning │ │  Manager │  │   │
│  │  │  (P1)    │ │  (P1)    │ │  (P2)    │ │   (P2)   │ │   (P2)   │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐                                          │   │
│  │  │  ASPICE  │ │  Multi   │                                          │   │
│  │  │ Conflict │ │  Agent   │                                          │   │
│  │  │Detector  │ │  Lock    │                                          │   │
│  │  │  (P2)    │ │  (P2)    │                                          │   │
│  │  └──────────┘ └──────────┘                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    LLM Integration (MCP/Native)                     │   │
│  │         Claude / GPT / Local Models via Model Context Protocol      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Skill Inventory

| # | Skill | Priority | Tests | Purpose | Location |
|---|-------|----------|-------|---------|----------|
| 1 | **safety-guard** | P1-Critical | 9/9 | Protect production data from accidental deletion | `conduvera/skills/safety-guard/` |
| 2 | **change-request** | P1 | 12/12 | CR-driven workflow management | `conduvera/skills/change-request/` |
| 3 | **aspice-link-manager** | P2 | 10/10 | ASPICE traceability compliance | `conduvera/skills/aspice-link-manager/` |
| 4 | **pattern-learning** | P2 | 9/9 | Learn from user behavior | `conduvera/skills/pattern-learning/` |
| 5 | **session-manager** | P2 | 13/13 | Session lifecycle management | `conduvera/skills/session-manager/` |
| 6 | **aspice-conflict-detector** | P2 | 18/18 | Detect ASPICE level conflicts | `conduvera/skills/aspice_conflict_detector/` |
| 7 | **multi-agent-lock** | P2 | 32/32 | File locking between agents | `conduvera/skills/multi-agent-lock/` |

**Total:** 103 Tests, 100% Pass Rate

---

## 4. Integration Patterns

### 4.1 Embedded Mode (Current)

```python
# Matrix OS imports Hermes skills directly
# Same Python process → Zero latency

from conduvera.skills.safety_guard import SafetyGuard
from conduvera.skills.change_request import ChangeRequest
from conduvera.skills.multi_agent_lock import MultiAgentLock

# Matrix OS Widget calls skill directly
class SafeFileBrowser(FileBrowser):
    def __init__(self):
        self.safety = SafetyGuard()
        self.locks = MultiAgentLock()
    
    def on_file_delete(self, path: Path):
        # P1-Critical: Always check Safety Guard
        result = self.safety.validate_delete(path)
        if result.risk_level == "CRITICAL":
            self.show_blocking_warning(result.reason)
            return False
        return True
```

**Pros:**
- Zero latency (<1ms)
- Simple debugging
- No serialization overhead

**Cons:**
- Tight coupling
- Single process failure domain

### 4.2 Future: MCP Mode (Optional)

```python
# If Hermes needs to run separately
# Use Model Context Protocol for communication

# Matrix OS side (MCP Client)
from mcp import ClientSession

async def call_safety_guard(path: str):
    async with ClientSession(server) as session:
        result = await session.call_tool(
            "safety_guard.validate",
            {"path": path, "operation": "delete"}
        )
        return result
```

---

## 5. CR-Driven Workflow (State Machine)

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
│  DRAFT  │────►│ VALIDATE │────►│   LOCK   │────►│ EXECUTE  │────►│  DONE   │
└────┬────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └─────────┘
     │               │                │                │
     │               │                │                │
     ▼               ▼                ▼                ▼
┌─────────┐    ┌──────────┐     ┌──────────┐    ┌──────────┐
│ CR      │    │ Safety   │     │  Multi   │    │ Pattern  │
│ Created │    │  Guard   │     │  Agent   │    │ Learning │
│         │    │ Validate │     │   Lock   │    │  Record  │
└─────────┘    └──────────┘     └──────────┘    └──────────┘
```

### State Transitions

| From | To | Trigger | Skills |
|------|-----|---------|--------|
| DRAFT | VALIDATE | User submits CR | change-request |
| VALIDATE | LOCK | Safety check passes | safety-guard, aspice-conflict-detector |
| LOCK | EXECUTE | Files locked | multi-agent-lock |
| EXECUTE | DONE | Work complete | session-manager, pattern-learning |

---

## 6. File Structure

```
matrix-os/
├── src/                          # Matrix OS Core
│   ├── core/
│   ├── ui/
│   ├── system/
│   └── utils/
│
├── conduvera/                      # CuraOps Integration (NEW)
│   ├── skills/                   # All 7 Skills
│   │   ├── safety-guard/
│   │   │   ├── SKILL.md
│   │   │   ├── __init__.py
│   │   │   ├── safety_guard.py
│   │   │   └── test_safety_guard.py
│   │   ├── change-request/
│   │   ├── aspice-link-manager/
│   │   ├── pattern-learning/
│   │   ├── session-manager/
│   │   ├── aspice_conflict_detector/
│   │   └── multi-agent-lock/
│   │
│   ├── docs/                     # Architecture Docs
│   │   ├── ARCHITECTURE.md
│   │   ├── WORKFLOWS.md
│   │   └── API_REFERENCE.md
│   │
│   └── tests/                    # Integration Tests
│       └── test_integration.py
│
├── tests/                        # Matrix OS Tests
├── docs/                         # Matrix OS Docs
├── config/
└── CURAOPS_ARCHITECTURE.md       # This file
```

---

## 7. Safety-Critical Path (P1)

```python
# P1-Critical: Safety Guard must block before ANY destructive operation

class CuraOpsSafetyMiddleware:
    """Middleware that intercepts all destructive operations."""
    
    def __init__(self):
        self.safety = SafetyGuard()
    
    def intercept(self, operation: str, path: Path) -> SafetyResult:
        # ALWAYS validate through Safety Guard
        result = self.safety.validate(
            operation=operation,
            path=path,
            context=self.get_context()
        )
        
        if result.blocked:
            self.log_blocked_operation(operation, path, result)
            raise SafetyBlockedError(result.reason)
        
        return result

# Usage in Matrix OS
middleware = CuraOpsSafetyMiddleware()

# File deletion
middleware.intercept("delete", path)

# Git operations
try:
    middleware.intercept("git_reset_hard", repo_path)
except SafetyBlockedError as e:
    show_blocking_modal(e.reason)
```

---

## 8. Multi-Agent Coordination

```python
# When multiple agents work on same codebase

class AgentCoordinator:
    """Coordinates file access between Matrix OS and external agents."""
    
    def __init__(self):
        self.locks = MultiAgentLock(storage_dir="/tmp/conduvera/locks")
    
    def start_session(self, agent_id: str, files: List[str]):
        # Claim files for this agent
        for file in files:
            try:
                lock = self.locks.claim_file(file, agent_id=agent_id)
                logger.info(f"Agent {agent_id} locked {file}")
            except MultiAgentLockError as e:
                # Show conflict in Matrix OS UI
                conflicts = self.locks.check_conflicts([file], agent_id)
                suggestions = self.locks.get_resolution_suggestions(conflicts)
                self.show_conflict_dialog(conflicts, suggestions)
                raise
    
    def end_session(self, agent_id: str):
        # Release all locks for this agent
        released = self.locks.release_agent_locks(agent_id)
        logger.info(f"Agent {agent_id} released {released} locks")
```

---

## 9. ASPICE Compliance Integration

```python
# Every operation is traceable

class CuraOpsTracer:
    """Traces all operations for ASPICE compliance."""
    
    def __init__(self):
        self.links = ASPICELinkManager()
        self.session = SessionManager()
    
    def trace_operation(self, operation: str, result: Any):
        """Create traceability link for operation."""
        
        # Get current session
        session = self.session.get_current_session()
        
        # Create link
        link = self.links.create_link(
            source=f"session:{session.id}",
            target=f"operation:{operation}",
            link_type="implements",
            metadata={
                "timestamp": datetime.now().isoformat(),
                "result": result,
                "agent": "hermes"
            }
        )
        
        # Store in session
        session.add_trace(link)
```

---

## 10. Implementation Roadmap

### Phase 1: ✅ COMPLETE (2026-04-07)
- [x] Extract 7 Skills from CuraOps Framework
- [x] 103 Tests, 100% Pass
- [x] E2E Verification complete

### Phase 2: Integration (Next)
- [ ] Create CuraOps Integration Layer in Matrix OS
- [ ] Implement Safety Middleware (P1-Critical)
- [ ] Add Agent Coordinator
- [ ] Create Session Management Widget
- [ ] Implement CR Workflow UI

### Phase 3: Advanced Features
- [ ] Pattern Learning UI
- [ ] ASPICE Compliance Dashboard
- [ ] Multi-Agent Visualizer
- [ ] Conflict Resolution UI

---

## 11. Testing Strategy

| Level | Scope | Location |
|-------|-------|----------|
| Unit | Individual skills | `conduvera/skills/*/test_*.py` |
| Integration | Skill interactions | `conduvera/tests/` |
| E2E | Full workflow | `tests/test_curaops_workflow.py` |
| Safety | P1-Critical paths | `conduvera/skills/safety-guard/test_*.py` |

---

## 12. References

- **CuraOps Framework**: `/home/roberto_schmidt/projects/CuraOps_Framework/`
- **Hermes Skills**: `~/.hermes/skills/`
- **Matrix OS**: `https://github.com/wietrob/matrix-os`
- **ASPICE Standard**: Automotive SPICE v3.1

---

## 13. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-07 | Embedded integration | Same Python process = zero latency |
| 2026-04-07 | State Machine for CRs | Deterministic, ASPICE-compliant |
| 2026-04-07 | Safety Guard as middleware | P1-Critical = cannot be bypassed |
| 2026-04-07 | 7 Skills complete | All P1/P2 skills extracted and tested |

---

**Next Action:** Implement CuraOps Integration Layer (Phase 2)
