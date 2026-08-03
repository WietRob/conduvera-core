"""Canonical Schema Tests v0.19

Testet:
1. directive_file wird als spec verwendet
2. directive_required=true blockiert fehlende directive
3. Researcher canonical schema pass
4. Researcher missing schema fail
5. Researcher missing Safety fail
6. Researcher missing Snapshot fail
7. Dreamer canonical schema pass
8. Dreamer heading drift egal, weil slug/priority/epic Felder zaehlen
9. Dreamer missing rollback fail
10. Dreamer forbidden slug fail
11. Compliance retry Researcher pass ohne manuellen State-Fix
12. Compliance retry Dreamer pass stoppt nach DREAMER
13. Generic body bei directive_required=true verboten
14. stop_after_phase bleibt aktiv
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.home() / ".hermes/scripts"))

import peekxd_buildroom_loop_v19 as v19
from peekxd_buildroom_loop_v19 import BuildroomOrchestrator


def make_orchestrator(tmp_path, state_overrides=None):
    state_path = Path(tmp_path) / "orchestrator-state.json"
    evidence_dir = Path(tmp_path) / "evidence"

    with patch.object(v19, "STATE_FILE", state_path):
        with patch.object(v19, "EVIDENCE_DIR", evidence_dir):
            o = BuildroomOrchestrator()

    base_state = {
        "cycle": 21,
        "phase": "RESEARCHER",
        "status": "NEXT_CYCLE",
        "mode": "RESEARCHER_DREAMER_ONLY",
        "stop_after_phase": "DREAMER",
        "compliance_required": True,
        "directive_required": True,
        "canonical_schema_required": True,
        "directive_file": None,
        "strategy_file": None,
        "current_candidate": None,
        "pr_open": None,
        "task_ids": {},
        "attempts": {},
        "compliance_retries": {},
    }
    if state_overrides:
        base_state.update(state_overrides)
    o.state = base_state
    return o, state_path, evidence_dir


def write_evidence(evidence_dir, phase, cycle, content):
    d = evidence_dir / phase
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{phase}-cycle-{cycle}-20260626.md"
    p.write_text(content)
    return p


class TestDirectiveFileAsSpec:
    """Test 1: directive_file wird als spec verwendet."""

    def test_directive_file_used_as_spec(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        spec_file = tmp_path / "cycle-17-v0.4.0-spec.md"
        spec_file.write_text("# Spec\nSafety Moat first.\n")
        o.state["directive_file"] = str(spec_file)
        directive = o.load_cycle_directive(21)
        assert directive.get("spec") is not None
        assert "Safety Moat first" in directive["spec"]

    def test_no_cycle_spec_uses_directive_file(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        spec_file = tmp_path / "my-spec.md"
        spec_file.write_text("# Custom Directive\nSnapshot core.\n")
        o.state["directive_file"] = str(spec_file)
        directive = o.load_cycle_directive(21)
        assert directive.get("spec") is not None
        assert "Snapshot core" in directive["spec"]


class TestDirectiveRequiredStrict:
    """Test 2: directive_required=true blockiert fehlende directive."""

    def test_missing_directive_blocked(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        body = o.build_researcher_body(21, {})
        assert body == "__BLOCKED_MISSING_DIRECTIVE__"

    def test_dreamer_missing_directive_blocked(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        body = o.build_dreamer_body(21, "", {})
        assert body == "__BLOCKED_MISSING_DIRECTIVE__"

    def test_directive_present_allows_body(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        body = o.build_researcher_body(21, {"spec": "# Directive\n"})
        assert body != "__BLOCKED_MISSING_DIRECTIVE__"
        assert "STRATEGIC MISSION" in body


class TestResearcherCanonicalSchema:
    """Tests 3-6: Researcher schema validation."""

    def test_researcher_schema_pass(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 21, """
## Buildroom Schema
schema: researcher-evidence-v1
cycle: 21
directive_required: true
compliance_required: true

## Directive Compliance
directive_used: true
covered_epics:
  safety_moat_mcp: true
  snapshot_element_id: true
  atspi_action_first: true
  wayland_wslg: true
non_compliant_tactical_findings: 0

## Findings by Epic

### Epic 1 — Safety-Moat MCP-Exposition
#### Finding R1
affected_epic: safety_moat_mcp
file_refs:
  - peekxd/mcp_server.py:42
  - peekxd/core/safety.py:10
