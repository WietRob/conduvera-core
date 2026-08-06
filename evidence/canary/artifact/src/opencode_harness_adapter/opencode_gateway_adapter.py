"""Conduvera harness gateway adapter contract for the OpenCode wrapper
(goal close-the-true-provider-lifecycle-e2e, Arbeit 4).

Conduvera Core and Hermes are separate repositories — integration happens
ONLY through this explicit adapter contract, never by importing Conduvera
internals. The contract mirrors the public ``HarnessAdapterProtocol``
(hermes-adapter.v1 compatible) so the Conduvera Harness Gateway can load the
OpenCode capability through its versioned registry entry point.

A normal gateway call flows:

    Conduvera Core -> Harness Gateway Registry -> OpenCode Adapter
    -> invoke_opencode -> structured result

The registry entry (``harness-registry.yaml``) points at the entry point
``OpenCodeHarnessAdapter`` in this module. The adapter itself delegates to
the existing production wrapper :func:`hermes_cli.opencode_harness.invoke_opencode`
— no second wrapper.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from opencode_harness_adapter.opencode_harness import OpenCodeHarnessResult, invoke_opencode


@dataclass(frozen=True)
class AdapterResult:
    """Minimal adapter result shape (Conduvera AdapterResult-compatible)."""

    ok: bool
    status: str
    detail: dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenCodeHarnessAdapter:
    """Versioned adapter entry point (``opencode-adapter.v1``).

    Exposes the OpenCode harness capability through the Conduvera gateway
    contract: ``health_check``, ``start_session`` (one-shot invocation),
    ``collect_evidence`` (structured result). Never imports Conduvera
    internals — the gateway calls these methods by name.
    """

    name = "opencode"
    adapter_version = "opencode-adapter.v1"
    contract = "CONDUVERA-GOAL-1.0"

    def __init__(self, *, binary: str = "opencode", timeout_s: int = 150) -> None:
        self.binary = binary
        self.timeout_s = timeout_s

    # -- HarnessAdapterProtocol surface ------------------------------------

    def health_check(self) -> AdapterResult:
        try:
            result = invoke_opencode(
                "PONG",
                model="litellm/provider/openai/gpt-5.6-sol",
                binary=self.binary,
                timeout_s=self.timeout_s,
            )
            ok = result.status == "SUCCESS" and result.stdout_non_empty
            return AdapterResult(
                ok=ok,
                status="healthy" if ok else "unhealthy",
                detail={
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "stdout_non_empty": result.stdout_non_empty,
                },
                error=None if ok else "opencode probe did not return SUCCESS",
            )
        except Exception as exc:  # noqa: BLE001 -- adapter boundary
            return AdapterResult(
                ok=False,
                status="unhealthy",
                detail={},
                error=str(exc),
            )

    def start_session(
        self,
        agent_id: str,
        worktree: str,
        task: str,
        config: dict[str, Any],
    ) -> AdapterResult:
        """One-shot OpenCode invocation (no long-running session)."""
        try:
            model = config.get("model") or "litellm/provider/openai/gpt-5.6-sol"
            result = invoke_opencode(
                task,
                model=model,
                binary=self.binary,
                timeout_s=self.timeout_s,
            )
            return AdapterResult(
                ok=True,
                status="completed",
                detail={
                    "session_id": f"opencode-{agent_id}-{worktree}",
                    "result_status": result.status,
                    "exit_code": result.exit_code,
                    "stdout_non_empty": result.stdout_non_empty,
                    "provider_hint": result.provider_hint,
                },
            )
        except Exception as exc:  # noqa: BLE001 -- adapter boundary
            return AdapterResult(
                ok=False,
                status="failed",
                detail={},
                error=str(exc),
            )

    def status_session(self, session_id: str) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="completed",
            detail={"session_id": session_id, "note": "one-shot adapter"},
        )

    def cancel_session(self, session_id: str) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="cancelled",
            detail={"session_id": session_id, "note": "one-shot adapter"},
        )

    def timeout_session(self, session_id: str) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="timed_out",
            detail={"session_id": session_id, "note": "one-shot adapter"},
        )

    def await_completion(
        self, session_id: str, timeout_policy: Optional[dict[str, Any]] = None
    ) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="completed",
            detail={"session_id": session_id, "note": "one-shot adapter"},
        )

    def collect_evidence(self, session_id: str) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "version": self.adapter_version,
            "session_id": session_id,
            "format": "opencode-harness.v1",
        }


# -- Registry entry point (harness-registry.yaml -> entry_point) -----------

def entry_point() -> OpenCodeHarnessAdapter:
    """Factory the Conduvera registry calls to instantiate the adapter."""
    return OpenCodeHarnessAdapter()
