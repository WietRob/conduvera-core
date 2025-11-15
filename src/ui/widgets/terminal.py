"""Terminal emulator widget with PTY support."""
from textual.widgets import RichLog
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
import pty
import os
import select
import subprocess
import fcntl
import struct
import termios
from threading import Thread
from typing import Optional
from src.utils.logger import logger


class Terminal(RichLog):
    """
    Terminal emulator widget with PTY support.

    Provides a full terminal emulator with shell integration.
    """

    command_running = reactive(False)

    DEFAULT_CSS = """
    Terminal {
        background: #000000;
        color: #00FF00;
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    Terminal:focus {
        border: heavy #00FF00;
        background: rgba(0, 10, 0, 0.3);
    }
    """

    class CommandExecuted(Message):
        """Message sent when a command is executed."""

        def __init__(self, command: str) -> None:
            super().__init__()
            self.command = command

    def __init__(
        self,
        shell: str = "/bin/bash",
        auto_scroll: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(auto_scroll=auto_scroll, **kwargs)
        self.shell = shell
        self.master_fd: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None
        self.read_thread: Optional[Thread] = None
        self._running = False

    def on_mount(self) -> None:
        """Start shell when terminal is mounted."""
        try:
            self.start_shell()
            logger.info(f"Terminal started with shell: {self.shell}")
        except Exception as e:
            logger.error(f"Failed to start terminal: {e}")
            self.write(f"[bold red]Failed to start terminal: {e}[/]")

    def start_shell(self) -> None:
        """Start shell process with PTY."""
        try:
            # Create PTY
            self.master_fd, slave_fd = pty.openpty()

            # Set terminal size
            self._set_terminal_size()

            # Start shell process
            self.process = subprocess.Popen(
                [self.shell],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                env=os.environ.copy(),
            )

            # Close slave fd in parent process
            os.close(slave_fd)

            # Make master_fd non-blocking
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Start read thread
            self._running = True
            self.read_thread = Thread(target=self._read_output, daemon=True)
            self.read_thread.start()

            self.command_running = True

        except Exception as e:
            logger.error(f"Failed to start shell: {e}")
            raise

    def _set_terminal_size(self) -> None:
        """Set PTY terminal size to match widget size."""
        if self.master_fd is None:
            return

        try:
            # Get widget size (default to 80x24 if not available)
            rows = max(24, self.size.height - 2)  # Account for padding
            cols = max(80, self.size.width - 2)

            # Set window size
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

        except Exception as e:
            logger.warning(f"Failed to set terminal size: {e}")

    def _read_output(self) -> None:
        """Read output from PTY in background thread."""
        while self._running and self.master_fd is not None:
            try:
                # Use select for non-blocking read with timeout
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)

                if ready:
                    data = os.read(self.master_fd, 4096)
                    if data:
                        # Decode and write to terminal display
                        text = data.decode("utf-8", errors="replace")
                        # Remove null bytes and other control characters
                        text = text.replace("\x00", "")
                        self.write(text)
                    else:
                        # EOF - shell closed
                        break

            except OSError as e:
                if e.errno == 5:  # EIO - process ended
                    break
                logger.debug(f"Read error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in read thread: {e}")
                break

        self.command_running = False
        logger.info("Terminal read thread ended")

    def execute_command(self, command: str) -> None:
        """
        Execute a command in the terminal.

        Args:
            command: Command string to execute
        """
        if self.master_fd and self.process and self.process.poll() is None:
            try:
                # Write command to PTY
                os.write(self.master_fd, f"{command}\n".encode("utf-8"))
                self.post_message(self.CommandExecuted(command))
                logger.debug(f"Executed command: {command}")
            except Exception as e:
                logger.error(f"Failed to execute command: {e}")
                self.write(f"[bold red]Error executing command: {e}[/]")
        else:
            self.write("[bold yellow]Terminal not ready[/]")

    def send_input(self, text: str) -> None:
        """
        Send raw input to terminal.

        Args:
            text: Text to send (without newline)
        """
        if self.master_fd:
            try:
                os.write(self.master_fd, text.encode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to send input: {e}")

    def send_control(self, char: str) -> None:
        """
        Send control character (e.g., Ctrl+C).

        Args:
            char: Character to send with Ctrl (e.g., 'c' for Ctrl+C)
        """
        if self.master_fd and len(char) == 1:
            try:
                # Control character is ord(char) - ord('a') + 1
                ctrl_char = chr(ord(char.lower()) - ord("a") + 1)
                os.write(self.master_fd, ctrl_char.encode("utf-8"))
                logger.debug(f"Sent Ctrl+{char.upper()}")
            except Exception as e:
                logger.error(f"Failed to send control character: {e}")

    def clear_terminal(self) -> None:
        """Clear terminal display."""
        self.clear()
        self.write("[dim]Terminal cleared[/]")

    def restart_shell(self) -> None:
        """Restart the shell."""
        self.stop_shell()
        self.clear()
        self.write("[bold yellow]Restarting shell...[/]")
        try:
            self.start_shell()
            self.write("[bold green]Shell restarted successfully[/]")
        except Exception as e:
            self.write(f"[bold red]Failed to restart shell: {e}[/]")

    def stop_shell(self) -> None:
        """Stop the shell process."""
        self._running = False

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception as e:
                logger.error(f"Error stopping process: {e}")

        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception as e:
                logger.error(f"Error closing PTY: {e}")

        self.master_fd = None
        self.process = None
        self.command_running = False

    def on_unmount(self) -> None:
        """Cleanup when terminal is unmounted."""
        self.stop_shell()
        logger.info("Terminal unmounted")
