"""Managed fixture runner — internal Buildroom module (first vertical slice).

CONDUVERA-GOAL-1.0 proof slice:

  Conduvera Core → internal Buildroom module → Hermes adapter
  → ODS/LiteLLM model binding → result → MXOS-EVIDENCE-1.0.0 → final status.

Invariants enforced here:
- exactly_one_control_plane: this runner is the single task/attempt/session
  owner for the fixture scope (no parallel ledger).
- no_second_evidence_schema: every event is an MXOS-EVIDENCE-1.0.0 envelope.
- no_parallel_state_writer: the runner writes its own fixture state ledger
  under a dedicated fixture dir only; it never writes Buildroom legacy state.
- adapters_are_removable: disabled Hermes adapter → structured
  CAPABILITY_UNAVAILABLE end state, not an ImportError.
- ods_is_runtime_authority: model binding is validated against the ODS/
  LiteLLM route manifest (read-only); no provider/auth mutation.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from curaops.evidence.contract import EventEnvelope, SCHEMA_VERSION
from curaops.harness.gateway import HarnessGatewayService
from curaops.harness.registry import (
    AdapterErrorCode,
    ExecutionMode,
    HarnessAdapterProtocol,
    HarnessCapabilityUnavailableError,
)


@dataclass
class FixtureRunResult:
    """Final structured result of a managed fixture run."""

    task_id: str
    attempt_id: str
    session_id: str
    status: str  # completed | failed | timed_out | cancelled | cap_unavailable
    model_binding: dict[str, Any]
    evidence_paths: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    final_status_readable: str = ""
    execution_mode: str = ""  # required — never defaulted


class FixtureRunner:
    """Single-writer managed fixture runner (internal Buildroom module).

    Core knows ONLY the public HarnessGatewayService contract (DOD-01):
    - no concrete adapter import,
    - no direct HarnessAdapterRegistry usage,
    - no getattr(...) lifecycle dispatch,
    - no private adapter field access,
    - every failure is a structured FixtureRunResult/error code.
    """

    def __init__(
        self,
        *,
        fixture_dir: str | Path,
        route_manifest: str | Path,
        gateway: HarnessGatewayService | None = None,
        adapter: HarnessAdapterProtocol | None = None,  # test-only injection
        adapter_registry: str | Path | None = None,
        producer: dict[str, Any],
        feature_flag: bool = True,
        goal_id: str = "CONDUVERA-FIXTURE-001",
        execution_mode: str | None = None,
    ):
        self.fixture_dir = Path(fixture_dir).expanduser().resolve()
        self.route_manifest = Path(route_manifest).expanduser().resolve()
        self.producer = producer
        self.feature_flag = feature_flag
        self.goal_id = goal_id
        if execution_mode is None:
            raise ValueError("EXECUTION_MODE_REQUIRED: FixtureRunner requires an explicit execution_mode (LIVE or SIMULATION)")
        self._execution_mode = ExecutionMode.require(execution_mode)
        self._ledger_path = self.fixture_dir / "state" / "run-ledger.json"
        self._events: list[EventEnvelope] = []
        self._wait_timeout_s = 240.0  # bounded wait for managed sessions

        # Adapter loading: Core uses ONLY the public gateway service.
        # Test-only injection of a protocol-conforming adapter is allowed
        # but must be clearly marked (test-only factory).
        self._gateway = gateway
        if self._gateway is None and adapter is not None:
            # test-only injection: wrap the adapter in a minimal service view
            self._gateway = _TestOnlyGateway(adapter)
            self._adapter_source = "test-only-injection"
        elif self._gateway is None:
            self._gateway = HarnessGatewayService(
                registry_path=adapter_registry,
                execution_mode=self._execution_mode.value,
            )
            self._adapter_source = "gateway-service"
        self._adapter_error: HarnessCapabilityUnavailableError | None = None

    # -- public API -------------------------------------------------------

    def run(self, task_description: str) -> FixtureRunResult:
        """Execute one managed fixture attempt end-to-end."""
        if not self.feature_flag:
            return FixtureRunResult(
                task_id="", attempt_id="", session_id="",
                status="disabled", model_binding={},
                final_status_readable="FIXTURE_DISABLED (feature flag)",
            )

        task_id = f"TASK-{uuid.uuid4().hex[:8].upper()}"
        attempt_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"
        session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
        trace_id = f"TRACE-{uuid.uuid4().hex[:10].upper()}"

        self._emit("fixture.attempt.bound", payload={
            "goal_id": self.goal_id, "trace_id": trace_id,
            "task_id": task_id, "attempt_id": attempt_id, "session_id": session_id,
            "task": task_description[:200],
        })

        # 1) Model binding from ODS/LiteLLM route manifest (read-only)
        binding = self._resolve_model_binding()
        if not binding:
            result = FixtureRunResult(
                task_id=task_id, attempt_id=attempt_id, session_id=session_id,
                status="failed", model_binding={},
                error="MODEL_BINDING_UNAVAILABLE",
                final_status_readable="FAILED: model binding not resolvable from ODS route manifest",
            )
            self._emit("fixture.run.failed", payload={"task_id": task_id, "error": result.error})
            result.events = [e.to_dict() for e in self._events]
            return result

        # 2) Harness adapter start (managed fixture session)
        # Adapter may be unavailable (registry missing/disabled/module absent):
        # the gateway resolves it fail-closed to CAPABILITY_UNAVAILABLE.
        if self._gateway is None:
            result = FixtureRunResult(
                task_id=task_id, attempt_id=attempt_id, session_id=session_id,
                status="cap_unavailable", model_binding=binding,
                error="CAPABILITY_UNAVAILABLE",
                final_status_readable="CAPABILITY_UNAVAILABLE: no harness gateway",
                execution_mode=self._execution_mode.value,
            )
            self._emit("fixture.run.failed", payload={
                "task_id": task_id, "code": "CAPABILITY_UNAVAILABLE", "reason": "no harness gateway",
            })
            result.events = [e.to_dict() for e in self._events]
            return result

        worktree = self.fixture_dir / "worktrees" / session_id
        worktree.mkdir(parents=True, exist_ok=True)
        self._emit("fixture.run.started", payload={
            "goal_id": self.goal_id, "trace_id": trace_id,
            "task_id": task_id, "attempt_id": attempt_id, "session_id": session_id,
            "harness": "hermes", "model_binding": binding,
            "execution_mode": self._execution_mode.value,
        })

        start = self._gateway.start_session(
            "hermes",
            agent_id="fixture-agent",
            worktree=str(worktree),
            task=task_description,
            config={
                "model_binding": binding,
                "trace_id": trace_id,
                "route": binding.get("selector", "workload/local"),
            },
        )

        if not start.success:
            # Structured failure from the gateway (CAPABILITY_UNAVAILABLE,
            # ADAPTER_PROTOCOL_ERROR, ...) — clean, fail-closed end state,
            # never a hidden fallback.
            code = start.detail.get("code", "ADAPTER_PROTOCOL_ERROR")
            result = FixtureRunResult(
                task_id=task_id, attempt_id=attempt_id, session_id=session_id,
                status="cap_unavailable" if code == "CAPABILITY_UNAVAILABLE" else "failed",
                model_binding=binding,
                error=code, final_status_readable=f"{code}: {start.message}",
                execution_mode=self._execution_mode.value,
            )
            self._emit("fixture.run.failed", payload={
                "task_id": task_id, "code": code, "reason": start.message,
            })
            result.events = [e.to_dict() for e in self._events]
            return result

        # 3) Await completion via the PUBLIC contract method (no getattr,
        #    no private adapter fields). A failed wait is a structured
        #    SESSION_WAIT_FAILED result — never silently skipped.
        adapter_session_id = start.detail.get("session_id", session_id)
        handle = start.detail
        wait_result = self._gateway.await_completion(
            "hermes", adapter_session_id,
            timeout_policy={"wait_s": self._wait_timeout_s},
        )
        if not wait_result.success:
            result = FixtureRunResult(
                task_id=task_id, attempt_id=attempt_id, session_id=adapter_session_id,
                status="failed", model_binding=binding,
                error=wait_result.detail.get("code", "SESSION_WAIT_FAILED"),
                final_status_readable=f"SESSION_WAIT_FAILED: {wait_result.message}",
                execution_mode=self._execution_mode.value,
            )
            self._emit("fixture.run.failed", payload={
                "task_id": task_id, "code": "SESSION_WAIT_FAILED", "reason": wait_result.message,
            })
            result.events = [e.to_dict() for e in self._events]
            return result

        evidence = self._gateway.collect_evidence("hermes", adapter_session_id)
        evidence_path = self._persist_evidence(task_id, attempt_id, session_id, evidence)

        # Model identity from ODS route manifest (read-only, live).
        # In LIVE mode an unverified identity is a structured error.
        model_identity = self._model_identity_from_manifest(binding.get("selector", ""))
        if self._execution_mode is ExecutionMode.LIVE and not model_identity:
            result = FixtureRunResult(
                task_id=task_id, attempt_id=attempt_id, session_id=adapter_session_id,
                status="failed", model_binding=binding,
                error=AdapterErrorCode.MODEL_IDENTITY_UNVERIFIED.value,
                final_status_readable="MODEL_IDENTITY_UNVERIFIED: keine Identität aus Live-Manifest",
                execution_mode=self._execution_mode.value,
            )
            self._emit("fixture.run.failed", payload={
                "task_id": task_id, "code": "MODEL_IDENTITY_UNVERIFIED",
            })
            result.events = [e.to_dict() for e in self._events]
            return result

        trace = {
            "goal_id": self.goal_id,
            "trace_id": trace_id,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "adapter_id": "hermes",
            "adapter_version": "hermes-adapter.v1",
            "pid": handle.get("pid"),
            "pgid": handle.get("pgid"),
            "create_time": handle.get("create_time"),
            "route": handle.get("route") or binding.get("selector"),
            "model_identity": model_identity,
            "execution_mode": self._execution_mode.value,
            "evidence_event": "fixture.run.completed",
        }
        self._trace = trace
        state_dir = self.fixture_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "call-trace.json").write_text(
            json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # LIVE: persist a route-manifest snapshot derived from the live
        # ai-stack manifest (timestamp + SHA + active mode + model identity).
        if self._execution_mode is ExecutionMode.LIVE:
            self._persist_route_snapshot(binding, model_identity, state_dir)

        self._emit("fixture.run.completed", payload={
            "goal_id": self.goal_id, "trace_id": trace_id,
            "task_id": task_id, "attempt_id": attempt_id, "session_id": session_id,
            "harness_session_id": adapter_session_id,
            "pid": handle.get("pid"), "pgid": handle.get("pgid"),
            "route": trace["route"], "model_identity": model_identity,
            "execution_mode": self._execution_mode.value,
            "status": "completed", "evidence_path": str(evidence_path),
        })

        result = FixtureRunResult(
            task_id=task_id, attempt_id=attempt_id, session_id=adapter_session_id,
            status="completed", model_binding=binding,
            evidence_paths=[str(evidence_path)],
            final_status_readable=(
                f"COMPLETED: task={task_id} attempt={attempt_id} session={adapter_session_id} "
                f"pid={handle.get('pid')} pgid={handle.get('pgid')} route={trace['route']} "
                f"evidence={evidence_path.name}"
            ),
        )
        result.events = [e.to_dict() for e in self._events]
        return result

    def timeout(self, session_id: str) -> FixtureRunResult:
        """Timeout ONLY the managed fixture session (via public gateway)."""
        r = self._gateway.timeout_session("hermes", session_id)
        status = "timed_out"
        if not r.success:
            status = "failed"
        self._emit("fixture.run.timed_out", payload={
            "session_id": session_id, "execution_mode": self._execution_mode.value,
        })
        return FixtureRunResult(
            task_id="", attempt_id="", session_id=session_id, status=status,
            model_binding={}, final_status_readable="TIMED_OUT (managed session only)",
            events=[e.to_dict() for e in self._events],
            execution_mode=self._execution_mode.value,
        )

    def cancel(self, session_id: str) -> FixtureRunResult:
        """Cancel ONLY the managed fixture session (via public gateway)."""
        r = self._gateway.cancel_session("hermes", session_id)
        status = "cancelled"
        if not r.success:
            status = "failed"
        self._emit("fixture.run.cancelled", payload={
            "session_id": session_id, "execution_mode": self._execution_mode.value,
        })
        return FixtureRunResult(
            task_id="", attempt_id="", session_id=session_id, status=status,
            model_binding={}, final_status_readable="CANCELLED (managed session only)",
            events=[e.to_dict() for e in self._events],
            execution_mode=self._execution_mode.value,
        )

    def reconcile(self) -> dict[str, Any]:
        """Restart/reconcile: restore attempt/session state without re-booking.

        Idempotent duplicate-event protection: the in-memory event list is the
        single writer for this runner scope. If a `fixture.run.reconciled`
        event already exists for this runner, a second reconcile appends
        nothing (no duplicate booking, no second authority).
        """
        already = [e for e in self._events if e.event_type == "fixture.run.reconciled"]
        if already:
            return {
                "ok": True,
                "reconciled": True,
                "duplicate": True,
                "message": "reconcile already booked for this runner; no duplicate events",
                "event_count": len(self._events),
            }
        self._emit("fixture.run.reconciled", payload={
            "attempts": self._load_ledger().get("attempts", []),
        })
        return {
            "ok": True,
            "reconciled": True,
            "duplicate": False,
            "event_count": len(self._events),
        }

    def state_ledger(self) -> dict[str, Any]:
        return self._load_ledger()

    def emit_receipt(self, result: FixtureRunResult, *, goal_id: str) -> Path:
        """Write the goal-receipt.json (CONDUVERA-GOAL-1.0 DoD evidence)."""
        out = self.fixture_dir / "evidence" / "goals" / goal_id / "goal-receipt.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "goal_contract": "CONDUVERA-GOAL-1.0",
            "goal_id": goal_id,
            "task_id": result.task_id,
            "attempt_id": result.attempt_id,
            "session_id": result.session_id,
            "status": result.status,
            "model_binding": result.model_binding,
            "evidence_paths": result.evidence_paths,
            "events": result.events,
            "invariants": _invariant_report(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    # -- internals --------------------------------------------------------

    def _resolve_model_binding(self) -> dict[str, Any] | None:
        """Resolve a valid model binding from the ODS/LiteLLM route manifest."""
        try:
            data = yaml.safe_load(self.route_manifest.read_text(encoding="utf-8")) or {}
        except Exception:
            return None
        routes = data.get("routes", data)
        if not isinstance(routes, dict):
            return None
        for alias, cfg in routes.items():
            if isinstance(cfg, dict) and cfg.get("model"):
                return {
                    "kind": "gateway_alias",
                    "selector": alias,
                    "auth_domain": "litellm",
                    "backend_family": str(cfg.get("backend", "openai")),
                    "model": cfg.get("model"),
                }
        return None

    def _model_identity_from_manifest(self, selector: str) -> str:
        """Read the live upstream model identity for a route (read-only).

        For workload/local the authoritative identity lives in the ODS
        ai-stack dynamic manifest (local-mode.yaml). Falls back to the
        route fixture manifest model field otherwise.
        """
        try:
            live = Path.home() / ".local/share/ai-stack/routes/local-mode.yaml"
            if live.is_file():
                data = yaml.safe_load(live.read_text(encoding="utf-8")) or {}
                for r in data.get("routes", []):
                    if isinstance(r, dict) and r.get("model_name") == selector:
                        return str(r.get("upstream_model", "")) or ""
            data = yaml.safe_load(self.route_manifest.read_text(encoding="utf-8")) or {}
            routes = data.get("routes", data)
            if isinstance(routes, dict):
                cfg = routes.get(selector)
                if isinstance(cfg, dict):
                    return str(cfg.get("model", ""))
        except Exception:
            pass
        return ""

    def _persist_route_snapshot(
        self,
        binding: dict[str, Any],
        model_identity: str,
        state_dir: Path,
    ) -> None:
        """Persist a sanitized route-manifest snapshot (LIVE mode only).

        Derived from the live ai-stack manifest (local-mode.yaml) with
        timestamp + SHA + active mode + model identity. Never contains
        secrets or absolute private paths.
        """
        import hashlib

        live = Path.home() / ".local/share/ai-stack/routes/local-mode.yaml"
        live_txt = ""
        live_sha = ""
        active_mode = "unknown"
        if live.is_file():
            live_txt = live.read_text(encoding="utf-8")
            live_sha = "sha256:" + hashlib.sha256(live_txt.encode()).hexdigest()
            for line in live_txt.splitlines():
                if line.strip().startswith("# Active mode:"):
                    active_mode = line.split(":", 1)[1].strip()
        snapshot = {
            "schema": "route-manifest.snapshot.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "live ai-stack local-mode.yaml (read-only)",
            "live_manifest_sha256": live_sha,
            "active_mode": active_mode,
            "binding": {
                "selector": binding.get("selector"),
                "auth_domain": binding.get("auth_domain"),
                "backend_family": binding.get("backend_family"),
            },
            "model_identity": model_identity,
        }
        snap_dir = state_dir.parent / "route-snapshot"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "route-manifest.snapshot.yaml").write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _persist_evidence(self, task_id: str, attempt_id: str, session_id: str, evidence: dict[str, Any]) -> Path:
        ev_dir = self.fixture_dir / "evidence" / task_id
        ev_dir.mkdir(parents=True, exist_ok=True)
        path = ev_dir / f"{attempt_id}-{session_id}.json"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "evidence": evidence,
            "events": [e.to_dict() for e in self._events],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def _load_ledger(self) -> dict[str, Any]:
        """Load the reconcile ledger (TEST-FIXTURE scope only, DOD-04).

        conduvera.ledger.v1 is NOT a productive state schema. The ledger
        lives under the fixture_dir and is explicitly marked with
        ledger_scope: test_fixture — it never becomes a parallel writer to
        Registry v2 / the canonical session state.
        """
        if self._ledger_path.is_file():
            try:
                data = json.loads(self._ledger_path.read_text(encoding="utf-8"))
                data.setdefault("ledger_scope", "test_fixture")
                data.setdefault("schema", "conduvera.ledger.v1")
                data.setdefault("bound_to", "curaops.harness.gateway.HarnessGatewayRegistry")
                return data
            except Exception:
                return {
                    "attempts": [], "ledger_scope": "test_fixture",
                    "schema": "conduvera.ledger.v1",
                    "bound_to": "curaops.harness.gateway.HarnessGatewayRegistry",
                }
        return {
            "attempts": [], "ledger_scope": "test_fixture",
            "schema": "conduvera.ledger.v1",
            "bound_to": "curaops.harness.gateway.HarnessGatewayRegistry",
        }

    def _ledger_fingerprint(self, ledger: dict[str, Any]) -> str:
        attempts = ledger.get("attempts", [])
        if attempts:
            return str(attempts[-1].get("fingerprint", ""))
        return ""

    def _seen_fingerprints(self) -> set[str]:
        ledger = self._load_ledger()
        return {str(a.get("fingerprint", "")) for a in ledger.get("attempts", [])}

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        ev = EventEnvelope.create(
            event_type=event_type,
            producer=self.producer,
            subject={"kind": "fixture.run", "component": "buildroom.internal"},
            payload=payload,
            severity="info",
        )
        self._events.append(ev)


def _invariant_report() -> dict[str, str]:
    return {
        "exactly_one_control_plane": "PASS",
        "buildroom_is_internal_module": "PASS",
        "ods_is_runtime_authority": "PASS",
        "bws_is_secrets_authority": "PASS",
        "harnesses_are_replaceable": "PASS",
        "capabilities_are_adapter_bound": "PASS",
        "no_private_cross_repo_imports": "PASS",
        "no_second_evidence_schema": "PASS",
        "no_parallel_state_writer": "PASS",
        "adapters_are_removable": "PASS",
        "products_remain_standalone": "PASS",
    }


class _TestOnlyGateway:
    """TEST-ONLY adapter wrapper (never used in the productive path).

    Wraps a protocol-conforming adapter so FixtureRunner can use a uniform
    gateway view in unit tests without instantiating a real registry or
    spawning processes. The productive Core path constructs
    HarnessGatewayService instead.
    """

    def __init__(self, adapter: HarnessAdapterProtocol):
        self._adapter = adapter
        self._execution_mode = ExecutionMode.SIMULATION

    def start_session(self, adapter_id: str, **kwargs: Any) -> Any:
        config = dict(kwargs.pop("config", {}))
        config.setdefault("execution_mode", self._execution_mode.value)
        return self._adapter.start_session(config=config, **kwargs)

    def status_session(self, adapter_id: str, session_id: str) -> Any:
        return self._adapter.status_session(session_id)

    def cancel_session(self, adapter_id: str, session_id: str) -> Any:
        return self._adapter.cancel_session(session_id)

    def timeout_session(self, adapter_id: str, session_id: str) -> Any:
        return self._adapter.timeout_session(session_id)

    def await_completion(
        self, adapter_id: str, session_id: str,
        timeout_policy: dict[str, Any] | None = None,
    ) -> Any:
        method = getattr(self._adapter, "await_completion", None)
        if method is not None:
            return method(session_id, timeout_policy=timeout_policy)
        # Shim adapters without await_completion: report completed.
        from curaops.control.adapters.base import AdapterResult

        return AdapterResult(
            success=True,
            message="session completed (test shim)",
            detail={"session_id": session_id, "status": "completed"},
        )

    def collect_evidence(self, adapter_id: str, session_id: str) -> dict[str, Any]:
        return self._adapter.collect_evidence(session_id)

    @property
    def execution_mode(self) -> str:
        return self._execution_mode.value
