"""Tests for non-live Matrix UI route-plan panel attachment."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Button

from src.core.app import MatrixOS, Sidebar
from src.ui.widgets.route_plan_panel import MatrixRoutePlanPanel

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan"
PANEL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness" / "route_plan_panel"


def test_route_plan_panel_is_discoverable_from_sidebar_without_live_route() -> None:
    sidebar_widgets = list(Sidebar().compose())
    buttons = [widget for widget in sidebar_widgets if isinstance(widget, Button)]
    route_plan_buttons = [button for button in buttons if button.id == "btn_route_plan"]

    assert len(route_plan_buttons) == 1
    assert "Route Plan" in str(route_plan_buttons[0].label)


def test_matrix_app_can_create_route_plan_panel_view_without_starting_runtime() -> None:
    app = MatrixOS()

    widget = app._create_view_widget("route_plan")

    assert isinstance(widget, MatrixRoutePlanPanel)
    assert widget.id == "route-plan-panel-view"
    assert widget.panel_model.chosen_candidate_id == "hermes"
    assert widget.panel_model.runtime_execution is False
    assert widget.panel_model.dashboard_claim is False
    assert widget.panel_model.shell_execution is False
    assert widget.panel_model.destructive_command_path is False
    assert "no live UI route" in widget.renderable
    assert "Runtime execution: no" in widget.renderable
    assert "Production dashboard claim: no" in widget.renderable


def test_matrix_app_route_plan_panel_matches_stable_snapshot_contract() -> None:
    app = MatrixOS()

    widget = app._create_view_widget("route_plan")
    expected = (PANEL_FIXTURE_DIR / "agent-task.txt").read_text(encoding="utf-8")

    assert widget.renderable == expected


def test_route_plan_button_dispatches_to_non_live_panel_view(monkeypatch) -> None:
    app = MatrixOS()
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(app, "switch_view", lambda view_name: calls.append(("switch", view_name)))
    monkeypatch.setattr(app, "update_status", lambda message: calls.append(("status", message)))

    class Event:
        button = Button("🧭 Route Plan", id="btn_route_plan")

    app.on_button_pressed(Event())

    assert ("switch", "route_plan") in calls
    assert any("Route Plan Panel" in payload for kind, payload in calls if kind == "status")


def test_route_plan_panel_attachment_does_not_create_new_route_plans_or_execute() -> None:
    app = MatrixOS()
    widget = app._create_view_widget("route_plan")

    assert widget.panel_model.source_schema_version == "route-plan.v1"
    assert widget.panel_model.panel_boundary.startswith("Display-only")
    assert "Runtime execution: no" in widget.renderable
    assert "Shell execution: no" in widget.renderable
    assert "Destructive command path: no" in widget.renderable
    assert (FIXTURE_DIR / "agent-task.json").exists()
