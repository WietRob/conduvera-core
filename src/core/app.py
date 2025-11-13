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

from src.ui.widgets.matrix_rain import MatrixRain
from src.ui.widgets.file_browser import FileBrowser
from src.ui.widgets.process_monitor import ProcessMonitor
from src.ui.widgets.system_info import SystemInfoPanel
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
        yield Button("📊 Process Monitor", id="btn_processes")
        yield Button("✏️  Code Editor", id="btn_editor")
        yield Button("🎨 Matrix Effects", id="btn_effects")
        yield Button("🔌 Plugins", id="btn_plugins")

        yield Static("")
        yield Label("[dim green]─────────────────────[/]")
        yield Static("")

        # System controls
        yield Button("⚙️  Settings", id="btn_settings")
        yield Button("📊 System Info", id="btn_sysinfo")
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
        Binding("ctrl+t", "show_terminal", "Terminal", show=False),
        Binding("ctrl+f", "show_files", "Files", show=False),
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

    def action_show_terminal(self) -> None:
        """Show terminal view."""
        self.current_view = "terminal"
        self.update_status("💻 [bold green]Terminal view[/] - Full PTY support (Coming soon)")

    def action_show_files(self) -> None:
        """Show file browser view."""
        self.switch_view("files")
        self.update_status("📁 [bold green]File Browser loaded[/] - Navigate with arrow keys, Enter to expand")

    def action_show_processes(self) -> None:
        """Show process monitor view."""
        self.switch_view("processes")
        self.update_status("📊 [bold green]Process Monitor loaded[/] - Auto-refreshing every 2 seconds")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id

        actions = {
            "btn_files": lambda: self.action_show_files(),
            "btn_terminal": lambda: self.action_show_terminal(),
            "btn_processes": lambda: self.action_show_processes(),
            "btn_editor": lambda: self.update_status("✏️  Code editor (Coming soon)"),
            "btn_effects": lambda: self.action_toggle_rain(),
            "btn_plugins": lambda: self.update_status("🔌 Plugin manager (Coming soon)"),
            "btn_settings": lambda: self.update_status("⚙️  Settings panel (Coming soon)"),
            "btn_sysinfo": lambda: (
                self.switch_view("sysinfo"),
                self.update_status("📊 [bold green]System Info loaded[/] - Real-time metrics")
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
