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
        yield Label("[bold green]🟢 Matrix OS[/]", classes="sidebar-title")
        yield Static("─" * 26)
        yield Button("📁 File Browser", id="btn_files", variant="primary")
        yield Button("💻 Terminal", id="btn_terminal")
        yield Button("📊 Processes", id="btn_processes")
        yield Button("✏️  Code Editor", id="btn_editor")
        yield Button("🔌 Plugins", id="btn_plugins")
        yield Static("─" * 26)
        yield Button("⚙️  Settings", id="btn_settings")
        yield Button("❓ Help", id="btn_help")
        yield Button("🚪 Exit", id="btn_exit")


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
                if self.show_rain:
                    yield MatrixRain(
                        char_set=self.config.get("matrix_os.effects.rain.char_set", "mixed"),
                        fps=self.config.get("matrix_os.display.fps", 30),
                        speed_min=self.config.get("matrix_os.effects.rain.speed_min", 0.5),
                        speed_max=self.config.get("matrix_os.effects.rain.speed_max", 2.0),
                        id="matrix-rain",
                    )

                yield Container(
                    Label(
                        "[bold green]Welcome to Matrix OS[/]\n\n"
                        "A Matrix-themed development environment built with Python & Textual.\n\n"
                        "[dim]Press F1 to toggle rain effect[/]\n"
                        "[dim]Press Ctrl+Q to quit[/]\n"
                        "[dim]Use sidebar to navigate[/]",
                        id="welcome-message",
                    ),
                    id="welcome-container",
                    classes="status-panel",
                )

        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        logger.info("Matrix OS mounted successfully")
        self.update_status("Matrix OS initialized - Ready for action")

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
            status = "enabled" if rain_widget.rain_active else "disabled"
            self.update_status(f"Matrix rain {status}")
            logger.info(f"Matrix rain {status}")
        except Exception as e:
            logger.warning(f"Matrix rain widget not found: {e}")

    def action_help(self) -> None:
        """Show help information."""
        self.update_status("Help: Use sidebar buttons or keyboard shortcuts")

    def action_show_terminal(self) -> None:
        """Show terminal view."""
        self.current_view = "terminal"
        self.update_status("Terminal view (Coming soon)")

    def action_show_files(self) -> None:
        """Show file browser view."""
        self.current_view = "files"
        self.update_status("File browser view (Coming soon)")

    def action_show_processes(self) -> None:
        """Show process monitor view."""
        self.current_view = "processes"
        self.update_status("Process monitor view (Coming soon)")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id

        actions = {
            "btn_files": lambda: self.action_show_files(),
            "btn_terminal": lambda: self.action_show_terminal(),
            "btn_processes": lambda: self.action_show_processes(),
            "btn_editor": lambda: self.update_status("Code editor (Coming soon)"),
            "btn_plugins": lambda: self.update_status("Plugin manager (Coming soon)"),
            "btn_settings": lambda: self.update_status("Settings (Coming soon)"),
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
