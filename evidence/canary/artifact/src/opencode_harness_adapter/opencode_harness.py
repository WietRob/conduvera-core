"""Real OpenCode invocation wrapper (goal close-provider-failure-lifecycle,
Arbeit 5: the classifier must not stay an unused helper module).

``invoke_opencode`` runs the actual OpenCode CLI as a subprocess, captures
stdout/stderr/exit code, classifies the result via
:func:`hermes_cli.opencode_result.classify_opencode_result`, and returns a
structured harness result for Conduvera evidence.

The real operational/test invocation MUST go through this wrapper.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

from opencode_harness_adapter.opencode_result import classify_opencode_result


@dataclass(frozen=True)
class OpenCodeHarnessResult:
    """Structured harness result (Conduvera evidence)."""

    model: str
    status: str  # SUCCESS | FAILED | BLOCKED_EXTERNAL_PROVIDER
    stdout: str
    stdout_non_empty: bool
    exit_code: int
    provider_hint: str
    duration_s: float
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def invoke_opencode(
    prompt: str,
    *,
    model: str,
    binary: str = "opencode",
    timeout_s: int = 150,
    extra_args: Optional[list[str]] = None,
    port: Optional[int] = None,
) -> OpenCodeHarnessResult:
    """Run one OpenCode CLI invocation and classify the outcome.

    Args:
        prompt: the user prompt to pass to ``opencode run``.
        model: fully-qualified model id (e.g. ``litellm/provider/...``).
        binary: opencode binary path (defaults to ``opencode`` on PATH).
        timeout_s: subprocess timeout. A timeout is classified as a
            provider failure (BLOCKED_EXTERNAL_PROVIDER) — empty output
            with exit 0 is never SUCCESS.
        extra_args: additional CLI args before the prompt.
        port: optional ``--port`` for an isolated server instance.

    Returns:
        A structured :class:`OpenCodeHarnessResult`.
    """
    cmd = [binary, "run"]
    if extra_args:
        cmd.extend(extra_args)
    if port is not None:
        cmd.extend(["--port", str(port)])
    cmd.extend(["--model", model, prompt])

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = f"timeout after {timeout_s}s"
        exit_code = 1
    except FileNotFoundError:
        stdout = ""
        stderr = f"binary not found: {binary}"
        exit_code = 127

    client_log = stderr or ""
    result = classify_opencode_result(
        model=model,
        stdout=stdout,
        exit_code=exit_code,
        client_log=client_log,
    )
    return OpenCodeHarnessResult(
        model=model,
        status=result.status,
        stdout=stdout,
        stdout_non_empty=result.stdout_non_empty,
        exit_code=exit_code,
        provider_hint=result.provider_hint,
        duration_s=round(time.monotonic() - start, 3),
        timestamp=int(time.time()),
    )
