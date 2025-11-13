"""AI Assistant widget with Claude CLI integration."""
from textual.widgets import Static
from textual.containers import VerticalScroll, Horizontal
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.markdown import Markdown
from pathlib import Path
import subprocess
from typing import Optional
from src.utils.logger import logger


class AIAssistant(VerticalScroll):
    """
    AI Assistant widget integrating Claude CLI.

    Provides AI-powered code assistance, explanations, and debugging help.
    """

    is_thinking = reactive(False)
    last_response = reactive("")

    DEFAULT_CSS = """
    AIAssistant {
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    AIAssistant:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    AIAssistant .ai-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    AIAssistant .ai-thinking {
        color: #FFFF00;
        text-style: italic;
    }

    AIAssistant .ai-response {
        color: #00FF00;
        padding: 1;
        margin: 1 0;
    }

    AIAssistant .ai-error {
        color: #FF0000;
        text-style: bold;
    }
    """

    class ResponseReceived(Message):
        """Message sent when AI response is received."""

        def __init__(self, response: str) -> None:
            super().__init__()
            self.response = response

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.conversation_history = []

    def compose(self):
        """Create child widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║      🤖 Neo's AI Assistant (Claude)      ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="ai-header"
        )
        yield Static(
            "[dim green]Ask me anything about your code![/]\n"
            "[cyan]Commands:[/]\n"
            "[green]  • /explain <file>[/] - Explain code\n"
            "[green]  • /fix <file>[/] - Find and fix bugs\n"
            "[green]  • /refactor <file>[/] - Suggest improvements\n"
            "[green]  • /test <file>[/] - Generate tests\n",
            id="ai-help"
        )

    def check_claude_cli(self) -> bool:
        """
        Check if Claude CLI is installed.

        Returns:
            True if Claude CLI is available
        """
        try:
            result = subprocess.run(
                ["which", "claude"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking Claude CLI: {e}")
            return False

    async def ask_claude(
        self,
        prompt: str,
        code: Optional[str] = None,
        file_path: Optional[Path] = None
    ) -> str:
        """
        Ask Claude CLI for assistance.

        Args:
            prompt: Question/instruction for Claude
            code: Optional code snippet to analyze
            file_path: Optional file to analyze

        Returns:
            Claude's response
        """
        if not self.check_claude_cli():
            error_msg = (
                "❌ Claude CLI not found!\n\n"
                "Install it with: pip install claude-cli\n"
                "Or visit: https://docs.anthropic.com/claude/docs/cli"
            )
            self.show_error(error_msg)
            return error_msg

        try:
            self.is_thinking = True
            self.show_thinking()

            # Build command
            full_prompt = prompt

            if file_path and file_path.exists():
                # Read file and include in prompt
                with open(file_path, "r") as f:
                    file_content = f.read()
                full_prompt = f"{prompt}\n\nFile: {file_path}\n```\n{file_content}\n```"
            elif code:
                full_prompt = f"{prompt}\n\n```\n{code}\n```"

            # Call Claude CLI
            result = subprocess.run(
                ["claude", "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                response = result.stdout.strip()
                self.last_response = response
                self.show_response(response)
                self.conversation_history.append({
                    "prompt": prompt,
                    "response": response
                })
                self.post_message(self.ResponseReceived(response))
                logger.info("Received Claude response")
                return response
            else:
                error = result.stderr or "Unknown error"
                self.show_error(f"Claude CLI error: {error}")
                logger.error(f"Claude CLI error: {error}")
                return f"Error: {error}"

        except subprocess.TimeoutExpired:
            error = "Claude CLI timeout (30s)"
            self.show_error(error)
            return error
        except Exception as e:
            error = f"Unexpected error: {e}"
            self.show_error(error)
            logger.error(f"Error calling Claude: {e}")
            return error
        finally:
            self.is_thinking = False

    def show_thinking(self) -> None:
        """Show thinking indicator."""
        self.mount(
            Static(
                "🤔 [italic yellow]Neo is thinking...[/]",
                classes="ai-thinking",
                id="ai-thinking-indicator"
            )
        )

    def show_response(self, response: str) -> None:
        """
        Show AI response.

        Args:
            response: Response text to display
        """
        # Remove thinking indicator
        try:
            indicator = self.query_one("#ai-thinking-indicator")
            indicator.remove()
        except:
            pass

        # Show response
        self.mount(
            Static(
                f"[bold bright_green]╭─ Neo's Response ──────────────────────╮[/]\n"
                f"[green]{response}[/]\n"
                f"[bold bright_green]╰────────────────────────────────────────╯[/]",
                classes="ai-response"
            )
        )

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def show_error(self, error: str) -> None:
        """
        Show error message.

        Args:
            error: Error message
        """
        # Remove thinking indicator if present
        try:
            indicator = self.query_one("#ai-thinking-indicator")
            indicator.remove()
        except:
            pass

        self.mount(
            Static(
                f"[bold red]⚠️  Error[/]\n[red]{error}[/]",
                classes="ai-error"
            )
        )

    def clear_conversation(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        # Clear all responses from display
        for widget in self.query(".ai-response, .ai-error, .ai-thinking"):
            widget.remove()

    # Quick action methods
    async def explain_code(self, file_path: Path) -> str:
        """
        Explain code in file.

        Args:
            file_path: Path to file to explain

        Returns:
            Explanation
        """
        return await self.ask_claude(
            "Please explain what this code does, how it works, and any important details:",
            file_path=file_path
        )

    async def find_bugs(self, file_path: Path) -> str:
        """
        Find bugs in code.

        Args:
            file_path: Path to file to analyze

        Returns:
            Bug report
        """
        return await self.ask_claude(
            "Please analyze this code for bugs, errors, or potential issues. "
            "Provide specific line numbers and suggested fixes:",
            file_path=file_path
        )

    async def suggest_refactoring(self, file_path: Path) -> str:
        """
        Suggest code refactoring.

        Args:
            file_path: Path to file to refactor

        Returns:
            Refactoring suggestions
        """
        return await self.ask_claude(
            "Please suggest refactoring improvements for this code. "
            "Focus on code quality, readability, and best practices:",
            file_path=file_path
        )

    async def generate_tests(self, file_path: Path) -> str:
        """
        Generate test cases.

        Args:
            file_path: Path to file to generate tests for

        Returns:
            Generated tests
        """
        return await self.ask_claude(
            "Please generate comprehensive unit tests for this code. "
            "Include edge cases and use appropriate testing framework:",
            file_path=file_path
        )

    async def quick_question(self, question: str, code: Optional[str] = None) -> str:
        """
        Ask a quick question.

        Args:
            question: Question to ask
            code: Optional code context

        Returns:
            Answer
        """
        return await self.ask_claude(question, code=code)
