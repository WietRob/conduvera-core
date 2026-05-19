"""Matrix OS Main Application."""
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Static, Button, Label
from textual.binding import Binding
from textual.reactive import reactive
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from curaops.harness.route_plan_artifacts import default_route_plan_artifact
from src.ui.widgets.matrix_rain import MatrixRain
from src.ui.widgets.file_browser import FileBrowser
from src.ui.widgets.process_monitor import ProcessMonitor
from src.ui.widgets.system_info import SystemInfoPanel
from src.ui.widgets.terminal import Terminal
from src.ui.widgets.code_editor import CodeEditor
from src.ui.widgets.git_manager import GitManager
from src.ui.widgets.split_pane import EditorTerminalSplit
from src.ui.widgets.route_plan_panel import MatrixRoutePlanPanel
from src.ui.widgets.route_plan_artifact_picker import build_route_plan_artifact_selection_preview
from src.utils.config import get_config
from src.utils.logger import logger


class StatusBar(Static):
    """Custom status bar widget."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        background: $success-darken-2;
        color: $text;
        height: 1;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.update_status("Matrix OS Ready")

    def update_status(self, message: str) -> None:
        """Update status message."""
        self.update(f"[bold green]●[/] {message}")


class Sidebar(VerticalScroll):
    """Sidebar with navigation buttons."""

    DEFAULT_CSS = """
    Sidebar {
        width: 30;
        background: $panel-darken-1;
        border-right: solid $success;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create sidebar widgets."""
        # Rich-inspired header with box drawing
        yield Label("[bold bright_green]╔═══════════════════════╗[/]", classes="sidebar-border")
        yield Label("[bold bright_green]║   🟢 MATRIX OS  v0.1 ║[/]", classes="sidebar-title")
        yield Label("[bold bright_green]╚═══════════════════════╝[/]", classes="sidebar-border")
        yield Static("")

        # Main navigation with icons
        yield Button("📁 File Browser", id="btn_files", variant="primary")
        yield Button("💻 Terminal", id="btn_terminal")
        yield Button("✏️  Code Editor", id="btn_editor")
        yield Button("🔀 Split View", id="btn_split")
        yield Button("🤖 AI Assistant", id="btn_ai")
        yield Button("🧭 Route Plan", id="btn_route_plan")

        yield Static("")
        yield Label("[dim green]── Dev Tools ──────────[/]")
        yield Static("")

        # Dev tools
        yield Button("🔧 Git", id="btn_git")
        yield Button("🐳 Docker", id="btn_docker")
        yield Button("🌐 API Client", id="btn_api")
        yield Button("🗄️  Database", id="btn_database")
        yield Button("📊 Process Monitor", id="btn_processes")

        yield Static("")
        yield Label("[dim green]── System ─────────────[/]")
        yield Static("")

        # System controls
        yield Button("🎨 Matrix Effects", id="btn_effects")
        yield Button("📊 System Info", id="btn_sysinfo")
        yield Button("📈 Monitoring", id="btn_monitoring")
        yield Button("⚙️  Settings", id="btn_settings")
        yield Button("❓ Help", id="btn_help")
        yield Button("🚪 Exit", id="btn_exit", variant="error")


class MatrixOS(App):
    """
    Matrix OS - A Matrix-themed TUI development environment.
    """

    CSS_PATH = Path(__file__).parent.parent / "ui" / "themes" / "matrix.tcss"
    TITLE = "Matrix OS - Development Environment"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("f1", "toggle_rain", "Toggle Rain", show=True),
        Binding("f2", "help", "Help", show=False),
        Binding("f3", "show_split_view", "Split View", show=True),
        Binding("f4", "show_monitoring", "Monitor", show=True),
        Binding("ctrl+t", "show_terminal", "Terminal", show=True),
        Binding("ctrl+f", "show_files", "Files", show=False),
        Binding("ctrl+e", "show_editor", "Editor", show=True),
        Binding("ctrl+a", "show_ai", "AI Assistant", show=True),
        Binding("ctrl+g", "show_git", "Git", show=True),
        Binding("ctrl+d", "show_docker", "Docker", show=True),
        Binding("ctrl+r", "show_api", "API Client", show=True),
        Binding("ctrl+b", "show_database", "Database", show=True),
        Binding("ctrl+p", "show_processes", "Processes", show=False),
    ]

    show_rain = reactive(True)
    current_view = reactive("welcome")

    def __init__(self) -> None:
        super().__init__()
        self.config = get_config()
        logger.info("Initializing Matrix OS")

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with Horizontal(id="main-container"):
            yield Sidebar()

            with Vertical(id="content-area"):
                # Matrix rain background
                if self.show_rain:
                    yield MatrixRain(
                        char_set=self.config.get("matrix_os.effects.rain.char_set", "mixed"),
                        fps=self.config.get("matrix_os.display.fps", 30),
                        speed_min=self.config.get("matrix_os.effects.rain.speed_min", 0.5),
                        speed_max=self.config.get("matrix_os.effects.rain.speed_max", 2.0),
                        id="matrix-rain",
                    )

                # Main content container (switchable views)
                with Container(id="view-container"):
                    # Welcome view (default)
                    yield Container(
                        Label(
                            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
                            "[bold bright_green]║        Welcome to MATRIX OS v0.1         ║[/]\n"
                            "[bold bright_green]╚═══════════════════════════════════════════╝[/]\n\n"
                            "[bright_green]⚡ A Matrix-themed development environment[/]\n"
                            "[dim green]Built with Python & Textual[/]\n\n"
                            "[bold cyan]🎮 Quick Start:[/]\n"
                            "[green]  • F1[/] [dim]- Toggle Matrix rain effect[/]\n"
                            "[green]  • Ctrl+Q[/] [dim]- Quit application[/]\n"
                            "[green]  • Sidebar[/] [dim]- Navigate features[/]\n\n"
                            "[bold yellow]📊 System Status:[/] [bold green]● ONLINE[/]\n"
                            "[dim green]Matrix rain active • All systems operational[/]",
                            id="welcome-message",
                        ),
                        id="welcome-view",
                        classes="view status-panel",
                    )

        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        logger.info("Matrix OS mounted successfully")
        self.update_status("🟢 [bold green]Matrix OS v0.1[/] initialized - [bold bright_green]● ONLINE[/] | Press F1 for rain")

    def update_status(self, message: str) -> None:
        """Update status bar message."""
        try:
            status_bar = self.query_one(StatusBar)
            status_bar.update_status(message)
        except Exception as e:
            logger.error(f"Failed to update status: {e}")

    def action_quit(self) -> None:
        """Quit the application."""
        logger.info("Matrix OS shutting down")
        self.exit()

    def action_toggle_rain(self) -> None:
        """Toggle the matrix rain effect."""
        try:
            rain_widget = self.query_one("#matrix-rain", MatrixRain)
            rain_widget.rain_active = not rain_widget.rain_active
            if rain_widget.rain_active:
                self.update_status("🌧️  Matrix rain [bold green]ENABLED[/] - Digital rain active")
            else:
                self.update_status("🌧️  Matrix rain [bold yellow]DISABLED[/] - Effect paused")
            logger.info(f"Matrix rain {'enabled' if rain_widget.rain_active else 'disabled'}")
        except Exception as e:
            self.update_status("[bold red]⚠️  Error: Matrix rain widget not found[/]")
            logger.warning(f"Matrix rain widget not found: {e}")

    def action_help(self) -> None:
        """Show help information."""
        self.update_status("❓ [bold cyan]Help:[/] Use sidebar buttons or keyboard shortcuts (F1, Ctrl+Q)")

    def switch_view(self, view_name: str, widget=None) -> None:
        """
        Switch to a different view.

        Args:
            view_name: Name of the view to switch to
            widget: Optional widget to mount (if None, creates from view_name)
        """
        try:
            # Get the view container
            view_container = self.query_one("#view-container")

            # Remove all current views
            for child in view_container.children:
                child.remove()

            # Add new view
            if widget is None:
                widget = self._create_view_widget(view_name)

            if widget:
                view_container.mount(widget)
                self.current_view = view_name
                logger.info(f"Switched to view: {view_name}")

        except Exception as e:
            logger.error(f"Failed to switch view to {view_name}: {e}")
            self.update_status(f"[bold red]⚠️  Error switching view: {e}[/]")

    def _create_view_widget(self, view_name: str):
        """Create widget for specified view."""
        widgets = {
            "files": lambda: FileBrowser(
                root_path=Path.cwd(),
                label="📁 File Browser",
                id="file-browser-view",
                classes="view"
            ),
            "terminal": lambda: Terminal(
                shell="/bin/bash",
                id="terminal-view",
                classes="view"
            ),
            "editor": lambda: CodeEditor(
                language="python",
                id="editor-view",
                classes="view"
            ),
            "split": lambda: EditorTerminalSplit(
                editor_widget=CodeEditor(language="python"),
                terminal_widget=Terminal(shell="/bin/bash"),
                id="split-view",
                classes="view"
            ),
            "ai": lambda: self._create_ai_assistant_view(),
            "git": lambda: GitManager(
                repo_path=Path.cwd(),
                id="git-manager-view",
                classes="view"
            ),
            "docker": lambda: self._create_docker_view(),
            "api": lambda: self._create_api_view(),
            "database": lambda: self._create_database_view(),
            "processes": lambda: ProcessMonitor(
                refresh_interval=2.0,
                max_processes=50,
                id="process-monitor-view",
                classes="view"
            ),
            "sysinfo": lambda: SystemInfoPanel(
                id="system-info-view",
                classes="view"
            ),
            "monitoring": lambda: self._create_monitoring_view(),
            "route_plan": lambda: self._create_route_plan_panel_view(),
            "welcome": lambda: Container(
                Label(
                    "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
                    "[bold bright_green]║        Welcome to MATRIX OS v0.1         ║[/]\n"
                    "[bold bright_green]╚═══════════════════════════════════════════╝[/]\n\n"
                    "[bright_green]⚡ A Matrix-themed development environment[/]\n"
                    "[dim green]Built with Python & Textual[/]\n\n"
                    "[bold cyan]🎮 Quick Start:[/]\n"
                    "[green]  • F1[/] [dim]- Toggle Matrix rain effect[/]\n"
                    "[green]  • Ctrl+Q[/] [dim]- Quit application[/]\n"
                    "[green]  • Sidebar[/] [dim]- Navigate features[/]\n\n"
                    "[bold yellow]📊 System Status:[/] [bold green]● ONLINE[/]\n"
                    "[dim green]Matrix rain active • All systems operational[/]",
                ),
                id="welcome-view",
                classes="view status-panel",
            ),
        }

        creator = widgets.get(view_name)
        return creator() if creator else None

    def _create_ai_assistant_view(self):
        """Create AI assistant view lazily so route-plan tests do not import optional HTTP clients."""

        from src.ui.widgets.ai_assistant import AIAssistant

        return AIAssistant(id="ai-assistant-view", classes="view")

    def _create_docker_view(self):
        """Create Docker view lazily."""

        from src.ui.widgets.docker_manager import DockerManager

        return DockerManager(refresh_interval=5.0, id="docker-manager-view", classes="view")

    def _create_api_view(self):
        """Create API client view lazily."""

        from src.ui.widgets.api_client import APIClient

        return APIClient(id="api-client-view", classes="view")

    def _create_database_view(self):
        """Create database browser view lazily."""

        from src.ui.widgets.database_browser import DatabaseBrowser

        return DatabaseBrowser(id="database-browser-view", classes="view")

    def _create_monitoring_view(self):
        """Create monitoring view lazily so MatrixOS import remains lightweight."""

        from src.ui.widgets.monitoring_dashboard import MonitoringDashboard

        return MonitoringDashboard(id="monitoring-dashboard-view", classes="view")

    def _create_route_plan_panel_view(self, artifact_id: str | None = None) -> MatrixRoutePlanPanel:
        """Create a non-live route-plan panel from the canonical artifact selector."""

        selected_artifact = artifact_id or default_route_plan_artifact().artifact_id
        preview = build_route_plan_artifact_selection_preview(selected_artifact)
        widget = MatrixRoutePlanPanel(
            preview.panel_model,
            id="route-plan-panel-view",
            classes="view",
        )
        widget.artifact_picker_state = preview.picker_model
        widget.artifact_picker_renderable = preview.picker_renderable
        widget.renderable = preview.renderable
        widget.update(widget.renderable)
        return widget

    def action_show_terminal(self) -> None:
        """Show terminal view."""
        self.switch_view("terminal")
        self.update_status("💻 [bold green]Terminal loaded[/] - Full PTY shell access | Type commands")

    def action_show_files(self) -> None:
        """Show file browser view."""
        self.switch_view("files")
        self.update_status("📁 [bold green]File Browser loaded[/] - Navigate with arrow keys, Enter to expand")

    def action_show_processes(self) -> None:
        """Show process monitor view."""
        self.switch_view("processes")
        self.update_status("📊 [bold green]Process Monitor loaded[/] - Auto-refreshing every 2 seconds")

    def action_show_editor(self) -> None:
        """Show code editor view."""
        self.switch_view("editor")
        self.update_status("✏️  [bold green]Code Editor loaded[/] - Syntax highlighting enabled | Ctrl+S to save")

    def action_show_split_view(self) -> None:
        """Show split view (Editor + Terminal)."""
        self.switch_view("split")
        self.update_status("🔀 [bold green]Split View loaded[/] - Editor + Terminal side-by-side | F3 to toggle")

    def action_show_ai(self) -> None:
        """Show AI assistant view."""
        self.switch_view("ai")
        self.update_status("🤖 [bold green]Neo's AI Assistant ready[/] - Ask questions, get code help!")

    def action_show_git(self) -> None:
        """Show Git manager view."""
        self.switch_view("git")
        self.update_status("🔧 [bold green]Git Matrix loaded[/] - Visual git interface with diff viewer")

    def action_show_docker(self) -> None:
        """Show Docker manager view."""
        self.switch_view("docker")
        self.update_status("🐳 [bold green]Docker Manager loaded[/] - Container control & monitoring")

    def action_show_api(self) -> None:
        """Show API client view."""
        self.switch_view("api")
        self.update_status("🌐 [bold green]API Client ready[/] - Test REST APIs Postman-style")

    def action_show_database(self) -> None:
        """Show database browser view."""
        self.switch_view("database")
        self.update_status("🗄️  [bold green]Database Browser loaded[/] - PostgreSQL, MySQL, SQLite support")

    def action_show_monitoring(self) -> None:
        """Show monitoring dashboard view."""
        self.switch_view("monitoring")
        self.update_status("📈 [bold green]Monitoring Dashboard loaded[/] - Unified system, docker, and process monitoring")

    def action_show_route_plan(self) -> None:
        """Show non-live route-plan panel view."""
        self.switch_view("route_plan")
        self.update_status("🧭 [bold green]Route Plan Panel loaded[/] - Display-only snapshot, no runtime execution")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id

        actions = {
            "btn_files": lambda: self.action_show_files(),
            "btn_terminal": lambda: self.action_show_terminal(),
            "btn_editor": lambda: (
                self.switch_view("editor"),
                self.update_status("✏️  [bold green]Code Editor loaded[/] - Syntax highlighting enabled")
            ),
            "btn_split": lambda: (
                self.switch_view("split"),
                self.update_status("🔀 [bold green]Split View loaded[/] - Editor + Terminal side-by-side")
            ),
            "btn_ai": lambda: (
                self.switch_view("ai"),
                self.update_status("🤖 [bold green]Neo's AI Assistant ready[/] - Ask me anything!")
            ),
            "btn_route_plan": lambda: self.action_show_route_plan(),
            "btn_git": lambda: (
                self.switch_view("git"),
                self.update_status("🔧 [bold green]Git Matrix loaded[/] - Visual git interface with diff viewer")
            ),
            "btn_docker": lambda: (
                self.switch_view("docker"),
                self.update_status("🐳 [bold green]Docker Manager loaded[/] - Container control & monitoring")
            ),
            "btn_api": lambda: (
                self.switch_view("api"),
                self.update_status("🌐 [bold green]API Client ready[/] - Test REST APIs Postman-style")
            ),
            "btn_database": lambda: (
                self.switch_view("database"),
                self.update_status("🗄️  [bold green]Database Browser loaded[/] - PostgreSQL, MySQL, SQLite support")
            ),
            "btn_processes": lambda: self.action_show_processes(),
            "btn_effects": lambda: self.action_toggle_rain(),
            "btn_settings": lambda: self.update_status("⚙️  Settings panel (Coming soon)"),
            "btn_sysinfo": lambda: (
                self.switch_view("sysinfo"),
                self.update_status("📊 [bold green]System Info loaded[/] - Real-time metrics")
            ),
            "btn_monitoring": lambda: (
                self.switch_view("monitoring"),
                self.update_status("📈 [bold green]Monitoring Dashboard loaded[/] - Unified monitoring")
            ),
            "btn_help": lambda: self.action_help(),
            "btn_exit": lambda: self.action_quit(),
        }

        action = actions.get(button_id)
        if action:
            action()
        else:
            logger.warning(f"Unknown button pressed: {button_id}")


def main() -> None:
    """Main entry point for Matrix OS."""
    try:
        app = MatrixOS()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
