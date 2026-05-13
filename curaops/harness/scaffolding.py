"""Scaffolding manifest for Matrix OS UI/MCP/editor integration.

The manifest is intentionally declarative. This scaffolding slice records the ownership and launch
boundaries for the original Matrix UI and future MCP/editor surfaces without
starting servers, adding adapters, or changing compliance/accountability logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScaffoldingSlice:
    """Describes a planned or existing harness surface."""

    key: str
    name: str
    status: str
    owner: str
    entrypoints: tuple[str, ...]
    source_paths: tuple[str, ...]
    responsibilities: tuple[str, ...]
    excluded_scope: tuple[str, ...]


SCAFFOLDING_SLICES: tuple[ScaffoldingSlice, ...] = (
    ScaffoldingSlice(
        key="ui",
        name="Original Matrix UI",
        status="existing-app-preserved",
        owner="Matrix OS Harness",
        entrypoints=("matrix-os", "mxos", "python3 -m src.core.app"),
        source_paths=(
            "src/core/app.py",
            "src/ui/themes/matrix.tcss",
            "src/ui/widgets/matrix_rain.py",
            "src/ui/widgets/file_browser.py",
            "src/ui/widgets/terminal.py",
            "src/ui/widgets/code_editor.py",
            "src/ui/widgets/process_monitor.py",
            "docs/UI_DESIGN_COMPARISON.md",
        ),
        responsibilities=(
            "preserve Matrix Digital Rain visual identity",
            "preserve sidebar-driven Textual layout",
            "preserve terminal, file browser, process monitor, and code editor surfaces",
            "provide future integration points for compliance/accountability status panels",
        ),
        excluded_scope=(
            "no UI rewrite",
            "no production dashboard claim",
            "no external engine adapter integration",
        ),
    ),
    ScaffoldingSlice(
        key="mcp",
        name="MCP Server Scaffolding",
        status="planned-contract-only",
        owner="Matrix OS Harness",
        entrypoints=("matrix-cli scaffold status",),
        source_paths=("docs/MATRIX_OS_SCAFFOLDING.md",),
        responsibilities=(
            "document future MCP boundary",
            "keep MCP separate from CCC/AAL/ASPICE business logic",
            "reserve a narrow adapter contract for later implementation",
        ),
        excluded_scope=(
            "no MCP server implementation",
            "no network listener",
            "no tool registration runtime",
        ),
    ),
    ScaffoldingSlice(
        key="editor",
        name="Editor Scaffolding",
        status="existing-widget-preserved",
        owner="Matrix OS Harness",
        entrypoints=("matrix-os", "mxos"),
        source_paths=(
            "src/ui/widgets/code_editor.py",
            "src/ui/widgets/split_pane.py",
            "src/ui/themes/matrix.tcss",
        ),
        responsibilities=(
            "preserve original code editor widget",
            "preserve editor/terminal split-view direction",
            "document later compliance-aware editor integrations",
        ),
        excluded_scope=(
            "no IDE plugin implementation",
            "no language-server integration",
            "no agent-code execution bridge",
        ),
    ),
)


def list_scaffolding_slices() -> tuple[ScaffoldingSlice, ...]:
    """Return all registered UI/MCP/editor scaffolding slices."""

    return SCAFFOLDING_SLICES


def get_scaffolding_slice(key: str) -> ScaffoldingSlice:
    """Return one scaffolding slice by key.

    Raises:
        KeyError: if the slice key is unknown.
    """

    normalized = key.strip().lower()
    for item in SCAFFOLDING_SLICES:
        if item.key == normalized:
            return item
    known = ", ".join(item.key for item in SCAFFOLDING_SLICES)
    raise KeyError(f"Unknown scaffolding slice '{key}'. Known slices: {known}")


def source_path_exists(project_root: Path, source_path: str) -> bool:
    """Return whether a declared source path currently exists under project_root."""

    return (project_root / source_path).exists()
