"""Tests for Matrix OS UI/MCP/editor scaffolding metadata."""

from pathlib import Path

import pytest

from curaops.harness.scaffolding import get_scaffolding_slice, list_scaffolding_slices

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_scaffolding_registers_expected_slices() -> None:
    """PR F registers only the intended UI/MCP/editor scaffolding slices."""

    keys = {item.key for item in list_scaffolding_slices()}

    assert keys == {"ui", "mcp", "editor"}


def test_original_matrix_ui_design_is_preserved_in_manifest() -> None:
    """The original Matrix UI remains an explicit first-class scaffold target."""

    ui = get_scaffolding_slice("ui")

    assert ui.name == "Original Matrix UI"
    assert "matrix-os" in ui.entrypoints
    assert "src/core/app.py" in ui.source_paths
    assert "src/ui/themes/matrix.tcss" in ui.source_paths
    assert "src/ui/widgets/matrix_rain.py" in ui.source_paths
    assert any("Matrix Digital Rain" in item for item in ui.responsibilities)


def test_declared_existing_source_paths_are_present() -> None:
    """Existing UI/editor source paths in the manifest resolve in this checkout."""

    for item in list_scaffolding_slices():
        for source_path in item.source_paths:
            if source_path.startswith("src/") or source_path.startswith("docs/UI"):
                assert (PROJECT_ROOT / source_path).exists(), source_path


def test_scaffolding_excludes_external_engine_integration() -> None:
    """PR F scaffolding must not absorb future external engines."""

    external_names = {
        "Safety Guard",
        "agent-evidence-plane",
        "CAS",
        "failure-loop",
        "peekxd",
        "OpenCode",
        "ai-router",
    }
    combined_excludes = "\n".join(
        excluded for item in list_scaffolding_slices() for excluded in item.excluded_scope
    )

    assert "external engine adapter integration" in combined_excludes
    for name in external_names:
        assert name.lower() not in {item.key for item in list_scaffolding_slices()}


def test_unknown_scaffolding_slice_raises_key_error() -> None:
    """Unknown scaffold keys fail closed."""

    with pytest.raises(KeyError):
        get_scaffolding_slice("safety-guard")
