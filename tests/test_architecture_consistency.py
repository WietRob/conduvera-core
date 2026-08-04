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


def _brain_root() -> Path:
    """Resolve CONDUVERA_BRAIN_ROOT lazily (env may be set at run time).

    The env points at the ODS_Integration area directory; the feature
    catalog lives directly inside it.
    """
    return Path(os.environ.get("CONDUVERA_BRAIN_ROOT", "/nonexistent"))


def _brain_catalog() -> Path:
    return _brain_root() / "Conduvera_System_Feature_Catalog.md"

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
             "DESIGNED_ONLY", "BLOCKED", "DEPRECATED",
             "NOT_PROVEN", "NOT_STARTED", "PARTIAL", "NOT_OPERATIONAL",
             "PARITY_PROVEN_NOT_INTEGRATED", "INTEGRATED_AND_LIVE_PROVEN",
             "LIVE_PROVEN_AND_ENTRYPOINT_WIRED", "V1_REAL_TASK_PROVEN",
             "PILOT_PROVEN"}
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
    brain_doc = _brain_catalog()
    if not brain_doc.is_file():
        import pytest
        pytest.skip("CONDUVERA_BRAIN_ROOT nicht konfiguriert oder Katalog fehlt")
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    txt = brain_doc.read_text(encoding="utf-8")
    for comp in data["components"].values():
        fid = comp["feature_id"]
        assert fid in txt, f"Brain-Katalog fehlt Feature-ID {fid}"


# --- V1/V2: Status-Konsistenz zwischen Repo- und Brain-Katalog ---------------

def test_v1_core002b_status_identical_in_repo_and_brain():
    """V1: CORE-002B muss in Repo-Katalog UND Brain-Katalog LIVE_PROVEN sein."""
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    repo_status = data["components"]["real_buildroom_execution_path"]["status"]
    assert repo_status == "LIVE_PROVEN", f"CORE-002B Repo-Status: {repo_status}"

    brain_doc = _brain_catalog()
    if not brain_doc.is_file():
        import pytest
        pytest.skip("CONDUVERA_BRAIN_ROOT nicht konfiguriert oder Katalog fehlt")
    txt = brain_doc.read_text(encoding="utf-8")
    assert "CORE-002B | Real-Buildroom-Execution-Path | LIVE_PROVEN" in txt, \
        "Brain-Katalog CORE-002B ist nicht LIVE_PROVEN"


def test_v2_no_conflicting_status_for_same_feature():
    """V2: Kein Feature darf gleichzeitig INTEGRATED_AND_LIVE_PROVEN und
    PARITY_PROVEN_NOT_INTEGRATED (oder NOT_PROVEN) als AKTUELLEN Status haben."""
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    by_id: dict[str, list[str]] = {}
    for comp in data["components"].values():
        by_id.setdefault(comp["feature_id"], []).append(comp["status"])
    for fid, statuses in by_id.items():
        if "INTEGRATED_AND_LIVE_PROVEN" in statuses:
            assert not any(s in ("PARITY_PROVEN_NOT_INTEGRATED", "NOT_PROVEN")
                           for s in statuses), \
                f"{fid}: widersprüchliche Status {statuses}"


def test_v4_semantic_implied_status():
    """V4: Wenn B1/B2/B3 = INTEGRATED_AND_LIVE_PROVEN und CORE-002D =
    LIVE_PROVEN, dann MUSS CORE-002B = LIVE_PROVEN sein."""
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    c = data["components"]
    helpers = [c[k]["status"] for k in
               ("buildroom_backend_policy_slice", "buildroom_no_progress_slice",
                "buildroom_task_binding_slice")]
    caller = c["managed_execution_caller"]["status"]
    core002b = c["real_buildroom_execution_path"]["status"]
    if all(s == "INTEGRATED_AND_LIVE_PROVEN" for s in helpers) and caller == "LIVE_PROVEN":
        assert core002b == "LIVE_PROVEN", \
            f"CORE-002B muss LIVE_PROVEN sein (Helper {helpers}, Caller {caller}), ist {core002b}"


# --- V5: Caller-Authority ----------------------------------------------------

def test_v5_single_productive_execution_caller():
    """V5: Produktiver Buildroom-Code darf genau EINEN Execution-Caller
    besitzen; FixtureRunner ist test-only klassifiziert.

    managed_execution.py ruft start_session (produktiv); fixture_runner.py
    ist ausschliesslich Fixture-/Test-Seam (kein produktiver Import ausserhalb
    fixtures/live und tests/).
    """
    # managed_execution ist der einzige produktive Caller mit HarnessGateway-Spawn
    productive_spawners = []
    for py in (ROOT / "curaops/buildroom").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        if "start_session" in src and "class ManagedBuildroomCaller" in src:
            productive_spawners.append(py.name)
    assert productive_spawners == ["managed_execution.py"], \
        f"Produktive Execution-Caller: {productive_spawners}"

    # FixtureRunner darf nur aus fixtures/live und tests/ importiert werden
    import subprocess
    r = subprocess.run(
        ["grep", "-rln", "fixture_runner", "curaops/"],
        capture_output=True, text=True, cwd=ROOT,
    )
    hits = [l for l in r.stdout.splitlines() if "__pycache__" not in l]
    assert not hits, f"FixtureRunner wird produktiv genutzt: {hits}"


def test_v3_no_current_not_proven_statement():
    """V3: Keine AKTUELLE Aussage 'Real-Buildroom-Execution-Path = NOT_PROVEN'
    im Repo-Katalog (historische Evidence-/Review-Artefakte ausgenommen)."""
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    # Der kanonische Status ist LIVE_PROVEN (kein NOT_PROVEN für diesen Pfad)
    assert data["components"]["real_buildroom_execution_path"]["status"] == "LIVE_PROVEN"


def test_dod12_diagram_shows_real_call_path_edges():
    """DOD-12: Diagramm zeigt echte Kanten (Operator -> Dispatcher ->
    legacy|managed -> Gateway -> Hermes -> LiteLLM -> ODS), nicht nur Knoten."""
    md = DIAGRAM.read_text(encoding="utf-8")
    mmd = MMD.read_text(encoding="utf-8")
    required_edges = [
        "B5 --> B3",              # Operator Entry -> Dispatcher
        "B3 -->|legacy| B6",      # Dispatcher -> Legacy Orchestrator
        "B3 -->|managed_canary| B4",  # Dispatcher -> Managed Caller
        "B6 --> C4",              # Legacy -> Gateway
        "B4 --> C4",              # Managed -> Gateway
        "B4 --> B2",              # Managed -> backend_policy
    ]
    for edge in required_edges:
        assert edge in mmd, f"architecture.mmd fehlt Kante: {edge}"
        assert edge in md, f"Diagramm-MD fehlt Kante: {edge}"
