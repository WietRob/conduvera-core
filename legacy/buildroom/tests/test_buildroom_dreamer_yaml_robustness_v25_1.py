"""v0.25.1 Dreamer YAML Robustness Tests."""

import json, sys, tempfile, textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))
import peekxd_buildroom_loop_v20 as v20
from peekxd_buildroom_loop_v20 import BuildroomOrchestrator

MAX_RETRIES = 3
v20.MAX_COMPLIANCE_RETRIES = MAX_RETRIES


def _setup(tmpdir, extra_state=None):
    state_path = Path(tmpdir) / "orchestrator-state.json"
    patcher = patch.object(v20, "STATE_FILE", state_path)
    patcher.start()
    e_patcher = patch.object(v20, "EVIDENCE_DIR", Path(tmpdir))
    e_patcher.start()
    o = BuildroomOrchestrator()
    o.state.update({"cycle": 35, "phase": "DREAMER", "status": "WAITING",
        "canonical_schema_required": True, "compliance_required": True,
        "task_ids": {"RESEARCHER": "t_r_done", "DREAMER": "t_d_done"},
        "compliance_retries": {}})
    if extra_state:
        o.state.update(extra_state)
    return o, patcher, e_patcher


def _write_evidence(tmpdir, name, content):
    p = Path(tmpdir) / name / f"{name}-cycle-35-test.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


ADVERSE = textwrap.dedent("""\
```buildroom-dreamer-v1
schema: dreamer-candidates-v1
cycle: 35
epic_coverage:
  safety_moat_mcp: true
  snapshot_element_id: true
  atspi_action_first: true
  wayland_wslg: true
candidates:
  - id: D1
    slug: snapshot-store-ttl-cache
    priority: GREEN
    epic: snapshot_element_id
    title: SnapshotStore TTL cache
    source_finding: R1
    summary: SnapshotStore: TTL cache for semantic diff
    expected_files:
      - peekxd/snapshot/store.py
    acceptance_criteria:
      - Hit/miss from cache metadata
    tests:
      - tests/test_snapshot_cache.py
    risk: low
    effort: medium
    rollback: revert
```
""")

VALID_QUOTED = textwrap.dedent("""\
```buildroom-dreamer-v1
schema: dreamer-candidates-v1
cycle: 35
epic_coverage:
  safety_moat_mcp: true
  snapshot_element_id: true
  atspi_action_first: true
  wayland_wslg: true
candidates:
  - id: D1
    slug: snapshot-store-ttl-cache
    priority: GREEN
    epic: snapshot_element_id
    title: SnapshotStore TTL cache
    source_finding: R1
    summary: "SnapshotStore: TTL cache for semantic diff"
    expected_files:
      - peekxd/snapshot/store.py
    acceptance_criteria:
      - "Hit/miss from cache metadata"
    tests:
      - tests/test_snapshot_cache.py
    risk: low
    effort: medium
    rollback: revert
  - id: D2
    slug: atspi-set-value
    priority: GREEN
    epic: atspi_action_first
    title: AT-SPI set value
    source_finding: R2
    expected_files:
          - fake/file.py
    acceptance_criteria: []
    tests:
          - tests/fake.py
    risk: low
    effort: medium
    rollback: revert
  - id: D3
    slug: wayland-wtype-path
    priority: GREEN
    epic: wayland_wslg
    title: Wayland wtype path
    source_finding: R3
    expected_files:
          - fake/file.py
    acceptance_criteria: []
    tests:
          - tests/fake.py
    risk: low
    effort: low
    rollback: revert
  - id: D4
    slug: mcp-safety-middleware
    priority: GREEN
    epic: safety_moat_mcp
    title: MCP Safety middleware
    source_finding: R4
    expected_files:
          - fake/file.py
    acceptance_criteria: []
    tests:
          - tests/fake.py
    risk: medium
    effort: high
    rollback: remove
  - id: D5
    slug: wslg-socket-uid
    priority: YELLOW
    epic: wayland_wslg
    title: WSLg socket UID
    source_finding: R5
    expected_files:
          - fake/file.py
    acceptance_criteria: []
    tests:
          - tests/fake.py
    risk: low
    effort: low
    rollback: revert
  - id: D6
    slug: audit-trail-export
    priority: YELLOW
    epic: safety_moat_mcp
    title: Audit trail export
    source_finding: R6
    expected_files:
          - fake/file.py
    acceptance_criteria: []
    tests:
          - tests/fake.py
    risk: low
    effort: low
    rollback: remove
```
""")


