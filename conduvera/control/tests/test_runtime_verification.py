"""
Runtime Verification Tests — beweisen dass CuraOps-Control echte Pfade nutzt.

Nicht nur Mock-basiert. Wo moeglich werden echte Skripte ausgefuehrt
(verify-only, nicht mutierend).
"""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from conduvera.control.scripts_bridge import (
    ScriptRunner, ScriptConfig, ScriptName, MUTATING_SCRIPTS,
    parse_readiness_stdout, ReadinessDecision, ExitCode, VRP_SCRIPTS,
)
from conduvera.control.worktree_sentinel import WorktreeSentinel


# ═══════════════════════════════════════════════════════════════════
# A. CURAOPS_VRP_ROOT konfigurierbar
# ═══════════════════════════════════════════════════════════════════

class TestVrpRootConfigurable:
    """Beweist: Kein hardcoded Home-Pfad mehr."""

    def test_default_fallback(self):
        """Ohne Env-Var: Fallback auf ~/projects/CuraOps_VRP."""
        import importlib
        import conduvera.control.scripts_bridge as sb
        with patch.dict(os.environ, {}, clear=False):
            env = dict(os.environ)
            env.pop("CURAOPS_VRP_ROOT", None)
            with patch.dict(os.environ, env, clear=True):
                importlib.reload(sb)
                assert "CuraOps_VRP" in str(sb.VRP_SCRIPTS)
                assert "scripts" in str(sb.VRP_SCRIPTS)

    def test_env_override(self, tmp_path):
        """Mit CURAOPS_VRP_ROOT: Nutzt den Env-Pfad."""
        import importlib
        import conduvera.control.scripts_bridge as sb
        custom = tmp_path / "custom_vrp"
        custom.mkdir()
        with patch.dict(os.environ, {"CURAOPS_VRP_ROOT": str(custom)}):
            importlib.reload(sb)
            assert sb.VRP_SCRIPTS == custom / "scripts"

    def test_scripts_root_in_config(self, tmp_path):
        """ScriptConfig.scripts_root kann den Default uebersteuern."""
        config = ScriptConfig(scripts_root=tmp_path)
        assert config.scripts_root == tmp_path


# ═══════════════════════════════════════════════════════════════════
# B. MUTATING_SCRIPTS Klassifikation
# ═══════════════════════════════════════════════════════════════════

class TestMutatingScriptsClassification:
    """Beweist: Mutierende Skripte sind korrekt klassifiziert."""

    def test_finish_gate_is_mutating(self):
        assert ScriptName.AGENT_FINISH_GATE in MUTATING_SCRIPTS

    def test_sonar_gate_is_mutating(self):
        assert ScriptName.SONAR_AGENT_GATE in MUTATING_SCRIPTS

    def test_class_test_gate_is_mutating(self):
        assert ScriptName.AGENT_CLASS_TEST_GATE in MUTATING_SCRIPTS

    def test_open_pr_is_mutating(self):
        assert ScriptName.AGENT_OPEN_PR in MUTATING_SCRIPTS

    def test_write_evidence_is_mutating(self):
        assert ScriptName.WRITE_AGENT_EVIDENCE in MUTATING_SCRIPTS

    def test_merge_preflight_is_mutating(self):
        assert ScriptName.CAPTAIN_MERGE_PREFLIGHT in MUTATING_SCRIPTS

    def test_sonar_local_is_mutating(self):
        assert ScriptName.SONAR_GATE in MUTATING_SCRIPTS

    def test_agent_status_is_not_mutating(self):
        """agent-status.sh ist nur Status-Abfrage, nicht mutierend."""
        assert ScriptName.AGENT_STATUS not in MUTATING_SCRIPTS

    def test_pr_readiness_is_not_mutating(self):
        """pr-readiness-summary.sh ist nur Verify, nicht mutierend."""
        assert ScriptName.PR_READINESS_SUMMARY not in MUTATING_SCRIPTS


# ═══════════════════════════════════════════════════════════════════
# C. ScriptRunner Sentinel Guard
# ═══════════════════════════════════════════════════════════════════