#### Finding R2
#### Finding R3
#### Finding R4
#### Finding R5
#### Finding R6
#### Finding R7
#### Finding R8
""")
        data = o.parse_researcher_schema(ev)
        compliant, reason, details = o.validate_researcher_schema(data)
        assert compliant, reason
        assert data["schema"] == "researcher-evidence-v1"

    def test_researcher_missing_schema_fail(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 21, "Some free text without schema.")
        data = o.parse_researcher_schema(ev)
        compliant, reason, details = o.validate_researcher_schema(data)
        assert not compliant
        assert "WRONG_SCHEMA" in reason

    def test_researcher_missing_safety_fail(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 21, """
## Buildroom Schema
schema: researcher-evidence-v1
cycle: 21
directive_used: true
covered_epics:
  snapshot_element_id: true
  atspi_action_first: true
  wayland_wslg: true
non_compliant_tactical_findings: 0

## Findings by Epic
### Epic 2
#### Finding R1
#### Finding R2
#### Finding R3
#### Finding R4
#### Finding R5
#### Finding R6
#### Finding R7
#### Finding R8
""")
        data = o.parse_researcher_schema(ev)
        compliant, reason, details = o.validate_researcher_schema(data)
        assert not compliant
        assert "MISSING_SAFETY" in reason

    def test_researcher_missing_snapshot_fail(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "researcher", 21, """
## Buildroom Schema
schema: researcher-evidence-v1
cycle: 21
directive_used: true
covered_epics:
  safety_moat_mcp: true
  atspi_action_first: true
  wayland_wslg: true
non_compliant_tactical_findings: 0

## Findings by Epic
### Epic 1
#### Finding R1
#### Finding R2
#### Finding R3
#### Finding R4
#### Finding R5
#### Finding R6
#### Finding R7
#### Finding R8
""")
        data = o.parse_researcher_schema(ev)
        compliant, reason, details = o.validate_researcher_schema(data)
        assert not compliant
        assert "MISSING_SNAPSHOT" in reason


class TestDreamerCanonicalSchema:
    """Tests 7-10: Dreamer schema validation."""

    def test_dreamer_schema_pass(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 21, """
## Buildroom Schema
schema: dreamer-candidates-v1
cycle: 21
source_researcher_evidence: /path/to/evidence.md

## Epic Coverage
| Epic | Covered | Candidates |
|---|---:|---|
| safety_moat_mcp | true | D1, D2 |
| snapshot_element_id | true | D3 |
| atspi_action_first | true | D4 |
| wayland_wslg | true | D5 |

## Candidates

### Candidate D1
slug: mcp-action-safetyguard-gateway
priority: GREEN
epic: safety_moat_mcp
title: Safety middleware
source_finding: R1
expected_files:
  - peekxd/mcp_server.py
  - peekxd/core/safety.py
acceptance_criteria:
  - AC1
  - AC2
tests:
  - test_safety
  - test_mcp
risk: low
effort: medium
rollback: revert middleware registration

### Candidate D2
slug: safety-audit-export
priority: GREEN
epic: safety_moat_mcp
title: Audit export
source_finding: R2
expected_files:
  - peekxd/core/audit.py
acceptance_criteria:
  - AC1
tests:
  - test_audit
risk: low
effort: low
rollback: remove export endpoint

### Candidate D3
slug: snapshot-store-skeleton
priority: GREEN
epic: snapshot_element_id
title: Snapshot store
source_finding: R3
expected_files:
  - peekxd/inspection/detector.py
acceptance_criteria:
  - AC1
tests:
  - test_snapshot
risk: medium
effort: medium
rollback: remove store module

### Candidate D4
slug: atspi-set-value
priority: YELLOW
epic: atspi_action_first
title: AT-SPI set-value
source_finding: R4
expected_files:
  - peekxd/input/atspi.py
acceptance_criteria:
  - AC1
tests:
  - test_atspi
risk: medium
effort: high
rollback: fallback to synthetic input

### Candidate D5
slug: wayland-grim-path
priority: YELLOW
epic: wayland_wslg
title: Wayland grim path
source_finding: R5
expected_files:
  - peekxd/input/wayland.py
acceptance_criteria:
  - AC1
tests:
  - test_wayland
risk: low
effort: low
rollback: revert path change

### Candidate D6
slug: wslg-socket-fix
priority: YELLOW
epic: wayland_wslg
title: WSLg socket
source_finding: R6
expected_files:
  - peekxd/input/wayland.py
acceptance_criteria:
  - AC1
tests:
  - test_wslg
