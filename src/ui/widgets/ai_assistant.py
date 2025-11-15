"""AI Assistant widget with Smart Router integration."""
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
from src.utils.ai_router import SmartAIRouter


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

    AIAssistant .ai-routing-info {
        background: rgba(0, 50, 0, 0.6);
        border: round #00AA00;
        color: #00FFAA;
        padding: 1;
        margin: 1 0;
    }

    AIAssistant .ai-budget-warning {
        background: rgba(100, 50, 0, 0.8);
        border: round #FFAA00;
        color: #FFFF00;
        padding: 1;
        margin: 1 0;
        text-style: bold;
    }

    AIAssistant .model-ollama {
        color: #00FF00;
        text-style: bold;
    }

    AIAssistant .model-claude {
        color: #FFD700;
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
        self.router = SmartAIRouter()
        self.use_router = True  # Toggle for enabling/disabling smart routing

    def compose(self):
        """Create child widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║   🤖 Neo's AI Assistant (Smart Router)   ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="ai-header"
        )

        # Show budget status
        budget_status = self.router.get_budget_status()
        budget_pct = budget_status["percentage_used"]
        budget_color = "green" if budget_pct < 70 else ("yellow" if budget_pct < 90 else "red")
        budget_bar = self.get_budget_bar(budget_pct)

        yield Static(
            f"[dim green]Smart routing between Ollama (free) and Claude (paid)[/]\n"
            f"[yellow]⚠️  Note: Costs are estimated (CLI doesn't return actual tokens)[/]\n\n"
            f"[cyan]💰 Budget Status:[/] [{budget_color}]~${budget_status['spent']:.2f}[/] / "
            f"[green]${budget_status['budget']:.2f}[/] ({budget_pct:.1f}%)\n"
            f"[{budget_color}]{budget_bar}[/]\n"
            f"[dim]Ollama: {budget_status['ollama_requests']} | "
            f"Claude: {budget_status['claude_requests']}[/]\n\n"
            f"[cyan]Commands:[/]\n"
            f"[green]  • /explain <file>[/] - Explain code\n"
            f"[green]  • /fix <file>[/] - Find and fix bugs\n"
            f"[green]  • /refactor <file>[/] - Suggest improvements\n"
            f"[green]  • /test <file>[/] - Generate tests\n",
            id="ai-help"
        )

    def get_budget_bar(self, percentage: float, width: int = 20) -> str:
        """Create text-based budget progress bar."""
        filled = int((percentage / 100) * width)
        empty = width - filled
        return "█" * filled + "░" * empty

    def show_routing_info(self, model: str, cost: float, reason: str, is_estimate: bool = True, tiktoken_used: bool = False) -> None:
        """Show routing decision info with estimation warnings."""
        model_emoji = "🟢" if "ollama" in model.lower() else "🟡"
        model_class = "model-ollama" if "ollama" in model.lower() else "model-claude"

        # Build cost display with warning if it's an estimate
        if is_estimate and cost > 0:
            cost_method = "tiktoken" if tiktoken_used else "char-based"
            cost_display = f"[dim]~${cost:.4f} [yellow]⚠ estimated ({cost_method})[/][/]"
        else:
            cost_display = f"[dim]${cost:.4f}[/]"

        self.mount(
            Static(
                f"{model_emoji} [bold]Routed to:[/] [{model_class}]{model}[/] "
                f"{cost_display}\n"
                f"[dim]{reason}[/]",
                classes="ai-routing-info"
            )
        )

    def check_budget_warning(self):
        """Check and display budget warnings."""
        budget_status = self.router.get_budget_status()
        if budget_status["percentage_used"] >= 80 and budget_status["remaining"] > 0:
            self.mount(
                Static(
                    f"⚠️ [bold]BUDGET WARNING[/]\n"
                    f"You've used {budget_status['percentage_used']:.1f}% of your ${budget_status['budget']:.2f} monthly budget.\n"
                    f"Remaining: ${budget_status['remaining']:.2f}",
                    classes="ai-budget-warning"
                )
            )
        elif budget_status["remaining"] <= 0:
            self.mount(
                Static(
                    f"🚫 [bold]BUDGET EXHAUSTED[/]\n"
                    f"Monthly budget of ${budget_status['budget']:.2f} fully used.\n"
                    f"Falling back to Ollama only until next month.",
                    classes="ai-budget-warning"
                )
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
        Ask AI for assistance (routed through SmartAIRouter).

        Args:
            prompt: Question/instruction
            code: Optional code snippet to analyze
            file_path: Optional file to analyze

        Returns:
            AI response
        """
        try:
            self.is_thinking = True
            self.show_thinking()

            # Build full prompt
            full_prompt = prompt

            if file_path and file_path.exists():
                with open(file_path, "r") as f:
                    file_content = f.read()
                full_prompt = f"{prompt}\n\nFile: {file_path}\n```\n{file_content}\n```"
            elif code:
                full_prompt = f"{prompt}\n\n```\n{code}\n```"

            # Get routing decision
            routing_info = self.router.get_routing_info(full_prompt)
            should_use_claude = routing_info["should_use_claude"]

            # Show routing decision with estimate warning
            self.show_routing_info(
                model=routing_info["recommended_model"],
                cost=routing_info["estimated_cost"],
                reason=routing_info["reason"],
                is_estimate=routing_info.get("is_estimate", True),
                tiktoken_used=routing_info.get("tiktoken_used", False)
            )

            # Check budget warnings
            self.check_budget_warning()

            # Route to appropriate model
            if should_use_claude and self.use_router:
                response = await self._call_claude_cli(full_prompt)
                cost = routing_info["estimated_cost"]
                model = "claude"
            else:
                # Use Ollama
                result = self.router.call_ollama(full_prompt)
                if result["success"]:
                    response = result["response"]
                    cost = 0.0
                    model = "ollama/mistral"
                else:
                    # Fallback to Claude if Ollama fails
                    logger.warning(f"Ollama failed: {result.get('error')}. Falling back to Claude.")
                    response = await self._call_claude_cli(full_prompt)
                    cost = routing_info["estimated_cost"]
                    model = "claude (fallback)"

            # Update budget tracking
            self.router.update_budget(cost, model)

            # Store and display response
            self.last_response = response
            self.show_response(response)
            self.conversation_history.append({
                "prompt": prompt,
                "response": response,
                "model": model,
                "cost": cost
            })
            self.post_message(self.ResponseReceived(response))
            logger.info(f"Received response from {model}, cost: ${cost:.4f}")
            return response

        except Exception as e:
            error = f"Unexpected error: {e}"
            self.show_error(error)
            logger.error(f"Error in AI request: {e}")
            return error
        finally:
            self.is_thinking = False

    async def _call_claude_cli(self, prompt: str) -> str:
        """Internal: Call Claude CLI directly."""
        if not self.check_claude_cli():
            raise Exception("Claude CLI not available")

        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            error = result.stderr or "Unknown error"
            raise Exception(f"Claude CLI error: {error}")

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
