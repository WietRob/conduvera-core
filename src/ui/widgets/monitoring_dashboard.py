"""Advanced Monitoring Dashboard - Unified system, docker, process, and AI budget monitoring."""
from textual.widgets import Static
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.message import Message
from typing import Dict, Any
import psutil
import subprocess
import json
from datetime import datetime
from src.utils.logger import logger
from src.utils.ai_router import SmartAIRouter
from src.utils.feedback_tracker import FeedbackTracker


class MonitoringDashboard(VerticalScroll):
    """
    Advanced Monitoring Dashboard.

    Combines system metrics, Docker container stats, and process monitoring
    in a unified real-time dashboard.
    """

    auto_refresh = reactive(True)
    refresh_interval = reactive(2.0)  # seconds

    DEFAULT_CSS = """
    MonitoringDashboard {
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    MonitoringDashboard:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    .dashboard-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    .dashboard-section {
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin: 1 0;
    }

    .dashboard-metric {
        padding: 0 1;
    }

    .metric-good {
        color: #00FF00;
    }

    .metric-warning {
        color: #FFAA00;
    }

    .metric-critical {
        color: #FF0000;
    }

    .dashboard-grid {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        height: auto;
    }
    """

    class MetricsUpdated(Message):
        """Message sent when metrics are updated."""

        def __init__(self, metrics: Dict[str, Any]) -> None:
            super().__init__()
            self.metrics = metrics

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.last_update = None
        self.metrics_history = []
        self.router = SmartAIRouter()
        self.feedback_tracker = FeedbackTracker()

    def compose(self):
        """Create dashboard widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║   📊 Matrix Monitoring Dashboard         ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="dashboard-header"
        )
        yield Static(
            "[dim green]Real-time system, container, and process monitoring[/]\n"
            "[cyan]Auto-refresh every 2 seconds[/]",
            id="dashboard-help"
        )

    def on_mount(self) -> None:
        """Start auto-refresh when mounted."""
        if self.auto_refresh:
            self.set_interval(self.refresh_interval, self.refresh_dashboard)
        self.refresh_dashboard()
        logger.info("Monitoring Dashboard initialized")

    def refresh_dashboard(self) -> None:
        """Refresh all dashboard metrics."""
        try:
            # Collect metrics
            metrics = {
                "system": self.get_system_metrics(),
                "docker": self.get_docker_metrics(),
                "processes": self.get_process_metrics(),
                "network": self.get_network_metrics(),
                "ai_budget": self.get_ai_budget_metrics(),
                "timestamp": datetime.now().isoformat()
            }

            self.last_update = datetime.now()
            self.metrics_history.append(metrics)

            # Keep only last 60 updates (2 minutes at 2s interval)
            if len(self.metrics_history) > 60:
                self.metrics_history = self.metrics_history[-60:]

            # Clear previous displays
            for widget in self.query(".dashboard-section"):
                widget.remove()

            # Display metrics
            self.display_system_metrics(metrics["system"])
            self.display_docker_metrics(metrics["docker"])
            self.display_process_metrics(metrics["processes"])
            self.display_network_metrics(metrics["network"])
            self.display_ai_budget(metrics["ai_budget"])

            self.post_message(self.MetricsUpdated(metrics))

        except Exception as e:
            logger.error(f"Error refreshing dashboard: {e}")

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system resource metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "memory_percent": memory.percent,
                "memory_used_gb": memory.used / (1024**3),
                "memory_total_gb": memory.total / (1024**3),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024**3),
                "disk_total_gb": disk.total / (1024**3),
                "uptime": self.get_uptime(),
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}

    def get_docker_metrics(self) -> Dict[str, Any]:
        """Get Docker container metrics."""
        try:
            # Check if Docker is available
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=2
            )

            if result.returncode != 0:
                return {"available": False}

            # Get container count
            ps_result = subprocess.run(
                ["docker", "ps", "-q"],
                capture_output=True,
                text=True,
                timeout=2
            )
            running_count = len(ps_result.stdout.strip().split('\n')) if ps_result.stdout.strip() else 0

            ps_all_result = subprocess.run(
                ["docker", "ps", "-aq"],
                capture_output=True,
                text=True,
                timeout=2
            )
            total_count = len(ps_all_result.stdout.strip().split('\n')) if ps_all_result.stdout.strip() else 0

            # Get running container stats (top 5 by CPU)
            stats_result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=5
            )

            containers = []
            if stats_result.returncode == 0 and stats_result.stdout:
                for line in stats_result.stdout.strip().split('\n')[:5]:
                    if line:
                        try:
                            stat = json.loads(line)
                            containers.append({
                                "name": stat.get("Name", ""),
                                "cpu": stat.get("CPUPerc", "0%"),
                                "memory": stat.get("MemPerc", "0%"),
                            })
                        except json.JSONDecodeError:
                            pass

            return {
                "available": True,
                "running": running_count,
                "total": total_count,
                "containers": containers
            }

        except Exception as e:
            logger.error(f"Error getting Docker metrics: {e}")
            return {"available": False}

    def get_process_metrics(self) -> Dict[str, Any]:
        """Get top processes by CPU usage."""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    processes.append({
                        "pid": pinfo["pid"],
                        "name": pinfo["name"] or "Unknown",
                        "cpu": pinfo["cpu_percent"] or 0.0,
                        "memory": pinfo["memory_percent"] or 0.0,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Sort by CPU and get top 5
            top_processes = sorted(processes, key=lambda x: x["cpu"], reverse=True)[:5]

            return {
                "total_count": len(processes),
                "top_processes": top_processes
            }

        except Exception as e:
            logger.error(f"Error getting process metrics: {e}")
            return {"total_count": 0, "top_processes": []}

    def get_network_metrics(self) -> Dict[str, Any]:
        """Get network I/O metrics."""
        try:
            net_io = psutil.net_io_counters()
            return {
                "bytes_sent_gb": net_io.bytes_sent / (1024**3),
                "bytes_recv_gb": net_io.bytes_recv / (1024**3),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            }
        except Exception as e:
            logger.error(f"Error getting network metrics: {e}")
            return {}

    def get_uptime(self) -> str:
        """Get system uptime."""
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{days}d {hours}h {minutes}m"
        except Exception:
            return "Unknown"

    def display_system_metrics(self, metrics: Dict[str, Any]) -> None:
        """Display system metrics section."""
        if not metrics:
            return

        cpu = metrics.get("cpu_percent", 0)
        mem = metrics.get("memory_percent", 0)
        disk = metrics.get("disk_percent", 0)

        # Color coding
        cpu_color = self.get_metric_color(cpu)
        mem_color = self.get_metric_color(mem)
        disk_color = self.get_metric_color(disk)

        text = (
            f"[bold cyan]🖥️  SYSTEM RESOURCES[/]\n\n"
            f"[bold]CPU:[/] [{cpu_color}]{cpu:.1f}%[/] {self.get_bar(cpu)} "
            f"[dim]({metrics.get('cpu_count', 0)} cores)[/]\n"
            f"[bold]Memory:[/] [{mem_color}]{mem:.1f}%[/] {self.get_bar(mem)} "
            f"[dim]({metrics.get('memory_used_gb', 0):.1f}GB / {metrics.get('memory_total_gb', 0):.1f}GB)[/]\n"
            f"[bold]Disk:[/] [{disk_color}]{disk:.1f}%[/] {self.get_bar(disk)} "
            f"[dim]({metrics.get('disk_used_gb', 0):.1f}GB / {metrics.get('disk_total_gb', 0):.1f}GB)[/]\n"
            f"[bold]Uptime:[/] [green]{metrics.get('uptime', 'Unknown')}[/]"
        )

        self.mount(Static(text, classes="dashboard-section"))

    def display_docker_metrics(self, metrics: Dict[str, Any]) -> None:
        """Display Docker metrics section."""
        if not metrics.get("available", False):
            text = (
                "[bold cyan]🐳 DOCKER CONTAINERS[/]\n\n"
                "[dim yellow]Docker not available or not running[/]"
            )
        else:
            running = metrics.get("running", 0)
            total = metrics.get("total", 0)
            containers = metrics.get("containers", [])

            text = (
                f"[bold cyan]🐳 DOCKER CONTAINERS[/]\n\n"
                f"[bold]Status:[/] [green]{running}[/] running / [yellow]{total}[/] total\n"
            )

            if containers:
                text += "\n[bold]Top Containers:[/]\n"
                for container in containers:
                    name = container["name"][:20]
                    cpu = container["cpu"]
                    mem = container["memory"]
                    text += f"  [green]▶[/] {name:20} [cyan]CPU:[/] {cpu:>6} [magenta]MEM:[/] {mem:>6}\n"
            else:
                text += "\n[dim]No running containers[/]"

        self.mount(Static(text, classes="dashboard-section"))

    def display_process_metrics(self, metrics: Dict[str, Any]) -> None:
        """Display process metrics section."""
        total = metrics.get("total_count", 0)
        processes = metrics.get("top_processes", [])

        text = (
            f"[bold cyan]⚙️  PROCESSES[/]\n\n"
            f"[bold]Total:[/] [green]{total}[/] processes\n"
        )

        if processes:
            text += "\n[bold]Top CPU Consumers:[/]\n"
            for proc in processes:
                pid = proc["pid"]
                name = proc["name"][:20]
                cpu = proc["cpu"]
                mem = proc["memory"]

                cpu_color = self.get_metric_color(cpu)
                text += f"  [{cpu_color}]{pid:>6}[/] {name:20} [{cpu_color}]{cpu:>5.1f}%[/] [dim]{mem:>5.1f}%[/]\n"

        self.mount(Static(text, classes="dashboard-section"))

    def display_network_metrics(self, metrics: Dict[str, Any]) -> None:
        """Display network metrics section."""
        if not metrics:
            return

        sent_gb = metrics.get("bytes_sent_gb", 0)
        recv_gb = metrics.get("bytes_recv_gb", 0)
        sent_pkts = metrics.get("packets_sent", 0)
        recv_pkts = metrics.get("packets_recv", 0)

        text = (
            f"[bold cyan]🌐 NETWORK I/O[/]\n\n"
            f"[bold]Sent:[/] [green]{sent_gb:.2f} GB[/] [dim]({sent_pkts:,} packets)[/]\n"
            f"[bold]Received:[/] [cyan]{recv_gb:.2f} GB[/] [dim]({recv_pkts:,} packets)[/]"
        )

        self.mount(Static(text, classes="dashboard-section"))

    def get_metric_color(self, value: float) -> str:
        """Get color based on metric value."""
        if value >= 90:
            return "red"
        elif value >= 70:
            return "yellow"
        else:
            return "green"

    def get_bar(self, percent: float, width: int = 20) -> str:
        """Create a text-based progress bar."""
        filled = int((percent / 100) * width)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        color = self.get_metric_color(percent)
        return f"[{color}]{bar}[/]"

    def toggle_auto_refresh(self) -> None:
        """Toggle auto-refresh."""
        self.auto_refresh = not self.auto_refresh
        logger.info(f"Dashboard auto-refresh: {self.auto_refresh}")

    def get_ai_budget_metrics(self) -> Dict[str, Any]:
        """Get AI budget metrics."""
        try:
            budget_status = self.router.get_budget_status()
            monthly_stats = self.router.get_monthly_stats()

            return {
                "current_month": budget_status["current_month"],
                "spent": budget_status["spent"],
                "budget": budget_status["budget"],
                "remaining": budget_status["remaining"],
                "percentage_used": budget_status["percentage_used"],
                "requests": budget_status["requests"],
                "ollama_requests": budget_status["ollama_requests"],
                "claude_requests": budget_status["claude_requests"],
                "monthly_stats": monthly_stats[:3]  # Last 3 months
            }
        except Exception as e:
            logger.error(f"Error getting AI budget metrics: {e}")
            return {}

    def display_ai_budget(self, metrics: Dict[str, Any]) -> None:
        """Display AI budget section."""
        if not metrics:
            text = (
                "[bold cyan]🧠 AI BUDGET[/]\n\n"
                "[dim yellow]AI Router not configured[/]"
            )
        else:
            spent = metrics.get("spent", 0.0)
            budget = metrics.get("budget", 5.0)
            remaining = metrics.get("remaining", 0.0)
            percentage = metrics.get("percentage_used", 0.0)
            ollama = metrics.get("ollama_requests", 0)
            claude = metrics.get("claude_requests", 0)
            total_requests = metrics.get("requests", 0)

            # Color coding
            budget_color = self.get_metric_color(percentage)

            # Calculate percentages
            ollama_pct = (ollama / total_requests * 100) if total_requests > 0 else 0
            claude_pct = (claude / total_requests * 100) if total_requests > 0 else 0

            text = (
                f"[bold cyan]🧠 AI BUDGET ({metrics['current_month']})[/]\n"
                f"[yellow]⚠️  Estimated costs (not measured)[/]\n\n"
                f"[bold]Spent:[/] [{budget_color}]~${spent:.2f}[/] / [green]${budget:.2f}[/] "
                f"[dim]({percentage:.1f}%)[/]\n"
                f"[{budget_color}]{self.get_bar(percentage)}[/]\n"
                f"[bold]Remaining:[/] [green]~${remaining:.2f}[/]\n\n"
                f"[bold]Requests:[/] [green]{total_requests}[/] total\n"
                f"  [green]🟢 Ollama:[/] {ollama} [dim]({ollama_pct:.1f}%) - $0.00[/]\n"
                f"  [yellow]🟡 Claude:[/] {claude} [dim]({claude_pct:.1f}%) - ~${spent:.2f}[/]"
            )

            # Add user feedback stats (Phase 7C)
            feedback_stats = self.feedback_tracker.get_feedback_stats(days=30)
            if feedback_stats["total_feedback"] > 0:
                thumbs_up = feedback_stats["ratings"]["thumbs_up"]
                thumbs_down = feedback_stats["ratings"]["thumbs_down"]
                skip = feedback_stats["ratings"]["skip"]
                total_fb = feedback_stats["total_feedback"]

                thumbs_up_pct = feedback_stats["percentages"]["thumbs_up"]
                thumbs_down_pct = feedback_stats["percentages"]["thumbs_down"]

                # Routing accuracy
                routing_acc = feedback_stats["routing_accuracy"]
                ollama_acc = routing_acc["ollama_accuracy"]
                claude_acc = routing_acc["claude_accuracy"]
                misrouted = feedback_stats["misrouted"]["total"]

                text += (
                    f"\n\n[bold cyan]📊 USER SATISFACTION[/] [dim](30 days)[/]\n"
                    f"  [green]👍 Helpful:[/] {thumbs_up} [dim]({thumbs_up_pct:.0f}%)[/]\n"
                    f"  [red]👎 Not helpful:[/] {thumbs_down} [dim]({thumbs_down_pct:.0f}%)[/]\n"
                    f"  [yellow]⏭️  Skipped:[/] {skip} [dim]({skip / total_fb * 100:.0f}%)[/]\n\n"
                    f"[bold cyan]🎯 ROUTING ACCURACY[/]\n"
                    f"  [green]✅ Ollama:[/] {routing_acc['ollama_correct']}/{routing_acc['ollama_total']} "
                    f"[dim]({ollama_acc:.0f}%)[/]\n"
                    f"  [yellow]✅ Claude:[/] {routing_acc['claude_correct']}/{routing_acc['claude_total']} "
                    f"[dim]({claude_acc:.0f}%)[/]\n"
                )

                if misrouted > 0:
                    text += f"  [red]❌ Misrouted:[/] {misrouted} prompts [dim](should review)[/]\n"

            # Add monthly history if available
            monthly_stats = metrics.get("monthly_stats", [])
            if monthly_stats:
                text += "\n[bold]Recent Months:[/]\n"
                for stat in monthly_stats:
                    month = stat["month"]
                    spent_month = stat["spent"]
                    requests_month = stat["requests"]
                    avg_cost = stat.get("avg_cost_per_request", 0.0)
                    text += f"  [dim]{month}:[/] ${spent_month:.2f} [dim]({requests_month} req, ${avg_cost:.4f}/req)[/]\n"

        self.mount(Static(text, classes="dashboard-section"))

    def get_summary(self) -> Dict[str, Any]:
        """Get dashboard summary."""
        if not self.metrics_history:
            return {}

        latest = self.metrics_history[-1]
        return {
            "timestamp": latest["timestamp"],
            "cpu": latest["system"].get("cpu_percent", 0),
            "memory": latest["system"].get("memory_percent", 0),
            "disk": latest["system"].get("disk_percent", 0),
            "docker_running": latest["docker"].get("running", 0) if latest["docker"].get("available") else 0,
            "process_count": latest["processes"].get("total_count", 0),
        }
