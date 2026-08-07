# Multi-Agent Lock

Coordinate file access between multiple AI agents to prevent conflicts.

## Purpose

Prevent multiple agents from modifying the same files simultaneously by implementing a claim/lock system with conflict detection and resolution suggestions.

## Usage

```python
from multi_agent_lock import MultiAgentLock, LockScope

# Initialize lock manager
lock_mgr = MultiAgentLock(storage_dir="/path/to/locks")

# Claim a file for an agent
lock = lock_mgr.claim_file("src/payment.rs", agent_id="cursor")

# Claim with scope (file, directory, or pattern)
lock = lock_mgr.claim_file("src/", agent_id="claude", scope=LockScope.DIRECTORY)

# Check for conflicts before claiming
conflicts = lock_mgr.check_conflicts(["src/payment.rs", "src/auth.rs"], agent_id="codex")

# Get resolution suggestions
suggestions = lock_mgr.get_resolution_suggestions(conflicts)

# Release lock when done
lock_mgr.release_lock(lock.lock_id)

# Or release all locks for an agent
lock_mgr.release_agent_locks("cursor")
```

## Lock Scopes

| Scope | Description |
|-------|-------------|
| `FILE` | Single file only |
| `DIRECTORY` | Directory and all contents |
| `PATTERN` | Glob pattern match |

## Conflict Types

| Type | Description |
|------|-------------|
| `FILE_ALREADY_LOCKED` | File claimed by another agent |
| `DIRECTORY_OVERLAP` | Directory contains locked files |
| `PATTERN_MATCH` | Pattern overlaps with existing lock |
| `AGENT_SELF_CONFLICT` | Same agent has conflicting lock |

## API

### Classes

- `MultiAgentLock(storage_dir)` - Main lock manager
- `Lock` - Lock dataclass
- `LockScope` - Enum of lock scopes
- `Conflict` - Conflict dataclass
- `ConflictType` - Enum of conflict types

### Methods

- `claim_file(path, agent_id, scope=FILE, ttl=3600)` - Claim file/directory
- `check_conflicts(paths, agent_id)` - Check for conflicts
- `get_resolution_suggestions(conflicts)` - Get suggestions
- `release_lock(lock_id)` - Release specific lock
- `release_agent_locks(agent_id)` - Release all agent locks
- `is_locked(path)` - Check if path is locked
- `get_active_locks()` - Get all active locks

## Storage

Locks are stored as JSON files in the storage directory:
- `{storage_dir}/{lock_id}.json`

Each lock file contains:
```json
{
  "lock_id": "uuid",
  "agent_id": "cursor",
  "path": "src/file.rs",
  "scope": "FILE",
  "claimed_at": "2026-01-07T10:00:00",
  "expires_at": "2026-01-07T11:00:00"
}
```

## TTL

Default TTL is 3600 seconds (1 hour). Expired locks are automatically cleaned up.
