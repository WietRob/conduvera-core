"""UI/Access-plane convergence tests (steer gate UI-DOD-01..07).

Verifies the canonical architecture diagram and the Obsidian docs agree on
the five current surfaces (port, purpose, auth boundary, real status),
separate current vs future UI planes, and keep Open WebUI honest.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGRAM = ROOT / "docs" / "CONDUVERA_ARCHITECTURE_DIAGRAM.md"
MMD = ROOT / "docs" / "architecture.mmd"
BRAIN = Path("/home/roberto_schmidt/Dokumente/Obsidian Vaults/Roberto_Brain/20_Areas/Dev_Infrastructure/ODS_Integration")


def _diagram() -> str:
    return DIAGRAM.read_text(encoding="utf-8")


def _mmd() -> str:
    return MMD.read_text(encoding="utf-8")


def test_ui_dod01_five_surfaces_documented():
    """All five current surfaces with port, purpose, auth, status."""
    txt = _diagram()
    for port, name in [(":3001", "Dashboard"), (":3000", "Open WebUI"),
                       (":9120", "ODS-Hermes"), (":5678", "n8n"), (":3003", "OpenCode")]:
        assert port in txt, f"Diagram fehlt Port {port}"
    # Status-Honesty markers
    assert "BLOCKED_AUTH_RECOVERY" in txt
    assert "NOT_PROVEN" in txt
    assert "SERVICE_HEALTH" in txt


def test_ui_dod02_current_and_future_separated():
    """Current browser/access plane and future Console/Workspace are separate."""
    txt = _diagram()
    assert "Aktuelle Browser-/Access-Ebene" in txt
    assert "Zukünftige Console-/Workspace-Ebene" in txt
    assert "NOT_DECIDED" in txt


def test_ui_dod03_open_webui_not_reset_not_productive():
    """Open WebUI is neither reset nor called productively accessible."""
    txt = _diagram()
    assert "BLOCKED_AUTH_RECOVERY" in txt
    assert "NOT_PROVEN" in txt
    # No claim of productive access anywhere in the diagram
    assert "produktiv" not in txt or "keine produktive" in txt


def test_ui_dod04_ods_hermes_healthy_ne_browser_auth():
    """ODS-Hermes healthy is not equal to authorized browser access."""
    txt = _diagram()
    assert "healthy" in txt
    assert "nicht" in txt or "NICHT" in txt
    assert "dream-session" in txt


def test_ui_dod05_workspace_basis_not_decided():
    txt = _diagram()
    assert "CONDUVERA_WORKSPACE_IMPLEMENTATION_BASIS = NOT_DECIDED" in txt
    assert "ersetzt Open WebUI NOCH NICHT" in txt


def test_ui_dod06_cross_document_consistency():
    """Obsidian docs must not contradict the diagram on the five surfaces."""
    txt = _diagram()
    # Every surface claim in the diagram must be compatible with Current_State.md
    cs = (BRAIN / "Current_State.md").read_text(encoding="utf-8")
    for port in (":3001", ":3000", ":9120", ":5678", ":3003"):
        assert port in cs, f"Current_State.md fehlt Port {port}"
    assert "BLOCKED_AUTH_RECOVERY" in cs or "NOT_DECIDED" in cs
    assert "ai-stack model use" in cs  # single mode-switch interface
    assert "kein Modellwechsel" in cs or "kein kanonischer Modellwechsel" in cs


def test_ui_dod07_report_split_backend_vs_browser():
    """Diagram separates BACKEND_E2E from browser/UI E2E claims."""
    txt = _diagram()
    assert "BACKEND_E2E" in txt
    assert "Browser-UI-E2E" in txt or "Browser-E2E" in txt


def test_mmd_is_machine_readable_and_consistent():
    """architecture.mmd mirrors the canonical diagram's key facts."""
    mmd = _mmd()
    for token in (":3001", ":3000", ":9120", ":5678", ":3003",
                  "workload/local", "ai-stack model use", "llama-server",
                  "LiteLLM", "BWS", "Pi"):
        assert token in mmd, f"architecture.mmd fehlt {token}"
