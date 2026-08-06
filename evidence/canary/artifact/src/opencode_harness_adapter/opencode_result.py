"""OpenCode result classification for Conduvera evidence (goal
normalize-provider-failures, Arbeit 5).

Contract:
- non-empty stdout + exit 0  -> SUCCESS
- empty stdout + exit 0      -> NEVER success (could be provider 429/503 that
  the client swallowed, or a silently empty reasoning-model answer)
- known provider failure in client log/response (429/503/timeout/quota)
  -> BLOCKED_EXTERNAL_PROVIDER
- anything else               -> FAILED

The original opencode.json stays untouched: main = gpt-5.6-sol,
small_model = glm-5.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SUCCESS = "SUCCESS"
FAILED = "FAILED"
BLOCKED_EXTERNAL_PROVIDER = "BLOCKED_EXTERNAL_PROVIDER"

# Provider-failure fingerprints found in opencode client logs / stderr.
_PROVIDER_FAILURE_PATTERNS = (
    re.compile(r"\bHTTP 429\b|\b429\b.*rate|rate.*429", re.IGNORECASE),
    re.compile(r"\bHTTP 503\b|\b503\b.*(unavailable|overload)", re.IGNORECASE),
    re.compile(r"\bUsage limit reached\b|\bquota\b|\bcooldown\b", re.IGNORECASE),
    re.compile(r"\bRateLimitError\b|\bTimeoutError\b|\btimed?\s*out\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class OpenCodeResult:
    """One classified OpenCode invocation for Conduvera evidence."""

    status: str
    stdout_non_empty: bool
    exit_code: int
    model: str
    provider_hint: str = ""


def classify_opencode_result(
    *,
    model: str,
    stdout: str,
    exit_code: int,
    client_log: str = "",
) -> OpenCodeResult:
    """Classify one OpenCode run.

    ``stdout`` is the command's captured output; ``client_log`` is optional
    stderr / client log text that may carry a provider-failure fingerprint.
    """
    non_empty = bool(stdout and stdout.strip())
    provider_hint = ""
    for pat in _PROVIDER_FAILURE_PATTERNS:
        m = pat.search(client_log or "")
        if m:
            provider_hint = m.group(0)[:80]
            break
    if provider_hint:
        # A provider failure fingerprint wins over an empty/short output:
        # the client may have swallowed the 429 into empty stdout + exit 0.
        return OpenCodeResult(
            status=BLOCKED_EXTERNAL_PROVIDER,
            stdout_non_empty=non_empty,
            exit_code=exit_code,
            model=model,
            provider_hint=provider_hint,
        )
    if non_empty and exit_code == 0:
        return OpenCodeResult(
            status=SUCCESS, stdout_non_empty=True, exit_code=0, model=model,
        )
    if not non_empty and exit_code == 0:
        # Empty output + exit 0 is NEVER success.
        return OpenCodeResult(
            status=FAILED, stdout_non_empty=False, exit_code=0, model=model,
            provider_hint="empty stdout with exit 0 is not a success",
        )
    return OpenCodeResult(
        status=FAILED, stdout_non_empty=non_empty, exit_code=exit_code, model=model,
    )
