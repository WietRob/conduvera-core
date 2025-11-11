#!/usr/bin/env python3
"""
Rich-based Matrix OS Demo

Alternative implementation using Rich library for status dashboards
and data visualization without full interactive TUI.
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.tree import Tree
from rich.syntax import Syntax
import psutil
import time
import random
from datetime import datetime
from pathlib import Path


class MatrixOSRichDemo:
    """Matrix OS implementation using Rich library."""

    def __init__(self):
        self.console = Console()
        self.running = True
        self.iteration = 0

    def create_header(self) -> Panel:
        """Create header panel."""
        header_text = Text()
        header_text.append("MATRIX OS", style="bold green")
        header_text.append(" | ", style="dim")
        header_text.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="cyan")

        return Panel(
            header_text,
            style="green",
            border_style="bright_green",
        )

    def create_system_info(self) -> Panel:
        """Create system information panel."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="green")
        table.add_column(style="bright_green")

        table.add_row("CPU", f"{cpu_percent:.1f}%")
        table.add_row("Memory", f"{memory.percent:.1f}%")
        table.add_row("Disk", f"{disk.percent:.1f}%")
        table.add_row("Processes", str(len(psutil.pids())))

        return Panel(
            table,
            title="[bold green]System Info[/]",
            border_style="green",
        )

    def create_process_table(self) -> Panel:
        """Create process monitor table."""
        table = Table(title="Top Processes", style="green", border_style="green")

        table.add_column("PID", style="cyan", width=8)
        table.add_column("Name", style="bright_green", width=25)
        table.add_column("CPU%", style="yellow", width=8)
        table.add_column("MEM%", style="magenta", width=8)

        # Get top 5 processes by CPU
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        processes.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)

        for proc in processes[:5]:
            cpu_style = "red" if proc["cpu_percent"] > 50 else "yellow"
            mem_style = "red" if proc["memory_percent"] > 50 else "magenta"

            table.add_row(
                str(proc["pid"]),
                proc["name"][:23],
                f"[{cpu_style}]{proc['cpu_percent']:.1f}[/]",
                f"[{mem_style}]{proc['memory_percent']:.1f}[/]",
            )

        return Panel(table, border_style="green")

    def create_file_tree(self) -> Panel:
        """Create file tree view."""
        tree = Tree(
            "[bold green]📂 Project Files[/]",
            guide_style="green",
        )

        # Show current directory structure (limited)
        root_path = Path.cwd()

        try:
            # Add some directories and files
            for item in list(root_path.iterdir())[:5]:
                if item.is_dir():
                    branch = tree.add(f"[bold cyan]📁 {item.name}[/]")
                    # Add some files from directory
                    try:
                        for subitem in list(item.iterdir())[:3]:
                            icon = "📄" if subitem.is_file() else "📁"
                            branch.add(f"[dim]{icon} {subitem.name}[/]")
                    except PermissionError:
                        branch.add("[dim red]🔒 Permission denied[/]")
                else:
                    tree.add(f"[green]📄 {item.name}[/]")

        except PermissionError:
            tree.add("[red]Permission denied[/]")

        return Panel(tree, title="Files", border_style="green")

    def create_matrix_rain(self) -> Text:
        """Create simple matrix rain effect."""
        text = Text()
        chars = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄ0123456789"

        for _ in range(5):
            line = "".join(random.choice(chars) for _ in range(40))
            brightness = random.random()

            if brightness > 0.7:
                style = "bright_green"
            elif brightness > 0.4:
                style = "green"
            else:
                style = "dim green"

            text.append(line + "\n", style=style)

        return text

    def create_layout(self) -> Layout:
        """Create main layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )

        layout["left"].split_column(
            Layout(name="processes"),
            Layout(name="files"),
        )

        # Populate layout
        layout["header"].update(self.create_header())
        layout["right"].update(
            Panel(
                self.create_matrix_rain(),
                title="[bold green]Matrix Rain[/]",
                border_style="bright_green",
            )
        )
        layout["processes"].update(self.create_process_table())
        layout["files"].update(self.create_file_tree())
        layout["footer"].update(
            Panel(
                Text("Press Ctrl+C to exit", style="dim green", justify="center"),
                border_style="green",
            )
        )

        # Add system info to right panel
        layout["right"].split_column(
            Layout(name="matrix", ratio=2),
            Layout(name="sysinfo", ratio=1),
        )

        layout["matrix"].update(
            Panel(
                self.create_matrix_rain(),
                title="[bold green]Matrix Rain[/]",
                border_style="bright_green",
            )
        )
        layout["sysinfo"].update(self.create_system_info())

        return layout

    def run(self):
        """Run the Rich demo with live updates."""
        try:
            with Live(self.create_layout(), refresh_per_second=2, console=self.console) as live:
                while self.running:
                    time.sleep(0.5)
                    self.iteration += 1
                    live.update(self.create_layout())

        except KeyboardInterrupt:
            self.console.print("\n[bold green]Matrix OS terminated[/]")


def main():
    """Main entry point."""
    console = Console()

    # Show welcome
    console.print(
        Panel(
            "[bold green]Matrix OS - Rich Demo[/]\n\n"
            "This is an alternative implementation using Rich library\n"
            "for status dashboards and monitoring.",
            border_style="green",
        )
    )

    time.sleep(2)

    # Run demo
    demo = MatrixOSRichDemo()
    demo.run()


if __name__ == "__main__":
    main()
