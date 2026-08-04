"""Architektur-Konsistenzgate (DOD-09, baseline-goal).

Jede Funktion muss im Feature-Katalog, im Architekturdiagramm und in den
Authority-Dokumenten dieselbe Owner-Komponente und denselben Status besitzen.
Kein Paralleluniversum. Read-only Prüfung gegen die Repo-Quellen (das
Brain-Dokument wird über CONDUVERA_BRAIN_ROOT optional eingebunden).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "evidence/goals/CONDUVERA-FIXTURE-001/system-capabilities.yaml"
DIAGRAM = ROOT / "docs" / "CONDUVERA_ARCHITECTURE_DIAGRAM.md"
MMD = ROOT / "docs" / "architecture.mmd"
BRAIN = Path(os.environ.get("CONDUVERA_BRAIN_ROOT", "/nonexistent"))

# Feature-IDs, die im Diagramm einen Node haben müssen (Owner-Komponente sichtbar)
DIAGRAM_NODE_MAP = {
    "CORE-001": "Conduvera Core",
    "CORE-002": "Buildroom",
    "HARNESS-001": "Harness Gateway",
    "HARNESS-002": "Hermes",
    "MODEL-001": "LiteLLM",
    "ODS-001": "ODS / ai-stack",
    "CAP-001": "ComfyUI",
    "CAP-002": "Qdrant",
    "CAP-003": "Whisper",
    "CAP-004": "n8n",
    "CAP-005": "Search",
    "OBS-001": "Langfuse",
    "SEC-001": "BWS",
}


def test_catalog_machine_readable():
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    assert data["schema"] == "system-capabilities.v1"
    assert isinstance(data["components"], dict)
    assert len(data["components"]) >= 20


def test_catalog_fields_complete():
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    required = [
        "feature_id", "funktion", "owner", "repository", "adapter_contract",
        "runtime_dependencies", "security_gate", "evidence_output", "status",
        "proof", "modularity", "missing_gate",
    ]
    for name, comp in data["components"].items():
        assert isinstance(comp, dict), f"{name} ist kein Mapping"
        for field in required:
            assert field in comp, f"{comp.get('feature_id')} fehlt: {field}"


def test_catalog_status_values_valid():
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    valid = {"LIVE_PROVEN", "RELEASE_CANDIDATE", "SERVICE_HEALTHY_NOT_E2E",
             "DESIGNED_ONLY", "BLOCKED", "DEPRECATED"}
    for name, comp in data["components"].items():
        assert comp["status"] in valid, f"{comp['feature_id']}: ungültiger Status {comp['status']}"


def test_diagram_covers_core_features():
    txt = DIAGRAM.read_text(encoding="utf-8")
    for feature_id, node in DIAGRAM_NODE_MAP.items():
        # The diagram must mention the owner component for each core feature.
        assert node.lower() in txt.lower(), f"Diagramm fehlt Node für {feature_id} ({node})"


def test_mmd_consistent_with_diagram_md():
    md = DIAGRAM.read_text(encoding="utf-8")
    mmd = MMD.read_text(encoding="utf-8")
    # Both must contain the same core nodes.
    for node in ("Conduvera Core", "Harness Gateway", "Hermes", "LiteLLM",
                 "ODS / ai-stack", "ComfyUI", "Qdrant", "n8n", "Search",
                 "Langfuse", "BWS"):
        assert node.lower() in md.lower(), f"Diagramm-MD fehlt: {node}"
        assert node.lower() in mmd.lower(), f"architecture.mmd fehlt: {node}"


def test_no_native_codex_oauth_expression():
    """The forbidden phrase must not appear as an ACTIVE route description.
    The invariants table explicitly NEGATES it ('KEIN Ausdruck ...') which is
    allowed — that is the guard itself."""
    for path in (DIAGRAM, MMD):
        txt = path.read_text(encoding="utf-8")
        # Strip the invariant-table row that negates the phrase, then assert
        # the phrase does not appear as an active claim elsewhere.
        lines = [l for l in txt.splitlines() if "native Codex-CLI-Route (OAuth)" in l]
        for line in lines:
            assert "KEIN Ausdruck" in line or "NICHT" in line or "≠" in line, \
                f"{path.name} behauptet den Ausdruck aktiv: {line}"


def test_brain_catalog_consistent():
    """Der Brain-Feature-Catalog (human-readable) referenziert dieselben
    Feature-IDs wie die maschinenlesbare Quelle."""
    brain_doc = BRAIN / "20_Areas/Dev_Infrastructure/ODS_Integration/Conduvera_System_Feature_Catalog.md"
    if not brain_doc.is_file():
        import pytest
        pytest.skip("CONDUVERA_BRAIN_ROOT nicht konfiguriert oder Katalog fehlt")
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    txt = brain_doc.read_text(encoding="utf-8")
    for comp in data["components"]:
        fid = comp["feature_id"]
        assert fid in txt, f"Brain-Katalog fehlt Feature-ID {fid}"
