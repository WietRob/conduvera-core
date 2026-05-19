"""HTTP/REST API Client widget (Postman-style TUI)."""
from textual.widgets import Static
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.message import Message
from typing import Dict, Any, Optional
import json
import time
from datetime import datetime
import subprocess
from src.utils.logger import logger


class APIClient(VerticalScroll):
    """
    HTTP/REST API Client widget.

    Postman-style TUI for testing APIs.
    """

    request_in_progress = reactive(False)
    last_response = reactive(None)

    DEFAULT_CSS = """
    APIClient {
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    APIClient:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    .api-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    .api-request {
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin: 1 0;
    }

    .api-response {
        background: rgba(0, 20, 0, 0.7);
        border: round #00FF00;
        padding: 1;
        margin: 1 0;
    }

    .api-success {
        color: #00FF00;
    }

    .api-error {
        color: #FF0000;
    }

    .api-warning {
        color: #FFAA00;
    }
    """

    class RequestSent(Message):
        """Message sent when API request is made."""

        def __init__(self, method: str, url: str) -> None:
            super().__init__()
            self.method = method
            self.url = url

    class ResponseReceived(Message):
        """Message sent when response is received."""

        def __init__(self, response: Dict[str, Any]) -> None:
            super().__init__()
            self.response = response

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.request_history = []

    def compose(self):
        """Create child widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║      🌐 API Testing Console (REST)       ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="api-header"
        )
        yield Static(
            "[dim green]HTTP/REST API client - Test your APIs[/]\n\n"
            "[cyan]Quick Start:[/]\n"
            "[green]  • Use send_request() to make requests[/]\n"
            "[green]  • Supports GET, POST, PUT, DELETE, PATCH[/]\n"
            "[green]  • JSON request/response formatting[/]\n"
            "[green]  • Headers and authentication[/]\n",
            id="api-help"
        )

    def send_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Send HTTP request using curl.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Optional headers dictionary
            body: Optional request body
            timeout: Request timeout in seconds

        Returns:
            Response dictionary with status, headers, body, time
        """
        if self.request_in_progress:
            return {"error": "Request already in progress"}

        try:
            self.request_in_progress = True
            self.show_request(method, url, headers, body)

            # Build curl command
            cmd = ["curl", "-X", method.upper(), url, "-w", "\\n%{http_code}",
                   "-s", "-i", "--max-time", str(timeout)]

            # Add headers
            if headers:
                for key, value in headers.items():
                    cmd.extend(["-H", f"{key}: {value}"])

            # Add body
            if body:
                cmd.extend(["-d", body])

            # Execute request
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5
            )
            duration = time.time() - start_time

            # Parse response
            output = result.stdout
            parts = output.rsplit("\\n", 1)

            if len(parts) == 2:
                response_text, status_code = parts
            else:
                response_text = output
                status_code = "000"

            # Parse headers and body
            response_lines = response_text.split("\\n", 1)
            status_line = response_lines[0] if response_lines else ""

            # Extract headers
            response_headers = {}
            response_body = ""
            if len(response_lines) > 1:
                header_body = response_lines[1].split("\\n\\n", 1)
                if len(header_body) == 2:
                    header_text, response_body = header_body
                    for line in header_text.split("\\n"):
                        if ": " in line:
                            key, value = line.split(": ", 1)
                            response_headers[key] = value
                else:
                    response_body = header_body[0]

            # Try to parse JSON body
            parsed_body = response_body
            try:
                parsed_body = json.loads(response_body)
            except Exception:
                pass

            response_data = {
                "method": method.upper(),
                "url": url,
                "status_code": int(status_code) if status_code.isdigit() else 0,
                "status_line": status_line,
                "headers": response_headers,
                "body": parsed_body,
                "duration_ms": int(duration * 1000),
                "timestamp": datetime.now().isoformat(),
                "error": None
            }

            self.last_response = response_data
            self.request_history.append(response_data)
            self.show_response(response_data)
            self.post_message(self.ResponseReceived(response_data))

            logger.info(f"API request: {method} {url} -> {status_code} ({duration:.2f}s)")
            return response_data

        except subprocess.TimeoutExpired:
            error_response = {
                "method": method.upper(),
                "url": url,
                "status_code": 0,
                "error": f"Request timeout ({timeout}s)",
                "timestamp": datetime.now().isoformat()
            }
            self.show_error("Request timeout")
            return error_response

        except Exception as e:
            error_response = {
                "method": method.upper(),
                "url": url,
                "status_code": 0,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            self.show_error(str(e))
            logger.error(f"API request error: {e}")
            return error_response

        finally:
            self.request_in_progress = False

    def show_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None
    ) -> None:
        """Display request details."""
        request_text = f"[bold cyan]→ {method.upper()}[/] {url}\n"

        if headers:
            request_text += "\n[dim]Headers:[/]\n"
            for key, value in headers.items():
                request_text += f"  [green]{key}:[/] {value}\n"

        if body:
            request_text += f"\n[dim]Body:[/]\n[yellow]{body}[/]"

        self.mount(
            Static(
                request_text,
                classes="api-request"
            )
        )

    def show_response(self, response: Dict[str, Any]) -> None:
        """Display response."""
        status_code = response.get("status_code", 0)
        duration = response.get("duration_ms", 0)
        body = response.get("body", "")

        # Determine status color
        if 200 <= status_code < 300:
            status_style = "bold green"
            status_icon = "✅"
        elif 300 <= status_code < 400:
            status_style = "bold yellow"
            status_icon = "↪️"
        elif 400 <= status_code < 500:
            status_style = "bold yellow"
            status_icon = "⚠️"
        else:
            status_style = "bold red"
            status_icon = "❌"

        # Format body
        if isinstance(body, dict):
            body_text = json.dumps(body, indent=2)
        else:
            body_text = str(body)

        response_text = (
            f"[{status_style}]{status_icon} Response: {status_code}[/] "
            f"[dim]({duration}ms)[/]\n\n"
            f"[dim]Body:[/]\n"
            f"[green]{body_text}[/]"
        )

        self.mount(
            Static(
                response_text,
                classes="api-response"
            )
        )

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def show_error(self, error: str) -> None:
        """Show error message."""
        self.mount(
            Static(
                f"[bold red]❌ Error[/]\n[red]{error}[/]",
                classes="api-error"
            )
        )

    # Quick HTTP methods
    async def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """GET request."""
        return self.send_request("GET", url, headers=headers)

    async def post(
        self,
        url: str,
        body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """POST request."""
        if headers is None:
            headers = {}
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        return self.send_request("POST", url, headers=headers, body=body)

    async def put(
        self,
        url: str,
        body: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """PUT request."""
        if headers is None:
            headers = {}
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        return self.send_request("PUT", url, headers=headers, body=body)

    async def delete(self, url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """DELETE request."""
        return self.send_request("DELETE", url, headers=headers)

    def clear_history(self) -> None:
        """Clear request history."""
        self.request_history = []
        # Clear all responses from display
        for widget in self.query(".api-request, .api-response, .api-error"):
            widget.remove()