class TestDreamerSOULYamlQuoting:

    def test_soul_contains_yaml_quoting_hard_rule(self):
        soul = Path.home() / ".hermes/profiles/dreamer/SOUL.md"
        text = soul.read_text()
        assert "YAML QUOTING HARD RULE" in text
        assert "double quotes" in text.lower()
        assert "ScannerError" in text

    def test_soul_example_shows_quoted_values(self):
        soul = Path.home() / ".hermes/profiles/dreamer/SOUL.md"
        text = soul.read_text()
        assert '"MCP click/type/drag' in text


class TestDreamerBodyYamlQuoting:

    def test_body_contains_yaml_quoting_requirement(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        o.state["directive_required"] = True
        o.state["canonical_schema_required"] = True
        body = o.build_dreamer_body(35, "/fake/evidence.md", {"directive_required": True, "spec": "test spec", "strategy_context": "test"})
        assert "YAML QUOTING REQUIREMENT" in body
        assert "double quotes" in body.lower()
        patcher.stop()
        e_patcher.stop()


class TestYamlParseFailure:

    def test_unquoted_colon_fails_parse(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert not compliant
        assert "YAML_PARSE_ERROR" in reason

    def test_parse_failure_does_not_advance_to_builder(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        with patch.object(o, "check_phase_complete", return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, "check_bound_evidence", return_value=(True, ev)):
                with patch.object(o, "safety_checks", return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []}):
                    with patch.object(o, "save_state"):
                        o.run()
        assert o.state["phase"] != "BUILDER"
        patcher.stop()
        e_patcher.stop()

    def test_parse_failure_sets_yaml_retry_status(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        with patch.object(o, "check_phase_complete", return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, "check_bound_evidence", return_value=(True, ev)):
                with patch.object(o, "safety_checks", return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []}):
                    with patch.object(o, "save_state"):
                        with patch.object(o, "_dispatch_compliance_retry"):
                            o.run()
        assert o.state["status"] == "RETRYING_DREAMER_YAML_PARSE"
        patcher.stop()
        e_patcher.stop()

    def test_retry_limit_blocks(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path, {"compliance_retries": {"DREAMER_YAML_PARSE": MAX_RETRIES}})
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        with patch.object(o, "check_phase_complete", return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, "check_bound_evidence", return_value=(True, ev)):
                with patch.object(o, "safety_checks", return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []}):
                    with patch.object(o, "save_state"):
                        o.run()
        assert o.state["status"] == "BLOCKED_DREAMER_YAML_PARSE"
        patcher.stop()
        e_patcher.stop()

    def test_retry_body_includes_parse_error(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert not compliant
        assert "ScannerError" in reason or "mapping values" in reason.lower()

    def test_retry_body_includes_double_quote_instruction(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        guidance = details.get("guidance", "")
        assert "quote" in guidance.lower()

    def test_properly_quoted_parses_successfully(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", VALID_QUOTED)
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert compliant, f"Expected compliant, got reason={reason}"
        patcher.stop()
        e_patcher.stop()

    def test_no_real_kanban_task_spawned(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        compliant, reason, details = o.validate_dreamer_directive_compliance(ev)
        assert not compliant
        patcher.stop()
        e_patcher.stop()

    def test_no_existing_evidence_patched(self, tmp_path):
        o, patcher, e_patcher = _setup(tmp_path)
        ev = _write_evidence(tmp_path, "dreamer", ADVERSE)
        orig = ev.read_text()
        o.validate_dreamer_directive_compliance(ev)
        assert ev.read_text() == orig, "Evidence file was modified!"
        patcher.stop()
        e_patcher.stop()
