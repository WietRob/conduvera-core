# Agent Session Manager

Session Persistence & Management for AI Agents
Extracted from CuraOps Framework (SW-REQ-053)

## Features

✅ Create and manage agent sessions  
✅ Session persistence (JSON)  
✅ Session history tracking  
✅ Resume existing sessions  
✅ Session search & filtering  
✅ Session statistics  
✅ Metadata tracking  
✅ **No external dependencies**  

## Installation

```bash
# No external dependencies!
# Only uses Python standard library
```

## Usage

### Python API

```python
from session_manager import AgentSessionManager

# Initialize
manager = AgentSessionManager(storage_dir="./sessions")

# Create session
session = manager.create_session(
    agent="cursor",
    model="claude-sonnet",
    prompt="Refactor auth module",
    metadata={"project": "my-app"},
)
print(session.session_id)  # sess_20260405_123456_abc123

# Add exchange
manager.append_exchange(
    session_id=session.session_id,
    task="Analyze code",
    outcome="Found 3 issues",
    tokens=150,
)

# Update status
manager.update_status(session.session_id, "completed")

# List sessions
sessions = manager.list_sessions()

# Filter by agent
cursor_sessions = manager.list_sessions(agent="cursor")

# Search
results = manager.search_sessions("auth")

# Get stats
stats = manager.get_session_stats()
```

### CLI

```python
# Create session
create_session("./my-project", "cursor", "claude-sonnet", "Refactor auth")

# List sessions
list_sessions("./my-project")

# Filter by agent
list_sessions("./my-project", agent="cursor")

# Show session details
show_session("./my-project", "sess_20260405_123456_abc123")

# Show statistics
session_stats("./my-project")
```

## Session Format

```json
{
  "session_id": "sess_20260405_123456_abc123",
  "agent": "cursor",
  "model": "claude-sonnet",
  "mode": "interactive",
  "prompt": "Refactor auth module",
  "created_at": "2026-04-05T12:34:56",
  "updated_at": "2026-04-05T12:45:00",
  "status": "active",
  "history": [
    {
      "timestamp": "2026-04-05T12:35:00",
      "task": "Analyze code",
      "outcome": "Found issues",
      "tokens": 150,
      "duration_ms": 5000
    }
  ],
  "metadata": {
    "project": "my-app"
  }
}
```

## Storage Structure

```
.sessions/
├── sess_20260405_123456_abc123.json
├── sess_20260405_123501_def456.json
└── ...
```

## Session States

- `active` - Currently running
- `paused` - Temporarily stopped
- `completed` - Finished successfully
- `error` - Error occurred

## Agents

Common agent names:
- `cursor` - Cursor IDE
- `vscode` - VS Code
- `cli` - Command line
- `github` - GitHub Copilot
- `zed` - Zed editor

## Models

Supported models:
- `claude-opus` - Anthropic Opus
- `claude-sonnet` - Anthropic Sonnet
- `claude-haiku` - Anthropic Haiku
- `gpt-4` - OpenAI GPT-4
- `gpt-4-turbo` - OpenAI GPT-4 Turbo
- `local` - Local model

## Tests

```bash
cd ~/.hermes/skills/session-manager
python -m pytest tests/ -v
```

13 tests covering:
- Session creation
- Session loading
- Exchange appending
- Status updates
- Filtering
- Statistics
- Search

## Example Output

```
✅ sess_20260406_123456_abc123 - cursor
✅ sess_20260406_123501_def456 - vscode

📋 Sessions:
   sess_20260406_123456_abc123 [active] - cursor
   sess_20260406_123501_def456 [completed] - vscode

📊 Session Statistics:
   Total Sessions: 2
   Total Exchanges: 2
   By Agent: {'cursor': 1, 'vscode': 1}
```

## Requirements Covered

- SW-REQ-053: Agent Session Management & Execution
- SW-ARCH-008: AI Orchestration Pattern
- Session persistence
- Execution tracking

## Differences from CuraOps Framework

- No UniversalContextManager dependency
- No LLMService integration (simplified)
- No caching layer
- Same session management logic
- Works standalone
