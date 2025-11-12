"""Process monitor widget."""
from textual.widgets import DataTable
from textual.reactive import reactive
from rich.text import Text
from typing import List, Dict, Any
import psutil
from src.utils.logger import logger


class ProcessMonitor(DataTable):
    """
    Process monitor widget showing system processes.

    Displays running processes with CPU, memory usage, and status.
    """

    sort_column = reactive("cpu")
    show_all = reactive(False)
    auto_refresh = reactive(True)

    DEFAULT_CSS = """
    ProcessMonitor {
        background: $panel;
        color: $text;
        border: solid $success;
    }

    ProcessMonitor:focus {
        border: solid $success-lighten-1;
    }

    ProcessMonitor > .datatable--header {
        background: $success-darken-1;
        color: $text;
        text-style: bold;
    }

    ProcessMonitor > .datatable--cursor {
        background: $success-darken-2;
    }
    """

    COLUMNS = [
        ("PID", 8),
        ("Name", 30),
        ("CPU%", 8),
        ("MEM%", 8),
        ("Status", 12),
        ("User", 15),
    ]

    def __init__(self, refresh_interval: float = 2.0, max_processes: int = 50, **kwargs) -> None:
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval
        self.max_processes = max_processes
        self.cursor_type = "row"
        self.zebra_stripes = True

    def on_mount(self) -> None:
        """Initialize process monitor when mounted."""
        # Add columns
        for column_name, width in self.COLUMNS:
            self.add_column(column_name, width=width)

        # Start auto-refresh
        if self.auto_refresh:
            self.set_interval(self.refresh_interval, self.update_processes)

        # Initial load
        self.update_processes()
        logger.info("Process monitor initialized")

    def get_processes(self) -> List[Dict[str, Any]]:
        """
        Get list of running processes.

        Returns:
            List of process info dictionaries
        """
        processes = []

        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status", "username"]
        ):
            try:
                pinfo = proc.info
                processes.append(
                    {
                        "pid": pinfo["pid"],
                        "name": pinfo["name"] or "N/A",
                        "cpu": pinfo["cpu_percent"] or 0.0,
                        "memory": pinfo["memory_percent"] or 0.0,
                        "status": pinfo["status"] or "unknown",
                        "user": pinfo["username"] or "N/A",
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception as e:
                logger.warning(f"Error getting process info: {e}")

        return processes

    def format_cpu(self, cpu_percent: float) -> Text:
        """
        Format CPU percentage with color coding.

        Args:
            cpu_percent: CPU usage percentage

        Returns:
            Formatted Rich Text
        """
        if cpu_percent > 80:
            style = "bold red"
        elif cpu_percent > 50:
            style = "bold yellow"
        elif cpu_percent > 20:
            style = "yellow"
        else:
            style = "green"

        return Text(f"{cpu_percent:>5.1f}", style=style)

    def format_memory(self, mem_percent: float) -> Text:
        """
        Format memory percentage with color coding.

        Args:
            mem_percent: Memory usage percentage

        Returns:
            Formatted Rich Text
        """
        if mem_percent > 80:
            style = "bold red"
        elif mem_percent > 50:
            style = "bold yellow"
        elif mem_percent > 20:
            style = "yellow"
        else:
            style = "green"

        return Text(f"{mem_percent:>5.1f}", style=style)

    def format_status(self, status: str) -> Text:
        """
        Format process status with color coding.

        Args:
            status: Process status string

        Returns:
            Formatted Rich Text
        """
        status_colors = {
            "running": "green",
            "sleeping": "blue",
            "disk-sleep": "cyan",
            "stopped": "yellow",
            "zombie": "red",
            "dead": "red",
            "wake_kill": "yellow",
            "waking": "cyan",
            "idle": "dim",
            "locked": "magenta",
            "waiting": "blue",
        }

        style = status_colors.get(status, "white")
        return Text(status, style=style)

    def update_processes(self) -> None:
        """Update process list."""
        try:
            # Get processes
            processes = self.get_processes()

            # Sort processes
            sort_keys = {
                "pid": lambda p: p["pid"],
                "name": lambda p: p["name"].lower(),
                "cpu": lambda p: p["cpu"],
                "memory": lambda p: p["memory"],
                "status": lambda p: p["status"],
                "user": lambda p: p["user"],
            }

            sort_key = sort_keys.get(self.sort_column, sort_keys["cpu"])
            processes.sort(key=sort_key, reverse=(self.sort_column in ["cpu", "memory"]))

            # Limit number of processes shown
            processes = processes[: self.max_processes]

            # Clear and repopulate table
            self.clear()

            for proc in processes:
                self.add_row(
                    str(proc["pid"]),
                    proc["name"][:28],  # Truncate long names
                    self.format_cpu(proc["cpu"]),
                    self.format_memory(proc["memory"]),
                    self.format_status(proc["status"]),
                    proc["user"][:13],  # Truncate long usernames
                )

        except Exception as e:
            logger.error(f"Error updating processes: {e}")

    def action_sort_by_cpu(self) -> None:
        """Sort processes by CPU usage."""
        self.sort_column = "cpu"
        self.update_processes()

    def action_sort_by_memory(self) -> None:
        """Sort processes by memory usage."""
        self.sort_column = "memory"
        self.update_processes()

    def action_sort_by_name(self) -> None:
        """Sort processes by name."""
        self.sort_column = "name"
        self.update_processes()

    def action_refresh(self) -> None:
        """Manually refresh process list."""
        self.update_processes()
        logger.info("Process list refreshed")

    def action_toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh."""
        self.auto_refresh = not self.auto_refresh
        logger.info(f"Auto-refresh: {self.auto_refresh}")

    def get_selected_process(self) -> Dict[str, Any]:
        """
        Get currently selected process info.

        Returns:
            Process info dictionary or empty dict
        """
        if self.cursor_row is not None and self.cursor_row < len(self.rows):
            row_data = self.get_row_at(self.cursor_row)
            if row_data:
                return {
                    "pid": int(row_data[0]),
                    "name": row_data[1],
                }
        return {}
