# Matrix OS MCP / UI / Editor Scaffolding

Status: authoritative scaffolding contract for the next Matrix OS harness slice.

This document starts the MCP / UI / Editor scaffolding slice without implementing new external-engine adapters, MCP server runtime, or production dashboard behavior.

## Intent

The original Matrix UI remains part of Matrix OS and must not be forgotten. The current repository already contains the Textual Matrix UI entry points and widgets. This scaffolding slice records their ownership and creates a thin CLI-discoverable manifest so later work can attach compliance/accountability views without rewriting the UI.

## Preserved original Matrix UI

| Surface | Current path / entry point | Scaffolding treatment |
|---|---|---|
| App entry points | `matrix-os`, `mxos`, `python3 -m src.core.app` | preserve |
| Textual app shell | `src/core/app.py` | preserve as original Matrix UI host |
| Matrix theme | `src/ui/themes/matrix.tcss` | preserve |
| Matrix Digital Rain | `src/ui/widgets/matrix_rain.py` | preserve visual identity |
| File Browser | `src/ui/widgets/file_browser.py` | preserve |
| Terminal | `src/ui/widgets/terminal.py` | preserve |
| Code Editor | `src/ui/widgets/code_editor.py` | preserve |
| Process Monitor | `src/ui/widgets/process_monitor.py` | preserve |
| Design comparison | `docs/UI_DESIGN_COMPARISON.md` | historical design source; not current runtime authority |

## Scaffolding command surface

This scaffolding slice adds a discovery-only CLI namespace:

```bash
python3 -m conduvera.cli.main scaffold --help
python3 -m conduvera.cli.main scaffold status
python3 -m conduvera.cli.main scaffold show ui
python3 -m conduvera.cli.main scaffold show mcp
python3 -m conduvera.cli.main scaffold show editor
```

These commands print the declared scaffolding status and source paths. They do not launch UI, open network sockets, start an MCP server, register tools, invoke agents, or integrate external engines.

## Module boundaries

| Slice | Status | Boundary |
|---|---|---|
| UI | existing app preserved | Matrix OS owns the Textual shell, Matrix rain identity, sidebar layout, and future compliance/accountability view slots |
| MCP | planned contract only | Matrix OS may later expose reviewed harness actions through a narrow MCP server, but this slice does not implement the server |
| Editor | existing widget preserved | Matrix OS owns the existing code editor widget and editor/terminal split direction; no IDE plugin or agent execution bridge is added here |

## Explicit exclusions

This slice does not include:

- MCP server implementation
- UI rewrite
- production dashboard claims
- IDE plugin implementation
- language-server integration
- agent-code execution bridge
- Safety Guard integration
- agent-evidence-plane integration
- CAS integration
- failure-loop integration
- peekxd integration
- OpenCode plugin integration
- ai-router integration

## Verification

Required local checks for this slice:

```bash
python3 -m pytest tests/test_packaging_contract.py
python3 -m pytest tests/test_scaffolding_contract.py
python3 -m pytest conduvera/skills/change_request/tests
python3 -m pytest conduvera/skills/accountable_agent/tests
python3 -m pytest conduvera/skills/aspice_conflict_detector/test_conflict_detector.py
python3 -m pytest conduvera/skills/aspice_link_manager/tests
python3 -m conduvera.cli.main --help
python3 -m conduvera.cli.main scaffold --help
python3 -m conduvera.cli.main scaffold status
python3 -m conduvera.cli.main scaffold show ui
```
