# Matrix OS Origin and Provenance

Status: evidence-based provenance note for the current Matrix OS repository.

This document records confirmed facts and unknowns. It does not invent a Pi, fork, or upstream lineage claim.

## Confirmed facts

| Fact | Evidence |
|---|---|
| Current remote | `origin git@github.com:WietRob/matrix-os.git` |
| Current main at slice start | `58b89069db6c9261da95255233753744a3c193e6` |
| Root commit on current main graph | `0724a12dd0547e9d4ff1e945680eae38cab05273` |
| Early local/root-line commit | `0724a12 Initial commit` |
| Early branch visible | `origin/feature-final-matrix-os` with `1fe1386 Initial working version of Matrix OS with all features` |
| Early TUI implementation branch visible | `origin/claude/matrix-os-python-tui-011CV2PhfQfWRPCVbXYKSiQ1` |
| Early design comparison branch visible | `origin/claude/matrix-os-ui-design-comparison-011CV5dNAePdv7fjnr4ABzKW` |
| Package name | `matrix-os` in `pyproject.toml` |
| Entrypoints | `matrix-os`, `mxos`, `matrix-cli` in `pyproject.toml` |
| Original Matrix UI app shell present | `src/core/app.py` |
| Original Matrix UI widgets present | `src/ui/widgets/matrix_rain.py`, file browser, terminal, process monitor, code editor, split pane, monitoring dashboard |
| Historical TUI analysis present | `ANALYSIS_MATRIX_OS_TUI.md` |
| UI design comparison docs present | `docs/UI_DESIGN_COMPARISON.md` |

## Uncertain / UNKNOWN facts

| Claim | Status | Reason |
|---|---|---|
| Matrix OS was forked from a Pi repository | UNKNOWN | current Git remotes show only `WietRob/matrix-os`; no Pi upstream remote was present in inspected checkout |
| Matrix OS descends from a Raspberry Pi harness foundation | UNKNOWN | no inspected commit, remote, package metadata, or docs proved Raspberry Pi lineage |
| Original root authorship beyond visible git history | UNKNOWN | would require full remote/old-local backup/commit metadata review beyond current evidence |
| Whether `origin/feature-final-matrix-os` predates `main` root in an external repo | UNKNOWN | visible local history shows the branch but not an external upstream/fork relation |

## What would be needed to prove Pi/fork lineage

- old Git remotes or reflogs showing a Pi/upstream URL,
- archived clone from the Raspberry Pi with matching commit ancestry,
- signed/tagged releases or commit metadata tying Matrix OS to the Pi foundation,
- original README/history from the alleged source repository,
- explicit migration notes in docs or issues.

## Original Matrix UI foundation status

Confirmed present and preserved:

```text
src/core/app.py
src/ui/widgets/matrix_rain.py
src/ui/widgets/file_browser.py
src/ui/widgets/terminal.py
src/ui/widgets/process_monitor.py
src/ui/widgets/code_editor.py
src/ui/widgets/split_pane.py
src/ui/themes/matrix.tcss
```

The current CLI/harness architecture preserves this basis through `curaops.harness.scaffolding` and `docs/MATRIX_OS_UI_VALUE_MAP.md`.

## Future harness preservation

The future Gateway/Harness architecture preserves the Matrix UI basis by treating it as an `EditorSurfaceDescriptor` / display host rather than replacing it. The generic gateway descriptors allow Hermes, OpenCode, Zed/MCP, local shell, peekxd, and future evidence producers to remain external and attach through explicit adapter contracts.

## Provenance conclusion

The original Matrix UI/TUI foundation is confirmed present in this repository. A Pi/fork origin is not proven from the inspected evidence and is therefore UNKNOWN.
