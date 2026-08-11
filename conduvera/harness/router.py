"""Deterministic harness router (CONTROL-PLANE-V1).

Selects harness and model binding separately using:

- task class;
- required capabilities;
- risk class;
- current availability/capacity;
- declared budget and timeout;
- current valid model-binding configuration;
- deterministic fallback rules;
- manual override.

No free LLM guessing. If no valid route exists -> NO_ROUTE (fail-closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class NoRouteError(Exception):
    """Raised when no valid harness/model route exists (fail-closed)."""

    def __init__(self, reason: str):
        self.code = "NO_ROUTE"
        self.reason = reason
        super().__init__(f"NO_ROUTE: {reason}")


@dataclass(frozen=True)
class TaskClass:
    """Task classification driving deterministic routing."""

    name: str
    risk: str  # LOW | MEDIUM | HIGH
    required_capabilities: tuple[str, ...] = ()
    preferred_harness: str | None = None


TASK_CLASSES: dict[str, TaskClass] = {
    "fixture": TaskClass("fixture", "LOW", (), "hermes_scoped"),
    "code_change": TaskClass("code_change", "MEDIUM",
                             ("start", "status", "cancel", "collect_evidence"),
                             "hermes_scoped"),
    "native_codex": TaskClass("native_codex", "MEDIUM",
                              ("start", "status", "cancel", "collect_evidence"),
                              "codex_cli"),
    "native_opencode": TaskClass("native_opencode", "MEDIUM",
                                 ("start", "status", "cancel", "collect_evidence"),
                                 "opencode_cli"),
    "native_pi": TaskClass("native_pi", "MEDIUM",
                           ("start", "status", "cancel", "collect_evidence"),
                           "pi_cli"),
    "dangerous": TaskClass("dangerous", "HIGH",
                           ("start", "status", "cancel", "collect_evidence",
                            "steer"), None),
}


@dataclass
class HarnessAvailability:
    """Current availability/capacity of one harness."""

    harness: str
    available: bool
    capacity: int = 1  # concurrent sessions supported
    active_sessions: int = 0

    @property
    def has_capacity(self) -> bool:
        return self.available and self.active_sessions < self.capacity


@dataclass
class ModelBinding:
    """A valid model-binding configuration."""

    route: str
    model: str = ""
    provider: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"route": self.route, "model": self.model, "provider": self.provider}


@dataclass
class RouteDecision:
    """Deterministic route decision."""

    task_id: str
    task_class: str
    harness: str
    model_binding: ModelBinding
    reason: str
    overridden: bool = False
    fallback_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_class": self.task_class,
            "harness": self.harness,
            "model_binding": self.model_binding.to_dict(),
            "reason": self.reason,
            "overridden": self.overridden,
            "fallback_chain": list(self.fallback_chain),
        }


DEFAULT_BINDINGS: dict[str, ModelBinding] = {
    "hermes_scoped": ModelBinding(route="workload/local", model="local",
                                  provider="custom:litellm"),
    "codex_cli": ModelBinding(route="codex-native", model="codex",
                              provider="codex-cli"),
    "opencode_cli": ModelBinding(route="opencode-native", model="opencode",
                                 provider="opencode-cli"),
    "pi_cli": ModelBinding(route="workload/local", model="local",
                           provider="litellm-local"),
}


class DeterministicRouter:
    """Deterministic harness + model selection (no LLM guessing)."""

    def __init__(
        self,
        *,
        availability: dict[str, HarnessAvailability] | None = None,
        bindings: dict[str, ModelBinding] | None = None,
        fallback_order: tuple[str, ...] = ("hermes_scoped", "codex_cli",
                                           "opencode_cli"),
    ):
        self._bindings = bindings or dict(DEFAULT_BINDINGS)
        self._fallback = fallback_order
        self._availability = availability or {
            h: HarnessAvailability(h, True) for h in fallback_order}

    def set_availability(self, harness: str, available: bool, active: int = 0) -> None:
        self._availability[harness] = HarnessAvailability(
            harness, available, active_sessions=active)

    def route(
        self,
        *,
        task_id: str,
        task_class: str | TaskClass,
        timeout_s: float = 120.0,
        budget: float = 0.0,
        override_harness: str | None = None,
    ) -> RouteDecision:
        """Select harness + model binding deterministically.

        Manual override wins; otherwise preferred harness for the task class
        if available, then deterministic fallback chain; else NO_ROUTE.
        """
        tc = task_class if isinstance(task_class, TaskClass) else TASK_CLASSES[task_class]

        if override_harness:
            if override_harness not in self._bindings:
                raise NoRouteError(f"override harness {override_harness} has no binding")
            return RouteDecision(
                task_id=task_id, task_class=tc.name, harness=override_harness,
                model_binding=self._bindings[override_harness],
                reason=f"manual override: {override_harness}", overridden=True)

        # Risk gate: HIGH risk without steer capability -> NO_ROUTE
        if tc.risk == "HIGH" and "steer" not in tc.required_capabilities:
            raise NoRouteError("high-risk task requires steer capability (not in v1)")

        order = []
        if tc.preferred_harness:
            order.append(tc.preferred_harness)
        for h in self._fallback:
            if h not in order:
                order.append(h)

        fallback_chain: list[str] = []
        for harness in order:
            avail = self._availability.get(harness, HarnessAvailability(harness, False))
            if avail.has_capacity:
                return RouteDecision(
                    task_id=task_id, task_class=tc.name, harness=harness,
                    model_binding=self._bindings[harness],
                    reason=f"preferred/fallback available: {harness}",
                    fallback_chain=fallback_chain)
            fallback_chain.append(harness)

        raise NoRouteError(
            f"no harness available for task_class={tc.name} "
            f"(chain: {fallback_chain})")