class TestScriptRunnerSentinelGuard:
    """Beweist: Sentinel blockiert mutierende Skripte bei aktiven Agents."""

    def _make_runner_with_sentinel(self, can_mutate_result: bool):
        sentinel = MagicMock(spec=WorktreeSentinel)
        sentinel.can_mutate.return_value = can_mutate_result
        return ScriptRunner(sentinel=sentinel), sentinel

    def test_mutating_blocked_when_active(self, tmp_path):
        """Aktiver Agent + mutierendes Skript = BLOCKED."""
        runner, sentinel = self._make_runner_with_sentinel(False)
        captain_dir = tmp_path / "captain"
        captain_dir.mkdir()
        script = captain_dir / "agent-finish-gate.sh"
        script.write_text("#!/bin/bash\nexit 0")
        config = ScriptConfig(scripts_root=tmp_path)
        runner._config = config

        result = runner.run("captain/agent-finish-gate.sh", agent_id="Batman")
        assert not result.success
        assert result.exit_code == ExitCode.STREAM_BLOCKED
        assert "BLOCKED" in result.stderr
        sentinel.can_mutate.assert_called_once_with("Batman", "captain/agent-finish-gate.sh")

    def test_mutating_allowed_when_inactive(self, tmp_path):
        """Inaktiver Agent + mutierendes Skript = erlaubt."""
        runner, sentinel = self._make_runner_with_sentinel(True)
        captain_dir = tmp_path / "captain"
        captain_dir.mkdir()
        script = captain_dir / "agent-finish-gate.sh"
        script.write_text("#!/bin/bash\necho OK")
        os.chmod(script, 0o755)
        config = ScriptConfig(scripts_root=tmp_path)
        runner._config = config

        result = runner.run("captain/agent-finish-gate.sh", agent_id="Batman")
        assert result.success
        sentinel.can_mutate.assert_called_once()

    def test_non_mutating_skips_sentinel(self, tmp_path):
        """Nicht-mutierendes Skript (pr_readiness) fragt Sentinel nicht."""
        runner, sentinel = self._make_runner_with_sentinel(False)
        captain_dir = tmp_path / "captain"
        captain_dir.mkdir()
        script = captain_dir / "pr-readiness-summary.sh"
        script.write_text("#!/bin/bash\necho 'decision=GO'")
        os.chmod(script, 0o755)
        config = ScriptConfig(scripts_root=tmp_path)
        runner._config = config

        result = runner.run("captain/pr-readiness-summary.sh", agent_id="Batman")
        assert result.success
        sentinel.can_mutate.assert_not_called()

    def test_no_agent_id_skips_sentinel(self, tmp_path):
        """Ohne agent_id wird Sentinel nicht gefragt."""
        runner, sentinel = self._make_runner_with_sentinel(False)
        captain_dir = tmp_path / "captain"
        captain_dir.mkdir()
        script = captain_dir / "agent-finish-gate.sh"
        script.write_text("#!/bin/bash\necho OK")
        os.chmod(script, 0o755)
        config = ScriptConfig(scripts_root=tmp_path)
        runner._config = config

        result = runner.run("captain/agent-finish-gate.sh")
        assert result.success
        sentinel.can_mutate.assert_not_called()

    def test_no_sentinel_skips_check(self, tmp_path):
        """Ohne Sentinel im ScriptRunner wird nicht geprueft."""
        runner = ScriptRunner()  # kein sentinel
        captain_dir = tmp_path / "captain"
        captain_dir.mkdir()
        script = captain_dir / "agent-finish-gate.sh"
        script.write_text("#!/bin/bash\necho OK")
        os.chmod(script, 0o755)
        config = ScriptConfig(scripts_root=tmp_path)
        runner._config = config

        result = runner.run("captain/agent-finish-gate.sh", agent_id="Batman")
        assert result.success


# ═══════════════════════════════════════════════════════════════════
# D. Readiness Decision Parsing
# ═══════════════════════════════════════════════════════════════════

class TestReadinessDecisionParsing:
    """Beweist: pr-readiness-summary.sh Output wird korrekt geparst."""

    def test_go_decision(self):
        stdout = "decision=GO\nfinish=pass\nsonar=pass\ntests=pass"
        result = parse_readiness_stdout(stdout)
        assert result.is_go
        assert result.decision == "GO"
        assert result.details["finish"] == "pass"

    def test_nogo_decision(self):
        stdout = "decision=NO-GO\nfinish=fail\nsonar=skipped"
        result = parse_readiness_stdout(stdout)
        assert not result.is_go
        assert result.decision == "NO-GO"

    def test_empty_stdout_is_nogo(self):
        result = parse_readiness_stdout("")
        assert not result.is_go
        assert result.decision == "NO-GO"

    def test_partial_output(self):
        stdout = "finish=pass\nsonar=pass"
        result = parse_readiness_stdout(stdout)
        assert not result.is_go  # kein decision=GO


