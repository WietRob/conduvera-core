"""Tests for the read-only BuildroomLegacyStateReader (strangler slice).

Uses frozen fixtures under tests/buildroom/fixtures/ — NEVER live
~/.hermes state. Verifies the reader's hard constraints: no writes, no
processes, no subprocesses, no secrets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from curaops.buildroom.legacy_state import BuildroomLegacyStateReader
from curaops.evidence.contract import SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_backends_and_projects(fixture_reader):
    result = fixture_reader.read()
    assert result.ok
    snap = result.snapshot
    assert snap is not None
    assert len(snap.backends) == 3
    by_name = {b.backend: b for b in snap.backends}
    assert by_name["native"].enabled is True
    assert by_name["codex_cli"].enabled is False
    assert by_name["codex_cli"].status == "disabled_by_owner"
    assert by_name["opencode_cli"].requires_explicit_owner_activation is True
    assert snap.active_project.active_project_id == "fixture-project"
    assert len(snap.project_packs) == 2
    names = {p.project_name for p in snap.project_packs}
    assert names == {"alpha", "beta"}


def test_emits_mxos_evidence_events(fixture_reader):
    readiness = fixture_reader.read()
    producer = {"name": "test-runner", "version": "0.0.0"}
    events = fixture_reader.emit_events(readiness, producer=producer)
    assert len(events) == 2
    for ev in events:
        assert ev.schema_version == SCHEMA_VERSION
        assert ev.event_hash  # integrity hash present
    types = {ev.event_type for ev in events}
    assert types == {
        "buildroom.legacy.inventory.completed",
        "buildroom.legacy.readiness.completed",
    }
    inventory = next(e for e in events if e.event_type == "buildroom.legacy.inventory.completed")
    assert inventory.payload["project_packs"] == ["alpha", "beta"]
    assert inventory.payload["active_project"] == "fixture-project"
    assert inventory.payload["file_count"] == 4


def test_missing_files_fail_closed(tmp_path):
    reader = BuildroomLegacyStateReader(tmp_path)
    result = reader.read()
    assert result.ok is False
    assert "execution-backends.yaml" in result.missing_files
    assert "state/active-project.json" in result.missing_files


def test_reader_never_invokes_subprocesses():
    import inspect

    src = inspect.getsource(BuildroomLegacyStateReader)
    for forbidden in ("subprocess", "os.system", "Popen", "systemctl", "signal."):
        assert forbidden not in src, f"reader must not use {forbidden}"


def test_reader_never_writes_state():
    import inspect

    src = inspect.getsource(BuildroomLegacyStateReader)
    for forbidden in ("write_text", "write_bytes", "open("):
        assert forbidden not in src, f"reader must not write: {forbidden}"


def test_events_validated_against_envelope(fixture_reader):
    readiness = fixture_reader.read()
    events = fixture_reader.emit_events(readiness, producer={"name": "p", "version": "1"})
    for ev in events:
        d = ev.to_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["integrity"]["algorithm"] == "sha256"
        assert d["event_hash"].startswith("sha256:")


@pytest.fixture
def fixture_reader() -> BuildroomLegacyStateReader:
    assert FIXTURES.is_dir(), f"fixtures missing: {FIXTURES}"
    return BuildroomLegacyStateReader(FIXTURES)
