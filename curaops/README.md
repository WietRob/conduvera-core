# CuraOps for Matrix OS

**CR-driven development framework integrated into Matrix OS.**

## Quick Start

```python
# From anywhere in Matrix OS
from curaops.skills.safety_guard import SafetyGuard
from curaops.skills.session_manager import SessionManager

# Initialize
safety = SafetyGuard()
session = SessionManager()

# Use in your widget
result = safety.validate_delete(path)
if result.blocked:
    show_error(result.reason)
```

## Structure

```
curaops/
├── skills/           # 7 production-ready skills
│   ├── safety-guard/          # P1: Production data protection
│   ├── change-request/        # P1: CR workflow management
│   ├── aspice-link-manager/   # P2: Traceability compliance
│   ├── pattern-learning/      # P2: Behavior learning
│   ├── session-manager/       # P2: Session lifecycle
│   ├── aspice_conflict_detector/  # P2: Conflict detection
│   └── multi-agent-lock/      # P2: File locking
│
├── docs/            # Architecture documentation
│   ├── WORKFLOWS.md         # Concrete workflows
│   └── API_REFERENCE.md     # (coming in Phase 2)
│
└── tests/           # Integration tests
    └── test_integration.py
```

## Testing

```bash
# Run all skill tests
cd curaops/skills/safety-guard && python -m pytest

# Run integration tests
cd curaops && python -m pytest tests/
```

## Architecture

See [CURAOPS_ARCHITECTURE.md](../CURAOPS_ARCHITECTURE.md) for full system design.

**Key Principle:** Matrix OS (Control Plane) + Hermes Skills (Execution Plane)

## Status

- ✅ **Phase 1:** All 7 skills extracted (103 tests, 100% pass)
- 🔄 **Phase 2:** Integration layer implementation
- ⏳ **Phase 3:** Advanced UI features

## License

Same as Matrix OS (Apache 2.0)
