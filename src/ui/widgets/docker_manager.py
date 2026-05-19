"""Docker/Container Manager widget."""
from textual.widgets import Static
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from typing import List, Dict, Any
import subprocess
import json
from src.utils.logger import logger


class DockerManager(VerticalScroll):
    """
    Docker/Container Manager widget.

    Provides container management: list, start, stop, logs, stats.
    """

    auto_refresh = reactive(True)
    selected_container = reactive(None)

    DEFAULT_CSS = """
    DockerManager {
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    DockerManager:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    .docker-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    .docker-container {
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin: 1 0;
    }

    .docker-running {
        color: #00FF00;
    }

    .docker-stopped {
        color: #FFAA00;
    }

    .docker-error {
        color: #FF0000;
    }

    DockerManager DataTable {
        background: transparent;
    }
    """

    class ContainerAction(Message):
        """Message sent when container action is performed."""

        def __init__(self, action: str, container_id: str) -> None:
            super().__init__()
            self.action = action
            self.container_id = container_id

    def __init__(self, refresh_interval: float = 5.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.refresh_interval = refresh_interval
        self.containers_cache = []

    def compose(self):
        """Create child widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║      🐳 Docker Container Matrix          ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="docker-header"
        )
        yield Static(
            "[dim green]Container management and monitoring[/]\n"
            "[cyan]Commands:[/]\n"
            "[green]  • S[/] - Start container\n"
            "[green]  • X[/] - Stop container\n"
            "[green]  • R[/] - Restart container\n"
            "[green]  • L[/] - View logs\n"
            "[green]  • D[/] - Remove container\n",
            id="docker-help"
        )

    def on_mount(self) -> None:
        """Start auto-refresh when mounted."""
        if self.auto_refresh:
            self.set_interval(self.refresh_interval, self.refresh_containers)
        self.refresh_containers()
        logger.info("Docker Manager initialized")

    def check_docker(self) -> bool:
        """
        Check if Docker is installed and running.

        Returns:
            True if Docker is available
        """
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Docker check failed: {e}")
            return False

    def get_containers(self, all_containers: bool = True) -> List[Dict[str, Any]]:
        """
        Get list of Docker containers.

        Args:
            all_containers: Include stopped containers

        Returns:
            List of container info dictionaries
        """
        try:
            cmd = ["docker", "ps", "--format", "{{json .}}"]
            if all_containers:
                cmd.append("-a")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.error(f"Docker ps failed: {result.stderr}")
                return []

            containers = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        container = json.loads(line)
                        containers.append({
                            "id": container.get("ID", ""),
                            "name": container.get("Names", ""),
                            "image": container.get("Image", ""),
                            "status": container.get("Status", ""),
                            "state": container.get("State", ""),
                            "ports": container.get("Ports", ""),
                        })
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse container JSON: {e}")

            return containers

        except subprocess.TimeoutExpired:
            logger.error("Docker ps timeout")
            return []
        except Exception as e:
            logger.error(f"Error getting containers: {e}")
            return []

    def get_container_stats(self, container_id: str) -> Dict[str, str]:
        """
        Get container resource stats.

        Args:
            container_id: Container ID

        Returns:
            Stats dictionary
        """
        try:
            result = subprocess.run(
                ["docker", "stats", container_id, "--no-stream", "--format",
                 "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and result.stdout:
                stats = json.loads(result.stdout)
                return {
                    "cpu": stats.get("CPUPerc", "0%"),
                    "memory": stats.get("MemPerc", "0%"),
                    "mem_usage": stats.get("MemUsage", "0B / 0B"),
                    "net_io": stats.get("NetIO", "0B / 0B"),
                    "block_io": stats.get("BlockIO", "0B / 0B"),
                }
            return {}

        except Exception as e:
            logger.error(f"Error getting stats for {container_id}: {e}")
            return {}

    def refresh_containers(self) -> None:
        """Refresh container list display."""
        if not self.check_docker():
            self.show_error("Docker is not running or not installed")
            return

        containers = self.get_containers(all_containers=True)
        self.containers_cache = containers

        # Clear previous container displays
        for widget in self.query(".docker-container"):
            widget.remove()

        # Display containers
        if not containers:
            self.mount(
                Static(
                    "[dim yellow]No containers found[/]\n"
                    "[dim]Start a container or check your Docker installation[/]",
                    classes="docker-container"
                )
            )
            return

        for container in containers:
            self.display_container(container)

    def display_container(self, container: Dict[str, Any]) -> None:
        """
        Display a container.

        Args:
            container: Container info dictionary
        """
        container_id = container["id"][:12]
        name = container["name"]
        image = container["image"]
        status = container["status"]
        state = container["state"].lower()

        # Determine status color and icon
        if state == "running":
            status_color = "bright_green"
            icon = "▶️"
            emoji = "💚"
        elif state == "exited":
            status_color = "yellow"
            icon = "⏸️"
            emoji = "💛"
        else:
            status_color = "red"
            icon = "⏹️"
            emoji = "❤️"

        # Get stats if running
        stats_text = ""
        if state == "running":
            stats = self.get_container_stats(container_id)
            if stats:
                cpu = stats.get("cpu", "0%")
                mem = stats.get("memory", "0%")
                stats_text = (
                    f"\n[cyan]  CPU:[/] {self._format_percentage(cpu)}  "
                    f"[magenta]MEM:[/] {self._format_percentage(mem)}"
                )

        # Build display text
        display_text = (
            f"[bold {status_color}]{icon} {name}[/] {emoji} [{status_color}]{state.upper()}[/]\n"
            f"[dim green]  ID:[/] {container_id}  "
            f"[dim green]Image:[/] {image}\n"
            f"[dim green]  Status:[/] {status}"
            f"{stats_text}"
        )

        self.mount(
            Static(
                display_text,
                classes="docker-container",
                id=f"container-{container_id}"
            )
        )

    def _format_percentage(self, percent_str: str) -> Text:
        """Format percentage with color coding."""
        try:
            value = float(percent_str.rstrip("%"))
            if value > 80:
                color = "red"
            elif value > 50:
                color = "yellow"
            else:
                color = "green"
            return Text(percent_str, style=color)
        except Exception:
            return Text(percent_str, style="white")

    def show_error(self, error: str) -> None:
        """Show error message."""
        self.mount(
            Static(
                f"[bold red]⚠️  Error[/]\n[red]{error}[/]",
                classes="docker-error"
            )
        )

    # Container control methods
    def start_container(self, container_id: str) -> bool:
        """Start a container."""
        try:
            result = subprocess.run(
                ["docker", "start", container_id],
                capture_output=True,
                timeout=10
            )
            success = result.returncode == 0
            if success:
                logger.info(f"Started container: {container_id}")
                self.post_message(self.ContainerAction("start", container_id))
                self.refresh_containers()
            else:
                logger.error(f"Failed to start container: {result.stderr}")
            return success
        except Exception as e:
            logger.error(f"Error starting container: {e}")
            return False

    def stop_container(self, container_id: str) -> bool:
        """Stop a container."""
        try:
            result = subprocess.run(
                ["docker", "stop", container_id],
                capture_output=True,
                timeout=30
            )
            success = result.returncode == 0
            if success:
                logger.info(f"Stopped container: {container_id}")
                self.post_message(self.ContainerAction("stop", container_id))
                self.refresh_containers()
            else:
                logger.error(f"Failed to stop container: {result.stderr}")
            return success
        except Exception as e:
            logger.error(f"Error stopping container: {e}")
            return False

    def restart_container(self, container_id: str) -> bool:
        """Restart a container."""
        try:
            result = subprocess.run(
                ["docker", "restart", container_id],
                capture_output=True,
                timeout=30
            )
            success = result.returncode == 0
            if success:
                logger.info(f"Restarted container: {container_id}")
                self.post_message(self.ContainerAction("restart", container_id))
                self.refresh_containers()
            else:
                logger.error(f"Failed to restart container: {result.stderr}")
            return success
        except Exception as e:
            logger.error(f"Error restarting container: {e}")
            return False

    def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        """
        Get container logs.

        Args:
            container_id: Container ID
            tail: Number of lines to tail

        Returns:
            Log output
        """
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_id],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout + result.stderr
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return f"Error: {e}"

    def remove_container(self, container_id: str, force: bool = False) -> bool:
        """Remove a container."""
        try:
            cmd = ["docker", "rm", container_id]
            if force:
                cmd.append("-f")

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10
            )
            success = result.returncode == 0
            if success:
                logger.info(f"Removed container: {container_id}")
                self.post_message(self.ContainerAction("remove", container_id))
                self.refresh_containers()
            else:
                logger.error(f"Failed to remove container: {result.stderr}")
            return success
        except Exception as e:
            logger.error(f"Error removing container: {e}")
            return False

    def action_toggle_refresh(self) -> None:
        """Toggle auto-refresh."""
        self.auto_refresh = not self.auto_refresh
        logger.info(f"Auto-refresh: {self.auto_refresh}")
