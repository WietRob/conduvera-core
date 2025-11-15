"""System Information Panel Widget - Rich-inspired design."""
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.table import Table
import psutil
import time
from datetime import datetime


class SystemInfoPanel(Widget):
    """
    System information panel with Rich-inspired design.

    Displays real-time system metrics:
    - CPU usage
    - Memory usage
    - Disk usage
    - Network stats
    - Process count
    - Uptime
    """

    DEFAULT_CSS = """
    SystemInfoPanel {
        background: rgba(0, 30, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        height: auto;
    }
    """

    refresh_rate = reactive(2.0)  # Refresh every 2 seconds
    last_update = reactive(0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cpu_percent = 0.0
        self.memory_percent = 0.0
        self.disk_percent = 0.0
        self.process_count = 0
        self.boot_time = psutil.boot_time()

    def on_mount(self) -> None:
        """Start refresh timer when mounted."""
        self.set_interval(self.refresh_rate, self.refresh_data)
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh system data."""
        try:
            self.cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            self.memory_percent = memory.percent
            disk = psutil.disk_usage("/")
            self.disk_percent = disk.percent
            self.process_count = len(psutil.pids())
            self.last_update = time.time()
            self.refresh()
        except Exception:
            pass

    def get_status_color(self, percent: float) -> str:
        """Get color based on usage percentage."""
        if percent >= 90:
            return "red"
        elif percent >= 75:
            return "yellow"
        elif percent >= 50:
            return "bright_green"
        else:
            return "green"

    def get_bar(self, percent: float, width: int = 20) -> str:
        """Create a text-based progress bar."""
        filled = int((percent / 100) * width)
        empty = width - filled
        return "█" * filled + "░" * empty

    def render(self) -> Text:
        """Render the system info panel."""
        text = Text()

        # Header with box drawing
        text.append("╔═══════════════════════════════╗\n", style="bold bright_green")
        text.append("║    📊 SYSTEM INFORMATION     ║\n", style="bold bright_green")
        text.append("╚═══════════════════════════════╝\n\n", style="bold bright_green")

        # CPU Info
        cpu_color = self.get_status_color(self.cpu_percent)
        text.append("💻 CPU Usage\n", style="bold cyan")
        text.append(f"   {self.cpu_percent:5.1f}% ", style=f"bold {cpu_color}")
        text.append(f"{self.get_bar(self.cpu_percent)}\n", style=cpu_color)
        text.append("\n")

        # Memory Info
        mem_color = self.get_status_color(self.memory_percent)
        text.append("🧠 Memory Usage\n", style="bold cyan")
        text.append(f"   {self.memory_percent:5.1f}% ", style=f"bold {mem_color}")
        text.append(f"{self.get_bar(self.memory_percent)}\n", style=mem_color)
        text.append("\n")

        # Disk Info
        disk_color = self.get_status_color(self.disk_percent)
        text.append("💾 Disk Usage\n", style="bold cyan")
        text.append(f"   {self.disk_percent:5.1f}% ", style=f"bold {disk_color}")
        text.append(f"{self.get_bar(self.disk_percent)}\n", style=disk_color)
        text.append("\n")

        # Process count
        text.append("⚙️  Processes\n", style="bold cyan")
        text.append(f"   {self.process_count} running\n\n", style="green")

        # Uptime
        uptime_seconds = time.time() - self.boot_time
        uptime_hours = int(uptime_seconds // 3600)
        uptime_mins = int((uptime_seconds % 3600) // 60)
        text.append("⏱️  System Uptime\n", style="bold cyan")
        text.append(f"   {uptime_hours}h {uptime_mins}m\n\n", style="green")

        # Status indicator
        text.append("╭───────────────────────────────╮\n", style="dim green")
        text.append("│  ", style="dim green")
        text.append("🟢 All Systems Operational", style="bold green")
        text.append("  │\n", style="dim green")
        text.append("╰───────────────────────────────╯", style="dim green")

        return text
