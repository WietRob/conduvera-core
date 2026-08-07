"""
Legacy Script Bridge — Wrapper fuer CuraOps_VRP Captain-Skripte.

Binde bestehende Shell-Skripte als Gate-/Status-Backends ein.
Keine neue Gate-Semantik — Skripte bleiben kanonisch.
Python ist nur Adapter/Orchestrator.

Exit-Code-Konventionen der Skripte:
  0  = Erfolg / GO
  1  = Gate failed / NO-GO
  2  = falsche Args
  3  = verify-only, Evidence fehlt/stale
  5  = ungelesene Captain-Nachrichten
  10-13 = Session-Binding-Fehler (agent-status)
  14 = Worktree nicht clean
  20 = AGENT_ID/TASK_KEY/Dependencies fehlen
  24 = Lock busy / no-preflight ohne Bypass
  25 = detached HEAD
  26 = keine Changes
  30 = git/jq/gh fehlen
  35 = Push fehlgeschlagen
  40 = PR-Erstellung fehlgeschlagen
  50 = Klassifikation ungueltig
  52 = Artefakte fehlen
  53 = Gate-Skript fehlt
  54 = Gate fehlgeschlagen
  55 = Readiness-Skript fehlt
  56 = Stream BLOCKED, nur BLOCKER erlaubt
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Standard-Pfade — konfigurierbar via CURAOPS_VRP_ROOT
# ---------------------------------------------------------------------------

_VRP_ROOT = Path(os.environ.get(
    "CURAOPS_VRP_ROOT",
    str(Path.home() / "projects" / "CuraOps_VRP"),
))
VRP_SCRIPTS = _VRP_ROOT / "scripts"


class ScriptName(str):
    """Kanonische Namen der eingebundenen Skripte."""
    AGENT_STATUS = "agent/agent-status.sh"
    AGENT_FINISH_GATE = "captain/agent-finish-gate.sh"
    SONAR_AGENT_GATE = "captain/sonar-agent-gate.sh"
    PR_READINESS_SUMMARY = "captain/pr-readiness-summary.sh"
    WRITE_AGENT_EVIDENCE = "captain/write-agent-evidence.sh"
    SONAR_GATE = "sonar-gate.sh"
    AGENT_CLASS_TEST_GATE = "agent/agent-class-test-gate.sh"
    AGENT_OPEN_PR = "agent/agent-open-pr.sh"
    CAPTAIN_MERGE_PREFLIGHT = "agent/captain-merge-preflight.sh"


# Skripte, die mutierend sind (Tests, Sonar, PR, Evidence)
MUTATING_SCRIPTS: frozenset = frozenset({
    ScriptName.AGENT_FINISH_GATE,
    ScriptName.SONAR_AGENT_GATE,
    ScriptName.SONAR_GATE,
    ScriptName.AGENT_CLASS_TEST_GATE,
    ScriptName.AGENT_OPEN_PR,
    ScriptName.WRITE_AGENT_EVIDENCE,
    ScriptName.CAPTAIN_MERGE_PREFLIGHT,
})


class ExitCode(IntEnum):
    """Standardisierte Exit-Codes fuer die Bridge."""
    OK = 0
    GATE_FAILED = 1
    BAD_ARGS = 2
    VERIFY_STALE = 3
    UNREAD_MESSAGES = 5
    SESSION_BINDING_INCOMPLETE = 10
    SESSION_FIELDS_MISSING = 12
    SESSION_OFFLINE = 13
    WORKTREE_DIRTY = 14
    CONTEXT_MISSING = 20
    LOCK_BUSY = 24
    DETACHED_HEAD = 25
    NO_CHANGES = 26
    DEPS_MISSING = 30
    PUSH_FAILED = 35
    PR_CREATE_FAILED = 40
    INVALID_CLASSIFICATION = 50
    ARTIFACTS_MISSING = 52
    SCRIPT_MISSING = 53
    GATE_SCRIPT_FAILED = 54
    READINESS_MISSING = 55
    STREAM_BLOCKED = 56


@dataclass(frozen=True)
class ScriptResult:
    """Ergebnis einer Skript-Ausfuehrung."""
    script: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool
    evidence_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "script": self.script,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "success": self.success,
            "evidence_path": self.evidence_path,
        }


@dataclass
class ScriptConfig:
    """Konfiguration fuer die Script-Ausfuehrung."""
    scripts_root: Path = VRP_SCRIPTS
    workdir: Optional[Path] = None
    env_overrides: Dict[str, str] = field(default_factory=dict)
    timeout: int = 300  # 5 Minuten Default-Timeout

    def resolve_script(self, script_name: str) -> Path:
        """Loest einen Skriptnamen zu einem vollen Pfad auf."""
        path = self.scripts_root / script_name
        if not path.exists():
            raise FileNotFoundError(f"Skript nicht gefunden: {path}")
        return path


class ScriptRunner:
    """
    Fuehrt Legacy-Captain-Skripte aus und interprepiert ihre Exit-Codes.

    Keine neue Gate-Semantik. Nur Adapter.

    Vor mutierenden Skripten wird WorktreeSentinel.can_mutate() geprueft,
    sofern ein Agent-Kontext gegeben ist.
    """

    def __init__(
        self,
        config: Optional[ScriptConfig] = None,
        sentinel: Optional[Any] = None,
    ) -> None:
        self._config = config or ScriptConfig()
        self._sentinel = sentinel

    @property
    def config(self) -> ScriptConfig:
        return self._config

    def run(
        self,
        script_name: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        agent_id: Optional[str] = None,
    ) -> ScriptResult:
        """
        Fuehrt ein Skript aus und gibt das Ergebnis zurueck.

        Args:
            script_name: Kanonischer Skriptname (z.B. "captain/agent-finish-gate.sh").
            args: Zusaetzliche Kommandozeilen-Argumente.
            env: Zusaetzliche Environment-Variablen.

        Returns:
            ScriptResult mit Exit-Code, stdout, stderr.
        """
        script_path = self._config.resolve_script(script_name)

        # Sentinel Guard: Mutierende Skripte blockieren wenn Agent aktiv
        if script_name in MUTATING_SCRIPTS and self._sentinel is not None and agent_id:
            if not self._sentinel.can_mutate(agent_id, script_name):
                return ScriptResult(
                    script=script_name,
                    exit_code=ExitCode.STREAM_BLOCKED,
                    stdout="",
                    stderr=f"BLOCKED: WorktreeSentinel verbietet '{script_name}' fuer aktiven Agent '{agent_id}'",
                    success=False,
                )

        cmd = [str(script_path)]
        if args:
            cmd.extend(args)

        # Environment zusammenbauen
        run_env = dict(os.environ)
        run_env.update(self._config.env_overrides)
        if env:
            run_env.update(env)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._config.workdir) if self._config.workdir else None,
                env=run_env,
                timeout=self._config.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return ScriptResult(
                script=script_name,
                exit_code=-1,
                stdout=exc.stdout or "",
                stderr=f"Timeout nach {self._config.timeout}s",
                success=False,
            )
        except FileNotFoundError as exc:
            return ScriptResult(
                script=script_name,
                exit_code=ExitCode.SCRIPT_MISSING,
                stdout="",
                stderr=str(exc),
                success=False,
            )

        # Evidence-Pfad aus stdout extrahieren
        evidence_path = self._extract_evidence_path(proc.stdout)

        return ScriptResult(
            script=script_name,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            success=proc.returncode == 0,
            evidence_path=evidence_path,
        )

    @staticmethod
    def _extract_evidence_path(stdout: str) -> Optional[str]:
        """Extrahiert den Evidence-Pfad aus Skript-stdout."""
        for line in stdout.splitlines():
            if "evidence=" in line:
                parts = line.split("evidence=")
                if len(parts) > 1:
                    return parts[1].strip().split()[0]
        return None

    # -----------------------------------------------------------------------
    # High-Level-Wrapper fuer einzelne Skripte
    # -----------------------------------------------------------------------

    def agent_status(
        self,
        stream_id: str,
        status_token: str,
        message: str = "",
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        agent-status.sh: Postet ACK/BLOCKER/READY_FOR_REVIEW.

        Exit 56 = Stream BLOCKED, nur BLOCKER erlaubt.
        """
        args = [stream_id, status_token]
        if message:
            args.append(message)
        return self.run(ScriptName.AGENT_STATUS, args=args, env=env)

    def finish_gate(
        self,
        agent_id: str = "",
        mode: str = "--enforce",
        skip_sonar: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        agent-finish-gate.sh: Orchestrriert alle lokalen Gates.

        mode: --enforce oder --verify-only
        """
        args = [mode]
        if skip_sonar:
            args.append("--skip-sonar")
        return self.run(ScriptName.AGENT_FINISH_GATE, args=args, env=env, agent_id=agent_id)

    def sonar_gate(
        self,
        agent_id: str = "",
        mode: str = "--require",
        skip_tests: bool = False,
        max_coverage_age: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        sonar-agent-gate.sh: Serialisierter SonarQube-Gate.

        mode: --require oder --optional
        """
        args = [mode]
        if skip_tests:
            args.append("--skip-tests")
        if max_coverage_age is not None:
            args.extend(["--max-coverage-age-minutes", str(max_coverage_age)])
        return self.run(ScriptName.SONAR_AGENT_GATE, args=args, env=env, agent_id=agent_id)

    def pr_readiness(
        self,
        verify: bool = False,
        markdown: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        pr-readiness-summary.sh: GO/NO-GO Entscheidung.

        Exit 1 nur bei --verify + NO-GO.
        """
        args: List[str] = []
        if verify:
            args.append("--verify")
        if markdown:
            args.append("--markdown")
        return self.run(ScriptName.PR_READINESS_SUMMARY, args=args, env=env)

    def write_evidence(
        self,
        gate: str,
        status: str,
        agent_id: str = "",
        summary: str = "",
        detail: str = "",
        skipped: Optional[bool] = None,
        required: Optional[bool] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        write-agent-evidence.sh: Schreibt strukturiertes Evidence-JSON.
        """
        args = ["--gate", gate, "--status", status]
        if summary:
            args.extend(["--summary", summary])
        if detail:
            args.extend(["--detail", detail])
        if skipped is not None:
            args.extend(["--skipped", "true" if skipped else "false"])
        if required is not None:
            args.extend(["--required", "true" if required else "false"])
        return self.run(ScriptName.WRITE_AGENT_EVIDENCE, args=args, env=env, agent_id=agent_id)

    def class_test_gate(
        self,
        agent_id: str = "",
        mode: str = "--enforce",
        skip_cache: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        agent-class-test-gate.sh: Klassengesteuerte Tests.
        """
        args = [mode]
        if skip_cache:
            args.append("--skip-cache")
        return self.run(ScriptName.AGENT_CLASS_TEST_GATE, args=args, env=env, agent_id=agent_id)

    def open_pr(
        self,
        agent_id: str = "",
        title: str = "",
        no_preflight: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        agent-open-pr.sh: Kompletter PR-Workflow.
        """
        args: List[str] = []
        if no_preflight:
            args.append("--no-preflight")
        if title:
            args.append(title)
        return self.run(ScriptName.AGENT_OPEN_PR, args=args, env=env, agent_id=agent_id)

    def merge_preflight(
        self,
        pr_number: int,
        agent_id: str = "",
        output_file: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        captain-merge-preflight.sh: Captain-seitiger Merge-Preflight.
        """
        args = [str(pr_number)]
        if output_file:
            args.append(output_file)
        return self.run(ScriptName.CAPTAIN_MERGE_PREFLIGHT, args=args, env=env, agent_id=agent_id)

    def sonar_local(
        self,
        agent_id: str = "",
        skip_tests: bool = False,
        skip_gate: bool = False,
        env: Optional[Dict[str, str]] = None,
    ) -> ScriptResult:
        """
        sonar-gate.sh: Lokaler SonarQube-Scan (Docker).
        """
        args: List[str] = []
        if skip_tests:
            args.append("--skip-tests")
        if skip_gate:
            args.append("--skip-gate")
        return self.run(ScriptName.SONAR_GATE, args=args, env=env, agent_id=agent_id)


@dataclass(frozen=True)
class ReadinessDecision:
    """Ergebnis der pr-readiness-summary Auswertung."""
    decision: str  # GO oder NO-GO
    raw_stdout: str
    details: Dict[str, str] = field(default_factory=dict)

    @property
    def is_go(self) -> bool:
        return self.decision == "GO"


def parse_readiness_stdout(stdout: str) -> ReadinessDecision:
    """
    Parst die key=value Ausgabe von pr-readiness-summary.sh.

    Erwartet Zeilen wie:
      decision=GO
      finish=pass
      sonar=pass
      tests=pass
    """
    details: Dict[str, str] = {}
    for line in stdout.strip().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            details[key.strip()] = value.strip()

    decision = details.get("decision", "NO-GO")
    return ReadinessDecision(
        decision=decision,
        raw_stdout=stdout,
        details=details,
    )