risk: low
effort: low
rollback: revert socket path
""")
        data = o.parse_dreamer_schema(ev)
        compliant, reason, details = o.validate_dreamer_schema(data)
        assert compliant, reason
        assert data["schema"] == "dreamer-candidates-v1"
        assert details["green_count"] == 3

    def test_dreamer_heading_drift_irrelevant(self, tmp_path):
        """Test 8: Heading format drift doesn't matter — key-value fields count."""
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 21, """
## Buildroom Schema
schema: dreamer-candidates-v1
cycle: 21

## Epic Coverage
safety_moat_mcp: true
snapshot_element_id: true
atspi_action_first: true
wayland_wslg: true

## Candidates

### D1
slug: mcp-action-safetyguard-gateway
priority: GREEN
epic: safety_moat_mcp
title: Safety middleware
source_finding: R1
expected_files:
  - peekxd/mcp_server.py
tests:
  - test_safety
risk: low
effort: medium
rollback: revert

### D2
slug: safety-audit-export
priority: GREEN
epic: safety_moat_mcp
title: Audit export
source_finding: R2
expected_files:
  - peekxd/core/audit.py
tests:
  - test_audit
risk: low
effort: low
rollback: remove

### D3
slug: snapshot-store-skeleton
priority: GREEN
epic: snapshot_element_id
title: Snapshot store
source_finding: R3
expected_files:
  - peekxd/inspection/detector.py
tests:
  - test_snapshot
risk: medium
effort: medium
rollback: remove

### D4
slug: atspi-set-value
priority: YELLOW
epic: atspi_action_first
title: AT-SPI set-value
source_finding: R4
expected_files:
  - peekxd/input/atspi.py
tests:
  - test_atspi
risk: medium
effort: high
rollback: fallback

### D5
slug: wayland-grim-path
priority: YELLOW
epic: wayland_wslg
title: Wayland grim path
source_finding: R5
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wayland
risk: low
effort: low
rollback: revert

### D6
slug: wslg-socket-fix
priority: YELLOW
epic: wayland_wslg
title: WSLg socket
source_finding: R6
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wslg
risk: low
effort: low
rollback: revert
""")
        data = o.parse_dreamer_schema(ev)
        compliant, reason, details = o.validate_dreamer_schema(data)
        assert compliant, reason
        assert len(data["candidates"]) == 6

    def test_dreamer_missing_rollback_fail(self, tmp_path):
        """Test 9: Missing rollback field fails."""
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 21, """
## Buildroom Schema
schema: dreamer-candidates-v1
cycle: 21

## Candidates

### D1
slug: mcp-action-safetyguard-gateway
priority: GREEN
epic: safety_moat_mcp
title: Safety middleware
source_finding: R1
expected_files:
  - peekxd/mcp_server.py
tests:
  - test_safety
risk: low
effort: medium

### D2
slug: safety-audit-export
priority: GREEN
epic: safety_moat_mcp
title: Audit export
source_finding: R2
expected_files:
  - peekxd/core/audit.py
tests:
  - test_audit
risk: low
effort: low
rollback: remove

### D3
slug: snapshot-store-skeleton
priority: GREEN
epic: snapshot_element_id
title: Snapshot store
source_finding: R3
expected_files:
  - peekxd/inspection/detector.py
tests:
  - test_snapshot
risk: medium
effort: medium
rollback: remove

### D4
slug: atspi-set-value
priority: YELLOW
epic: atspi_action_first
title: AT-SPI set-value
source_finding: R4
expected_files:
  - peekxd/input/atspi.py
tests:
  - test_atspi
risk: medium
effort: high
rollback: fallback

### D5
slug: wayland-grim-path
priority: YELLOW
epic: wayland_wslg
title: Wayland grim path
source_finding: R5
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wayland
risk: low
effort: low
rollback: revert

### D6
slug: wslg-socket-fix
priority: YELLOW
epic: wayland_wslg
title: WSLg socket
source_finding: R6
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wslg
risk: low
effort: low
rollback: revert
""")
        data = o.parse_dreamer_schema(ev)
        compliant, reason, details = o.validate_dreamer_schema(data)
        assert not compliant
        assert "MISSING_ROLLBACK" in reason

    def test_dreamer_forbidden_slug_fail(self, tmp_path):
        """Test 10: Forbidden slug fails."""
        o, state_path, ed = make_orchestrator(tmp_path)
        ev = write_evidence(ed, "dreamer", 21, """
## Buildroom Schema
schema: dreamer-candidates-v1
cycle: 21

## Candidates

### D1
slug: green
priority: GREEN
epic: safety_moat_mcp
title: Bad slug
source_finding: R1
expected_files:
  - peekxd/mcp_server.py
tests:
  - test_safety
risk: low
effort: medium
rollback: revert

### D2
slug: safety-audit-export
priority: GREEN
epic: safety_moat_mcp
title: Audit export
source_finding: R2
expected_files:
  - peekxd/core/audit.py
tests:
  - test_audit
risk: low
effort: low
rollback: remove

### D3
slug: snapshot-store-skeleton
priority: GREEN
epic: snapshot_element_id
title: Snapshot store
source_finding: R3
expected_files:
  - peekxd/inspection/detector.py
tests:
  - test_snapshot
risk: medium
effort: medium
rollback: remove

### D4
slug: atspi-set-value
priority: YELLOW
epic: atspi_action_first
title: AT-SPI set-value
source_finding: R4
expected_files:
  - peekxd/input/atspi.py
tests:
  - test_atspi
risk: medium
effort: high
rollback: fallback

### D5
slug: wayland-grim-path
priority: YELLOW
epic: wayland_wslg
title: Wayland grim path
source_finding: R5
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wayland
risk: low
effort: low
rollback: revert

### D6
slug: wslg-socket-fix
priority: YELLOW
epic: wayland_wslg
title: WSLg socket
source_finding: R6
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wslg
risk: low
effort: low
rollback: revert
""")
        data = o.parse_dreamer_schema(ev)
        compliant, reason, details = o.validate_dreamer_schema(data)
        assert not compliant
        assert "FORBIDDEN_SLUG" in reason


