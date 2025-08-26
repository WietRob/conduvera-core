from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich import box

from .colors import console
from . import crypto as crypt
from . import net as netmod
from . import monitor as mon
from . import matrix as matrixfx

app = typer.Typer(help="Matrix.OS CLI — the pragmatic devtool", add_completion=False, no_args_is_help=True)
crypto_app = typer.Typer(help="Cryptographic utilities")
net_app = typer.Typer(help="Networking utilities")
monitor_app = typer.Typer(help="Monitoring and anti-surveillance checks")

app.add_typer(crypto_app, name="crypto")
app.add_typer(net_app, name="net")
app.add_typer(monitor_app, name="monitor")


@app.command()
def matrix(duration: float = typer.Option(10.0, help="Duration in seconds"), speed: float = typer.Option(0.05, help="Frame delay (smaller is faster)")):
    """Matrix rain animation in the terminal."""
    matrixfx.run_matrix_rain(duration=duration, speed=speed)


# --- Crypto ---
@crypto_app.command("hash")
def crypto_hash(
    file: Optional[Path] = typer.Option(None, "--file", "-f", exists=True, readable=True, help="File to hash"),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text to hash (if no file)"),
    algo: str = typer.Option("sha256", "--algo", case_sensitive=False, help="sha256 | sha1 | blake2b"),
):
    """Compute a hash of a file or text."""
    if file is None and text is None:
        text = Prompt.ask("Enter text to hash")
    data = file.read_bytes() if file else (text or "").encode()
    digest = crypt.hash_bytes(data, algo=algo)
    console.print(Panel.fit(digest, title=f"[matrix.title]{algo.upper()}[/matrix.title]", border_style="matrix.primary"))


@crypto_app.command("enc")
def crypto_encrypt(
    input: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Argument(...),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (will prompt if omitted)"),
):
    """Encrypt a file with AES-256-GCM (password-based)."""
    if not password:
        password = Prompt.ask("Password", password=True)
    crypt.encrypt_file(str(input), str(output), password)
    console.print(f"[matrix.ok]Encrypted[/matrix.ok] -> {output}")


@crypto_app.command("dec")
def crypto_decrypt(
    input: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Argument(...),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (will prompt if omitted)"),
):
    """Decrypt a file encrypted by Matrix.OS crypto."""
    if not password:
        password = Prompt.ask("Password", password=True)
    crypt.decrypt_file(str(input), str(output), password)
    console.print(f"[matrix.ok]Decrypted[/matrix.ok] -> {output}")


# --- Net ---
@net_app.command("scan")
def net_scan(
    host: str = typer.Argument("127.0.0.1"),
    ports: Optional[str] = typer.Option(None, "--ports", "-p", help="e.g. 1-1024,80,443"),
    common: bool = typer.Option(False, "--common", help="Scan common ports set"),
    timeout: float = typer.Option(1.0, "--timeout", help="Per-port timeout in seconds"),
    concurrency: int = typer.Option(500, "--concurrency", help="Concurrent connections"),
):
    """Port scan a host (async connect)."""
    port_list = netmod.COMMON_PORTS if common else netmod.parse_ports(ports)

    async def run():
        open_ports = await netmod.scan_host(host, port_list, timeout=timeout, concurrency=concurrency)
        table = Table(title=f"Open ports on {host}", box=box.SIMPLE, border_style="matrix.primary")
        table.add_column("Port", justify="right")
        for p in open_ports:
            table.add_row(str(p))
        if not open_ports:
            console.print("[matrix.dim]No open ports found[/matrix.dim]")
        else:
            console.print(table)

    asyncio.run(run())


# --- Monitor ---
@monitor_app.command("check")
def monitor_check():
    """Run basic anti-monitoring checks."""
    s = mon.summary()
    table = Table(title="Monitoring checks", box=box.SIMPLE, border_style="matrix.primary")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Debugger attached", "YES" if s["debugger"] else "no")
    env_flags = ",".join(s["env_flags"]) if s["env_flags"] else "none"
    table.add_row("Suspicious env", env_flags)
    procs = ",".join(s["suspicious_processes"]) if s["suspicious_processes"] else "none"
    table.add_row("Suspicious processes", procs)
    console.print(table)