# ═══════════════════════════════════════════════════════════════════
# E. Echte Legacy-Script-Existenz
# ═══════════════════════════════════════════════════════════════════

class TestLegacyScriptExistence:
    """Beweist: Alle 9 kanonischen Skripte existieren."""

    @pytest.fixture
    def vrp_scripts(self):
        path = Path(os.environ.get(
            "CURAOPS_VRP_ROOT",
            str(Path.home() / "projects" / "CuraOps_VRP"),
        )) / "scripts"
        return path

    @pytest.mark.skipif(
        not Path(os.environ.get("CURAOPS_VRP_ROOT", str(Path.home() / "projects" / "CuraOps_VRP"))).exists(),
        reason="CuraOps_VRP nicht vorhanden"
    )
    def test_all_9_scripts_exist(self, vrp_scripts):
        scripts = [
            "agent/agent-status.sh",
            "captain/agent-finish-gate.sh",
            "captain/sonar-agent-gate.sh",
            "captain/pr-readiness-summary.sh",
            "captain/write-agent-evidence.sh",
            "sonar-gate.sh",
            "agent/agent-class-test-gate.sh",
            "agent/agent-open-pr.sh",
            "agent/captain-merge-preflight.sh",
        ]
        for s in scripts:
            assert (vrp_scripts / s).exists(), f"Missing: {s}"


# ═══════════════════════════════════════════════════════════════════
# F. Launcher Dry-Run
# ═══════════════════════════════════════════════════════════════════

class TestLauncherDryRun:
    """Beweist: Dry-Run zeigt Env ohne echte Session."""

    def test_dry_run_returns_env(self):
        from conduvera.control.launcher import AgentLauncher
        from conduvera.control.registry import AgentRegistry, AgentRecord, AgentStatus
        from conduvera.control.stream_state import StreamStateStore
        from conduvera.control.eventlog import EventLog
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ctrl = Path(tmp) / ".conduvera" / "control"
            ctrl.mkdir(parents=True)

            registry = AgentRegistry(control_dir=ctrl)
            registry.register(AgentRecord(
                agent_id="TestBot",
                tool="manual",
                task="TASK-001",
                worktree="",
                gate_profile="default",
                status=AgentStatus.BOOTING,
            ))

            stream = StreamStateStore(control_dir=ctrl)
            sentinel = MagicMock()
            sentinel.can_mutate.return_value = True
            eventlog = EventLog(control_dir=ctrl)

            launcher = AgentLauncher(
                registry=registry,
                stream_store=stream,
                sentinel=sentinel,
                event_log=eventlog,
                gateway_base_url="http://127.0.0.1:8900/v1",
            )

            result = launcher.launch("TestBot", dry_run=True)

            assert result.success
            assert "dry-run" in result.session_ref
            assert "DRY-RUN" in result.warnings[-1]
            assert result.env_set["OPENAI_BASE_URL"] == "http://127.0.0.1:8900/v1"
            assert result.env_set["X_GATEWAY_CLIENT"] == "TestBot"
            assert result.env_set["AGENT_ID"] == "TestBot"

    def test_dry_run_with_profile(self):
        from conduvera.control.launcher import AgentLauncher
        from conduvera.control.registry import AgentRegistry, AgentRecord, AgentStatus
        from conduvera.control.stream_state import StreamStateStore
        from conduvera.control.eventlog import EventLog
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ctrl = Path(tmp) / ".conduvera" / "control"
            ctrl.mkdir(parents=True)

            registry = AgentRegistry(control_dir=ctrl)
            registry.register(AgentRecord(
                agent_id="TestBot",
                tool="manual",
                task="TASK-001",
                worktree="",
                gate_profile="default",
                status=AgentStatus.BOOTING,
            ))

            stream = StreamStateStore(control_dir=ctrl)
            sentinel = MagicMock()
            sentinel.can_mutate.return_value = True
            eventlog = EventLog(control_dir=ctrl)

            launcher = AgentLauncher(
                registry=registry,
                stream_store=stream,
                sentinel=sentinel,
                event_log=eventlog,
            )

            result = launcher.launch(
                "TestBot",
                dry_run=True,
                gateway_profile="local_deep",
                sensitive_class="private_repo",
            )

            assert result.success
            assert result.env_set["GATEWAY_PROFILE"] == "local_deep"
            assert result.env_set["SENSITIVE_CLASS"] == "private_repo"
