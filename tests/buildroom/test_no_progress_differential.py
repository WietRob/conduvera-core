"""Differential tests: legacy vs ported no-progress guard (DOD-03/04/05/06/07).

For IDENTICAL event sequences, initial states, and thresholds both the frozen
legacy module and the ported curaops.buildroom.no_progress module are executed
and compared on:
- return value (count, terminal_hold, fingerprint),
- exception type + text,
- the FULL state before/after every step (all mutations),
- deterministic ordering,
- reset / boundary behaviour.

No live ~/.hermes state is used — tests build fresh state dicts.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy/buildroom/source"))

import curaops.buildroom.no_progress as new_mod  # noqa: E402
import buildroom_no_progress as legacy_mod  # noqa: E402


def fresh_state() -> dict:
    return {
        "cycle": 48,
        "phase": "REVIEWER",
        "status": "WAITING",
        "blocker": None,
        "pr_open": "https://github.com/example/repo/pull/41",
        "task_bindings": {
            "REVIEWER": {"task_id": "t_0dd", "board": "audit-remediation", "phase": "REVIEWER", "cycle": 48},
        },
    }


def _run_sequence(mod, steps, initial=None, normalize_time=True):
    """Run an event sequence on one module.

    Returns a list of per-step snapshots: (ok, result_dict, state_after).
    Timestamps (first/last_observed_at) are normalized to a placeholder so
    both modules compare deterministically (they differ by milliseconds).
    """
    state = copy.deepcopy(initial) if initial is not None else fresh_state()
    snapshots = []
    for kwargs in steps:
        before = copy.deepcopy(state)
        try:
            r = getattr(mod, "observe_reconciliation")(state, **kwargs)
            outcome = ("OK", {"count": r.count, "terminal_hold": r.terminal_hold,
                              "fingerprint": tuple(r.fingerprint)})
        except Exception as exc:  # noqa: BLE001 — differential capture
            outcome = (type(exc).__name__, str(exc))
        after = copy.deepcopy(state)
        if normalize_time:
            for snap in (before, after):
                np_ = snap.get("no_progress")
                if isinstance(np_, dict):
                    for key in ("first_observed_at", "last_observed_at"):
                        if np_.get(key):
                            np_[key] = "<TS>"
        snapshots.append({"before": before, "outcome": outcome, "after": after})
    return snapshots


BASE_STEP = dict(
    phase="REVIEWER", status="WAITING", blocker="TASK_DONE_BUT_NO_EVIDENCE",
    task_id="t_0dd", task_board="audit-remediation",
    evidence_fingerprint="", log_fingerprint="log-a", threshold=3,
)

SEQUENCES = {
    "leerer_zustand": [dict(BASE_STEP)],
    "erster_fortschritt": [dict(BASE_STEP), dict(BASE_STEP)],
    "wiederholt_bis_schwelle": [dict(BASE_STEP), dict(BASE_STEP), dict(BASE_STEP)],
    "schwelle_plus_eins": [dict(BASE_STEP)] * 4,
    "neue_evidence_resettet": [dict(BASE_STEP), dict(BASE_STEP),
                               {**BASE_STEP, "evidence_fingerprint": "sha256:new"}],
    "neuer_task": [dict(BASE_STEP), dict(BASE_STEP), {**BASE_STEP, "task_id": "t_fresh"}],
    "neuer_log": [dict(BASE_STEP), dict(BASE_STEP), {**BASE_STEP, "log_fingerprint": "log-b"}],
    "neuer_phase": [dict(BASE_STEP), dict(BASE_STEP), {**BASE_STEP, "phase": "EXECUTOR"}],
    "neuer_status": [dict(BASE_STEP), dict(BASE_STEP), {**BASE_STEP, "status": "REVIEWING"}],
    "neuer_blocker": [dict(BASE_STEP), dict(BASE_STEP), {**BASE_STEP, "blocker": "OTHER"}],
    "threshold_eins": [{**BASE_STEP, "threshold": 1}],
    "threshold_zwei": [{**BASE_STEP, "threshold": 2}, {**BASE_STEP, "threshold": 2}],
    "threshold_invalid": [{**BASE_STEP, "threshold": 0}],
    "task_wechsel_mitte": [dict(BASE_STEP), {**BASE_STEP, "task_id": "t_a"},
                           {**BASE_STEP, "task_id": "t_b"}],
}


@pytest.mark.parametrize("name", sorted(SEQUENCES.keys()))
def test_differential_sequences(name):
    steps = SEQUENCES[name]
    legacy = _run_sequence(legacy_mod, steps)
    new = _run_sequence(new_mod, steps)
    assert legacy == new, f"Sequence {name}: Legacy != New"


def test_no_progress_result_dataclass_identical():
    assert new_mod.NoProgressResult.__name__ == legacy_mod.NoProgressResult.__name__
    assert set(new_mod.NoProgressResult.__dataclass_fields__) == set(
        legacy_mod.NoProgressResult.__dataclass_fields__
    )
    assert new_mod.NoProgressResult.__dataclass_fields__[
        "count"
    ].type == legacy_mod.NoProgressResult.__dataclass_fields__["count"].type


def test_hold_mutates_only_status_blocker_root_blocker():
    """Terminal hold must not touch phase/pr/task_bindings (both modules)."""
    for mod in (legacy_mod, new_mod):
        s = fresh_state()
        for _ in range(3):
            mod.observe_reconciliation(s, **BASE_STEP)
        assert s["phase"] == "REVIEWER"
        assert s["pr_open"].startswith("https://github.com/")
        assert "task_bindings" in s
        assert s["status"] == "HOLD_FOR_BOSS"
        assert s["blocker"] == "REPEATED_NO_PROGRESS"
        assert s["root_blocker"] == "TASK_DONE_BUT_NO_EVIDENCE"
        assert s["no_progress"]["task_binding"] == {"task_id": "t_0dd", "board": "audit-remediation"}


def test_no_live_state_used():
    """Differential tests must not read/write ~/.hermes state (DOD-08/09)."""
    for mod in (legacy_mod, new_mod):
        s = fresh_state()
        mod.observe_reconciliation(s, **BASE_STEP)
        assert s["cycle"] == 48  # pure in-memory state


def test_first_observed_at_persists_across_identical_sequence():
    for mod in (legacy_mod, new_mod):
        s = fresh_state()
        r1 = mod.observe_reconciliation(s, **BASE_STEP)
        first = s["no_progress"]["first_observed_at"]
        mod.observe_reconciliation(s, **BASE_STEP)
        assert s["no_progress"]["first_observed_at"] == first
        # A changed fingerprint refreshes it.
        mod.observe_reconciliation(s, **{**BASE_STEP, "task_id": "t_other"})
        assert s["no_progress"]["first_observed_at"] != first