class TestComplianceRetryFlow:
    """Tests 11-12: Retry flow without manual state fix."""

    def test_researcher_retry_compliant_transitions_directly(self, tmp_path):
        """Test 11: Researcher retry compliant → transitions to DREAMER inline."""
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER",
            "status": "RETRYING_COMPLIANCE",
            "task_ids": {"RESEARCHER": "t_r_done"},
            "compliance_retries": {"RESEARCHER": 1},
        })
        ev = write_evidence(ed, "researcher", 21, """
## Buildroom Schema
schema: researcher-evidence-v1
cycle: 21
directive_used: true
covered_epics:
  safety_moat_mcp: true
  snapshot_element_id: true
  atspi_action_first: true
  wayland_wslg: true
non_compliant_tactical_findings: 0

## Findings by Epic
### Epic 1
#### Finding R1
#### Finding R2
#### Finding R3
#### Finding R4
#### Finding R5
#### Finding R6
#### Finding R7
#### Finding R8
""")

        with patch.object(o, 'check_phase_complete', return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, 'check_any_evidence', return_value=(True, ev)):
                with patch.object(o, 'safety_checks', return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []
                }):
                    with patch.object(o, 'should_stop_after_phase', return_value=False):
                        with patch.object(o, 'save_state') as mock_save:
                            o.run()
                            # After run, state should be DREAMER/NEXT_PHASE
                            assert o.state["phase"] == "DREAMER"
                            assert o.state["status"] == "NEXT_PHASE"

    def test_dreamer_retry_compliant_stops_after_dreamer(self, tmp_path):
        """Test 12: Dreamer retry compliant → STOPPED_AFTER_DREAMER inline."""
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "DREAMER",
            "status": "RETRYING_COMPLIANCE",
            "task_ids": {"DREAMER": "t_d_done"},
            "compliance_retries": {"DREAMER": 1},
        })
        ev = write_evidence(ed, "dreamer", 21, """
## Buildroom Schema
schema: dreamer-candidates-v1
cycle: 21

## Candidates

### D1
slug: mcp-action-safetyguard-gateway
priority: GREEN
epic: safety_moat_mcp
title: Safety middleware
source_finding: R1
expected_files:
  - peekxd/mcp_server.py
tests:
  - test_safety
risk: low
effort: medium
rollback: revert

### D2
slug: safety-audit-export
priority: GREEN
epic: safety_moat_mcp
title: Audit export
source_finding: R2
expected_files:
  - peekxd/core/audit.py
tests:
  - test_audit
risk: low
effort: low
rollback: remove

### D3
slug: snapshot-store-skeleton
priority: GREEN
epic: snapshot_element_id
title: Snapshot store
source_finding: R3
expected_files:
  - peekxd/inspection/detector.py
tests:
  - test_snapshot
risk: medium
effort: medium
rollback: remove

### D4
slug: atspi-set-value
priority: YELLOW
epic: atspi_action_first
title: AT-SPI set-value
source_finding: R4
expected_files:
  - peekxd/input/atspi.py
tests:
  - test_atspi
risk: medium
effort: high
rollback: fallback

### D5
slug: wayland-grim-path
priority: YELLOW
epic: wayland_wslg
title: Wayland grim path
source_finding: R5
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wayland
risk: low
effort: low
rollback: revert

### D6
slug: wslg-socket-fix
priority: YELLOW
epic: wayland_wslg
title: WSLg socket
source_finding: R6
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wslg
risk: low
effort: low
rollback: revert
""")

        with patch.object(o, 'check_phase_complete', return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, 'check_any_evidence', return_value=(True, ev)):
                with patch.object(o, 'safety_checks', return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []
                }):
                    with patch.object(o, 'should_stop_after_phase', return_value=True):
                        with patch.object(o, 'enter_stopped_state') as mock_stop:
                            o.run()
                            mock_stop.assert_called_once_with("DREAMER")


