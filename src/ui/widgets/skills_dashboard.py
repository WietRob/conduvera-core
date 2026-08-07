"""
CuraOps Skills Dashboard Widget for Matrix OS TUI

Integrates all 7 CuraOps skills into the Textual TUI:
- Safety Guard (P1-Critical)
- Change Request
- Session Manager
- ASPICE Link Manager
- ASPICE Conflict Detector
- Multi-Agent Lock
- Pattern Learning
"""

from textual.widgets import Static
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.table import Table as RichTable
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from src.utils.logger import logger


class SkillsDashboard(VerticalScroll):
    """
    Skills Dashboard - Real-time monitoring of CuraOps skills.
    
    Displays:
    - Active locks
    - Session status
    - ASPICE compliance
    - Recent change requests
    - Safety status
    """

    auto_refresh = reactive(True)
    refresh_interval = reactive(5.0)  # seconds (slower than system metrics)

    DEFAULT_CSS = """
    SkillsDashboard {
        background: rgba(0, 20, 40, 0.8);
        border: round #0088FF;
        padding: 1;
        scrollbar-background: rgba(0, 10, 20, 0.5);
        scrollbar-color: #0088FF;
    }

    SkillsDashboard:focus {
        border: heavy #0088FF;
        background: rgba(0, 30, 60, 0.9);
    }

    .skills-header {
        background: rgba(0, 80, 160, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    .skills-section {
        background: rgba(0, 15, 30, 0.7);
        border: round #0066CC;
        padding: 1;
        margin: 1 0;
    }

    .skill-critical {
        border: heavy #FF0000;
    }

    .skill-warning {
        border: round #FFAA00;
    }

    .skill-ok {
        border: round #00AA00;
    }

    .metric-critical {
        color: #FF0000;
    }

    .metric-warning {
        color: #FFAA00;
    }

    .metric-ok {
        color: #00FF00;
    }
    """

    class SkillsUpdated(Message):
        """Message sent when skills data is updated."""

        def __init__(self, data: Dict[str, Any]) -> None:
            super().__init__()
            self.data = data

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.last_update = None
        self.skills_data = {}

    def compose(self):
        """Create dashboard widgets."""
        yield Static(
            "[bold bright_blue]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_blue]║   🔧 CuraOps Skills Dashboard            ║[/]\n"
            "[bold bright_blue]╚═══════════════════════════════════════════╝[/]",
            classes="skills-header"
        )
        yield Static(
            "[dim cyan]Real-time skills monitoring and status[/]\n"
            "[dim]Auto-refresh every 5 seconds | Press 'S' to toggle panel[/dim]",
            id="skills-help"
        )

    def on_mount(self) -> None:
        """Start auto-refresh when mounted."""
        if self.auto_refresh:
            self.set_interval(self.refresh_interval, self.refresh_dashboard)
        self.refresh_dashboard()
        logger.info("Skills Dashboard initialized")

    def refresh_dashboard(self) -> None:
        """Refresh all skills data."""
        try:
            # Collect data from all skills
            self.skills_data = {
                "locks": self.get_lock_data(),
                "sessions": self.get_session_data(),
                "aspice": self.get_aspice_data(),
                "change_requests": self.get_cr_data(),
                "safety": self.get_safety_data(),
                "patterns": self.get_pattern_data(),
                "timestamp": datetime.now().isoformat()
            }

            self.last_update = datetime.now()

            # Clear previous displays
            for widget in self.query(".skills-section"):
                widget.remove()

            # Display sections
            self.display_locks(self.skills_data["locks"])
            self.display_sessions(self.skills_data["sessions"])
            self.display_aspice(self.skills_data["aspice"])
            self.display_change_requests(self.skills_data["change_requests"])
            self.display_safety(self.skills_data["safety"])
            self.display_patterns(self.skills_data["patterns"])

            self.post_message(self.SkillsUpdated(self.skills_data))

        except Exception as e:
            logger.error(f"Error refreshing skills dashboard: {e}")

    def get_lock_data(self) -> Dict[str, Any]:
        """Get multi-agent lock data."""
        try:
            import sys
            sys.path.insert(0, str(Path.cwd()))
            from conduvera.skills.multi_agent_lock import MultiAgentLock
            
            lock_mgr = MultiAgentLock()
            active_locks = lock_mgr.get_active_locks()
            
            locks_list = []
            for lock in active_locks[:5]:  # Top 5
                locks_list.append({
                    "id": lock.lock_id[:8],
                    "agent": lock.agent_id,
                    "path": lock.path[:30],
                    "scope": lock.scope.value,
                    "expires": lock.expires_at.strftime("%H:%M") if lock.expires_at else "N/A",
                })
            
            return {
                "available": True,
                "count": len(active_locks),
                "locks": locks_list,
            }
        except Exception as e:
            logger.debug(f"Lock data unavailable: {e}")
            return {"available": False, "count": 0, "locks": []}

    def get_session_data(self) -> Dict[str, Any]:
        """Get session manager data."""
        try:
            import sys
            sys.path.insert(0, str(Path.cwd()))
            from conduvera.skills.session_manager import AgentSessionManager
            
            sm = AgentSessionManager()
            sessions = sm.list_sessions()
            
            active = [s for s in sessions if s.status == "active"]
            recent = sorted(sessions, key=lambda x: x.created_at, reverse=True)[:3]
            
            return {
                "available": True,
                "total": len(sessions),
                "active_count": len(active),
                "active": [
                    {
                        "id": s.session_id[:8],
                        "agent": s.agent,
                        "model": s.model,
                        "started": s.created_at.strftime("%H:%M"),
                    }
                    for s in active[:2]
                ],
                "recent": [
                    {
                        "id": s.session_id[:8],
                        "agent": s.agent,
                        "status": s.status,
                    }
                    for s in recent
                ],
            }
        except Exception as e:
            logger.debug(f"Session data unavailable: {e}")
            return {"available": False, "total": 0, "active_count": 0, "active": [], "recent": []}

    def get_aspice_data(self) -> Dict[str, Any]:
        """Get ASPICE compliance data."""
        try:
            import sys
            sys.path.insert(0, str(Path.cwd()))
            from conduvera.skills.aspice_conflict_detector import ConflictDetector
            
            detector = ConflictDetector()
            conflicts = detector.detect_conflicts()
            
            critical = [c for c in conflicts if c.severity.value == "CRITICAL"]
            high = [c for c in conflicts if c.severity.value == "HIGH"]
            
            return {
                "available": True,
                "total_conflicts": len(conflicts),
                "critical": len(critical),
                "high": len(high),
                "status": "OK" if len(conflicts) == 0 else "WARNING" if len(critical) == 0 else "CRITICAL",
            }
        except Exception as e:
            logger.debug(f"ASPICE data unavailable: {e}")
            return {"available": False, "total_conflicts": 0, "critical": 0, "high": 0, "status": "UNKNOWN"}

    def get_cr_data(self) -> Dict[str, Any]:
        """Get change request data."""
        try:
            import sys
            sys.path.insert(0, str(Path.cwd()))
            from conduvera.skills.change_request import ChangeRequest
            
            crs = ChangeRequest.list_all(limit=10)
            
            open_crs = [cr for cr in crs if cr.status in ("proposed", "in_review")]
            
            return {
                "available": True,
                "total": len(crs),
                "open": len(open_crs),
                "recent": [
                    {
                        "id": cr.cr_id[:8],
                        "title": cr.title[:25],
                        "status": cr.status,
                        "priority": cr.priority,
                    }
                    for cr in crs[:3]
                ],
            }
        except Exception as e:
            logger.debug(f"CR data unavailable: {e}")
            return {"available": False, "total": 0, "open": 0, "recent": []}

    def get_safety_data(self) -> Dict[str, Any]:
        """Get safety guard status."""
        try:
            import sys
            sys.path.insert(0, str(Path.cwd()))
            from conduvera.skills.safety_guard import SafetyGuard
            
            sg = SafetyGuard()
            
            # Check protected patterns count
            protected_count = len(sg.protected_patterns)
            
            return {
                "available": True,
                "status": "ACTIVE",
                "protected_patterns": protected_count,
            }
        except Exception as e:
            logger.debug(f"Safety data unavailable: {e}")
            return {"available": False, "status": "UNKNOWN", "protected_patterns": 0}

    def get_pattern_data(self) -> Dict[str, Any]:
        """Get pattern learning data."""
        try:
            import sys
            sys.path.insert(0, str(Path.cwd()))
            from conduvera.skills.pattern_learning import PatternLearningEngine
            
            pl = PatternLearningEngine()
            patterns = pl.load_all_patterns()
            
            return {
                "available": True,
                "count": len(patterns),
                "high_confidence": sum(1 for p in patterns if p.confidence > 0.8),
            }
        except Exception as e:
            logger.debug(f"Pattern data unavailable: {e}")
            return {"available": False, "count": 0, "high_confidence": 0}

    def display_locks(self, data: Dict[str, Any]) -> None:
        """Display lock status section."""
        if not data.get("available", False):
            text = (
                "[bold cyan]🔒 Multi-Agent Locks[/]\n\n"
                "[dim yellow]Multi-Agent Lock skill not available[/]"
            )
            classes = "skills-section"
        else:
            count = data.get("count", 0)
            locks = data.get("locks", [])
            
            if count > 0:
                status_color = "metric-warning"
                classes = "skills-section skill-warning"
            else:
                status_color = "metric-ok"
                classes = "skills-section skill-ok"
            
            text = (
                f"[bold cyan]🔒 Multi-Agent Locks[/]\n\n"
                f"[bold]Active Locks:[/] [{status_color}]{count}[/]\n"
            )
            
            if locks:
                text += "\n[bold]Top Locks:[/]\n"
                for lock in locks:
                    text += (
                        f"  [yellow]🔒[/] {lock['id']} "
                        f"[dim]{lock['agent']}:[/] {lock['path']} "
                        f"[cyan]({lock['scope']})[/] "
                        f"[dim]until {lock['expires']}[/]\n"
                    )
            else:
                text += "\n[dim]No active locks[/]"

        self.mount(Static(text, classes=classes))

    def display_sessions(self, data: Dict[str, Any]) -> None:
        """Display session status section."""
        if not data.get("available", False):
            text = (
                "[bold cyan]🎯 Session Manager[/]\n\n"
                "[dim yellow]Session Manager skill not available[/]"
            )
            classes = "skills-section"
        else:
            active_count = data.get("active_count", 0)
            total = data.get("total", 0)
            active = data.get("active", [])
            
            if active_count > 0:
                status_color = "metric-ok"
                classes = "skills-section skill-ok"
            else:
                status_color = "metric-warning"
                classes = "skills-section"
            
            text = (
                f"[bold cyan]🎯 Session Manager[/]\n\n"
                f"[bold]Active:[/] [{status_color}]{active_count}[/] / {total} total\n"
            )
            
            if active:
                text += "\n[bold]Active Sessions:[/]\n"
                for session in active:
                    text += (
                        f"  [green]▶[/] {session['id']} "
                        f"[dim]{session['agent']}[/] "
                        f"[cyan]({session['model']})[/] "
                        f"[dim]since {session['started']}[/]\n"
                    )

        self.mount(Static(text, classes=classes))

    def display_aspice(self, data: Dict[str, Any]) -> None:
        """Display ASPICE compliance section."""
        if not data.get("available", False):
            text = (
                "[bold cyan]✅ ASPICE Compliance[/]\n\n"
                "[dim yellow]ASPICE skills not available[/]"
            )
            classes = "skills-section"
        else:
            status = data.get("status", "UNKNOWN")
            total = data.get("total_conflicts", 0)
            critical = data.get("critical", 0)
            high = data.get("high", 0)
            
            if status == "OK":
                status_color = "metric-ok"
                classes = "skills-section skill-ok"
            elif status == "WARNING":
                status_color = "metric-warning"
                classes = "skills-section skill-warning"
            else:
                status_color = "metric-critical"
                classes = "skills-section skill-critical"
            
            text = (
                f"[bold cyan]✅ ASPICE Compliance[/]\n\n"
                f"[bold]Status:[/] [{status_color}]{status}[/]\n"
            )
            
            if total > 0:
                text += (
                    f"[bold]Conflicts:[/] {total} total\n"
                    f"  [red]Critical:[/] {critical}\n"
                    f"  [yellow]High:[/] {high}\n"
                )
            else:
                text += "[green]✓ No compliance issues[/]"

        self.mount(Static(text, classes=classes))

    def display_change_requests(self, data: Dict[str, Any]) -> None:
        """Display change requests section."""
        if not data.get("available", False):
            text = (
                "[bold cyan]📝 Change Requests[/]\n\n"
                "[dim yellow]Change Request skill not available[/]"
            )
            classes = "skills-section"
        else:
            total = data.get("total", 0)
            open_count = data.get("open", 0)
            recent = data.get("recent", [])
            
            if open_count > 0:
                status_color = "metric-warning"
            else:
                status_color = "metric-ok"
            
            text = (
                f"[bold cyan]📝 Change Requests[/]\n\n"
                f"[bold]Open:[/] [{status_color}]{open_count}[/] / {total} total\n"
            )
            
            if recent:
                text += "\n[bold]Recent:[/]\n"
                for cr in recent:
                    priority_color = {
                        "CRITICAL": "red",
                        "HIGH": "yellow",
                        "MEDIUM": "cyan",
                        "LOW": "green",
                    }.get(cr["priority"], "white")
                    
                    text += (
                        f"  [cyan]•[/] {cr['id']} "
                        f"[dim]{cr['title']}[/] "
                        f"[{priority_color}]({cr['priority']})[/] "
                        f"[dim]{cr['status']}[/]\n"
                    )

        self.mount(Static(text, classes="skills-section"))

    def display_safety(self, data: Dict[str, Any]) -> None:
        """Display safety guard section."""
        if not data.get("available", False):
            text = (
                "[bold cyan]🛡️ Safety Guard[/] [red](P1-Critical)[/]\n\n"
                "[dim yellow]Safety Guard skill not available[/]"
            )
            classes = "skills-section"
        else:
            status = data.get("status", "UNKNOWN")
            patterns = data.get("protected_patterns", 0)
            
            if status == "ACTIVE":
                status_color = "metric-ok"
                classes = "skills-section skill-ok"
            else:
                status_color = "metric-critical"
                classes = "skills-section skill-critical"
            
            text = (
                f"[bold cyan]🛡️ Safety Guard[/] [red](P1-Critical)[/]\n\n"
                f"[bold]Status:[/] [{status_color}]{status}[/]\n"
                f"[bold]Protected Patterns:[/] [cyan]{patterns}[/]\n"
                f"\n[dim]Protects against accidental deletion of:[/]\n"
                f"  [red]•[/] Production data\n"
                f"  [red]•[/] Git repositories\n"
                f"  [red]•[/] Secrets and credentials"
            )

        self.mount(Static(text, classes=classes))

    def display_patterns(self, data: Dict[str, Any]) -> None:
        """Display pattern learning section."""
        if not data.get("available", False):
            text = (
                "[bold cyan]🧠 Pattern Learning[/]\n\n"
                "[dim yellow]Pattern Learning skill not available[/]"
            )
            classes = "skills-section"
        else:
            count = data.get("count", 0)
            high_conf = data.get("high_confidence", 0)
            
            text = (
                f"[bold cyan]🧠 Pattern Learning[/]\n\n"
                f"[bold]Patterns Learned:[/] [cyan]{count}[/]\n"
                f"[bold]High Confidence:[/] [green]{high_conf}[/]\n"
            )

        self.mount(Static(text, classes="skills-section"))

    def toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh."""
        self.auto_refresh = not self.auto_refresh
        logger.info(f"Skills Dashboard auto-refresh: {self.auto_refresh}")


class SkillsPanel(Vertical):
    """
    Compact skills panel for integration into other screens.
    
    Shows only essential status indicators.
    """

    def compose(self):
        """Create compact panel."""
        yield Static("[bold cyan]🔧 CuraOps Skills[/bold cyan]", id="skills-panel-header")
        yield SkillsDashboard(id="skills-dashboard")

    def toggle_visibility(self) -> bool:
        """Toggle panel visibility."""
        self.display = not self.display
        return self.display
