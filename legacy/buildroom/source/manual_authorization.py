#!/usr/bin/env python3
"""Durable one-shot capability for manual Buildroom phase entry."""

from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from buildroom_core import ProjectPack, ProjectPackError


AUTHORIZATION_PREFIX = "manual-auth-"
MAX_TTL_SECONDS = 900
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
AUTHORIZED_ISSUERS = {"owner"}
DEFAULT_AUTHORIZATION_STORE = (
    Path.home() / ".hermes/profiles/orchestrator/evidence/manual-authorizations.jsonl"
)


class ManualAuthorizationError(RuntimeError):
    """Exact fail-closed manual authorization blocker."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime:
    current = value or _utc_now()
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class ProcessIdentity:
    executable: str
    command_line: str


def _process_ancestry() -> tuple[ProcessIdentity, ...]:
    """Read kernel-owned executable identities from this process to the session root."""
    processes: list[ProcessIdentity] = []
    pid = os.getpid()
    for _ in range(16):
        try:
            proc = Path(f"/proc/{pid}")
            executable = str((proc / "exe").resolve()).lower()
            command_line = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                errors="replace"
            ).lower()
            processes.append(ProcessIdentity(executable, command_line))
            parent = int((proc / "stat").read_text().split()[3])
        except (OSError, ValueError, IndexError):
            break
        if parent <= 1 or parent == pid:
            break
        pid = parent
    return tuple(processes)


def trusted_issuer_identity() -> str:
    """Accept only an exact, non-interposable owner-shell process chain."""
    ancestry = _process_ancestry()
    interactive_shells = {"/usr/bin/bash", "/usr/bin/zsh", "/usr/bin/fish", "/usr/bin/dash", "/usr/bin/sh"}
    session_roots = {
        "/usr/bin/ghostty",
        "/usr/bin/gnome-terminal-server",
        "/usr/bin/konsole",
        "/usr/bin/kitty",
        "/usr/bin/wezterm-gui",
        "/usr/sbin/sshd",
        "/usr/bin/login",
    }
    system_roots = {"/usr/lib/systemd/systemd", "/usr/sbin/sshd", "/usr/bin/login"}
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    if len(ancestry) < 3:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    if ancestry[0].executable != str(Path(sys.executable).resolve()).lower():
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    if ancestry[1].executable not in interactive_shells:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    index = 2
    if ancestry[index].executable in interactive_shells:
        index += 1
    if index >= len(ancestry) or ancestry[index].executable not in session_roots:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    if any(process.executable not in system_roots for process in ancestry[index + 1 :]):
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    try:
        if Path.home().stat().st_uid != os.getuid():
            raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    except OSError as exc:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc
    return "owner"


def _phase_profile(pack: ProjectPack, phase: str) -> str:
    if phase == "MERGE":
        return "orchestrator"
    return pack.profile_for(phase)


@dataclass(frozen=True)
class ManualAuthorizationStore:
    path: Path = DEFAULT_AUTHORIZATION_STORE

    def _validate_path(self) -> Path:
        path = Path(os.path.abspath(self.path.expanduser()))
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            if current.is_symlink():
                raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
        return path

    def _open(self):
        path = self._validate_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._validate_path()
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
            return os.fdopen(descriptor, "a+", encoding="utf-8")
        except OSError as exc:
            raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc

    @staticmethod
    def _records(handle) -> dict[str, dict[str, Any]]:
        handle.seek(0)
        records: dict[str, dict[str, Any]] = {}
        for line in handle:
            try:
                event = json.loads(line)
                record = event["authorization"]
                authorization_id = record["id"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc
            if not isinstance(event, dict) or not isinstance(record, dict):
                raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
            records[str(authorization_id)] = record
        return records

    @staticmethod
    def _append(handle, event: str, record: dict[str, Any]) -> None:
        payload = {"schema": "manual-buildroom-authorization-v1", "event": event, "authorization": record}
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    def authorization(self, authorization_id: str) -> dict[str, Any] | None:
        try:
            with self._open() as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
                return self._records(handle).get(authorization_id)
        except OSError as exc:
            raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc

    def issue(self, record: dict[str, Any]) -> None:
        try:
            with self._open() as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                records = self._records(handle)
                if record["id"] in records:
                    raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
                self._append(handle, "ISSUED", record)
        except OSError as exc:
            raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc

    def consume(
        self,
        authorization_id: str,
        *,
        pack: ProjectPack,
        phase: str,
        dry_run: bool,
        now: datetime,
    ) -> dict[str, Any]:
        try:
            with self._open() as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                record = self._records(handle).get(authorization_id)
                if record is None:
                    raise ManualAuthorizationError("MANUAL_AUTHORIZATION_NOT_FOUND")
                if record.get("consumed_at"):
                    raise ManualAuthorizationError("MANUAL_AUTHORIZATION_ALREADY_CONSUMED")
                expires_at = datetime.fromisoformat(str(record.get("expires_at", "")))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if now >= expires_at:
                    raise ManualAuthorizationError("MANUAL_AUTHORIZATION_EXPIRED")
                expected = (
                    pack.project_name,
                    str(pack.repo_path.resolve()),
                    phase,
                    _phase_profile(pack, phase),
                )
                observed = (
                    record.get("project"),
                    record.get("repository"),
                    record.get("phase"),
                    record.get("allowed_profile"),
                )
                if observed != expected or (record.get("dry_run_only") and not dry_run):
                    raise ManualAuthorizationError("MANUAL_AUTHORIZATION_MISMATCH")
                consumed = dict(record)
                consumed["consumed_at"] = now.isoformat()
                self._append(handle, "CONSUMED", consumed)
                return consumed
        except ValueError as exc:
            raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc
        except OSError as exc:
            raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED") from exc


def issue_manual_authorization(
    pack: ProjectPack,
    *,
    phase: str,
    request_id: str,
    dry_run_only: bool,
    ttl_seconds: int = 300,
    store: ManualAuthorizationStore | None = None,
    now: datetime | None = None,
) -> str:
    """Issue a bounded capability from the current authoritative profile."""
    issuer = trusted_issuer_identity()
    request_id = request_id.strip()
    if issuer not in AUTHORIZED_ISSUERS or not REQUEST_ID_RE.fullmatch(request_id):
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    if pack.autopilot_enabled or pack.delivery_mode != "engineering_finish_line":
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_MISMATCH")
    if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    try:
        pack.require_phase(phase)
        allowed_profile = _phase_profile(pack, phase)
    except ProjectPackError as exc:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_MISMATCH") from exc
    if issuer == allowed_profile:
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    issued_at = _aware(now)
    authorization_id = AUTHORIZATION_PREFIX + secrets.token_urlsafe(24)
    record = {
        "id": authorization_id,
        "project": pack.project_name,
        "repository": str(pack.repo_path.resolve()),
        "phase": phase,
        "request_id": request_id,
        "issuer": issuer,
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(seconds=ttl_seconds)).isoformat(),
        "dry_run_only": bool(dry_run_only),
        "allowed_profile": allowed_profile,
        "consumed_at": None,
    }
    (store or ManualAuthorizationStore()).issue(record)
    return authorization_id


def consume_manual_authorization(
    authorization_id: str,
    *,
    pack: ProjectPack,
    phase: str,
    dry_run: bool,
    store: ManualAuthorizationStore | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Consume one exact capability or fail closed with an exact blocker."""
    if not authorization_id or not authorization_id.startswith(AUTHORIZATION_PREFIX):
        raise ManualAuthorizationError("MANUAL_AUTHORIZATION_REQUIRED")
    return (store or ManualAuthorizationStore()).consume(
        authorization_id,
        pack=pack,
        phase=phase,
        dry_run=dry_run,
        now=_aware(now),
    )
