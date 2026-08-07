"""Generic Matrix OS Harness/Gateway boundary descriptors.

The gateway contract is declarative. It describes future runners, tools, editor
surfaces, and capabilities without launching runtimes, opening sockets,
registering MCP tools, executing shell commands, or mutating external projects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conduvera.control.adapters.base import AdapterResult
from conduvera.harness.registry import AdapterErrorCode, ExecutionMode


@dataclass(frozen=True)
class GatewayCapability:
    """A generic Matrix OS harness capability boundary."""

    capability_id: str
    name: str
    owned_by_matrix_os: str
    external_boundary: str
    runtime_implemented: bool


@dataclass(frozen=True)
class RunnerDescriptor:
    """Future runner family Matrix OS may describe or launch through later adapters."""

    runner_id: str
    name: str
    runner_family: str
    execution_status: str
    runtime_enabled: bool
    observable_events: tuple[str, ...]
    external_boundary: str


@dataclass(frozen=True)
class ToolDescriptor:
    """Future or current tool/producer family Matrix OS may observe or gate."""

    tool_id: str
    name: str
    tool_family: str
    can_launch: bool
    can_observe: bool
    can_block: bool
    can_emit_evidence: bool
    execution_status: str
    external_boundary: str


@dataclass(frozen=True)
class EditorSurfaceDescriptor:
    """Editor or UI surface boundary for Matrix OS harness views."""

    surface_id: str
    name: str
    owner: str
    source_paths: tuple[str, ...]
    future_attach_points: tuple[str, ...]
    runtime_status: str


_GATEWAY_CAPABILITIES: tuple[GatewayCapability, ...] = (
    GatewayCapability(
        capability_id="launch",
        name="Launch future runner",
        owned_by_matrix_os="descriptor only",
        external_boundary="actual runner execution remains adapter-owned and future-reviewed",
        runtime_implemented=False,
    ),
    GatewayCapability(
        capability_id="observe",
        name="Observe runner/tool output",
        owned_by_matrix_os="evidence contract",
        external_boundary="producers remain standalone; Matrix OS accepts explicit translated events only",
        runtime_implemented=False,
    ),
    GatewayCapability(
        capability_id="approve_block",
        name="Approve or block proposed action",
        owned_by_matrix_os="policy decision boundary only",
        external_boundary="no automatic enforcement or shell interception in this contract",
        runtime_implemented=False,
    ),
    GatewayCapability(
        capability_id="convert_evidence",
        name="Convert external output into Matrix OS evidence",
        owned_by_matrix_os="translation adapter contract",
        external_boundary="adapters are narrow, fail-closed, and do not execute external projects",
        runtime_implemented=False,
    ),
)

_RUNNERS: tuple[RunnerDescriptor, ...] = (
    RunnerDescriptor(
        runner_id="hermes",
        name="Hermes Agent Runner",
        runner_family="agent-orchestrator",
        execution_status="future-adapter-contract-only",
        runtime_enabled=False,
        observable_events=("agent.run.started", "agent.run.completed", "agent.run.failed"),
        external_boundary="standalone; future runner adapter only; not executed by Matrix OS",
    ),
    RunnerDescriptor(
        runner_id="opencode",
        name="OpenCode Runner",
        runner_family="coding-agent",
        execution_status="future-adapter-contract-only",
        runtime_enabled=False,
        observable_events=("agent.run.started", "agent.run.completed", "agent.run.failed"),
        external_boundary="standalone; future runner adapter only; not executed by Matrix OS",
    ),
    RunnerDescriptor(
        runner_id="local-shell",
        name="Local Shell Runner Boundary",
        runner_family="shell",
        execution_status="future-adapter-contract-only",
        runtime_enabled=False,
        observable_events=("gate.run.completed", "failure.observed"),
        external_boundary="standalone local environment; future approval adapter only; not executed by Matrix OS",
    ),
    RunnerDescriptor(
        runner_id="pi-agent-harness",
        name="Pi Agent Harness Boundary",
        runner_family="agent-harness-runtime-candidate",
        execution_status="future-adapter-contract-only",
        runtime_enabled=False,
        observable_events=("agent.run.started", "agent.run.completed", "agent.run.failed"),
        external_boundary=(
            "earendil-works/pi descriptor only; future runtime backend candidate; "
            "not Raspberry Pi hardware; not executed by Matrix OS"
        ),
    ),
)

_TOOLS: tuple[ToolDescriptor, ...] = (
    ToolDescriptor(
        tool_id="agent-evidence-plane",
        name="agent-evidence-plane",
        tool_family="evidence-producer",
        can_launch=False,
        can_observe=True,
        can_block=False,
        can_emit_evidence=True,
        execution_status="translation-only-adapter-exists",
        external_boundary="standalone evidence producer; translation-only adapter exists",
    ),
    ToolDescriptor(
        tool_id="safety-guard",
        name="CuraOps Safety Guard",
        tool_family="safety-producer",
        can_launch=False,
        can_observe=True,
        can_block=True,
        can_emit_evidence=True,
        execution_status="translation-only-adapter-exists",
        external_boundary="standalone safety producer; translation-only adapter exists",
    ),
    ToolDescriptor(
        tool_id="failure-driven-loop",
        name="failure-driven-loop",
        tool_family="failure-learning-producer",
        can_launch=False,
        can_observe=True,
        can_block=False,
        can_emit_evidence=True,
        execution_status="translation-only-adapter-exists",
        external_boundary="standalone failure-loop producer; translation-only adapter exists",
    ),
    ToolDescriptor(
        tool_id="peekxd",
        name="peekxd",
        tool_family="computer-use",
        can_launch=False,
        can_observe=True,
        can_block=False,
        can_emit_evidence=False,
        execution_status="future-capability-descriptor-only",
        external_boundary="standalone computer-use tool; future capability descriptor only",
    ),
)

_EDITOR_SURFACES: tuple[EditorSurfaceDescriptor, ...] = (
    EditorSurfaceDescriptor(
        surface_id="matrix-ui-code-editor",
        name="Original Matrix UI code editor surface",
        owner="Matrix OS Harness",
        source_paths=("src/ui/widgets/code_editor.py", "src/ui/widgets/split_pane.py"),
        future_attach_points=("CR status", "evidence timeline", "runner status", "approval inbox"),
        runtime_status="existing-widget-preserved",
    ),
    EditorSurfaceDescriptor(
        surface_id="zed-mcp-future",
        name="Zed/MCP future editor surface",
        owner="Zed/editor integration remains external",
        source_paths=("docs/MATRIX_OS_HARNESS_GATEWAY_ARCHITECTURE.md",),
        future_attach_points=("MCP adapter PR", "editor evidence links", "review annotations"),
        runtime_status="future-adapter-contract-only",
    ),
)


@dataclass
class HarnessGatewayRegistry:
    """Stable declarative registry for generic Matrix OS harness boundaries.

    SINGLE registry authority (DOD-03): the declarative descriptors
    (runners/tools/editor surfaces/capabilities) AND the runtime adapter
    loader (HarnessAdapterRegistry) live in this one class. There is no
    second independent registry — the runtime loader is a component of the
    gateway registry and resolves adapter entry points for the same harness
    ids declared here.
    """

    runners: tuple[RunnerDescriptor, ...]
    tools: tuple[ToolDescriptor, ...]
    editor_surfaces: tuple[EditorSurfaceDescriptor, ...]
    capabilities: tuple[GatewayCapability, ...]

    def __init__(
        self,
        *,
        runners: tuple[RunnerDescriptor, ...] | None = None,
        tools: tuple[ToolDescriptor, ...] | None = None,
        editor_surfaces: tuple[EditorSurfaceDescriptor, ...] | None = None,
        capabilities: tuple[GatewayCapability, ...] | None = None,
        adapter_registry_path: str | Path | None = None,
    ):
        self.runners = runners if runners is not None else _RUNNERS
        self.tools = tools if tools is not None else _TOOLS
        self.editor_surfaces = editor_surfaces if editor_surfaces is not None else _EDITOR_SURFACES
        self.capabilities = capabilities if capabilities is not None else _GATEWAY_CAPABILITIES
        # Runtime adapter loading is PART of this registry (single authority).
        from conduvera.harness.registry import HarnessAdapterRegistry

        self.adapters = HarnessAdapterRegistry(adapter_registry_path) if adapter_registry_path else None

    @classmethod
    def default(cls) -> "HarnessGatewayRegistry":
        """Return the default declarative gateway registry (no cwd dependency)."""

        return cls(
            runners=_RUNNERS,
            tools=_TOOLS,
            editor_surfaces=_EDITOR_SURFACES,
            capabilities=_GATEWAY_CAPABILITIES,
        )

    def load_adapter(self, adapter_id: str) -> Any:
        """REMOVED public runtime loader (Arbeit 4 / DOD-07).

        Concrete adapters are never returned to core callers. Use
        HarnessGatewayService for lifecycle access; this facade only
        serves declarative descriptors.
        """
        from conduvera.harness.registry import HarnessCapabilityUnavailableError

        raise HarnessCapabilityUnavailableError(
            adapter_id,
            "runtime adapter loading is private to HarnessGatewayService; "
            "use the public service entry (DOD-07)",
        )

    def get_runner(self, runner_id: str) -> RunnerDescriptor:
        """Return a runner descriptor or fail closed for unknown runner ids."""

        normalized = runner_id.strip().lower()
        for runner in self.runners:
            if runner.runner_id == normalized:
                return runner
        raise KeyError(f"Unknown runner '{runner_id}'")

    def get_tool(self, tool_id: str) -> ToolDescriptor:
        """Return a tool descriptor or fail closed for unknown tool ids."""

        normalized = tool_id.strip().lower()
        for tool in self.tools:
            if tool.tool_id == normalized:
                return tool
        raise KeyError(f"Unknown tool '{tool_id}'")

    def get_editor_surface(self, surface_id: str) -> EditorSurfaceDescriptor:
        """Return an editor surface descriptor or fail closed for unknown ids."""

        normalized = surface_id.strip().lower()
        for surface in self.editor_surfaces:
            if surface.surface_id == normalized:
                return surface
        raise KeyError(f"Unknown editor surface '{surface_id}'")

    def external_project_boundaries(self) -> dict[str, str]:
        """Return concise external ownership boundaries for product docs/tests."""

        boundaries = {
            runner.runner_id: runner.external_boundary.split("; not executed by Matrix OS")[0].split("; not Raspberry Pi hardware")[0]
            for runner in self.runners
            if runner.runner_id != "local-shell"
        }
        boundaries["zed-mcp"] = "standalone editor/plugin/runtime; no hardcoded CCC/AAL/Evidence logic"
        for tool in self.tools:
            boundaries[tool.tool_id] = tool.external_boundary
        return boundaries


def list_gateway_capabilities() -> tuple[GatewayCapability, ...]:
    """Return gateway capabilities."""

    return HarnessGatewayRegistry.default().capabilities


def list_runners() -> tuple[RunnerDescriptor, ...]:
    """Return future runner descriptors."""

    return HarnessGatewayRegistry.default().runners


def list_tools() -> tuple[ToolDescriptor, ...]:
    """Return current/future tool descriptors."""

    return HarnessGatewayRegistry.default().tools


def list_editor_surfaces() -> tuple[EditorSurfaceDescriptor, ...]:
    """Return editor surface descriptors."""

    return HarnessGatewayRegistry.default().editor_surfaces


class HarnessGatewayService:
    """SINGLE public entry point for harness adapters (DOD-01/03).

    Core/Runner/CLI know ONLY this service — never a concrete adapter and
    never the internal HarnessAdapterRegistry. The service:

    - resolves the registry cwd-independently (explicit path -> env ->
      package resource),
    - loads adapters via the internal loader (fail-closed),
    - exposes the full lifecycle incl. await_completion and execution mode,
    - never swallows exceptions: every failure becomes a structured
      AdapterResult with an AdapterErrorCode.
    """

    def __init__(
        self,
        *,
        registry_path: str | Path | None = None,
        execution_mode: str | ExecutionMode | None = None,
    ):
        from conduvera.harness.registry import (
            ExecutionMode as _EM,
        )

        if execution_mode is None:
            raise ValueError("EXECUTION_MODE_REQUIRED: HarnessGatewayService requires an explicit execution_mode (LIVE or SIMULATION)")
        self._registry_path = registry_path
        self._execution_mode = _EM.require(execution_mode)
        self._adapter_cache: dict[str, Any] = {}
        self._loader: Any = None  # lazy: resolved on first load_adapter

    @classmethod
    def from_registry(cls, registry_path: str | Path) -> "HarnessGatewayService":
        """Construct from an explicit registry path (tests/fixtures)."""
        return cls(registry_path=registry_path)

    # -- public lifecycle -------------------------------------------------

    def _get_loader(self) -> Any:
        """Resolve the internal loader lazily (fail-closed on first use)."""
        if self._loader is None:
            from conduvera.harness.registry import HarnessAdapterRegistry

            self._loader = HarnessAdapterRegistry(self._registry_path)
        return self._loader

    def _load_adapter(self, adapter_id: str) -> Any:
        """INTERNAL adapter loading (fail-closed via internal loader).

        Private on purpose (DOD-03): concrete adapters are never returned
        to callers. The only public surface is the lifecycle methods
        (start_session/status/cancel/timeout/await_completion/collect_evidence).
        """
        if adapter_id not in self._adapter_cache:
            try:
                self._adapter_cache[adapter_id] = self._get_loader().load_adapter(adapter_id)
            except FileNotFoundError as exc:
                # Registry not resolvable -> CAPABILITY_UNAVAILABLE (fail-closed).
                from conduvera.harness.registry import HarnessCapabilityUnavailableError

                raise HarnessCapabilityUnavailableError(
                    adapter_id, f"registry not resolvable: {exc}"
                ) from exc
        return self._adapter_cache[adapter_id]

    def start_session(self, adapter_id: str, **kwargs: Any) -> AdapterResult:
        """Start a session on the adapter with the service's execution mode.

        The productive Core path requires LIVE; SIMULATION is only usable
        for tests and never satisfies operational gates.
        """
        config = dict(kwargs.pop("config", {}))
        config["execution_mode"] = self._execution_mode.value
        try:
            adapter = self._load_adapter(adapter_id)
            return adapter.start_session(config=config, **kwargs)
        except Exception as exc:  # structured, never silent
            from conduvera.harness.registry import HarnessCapabilityUnavailableError

            if isinstance(exc, HarnessCapabilityUnavailableError):
                return AdapterResult(
                    success=False,
                    message=str(exc),
                    detail={"code": exc.code, "adapter": exc.adapter_id},
                )
            return AdapterResult(
                success=False,
                message=f"adapter protocol error: {exc}",
                detail={"code": AdapterErrorCode.ADAPTER_PROTOCOL_ERROR.value},
            )

    def status_session(self, adapter_id: str, session_id: str) -> AdapterResult:
        try:
            return self._load_adapter(adapter_id).status_session(session_id)
        except Exception as exc:
            return AdapterResult(
                success=False,
                message=f"adapter protocol error: {exc}",
                detail={"code": AdapterErrorCode.ADAPTER_PROTOCOL_ERROR.value},
            )

    def cancel_session(self, adapter_id: str, session_id: str) -> AdapterResult:
        try:
            return self._load_adapter(adapter_id).cancel_session(session_id)
        except Exception as exc:
            return AdapterResult(
                success=False,
                message=f"adapter protocol error: {exc}",
                detail={"code": AdapterErrorCode.ADAPTER_PROTOCOL_ERROR.value},
            )

    def timeout_session(self, adapter_id: str, session_id: str) -> AdapterResult:
        try:
            return self._load_adapter(adapter_id).timeout_session(session_id)
        except Exception as exc:
            return AdapterResult(
                success=False,
                message=f"adapter protocol error: {exc}",
                detail={"code": AdapterErrorCode.ADAPTER_PROTOCOL_ERROR.value},
            )

    def await_completion(
        self,
        adapter_id: str,
        session_id: str,
        timeout_policy: dict[str, Any] | None = None,
    ) -> AdapterResult:
        """Block until the managed session completes (contract method)."""
        try:
            return self._load_adapter(adapter_id).await_completion(
                session_id, timeout_policy=timeout_policy
            )
        except Exception as exc:
            return AdapterResult(
                success=False,
                message=f"session wait failed: {exc}",
                detail={"code": AdapterErrorCode.SESSION_WAIT_FAILED.value},
            )

    def collect_evidence(self, adapter_id: str, session_id: str) -> dict[str, Any]:
        try:
            return self._load_adapter(adapter_id).collect_evidence(session_id)
        except Exception as exc:
            return {
                "session_id": session_id,
                "ok": False,
                "error": AdapterErrorCode.ADAPTER_PROTOCOL_ERROR.value,
                "message": str(exc),
            }

    @property
    def execution_mode(self) -> str:
        return self._execution_mode.value
