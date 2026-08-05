"""Managed Buildroom execution caller — internal Conduvera Core module.

Integrates the three reviewed helper modules (task_binding, backend_policy,
no_progress) into ONE real, production-near Buildroom caller, proving the
full path:

  Task → TaskBinding → Backend-Policy → HarnessGatewayService → Hermes
  → LiteLLM → Evidence → Reconciliation → No-Progress-Decision

MANDATORY ORDER (enforced by this module):
1. Validate task input.
2. Create TaskBinding and store it in the canonical state.
3. Read the binding back from state and verify identity.
4. Check backend policy.
5. Block BEFORE any spawn when the backend is disabled or unknown.
6. Start a MANAGED Hermes session via HarnessGatewayService.
7. Hermes uses the existing LiteLLM path.
8. Capture result and MXOS-EVIDENCE.
9. Run reconciliation with no_progress.
10. Persist state, evidence and terminal status consistently.

BOUNDARIES:
- Conduvera Core stays the single task/state/policy/evidence authority.
- Buildroom stays an internal Conduvera Core module.
- HarnessGatewayService stays the single harness-lifecycle boundary.
- LiteLLM stays the model gateway; ODS/ai-stack stays the runtime/GPU/
  service authority; BWS stays the secrets authority.
- No second state store, no second registry, no new evidence schema,
  no implicit GPU-mode switch.

The three helpers are used through their PUBLIC contracts only — no copied
or re-invented parallel semantics (DOD-02).
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, MutableMapping

import yaml

from curaops.buildroom.backend_policy import (
    BackendPolicyError,
    require_backend_enabled,
)
from curaops.buildroom.no_progress import NoProgressResult, observe_reconciliation
from curaops.buildroom.task_binding import (
    TaskBinding,
    binding_for_phase,
    store_task_binding,
)
from curaops.evidence.contract import EventEnvelope, SCHEMA_VERSION
from curaops.harness.gateway import HarnessGatewayService
from curaops.harness.registry import (
    ExecutionMode,
    HarnessAdapterProtocol,
)

DEFAULT_PHASE = "BUILDER"
DEFAULT_BOARD = "conduvera"
DEFAULT_BACKEND = "native"


@dataclass
class ManagedExecutionResult:
    """Final structured result of one managed Buildroom execution."""

    task_id: str
    phase: str
    attempt_id: str
    session_id: str
    status: str  # completed | policy_blocked | failed | cap_unavailable | hold
    policy_decision: dict[str, Any]
    model_binding: dict[str, Any]
    reconciliation: dict[str, Any]
    evidence_paths: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    final_status_readable: str = ""
    execution_mode: str = ""  # required — never defaulted


class ManagedBuildroomCaller:
    """Production-near Buildroom caller integrating the three reviewed helpers.

    Uses ONLY the public contracts of task_binding / backend_policy /
    no_progress and the public HarnessGatewayService lifecycle. No concrete
    adapter, no registry access, no private field access.
    """

    def __init__(
        self,
        *,
        state_path: str | Path,
        route_manifest: str | Path,
        gateway: HarnessGatewayService | None = None,
        adapter: HarnessAdapterProtocol | None = None,  # test-only injection
        adapter_registry: str | Path | None = None,
        producer: dict[str, Any],
        goal_id: str = "CONDUVERA-FIXTURE-001",
        execution_mode: str | None = None,
        policy_path: str | Path | None = None,
        threshold: int = 3,
    ):
        if execution_mode is None:
            raise ValueError(
                "EXECUTION_MODE_REQUIRED: ManagedBuildroomCaller requires an explicit execution_mode (LIVE or SIMULATION)"
            )
        self._execution_mode = ExecutionMode.require(execution_mode)
        self.state_path = Path(state_path).expanduser().resolve()
        self.route_manifest = Path(route_manifest).expanduser().resolve()
        self.producer = producer
        self.goal_id = goal_id
        self._policy_path = policy_path
        self._threshold = threshold
        self._wait_timeout_s = 240.0
        self._gateway = gateway
        if self._gateway is None and adapter is not None:
            self._gateway = _TestOnlyGateway(adapter)
        elif self._gateway is None:
            self._gateway = HarnessGatewayService(
                registry_path=adapter_registry,
                execution_mode=self._execution_mode.value,
            )
        self._events: list[EventEnvelope] = []
        self._state: MutableMapping[str, Any] = {}

    # -- public API -------------------------------------------------------

    def load_state(self) -> MutableMapping[str, Any]:
        if self.state_path.is_file():
            self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
        else:
            self._state = {}
        return self._state

    def persist_state(self) -> Path:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return self.state_path

    def execute(
        self,
        *,
        task_description: str,
        phase: str = DEFAULT_PHASE,
        board: str = DEFAULT_BOARD,
        cycle: int | None = None,
        task_id: str | None = None,
        backend: str = DEFAULT_BACKEND,
        evidence_fingerprint: str = "",
        log_fingerprint: str = "",
        worktree_root: str | Path | None = None,
    ) -> ManagedExecutionResult:
        """Run the full mandatory order (1-10)."""
        if not task_description or not task_description.strip():
            raise ValueError("TASK_DESCRIPTION_REQUIRED")
        if cycle is None:
            cycle = int(self._state.get("cycle", 1) or 1)

        # 1) Task entry validation
        # 2) Create TaskBinding and store in canonical state
        #    (task_id defaults to a valid t_[hex] id)
        binding_task_id = task_id or f"t_{uuid.uuid4().hex[:8]}"
        binding = TaskBinding(
            task_id=binding_task_id,
            board=board,
            phase=phase,
            cycle=cycle,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        store_task_binding(self._state, binding)

        # 3) Read the binding back from state and verify identity
        reloaded = binding_for_phase(self._state, phase)
        if reloaded is None or reloaded.task_id != binding_task_id or reloaded.board != board:
            return self._fail_result(
                task_id=binding_task_id, phase=phase, error="TASK_BINDING_IDENTITY_MISMATCH",
                binding=binding, reason="Binding-Identität nach Store/Reload nicht verifizierbar",
            )
        attempt_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"
        session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
        trace_id = f"TRACE-{uuid.uuid4().hex[:10].upper()}"

        self._emit("buildroom.attempt.bound", payload={
            "goal_id": self.goal_id, "trace_id": trace_id,
            "task_id": binding_task_id, "attempt_id": attempt_id, "session_id": session_id,
            "binding": binding.to_dict(), "phase": phase, "cycle": cycle,
        })

        # 4) Backend policy check — MANDATORY before any spawn
        try:
            policy = require_backend_enabled(backend, policy_path=self._policy_path or backend_policy_default_path())
            policy_decision = {"backend": backend, "decision": "ALLOWED", "policy": policy}
        except BackendPolicyError as exc:
            # 5) Block BEFORE any spawn; no PID/PGID, no partial attempt.
            reason = str(exc)
            if reason.startswith("BACKEND_DISABLED_BY_OWNER"):
                decision = "BACKEND_DISABLED_BY_OWNER"
            elif reason.startswith("UNKNOWN_BACKEND"):
                decision = "UNKNOWN_BACKEND"
            else:
                decision = "EXECUTION_BACKEND_POLICY_INVALID"
            policy_decision = {"backend": backend, "decision": decision, "detail": reason}
            result = ManagedExecutionResult(
                task_id=binding_task_id, phase=phase, attempt_id=attempt_id, session_id="",
                status="policy_blocked", policy_decision=policy_decision, model_binding={},
                reconciliation={}, execution_mode=self._execution_mode.value,
                final_status_readable=f"BLOCKED: {reason} (kein Spawn)",
            )
            self._emit("buildroom.attempt.policy_blocked", payload={
                "goal_id": self.goal_id, "task_id": binding_task_id,
                "backend": backend, "decision": decision, "detail": reason,
            })
            result.events = [e.to_dict() for e in self._events]
            self.persist_state()
            return result

        # 6) Model binding from ODS/LiteLLM route manifest (read-only)
        binding_cfg = self._resolve_model_binding()
        if not binding_cfg:
            result = self._fail_result(
                task_id=binding_task_id, phase=phase, error="MODEL_BINDING_UNAVAILABLE",
                binding=binding, reason="keine Modell-Route aus ODS/LiteLLM-Manifest",
                policy_decision=policy_decision, attempt_id=attempt_id,
            )
            self.persist_state()
            return result

        # 7) Managed Hermes session via HarnessGatewayService
        if self._gateway is None:
            self._gateway = HarnessGatewayService(
                execution_mode=self._execution_mode.value,
            )
        worktree_root = Path(worktree_root) if worktree_root else self.state_path.parent / "worktrees"
        worktree = worktree_root / session_id
        worktree.mkdir(parents=True, exist_ok=True)

        self._emit("buildroom.attempt.started", payload={
            "goal_id": self.goal_id, "trace_id": trace_id,
            "task_id": binding_task_id, "attempt_id": attempt_id, "session_id": session_id,
            "harness": "hermes", "backend": backend, "model_binding": binding_cfg,
            "execution_mode": self._execution_mode.value,
        })

        start = self._gateway.start_session(
            "hermes",
            agent_id="buildroom-agent",
            worktree=str(worktree),
            task=task_description,
            config={
                "model_binding": binding_cfg,
                "trace_id": trace_id,
                "route": binding_cfg.get("selector", "workload/local"),
            },
        )
        if not start.success:
            code = start.detail.get("code", "ADAPTER_PROTOCOL_ERROR")
            result = ManagedExecutionResult(
                task_id=binding_task_id, phase=phase, attempt_id=attempt_id,
                session_id=start.detail.get("session_id", ""),
                status="cap_unavailable" if code == "CAPABILITY_UNAVAILABLE" else "failed",
                policy_decision=policy_decision, model_binding=binding_cfg,
                reconciliation={}, error=code,
                final_status_readable=f"{code}: {start.message}",
                execution_mode=self._execution_mode.value,
            )
            self._emit("buildroom.attempt.failed", payload={
                "task_id": binding_task_id, "code": code, "reason": start.message,
            })
            result.events = [e.to_dict() for e in self._events]
            self.persist_state()
            return result

        adapter_session_id = start.detail.get("session_id", session_id)
        handle = start.detail

        # Await completion via the public contract method
        wait_result = self._gateway.await_completion(
            "hermes", adapter_session_id, timeout_policy={"wait_s": self._wait_timeout_s},
        )
        if not wait_result.success:
            result = ManagedExecutionResult(
                task_id=binding_task_id, phase=phase, attempt_id=attempt_id,
                session_id=adapter_session_id, status="failed",
                policy_decision=policy_decision, model_binding=binding_cfg,
                reconciliation={},
                error=wait_result.detail.get("code", "SESSION_WAIT_FAILED"),
                final_status_readable=f"SESSION_WAIT_FAILED: {wait_result.message}",
                execution_mode=self._execution_mode.value,
            )
            self._emit("buildroom.attempt.failed", payload={
                "task_id": binding_task_id, "code": "SESSION_WAIT_FAILED",
            })
            result.events = [e.to_dict() for e in self._events]
            self.persist_state()
            return result

        # 8) Capture result + MXOS-EVIDENCE
        evidence = self._gateway.collect_evidence("hermes", adapter_session_id)
        model_identity = self._model_identity_from_manifest(binding_cfg.get("selector", ""))
        if self._execution_mode is ExecutionMode.LIVE and not model_identity:
            result = ManagedExecutionResult(
                task_id=binding_task_id, phase=phase, attempt_id=attempt_id,
                session_id=adapter_session_id, status="failed",
                policy_decision=policy_decision, model_binding=binding_cfg,
                reconciliation={}, error="MODEL_IDENTITY_UNVERIFIED",
                final_status_readable="MODEL_IDENTITY_UNVERIFIED: keine Identität aus Live-Manifest",
                execution_mode=self._execution_mode.value,
            )
            self._emit("buildroom.attempt.failed", payload={
                "task_id": binding_task_id, "code": "MODEL_IDENTITY_UNVERIFIED",
            })
            result.events = [e.to_dict() for e in self._events]
            self.persist_state()
            return result

        evidence_path = self._persist_evidence(binding_task_id, attempt_id, adapter_session_id, evidence)
        trace = {
            "goal_id": self.goal_id, "trace_id": trace_id,
            "task_id": binding_task_id, "attempt_id": attempt_id, "session_id": adapter_session_id,
            "adapter_id": "hermes", "pid": handle.get("pid"), "pgid": handle.get("pgid"),
            "create_time": handle.get("create_time"),
            "route": handle.get("route") or binding_cfg.get("selector"),
            "model_identity": model_identity,
            "execution_mode": self._execution_mode.value,
            "evidence_event": "buildroom.run.completed",
        }
        self._state["call_trace"] = trace
        state_dir = self.state_path.parent / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "call-trace.json").write_text(
            json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 9) Reconciliation with no_progress
        reconciliation = observe_reconciliation(
            self._state,
            phase=phase, status="WAITING", blocker="TASK_DONE_BUT_NO_EVIDENCE"
            if not evidence_fingerprint else "",
            task_id=binding_task_id, task_board=board,
            evidence_fingerprint=evidence_fingerprint,
            log_fingerprint=log_fingerprint,
            threshold=self._threshold,
        )
        recon = _reconcil_dict(reconciliation)

        # 10) Terminal status
        hold = recon["terminal_hold"]
        status = "hold" if hold else "completed"
        self._emit("buildroom.run.completed", payload={
            "goal_id": self.goal_id, "task_id": binding_task_id,
            "attempt_id": attempt_id, "session_id": adapter_session_id,
            "pid": handle.get("pid"), "pgid": handle.get("pgid"),
            "route": trace["route"], "model_identity": model_identity,
            "reconciliation": recon, "status": status,
            "evidence_path": str(evidence_path),
        })

        result = ManagedExecutionResult(
            task_id=binding_task_id, phase=phase, attempt_id=attempt_id,
            session_id=adapter_session_id, status=status,
            policy_decision=policy_decision, model_binding=binding_cfg,
            reconciliation=recon, evidence_paths=[str(evidence_path)],
            final_status_readable=(
                f"{'HOLD_FOR_BOSS' if hold else 'COMPLETED'}: task={binding_task_id} "
                f"attempt={attempt_id} session={adapter_session_id} pid={handle.get('pid')} "
                f"route={trace['route']} model={model_identity} "
                f"no_progress={recon['count']}/{self._threshold}"
            ),
            execution_mode=self._execution_mode.value,
        )
        result.events = [e.to_dict() for e in self._events]
        self.persist_state()
        return result

    # -- internals ---------------------------------------------------------

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._events.append(EventEnvelope.create(
            event_type=event_type,
            producer=self.producer,
            subject={"kind": "buildroom.managed.execution", "goal_id": self.goal_id},
            payload=payload,
        ))

    def _fail_result(
        self, *, task_id: str, phase: str, error: str, binding: TaskBinding,
        reason: str, policy_decision: dict[str, Any] | None = None,
        attempt_id: str = "", session_id: str = "",
    ) -> ManagedExecutionResult:
        self._emit("buildroom.attempt.failed", payload={
            "task_id": task_id, "code": error, "reason": reason,
        })
        return ManagedExecutionResult(
            task_id=task_id, phase=phase, attempt_id=attempt_id, session_id=session_id,
            status="failed", policy_decision=policy_decision or {"decision": "N/A"},
            model_binding={}, reconciliation={}, error=error,
            final_status_readable=f"FAILED: {error} ({reason})",
            execution_mode=self._execution_mode.value,
        )

    def _resolve_model_binding(self) -> dict[str, Any] | None:
        try:
            data = yaml.safe_load(self.route_manifest.read_text(encoding="utf-8")) or {}
        except Exception:
            return None
        routes = data.get("routes", data)
        # Format 1: dict (Fixture: routes -> {alias: {model, backend}})
        if isinstance(routes, dict):
            for alias, cfg in routes.items():
                if isinstance(cfg, dict) and cfg.get("model"):
                    return {
                        "kind": "gateway_alias", "selector": alias,
                        "auth_domain": "litellm", "backend_family": str(cfg.get("backend", "openai")),
                        "model": cfg.get("model"),
                    }
        # Format 2: Liste (installierter ai-stack local-mode.yaml:
        # routes -> [{model_name, upstream_model, api_base, ...}])
        if isinstance(routes, list):
            for r in routes:
                if isinstance(r, dict) and r.get("upstream_model") and r.get("model_name"):
                    return {
                        "kind": "gateway_alias", "selector": str(r["model_name"]),
                        "auth_domain": "litellm",
                        "backend_family": "openai",
                        "model": str(r["upstream_model"]),
                        "api_base": str(r.get("api_base", "")),
                    }
        return None

    def _model_identity_from_manifest(self, selector: str) -> str:
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

    def _persist_evidence(
        self, task_id: str, attempt_id: str, session_id: str, evidence: dict[str, Any],
    ) -> Path:
        out_dir = self.state_path.parent / "evidence"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"mxos-evidence-{attempt_id}.json"
        doc = {
            "schema": "MXOS-EVIDENCE-1.0.0",
            "goal_id": self.goal_id,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "session_id": session_id,
            "harness": "hermes",
            "producer": self.producer,
            "evidence": evidence,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def backend_policy_default_path() -> str | Path:
    from curaops.buildroom.backend_policy import POLICY_PATH

    return POLICY_PATH


class _TestOnlyGateway:
    """TEST-ONLY adapter wrapper (never used in the productive path).

    Wraps a protocol-conforming adapter so ManagedBuildroomCaller can use a
    uniform gateway view in unit tests without instantiating a real registry
    or spawning processes. The productive Core path constructs
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


def _reconcil_dict(r: NoProgressResult) -> dict[str, Any]:
    return {"count": r.count, "terminal_hold": r.terminal_hold,
            "fingerprint": list(r.fingerprint)}