class TestGenericBodyBlocked:
    """Test 13: Generic body bei directive_required=true verboten."""

    def test_generic_body_blocked(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path)
        body = o.build_researcher_body(21, {})
        assert body == "__BLOCKED_MISSING_DIRECTIVE__"

    def test_generic_body_allowed_without_directive_required(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {"directive_required": False})
        body = o.build_researcher_body(21, {})
        assert body != "__BLOCKED_MISSING_DIRECTIVE__"
        assert "Analyze the PeekXD codebase" in body


class TestStopAfterPhaseActive:
    """Test 14: stop_after_phase bleibt aktiv."""

    def test_stop_after_researcher(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "RESEARCHER",
            "status": "WAITING",
            "stop_after_phase": "RESEARCHER",
        })
        ev = write_evidence(ed, "researcher", 21, """
## Buildroom Schema
schema: researcher-evidence-v1
cycle: 21
directive_used: true
covered_epics:
  safety_moat_mcp: true
  snapshot_element_id: true
  atspi_action_first: true
  wayland_wslg: true
non_compliant_tactical_findings: 0

## Findings by Epic
### Epic 1
#### Finding R1
#### Finding R2
#### Finding R3
#### Finding R4
#### Finding R5
#### Finding R6
#### Finding R7
#### Finding R8
""")

        with patch.object(o, 'check_phase_complete', return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, 'check_any_evidence', return_value=(True, ev)):
                with patch.object(o, 'safety_checks', return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []
                }):
                    with patch.object(o, 'enter_stopped_state') as mock_stop:
                        o.run()
                        mock_stop.assert_called_once_with("RESEARCHER")

    def test_stop_after_dreamer(self, tmp_path):
        o, state_path, ed = make_orchestrator(tmp_path, {
            "phase": "DREAMER",
            "status": "WAITING",
            "stop_after_phase": "DREAMER",
        })
        ev = write_evidence(ed, "dreamer", 21, """
## Buildroom Schema
schema: dreamer-candidates-v1
cycle: 21

## Candidates

### D1
slug: mcp-action-safetyguard-gateway
priority: GREEN
epic: safety_moat_mcp
title: Safety middleware
source_finding: R1
expected_files:
  - peekxd/mcp_server.py
tests:
  - test_safety
risk: low
effort: medium
rollback: revert

### D2
slug: safety-audit-export
priority: GREEN
epic: safety_moat_mcp
title: Audit export
source_finding: R2
expected_files:
  - peekxd/core/audit.py
tests:
  - test_audit
risk: low
effort: low
rollback: remove

### D3
slug: snapshot-store-skeleton
priority: GREEN
epic: snapshot_element_id
title: Snapshot store
source_finding: R3
expected_files:
  - peekxd/inspection/detector.py
tests:
  - test_snapshot
risk: medium
effort: medium
rollback: remove

### D4
slug: atspi-set-value
priority: YELLOW
epic: atspi_action_first
title: AT-SPI set-value
source_finding: R4
expected_files:
  - peekxd/input/atspi.py
tests:
  - test_atspi
risk: medium
effort: high
rollback: fallback

### D5
slug: wayland-grim-path
priority: YELLOW
epic: wayland_wslg
title: Wayland grim path
source_finding: R5
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wayland
risk: low
effort: low
rollback: revert

### D6
slug: wslg-socket-fix
priority: YELLOW
epic: wayland_wslg
title: WSLg socket
source_finding: R6
expected_files:
  - peekxd/input/wayland.py
tests:
  - test_wslg
risk: low
effort: low
rollback: revert
""")

        with patch.object(o, 'check_phase_complete', return_value=(True, "TASK_DONE_AND_EVIDENCE")):
            with patch.object(o, 'check_any_evidence', return_value=(True, ev)):
                with patch.object(o, 'safety_checks', return_value={
                    "main_green": True, "open_prs": True,
                    "active_builders": True, "no_revert_policy": True,
                    "no_revert_missing_profiles": []
                }):
                    with patch.object(o, 'enter_stopped_state') as mock_stop:
                        o.run()
                        mock_stop.assert_called_once_with("DREAMER")
