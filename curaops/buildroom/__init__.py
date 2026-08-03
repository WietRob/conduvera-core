"""Buildroom integration slice (read-only) for Matrix OS.

This package is the FIRST read-only strangler slice: it reads frozen legacy
Buildroom state/config formats from a supplied fixture directory and
normalizes them into Matrix-OS domain types plus MXOS-EVIDENCE-1.0.0 events.

Contract: it NEVER writes Buildroom state, never starts/stops/signals a
process, never invokes git/gh/systemd/Hermes/Codex/OpenCode/Buildroom, never
mutates a repo, and never acquires live execution authority. All paths are
dependency-injected.
"""
