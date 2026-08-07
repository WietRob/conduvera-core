"""
Runtime-Enforcement Tests fuer CuraOps-Control.

Beweisen dass das Harness Durchgriff hat:
- BLOCKED Stream + ACK => abgelehnt, nur BLOCKER erlaubt
- READY_FOR_REVIEW braucht head_sha Evidence
- optional Sonar skipped darf GO, wenn Finish/Test gruen
- required Sonar skipped muss NO-GO
- aktiver Agent + pytest/sonar => Worktree Sentinel blockiert
- aktiver Agent + read-only git status => erlaubt
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from conduvera.control.registry import AgentRegistry, AgentRecord, AgentStatus
from conduvera.control.stream_state import (
    StreamStateStore, StreamState, AgentReply,
    InvalidTransitionError, InvalidReplyError,
)
from conduvera.control.worktree_sentinel import WorktreeSentinel
from conduvera.control.eventlog import EventLog
from conduvera.control.launcher import AgentLauncher
from conduvera.control.scripts_bridge import (
    ScriptRunner,
    ScriptConfig,
    parse_readiness_stdout,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_control_dir(tmp_path: Path) -> Path:
    cd = tmp_path / ".conduvera" / "control"
    cd.mkdir(parents=True, exist_ok=True)
    return cd


def _make_stream_dir(tmp_path: Path) -> Path:
    sd = tmp_path / ".captain" / "state"
    sd.mkdir(parents=True, exist_ok=True)
    return sd


def _seed_agent(
    control_dir: Path,
    name: str = "Batman",
    status: AgentStatus = AgentStatus.BOOTING,
) -> AgentRegistry:
    reg = AgentRegistry(control_dir=control_dir)
    reg.register(AgentRecord(
        agent_id=name,
        tool="opencode",
        task="TASK-I198",
        issue=200,
        gate_profile="frontend_ui",
        status=status,
    ))
    return reg


def _seed_stream_to_blocked(stream_dir: Path, agent: str = "Batman") -> StreamStateStore:
    store = StreamStateStore(control_dir=stream_dir)
    store.set_state(agent, StreamState.ASSIGNED)
    store.set_state(agent, StreamState.WORKING)
    store.set_state(agent, StreamState.BLOCKED_EXTERNAL_PLATFORM)
    return store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def control_dir(tmp_path: Path) -> Path:
    return _make_control_dir(tmp_path)


@pytest.fixture()
def stream_dir(tmp_path: Path) -> Path:
    return _make_stream_dir(tmp_path)


@pytest.fixture()
def stream_store(stream_dir: Path) -> StreamStateStore:
    return StreamStateStore(control_dir=stream_dir)


@pytest.fixture()
def launcher(control_dir: Path, stream_dir: Path, tmp_path: Path) -> AgentLauncher:
    registry = _seed_agent(control_dir)
    ss = StreamStateStore(control_dir=stream_dir)
    sentinel = WorktreeSentinel(control_dir=control_dir)
    event_log = EventLog(control_dir=_make_control_dir(tmp_path))
    return AgentLauncher(
        registry=registry,
        stream_store=ss,
        sentinel=sentinel,
        event_log=event_log,
    )


# ===================================================================
# 1) BLOCKED Stream + ACK => abgelehnt, nur BLOCKER erlaubt
# ===================================================================


class TestBlockedStreamEnforcement:

    def test_blocked_state_gesetzt(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.BLOCKED_EXTERNAL_PLATFORM)
        rec = stream_store.get("Batman")
        assert "BLOCKED" in rec.state.value

    def test_blocked_ack_abgelehnt(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.BLOCKED_EXTERNAL_PLATFORM)
        assert stream_store.validate_reply("Batman", AgentReply.ACK) is False

    def test_blocked_blocker_erlaubt(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.BLOCKED_EXTERNAL_PLATFORM)
        assert stream_store.validate_reply("Batman", AgentReply.BLOCKER) is True

    def test_blocked_ready_abgelehnt(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.BLOCKED_EXTERNAL_PLATFORM)
        assert stream_store.validate_reply("Batman", AgentReply.READY) is False

    def test_blocked_accept_reply_raises_on_ack(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.BLOCKED_EXTERNAL_PLATFORM)
        with pytest.raises(InvalidReplyError):
            stream_store.accept_reply("Batman", AgentReply.ACK)

    @patch("conduvera.control.scripts_bridge.subprocess.run")
    def test_script_bridge_rc56(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=56, stdout="", stderr="BLOCKED")
        scripts_dir = tmp_path / "scripts" / "agent"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "agent-status.sh").write_text("#!/bin/bash\nexit 56\n")

        runner = ScriptRunner(config=ScriptConfig(scripts_root=tmp_path / "scripts"))
        result = runner.agent_status("Batman", "ACK")
        assert result.exit_code == 56
        assert result.success is False


# ===================================================================
# 2) READY_FOR_REVIEW braucht head_sha Evidence
# ===================================================================


class TestReadyRequiresEvidence:

    def test_ready_ohne_head_sha_verweigert(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.READY_CANDIDATE)
        with pytest.raises(InvalidTransitionError, match="head_sha"):
            stream_store.set_state("Batman", StreamState.READY_FOR_REVIEW)

    def test_ready_mit_head_sha_erlaubt(self, stream_store: StreamStateStore) -> None:
        stream_store.set_state("Batman", StreamState.ASSIGNED)
        stream_store.set_state("Batman", StreamState.WORKING)
        stream_store.set_state("Batman", StreamState.READY_CANDIDATE)
        rec = stream_store.set_state(
            "Batman", StreamState.READY_FOR_REVIEW, head_sha="abc123",
        )
        assert rec.state == StreamState.READY_FOR_REVIEW
        assert rec.head_sha == "abc123"

    @patch("conduvera.control.scripts_bridge.subprocess.run")
    def test_no_go_ohne_evidence(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="decision=NO-GO\nfinish=missing\ntests=missing",
            stderr="",
        )
        scripts_dir = tmp_path / "scripts" / "captain"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "pr-readiness-summary.sh").write_text("#!/bin/bash\n")

        runner = ScriptRunner(config=ScriptConfig(scripts_root=tmp_path / "scripts"))
        result = runner.pr_readiness()
        decision = parse_readiness_stdout(result.stdout)
        assert decision.is_go is False

    @patch("conduvera.control.scripts_bridge.subprocess.run")
    def test_go_mit_evidence(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="decision=GO\nfinish=pass\ntests=pass\nsonar=pass",
            stderr="",
        )
        scripts_dir = tmp_path / "scripts" / "captain"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "pr-readiness-summary.sh").write_text("#!/bin/bash\n")

        runner = ScriptRunner(config=ScriptConfig(scripts_root=tmp_path / "scripts"))
        result = runner.pr_readiness(verify=True)
        decision = parse_readiness_stdout(result.stdout)
        assert decision.is_go is True


# ===================================================================
# 3) optional Sonar skipped darf GO, wenn Finish/Test gruen
# ===================================================================


class TestOptionalSonarSkipped:

    def test_parse_optional_sonar_go(self) -> None:
        stdout = "decision=GO\nfinish=pass\ntests=pass\nsonar=skipped(optional)"
        decision = parse_readiness_stdout(stdout)
        assert decision.is_go is True
        assert "skipped" in decision.details.get("sonar", "")

    @patch("conduvera.control.scripts_bridge.subprocess.run")
    def test_sonar_optional_rc0(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="sonar: skipped (optional)\nevidence=/tmp/sonar.json",
            stderr="",
        )
        scripts_dir = tmp_path / "scripts" / "captain"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "sonar-agent-gate.sh").write_text("#!/bin/bash\n")

        runner = ScriptRunner(config=ScriptConfig(scripts_root=tmp_path / "scripts"))
        result = runner.sonar_gate(mode="--optional")
        assert result.success is True


# ===================================================================
# 4) required Sonar skipped muss NO-GO
# ===================================================================


class TestRequiredSonarSkipped:

    def test_parse_required_sonar_fail(self) -> None:
        stdout = "decision=NO-GO\nfinish=pass\ntests=pass\nsonar=fail(required)"
        decision = parse_readiness_stdout(stdout)
        assert decision.is_go is False

    @patch("conduvera.control.scripts_bridge.subprocess.run")
    def test_sonar_required_rc1(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="sonar: FAIL quality gate",
            stderr="Quality gate failed",
        )
        scripts_dir = tmp_path / "scripts" / "captain"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "sonar-agent-gate.sh").write_text("#!/bin/bash\n")

        runner = ScriptRunner(config=ScriptConfig(scripts_root=tmp_path / "scripts"))
        result = runner.sonar_gate(mode="--require")
        assert result.success is False
        assert result.exit_code == 1


# ===================================================================
# 5) aktiver Agent + pytest/sonar => Worktree Sentinel blockiert
# ===================================================================


class TestWorktreeSentinelMutationBlocked:

    def _make_sentinel_active(self, tmp_path: Path) -> WorktreeSentinel:
        cd = _make_control_dir(tmp_path)
        _seed_agent(cd, status=AgentStatus.ACTIVE)
        return WorktreeSentinel(control_dir=cd)

    def test_pytest_blockiert(self, tmp_path: Path) -> None:
        sentinel = self._make_sentinel_active(tmp_path)
        assert sentinel.can_mutate("Batman", "pytest") is False

    def test_sonar_blockiert(self, tmp_path: Path) -> None:
        sentinel = self._make_sentinel_active(tmp_path)
        assert sentinel.can_mutate("Batman", "sonar") is False

    def test_formatters_blockiert(self, tmp_path: Path) -> None:
        sentinel = self._make_sentinel_active(tmp_path)
        for op in ["black", "prettier", "npm_install", "git_restore"]:
            assert sentinel.can_mutate("Batman", op) is False, f"{op} sollte blockiert sein"


# ===================================================================
# 6) aktiver Agent + read-only => erlaubt
# ===================================================================


class TestWorktreeSentinelReadOnlyAllowed:

    def _make_sentinel_active(self, tmp_path: Path) -> WorktreeSentinel:
        cd = _make_control_dir(tmp_path)
        _seed_agent(cd, status=AgentStatus.ACTIVE)
        return WorktreeSentinel(control_dir=cd)

    def test_git_status_erlaubt(self, tmp_path: Path) -> None:
        assert self._make_sentinel_active(tmp_path).can_mutate("Batman", "git status") is True

    def test_git_log_erlaubt(self, tmp_path: Path) -> None:
        assert self._make_sentinel_active(tmp_path).can_mutate("Batman", "git log") is True

    def test_git_diff_erlaubt(self, tmp_path: Path) -> None:
        assert self._make_sentinel_active(tmp_path).can_mutate("Batman", "git diff --stat") is True

    def test_cat_ls_find_grep_erlaubt(self, tmp_path: Path) -> None:
        sentinel = self._make_sentinel_active(tmp_path)
        for op in ["cat", "ls", "find", "grep"]:
            assert sentinel.can_mutate("Batman", op) is True, f"{op} sollte erlaubt sein"

    def test_inaktiver_agent_pytest_erlaubt(self, tmp_path: Path) -> None:
        cd = _make_control_dir(tmp_path)
        _seed_agent(cd, status=AgentStatus.STOPPED)
        sentinel = WorktreeSentinel(control_dir=cd)
        assert sentinel.can_mutate("Batman", "pytest") is True


# ===================================================================
# 7) Launcher: BLOCKED => Launch abgelehnt
# ===================================================================


class TestLauncherBlockedAgent:

    def test_blocked_launch_verweigert(self, launcher: AgentLauncher) -> None:
        launcher._stream_store.set_state("Batman", StreamState.ASSIGNED)
        launcher._stream_store.set_state("Batman", StreamState.WORKING)
        launcher._stream_store.set_state("Batman", StreamState.BLOCKED_EXTERNAL_PLATFORM)

        result = launcher.launch("Batman")
        assert result.success is False
        assert "BLOCKED" in result.error


# ===================================================================
# 8) Launcher: Bereits aktiv => Launch abgelehnt
# ===================================================================


class TestLauncherAlreadyActive:

    def test_aktiver_launch_verweigert(self, launcher: AgentLauncher) -> None:
        launcher._registry.update("Batman", status=AgentStatus.ACTIVE, session="tmux:conduvera-Batman")
        result = launcher.launch("Batman")
        assert result.success is False
        assert "bereits aktiv" in result.error


# ===================================================================
# 9) Evidence-Extraktion
# ===================================================================


class TestScriptBridgeEvidence:

    def test_evidence_pfad(self) -> None:
        stdout = "agent-evidence: pass gate=finish evidence=/tmp/finish.json"
        assert ScriptRunner._extract_evidence_path(stdout) == "/tmp/finish.json"

    def test_kein_evidence(self) -> None:
        assert ScriptRunner._extract_evidence_path("some output") is None

    def test_evidence_mehrere_zeilen(self) -> None:
        stdout = "line1\nevidence=/var/sonar.json\nline3"
        assert ScriptRunner._extract_evidence_path(stdout) == "/var/sonar.json"


# ===================================================================
# 10) Readiness-Parser
# ===================================================================


class TestReadinessParser:

    def test_go(self) -> None:
        d = parse_readiness_stdout("decision=GO\nfinish=pass\ntests=pass\nsonar=pass")
        assert d.is_go is True

    def test_no_go(self) -> None:
        d = parse_readiness_stdout("decision=NO-GO\nfinish=pass\ntests=fail")
        assert d.is_go is False
        assert d.details["tests"] == "fail"

    def test_leer(self) -> None:
        d = parse_readiness_stdout("")
        assert d.is_go is False
