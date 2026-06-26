"""
Captain Launcher — agent launch Command.

Startet Agenten kontrolliert ueber das Harness:
1. Registry pruefen (Agent bekannt?)
2. Stream State pruefen (BLOCKED?)
3. Worktree Sentinel pruefen (Safe?)
4. Environment setzen (OPENAI_BASE_URL, Client-Kontext)
5. Session starten (tmux/Adapter)
6. Session-Ref speichern
7. EventLog schreiben

Keine neue Parallelwelt. Nur Integration.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import AgentRegistry, AgentRecord, AgentStatus
from .stream_state import StreamStateStore, StreamState
from .worktree_sentinel import WorktreeSentinel
from .eventlog import EventLog


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 8900
DEFAULT_GATEWAY_BASE_URL = f"http://{DEFAULT_GATEWAY_HOST}:{DEFAULT_GATEWAY_PORT}/v1"


# ---------------------------------------------------------------------------
# Launch Result
# ---------------------------------------------------------------------------

@dataclass
class LaunchResult:
    """Ergebnis eines Agent-Launch-Versuchs."""
    success: bool
    agent_name: str
    session_ref: str = ""
    error: str = ""
    warnings: List[str] = field(default_factory=list)
    env_set: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "success": self.success,
            "agent": self.agent_name,
        }
        if self.session_ref:
            d["session_ref"] = self.session_ref
        if self.error:
            d["error"] = self.error
        if self.warnings:
            d["warnings"] = self.warnings
        if self.env_set:
            d["env_set"] = self.env_set
        return d


class AgentLauncher:
    """
    Kontrollierter Agent-Start ueber das Harness.

    Workflow:
        1. Registry: Agent registriert?
        2. Stream State: Nicht BLOCKED?
        3. Worktree Sentinel: Kein aktiver Agent im Worktree?
        4. Environment: OPENAI_BASE_URL auf Gateway
        5. Adapter: Session starten (tmux/opencode/manual)
        6. Registry: Session-Ref speichern
        7. EventLog: Launch protokollieren
    """

    def __init__(
        self,
        registry: AgentRegistry,
        stream_store: StreamStateStore,
        sentinel: WorktreeSentinel,
        event_log: EventLog,
        gateway_base_url: str = DEFAULT_GATEWAY_BASE_URL,
    ) -> None:
        self._registry = registry
        self._stream_store = stream_store
        self._sentinel = sentinel
        self._event_log = event_log
        self._gateway_base_url = gateway_base_url

    def launch(
        self,
        agent_name: str,
        *,
        client_name: Optional[str] = None,
        gateway_profile: Optional[str] = None,
        sensitive_class: Optional[str] = None,
        extra_env: Optional[Dict[str, str]] = None,
        dry_run: bool = False,
    ) -> LaunchResult:
        """
        Startet einen Agenten kontrolliert.
        """
        warnings: List[str] = []
        client_name = client_name or agent_name

        # --- 1. Registry pruefen ---
        record = self._registry.get(agent_name)
        if record is None:
            return LaunchResult(
                success=False,
                agent_name=agent_name,
                error=f"Agent '{agent_name}' nicht in Registry gefunden",
            )

        if record.status == AgentStatus.ACTIVE:
            return LaunchResult(
                success=False,
                agent_name=agent_name,
                error=f"Agent '{agent_name}' ist bereits aktiv (session: {record.session})",
            )

        # --- 2. Stream State pruefen ---
        stream = self._stream_store.get(agent_name)
        if stream is not None:
            state_name = stream.state.value if hasattr(stream.state, 'value') else str(stream.state)
            if "BLOCKED" in state_name.upper():
                return LaunchResult(
                    success=False,
                    agent_name=agent_name,
                    error=f"Agent '{agent_name}' ist BLOCKED ({state_name}). Nur BLOCKER-Antwort erlaubt.",
                )
            if state_name in ("MERGED", "CLOSED"):
                warnings.append(f"Stream ist {state_name} — wird zurueckgesetzt")

        # --- 3. Worktree Sentinel pruefen ---
        worktree = record.worktree
        if worktree:
            allowed = self._sentinel.can_mutate(agent_name, "launch")
            if not allowed:
                return LaunchResult(
                    success=False,
                    agent_name=agent_name,
                    error=f"Worktree nicht sicher: Agent '{agent_name}' hat aktiven Worktree",
                )

        # --- 4. Environment zusammenbauen ---
        env_set: Dict[str, str] = {
            "OPENAI_BASE_URL": self._gateway_base_url,
            "OPENAI_API_KEY": "curaops-gateway-managed",
            "X_GATEWAY_CLIENT": client_name,
        }

        if gateway_profile:
            env_set["GATEWAY_PROFILE"] = gateway_profile
        if sensitive_class:
            env_set["SENSITIVE_CLASS"] = sensitive_class

        env_set["AGENT_ID"] = agent_name
        if record.task:
            env_set["TASK_KEY"] = record.task
        if worktree:
            env_set["AGENT_WORKTREE"] = worktree

        if extra_env:
            env_set.update(extra_env)

        # --- 5. Session starten (oder Dry-Run) ---
        if dry_run:
            return LaunchResult(
                success=True,
                agent_name=agent_name,
                session_ref=f"dry-run:{agent_name}",
                warnings=warnings + ["DRY-RUN: Keine Session gestartet"],
                env_set=env_set,
            )

        session_ref = self._start_session(record, env_set)
        if session_ref is None:
            return LaunchResult(
                success=False,
                agent_name=agent_name,
                error="Session-Start fehlgeschlagen",
            )

        # --- 6. Registry aktualisieren ---
        self._registry.update(
            agent_name,
            status=AgentStatus.ACTIVE,
            session=session_ref,
        )

        # --- 7. EventLog ---
        self._event_log.append({
            "event": "agent_launched",
            "agent": agent_name,
            "session_ref": session_ref,
            "gateway_client": client_name,
            "gateway_profile": gateway_profile,
            "worktree": worktree,
            "warnings": warnings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return LaunchResult(
            success=True,
            agent_name=agent_name,
            session_ref=session_ref,
            warnings=warnings,
            env_set=env_set,
        )

    def _start_session(
        self,
        record: AgentRecord,
        env_set: Dict[str, str],
    ) -> Optional[str]:
        """Startet eine Session basierend auf dem Adapter."""
        tool = record.tool
        worktree = record.worktree
        session_name = f"curaops-{record.agent_id}"

        if tool in ("opencode", "droid", "zed"):
            return self._start_tmux_session(session_name, worktree, env_set, tool)
        elif tool == "manual":
            return f"manual:{record.agent_id}"
        else:
            return self._start_tmux_session(session_name, worktree, env_set, tool)

    @staticmethod
    def _start_tmux_session(
        session_name: str,
        worktree: Optional[str],
        env_set: Dict[str, str],
        tool: str,
    ) -> Optional[str]:
        """Startet eine tmux-Session fuer den Agenten."""
        try:
            subprocess.run(
                ["tmux", "has-session", "-t", session_name],
                capture_output=True,
                timeout=5,
            )
            return f"tmux:{session_name}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        cwd = worktree or os.getcwd()

        # Build environment export string
        env_exports = " ".join(f"{k}={v}" for k, v in env_set.items())

        cmd = f"cd {cwd} && {env_exports} {tool}"
        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, cmd],
                capture_output=True,
                timeout=10,
            )
            return f"tmux:{session_name}"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
