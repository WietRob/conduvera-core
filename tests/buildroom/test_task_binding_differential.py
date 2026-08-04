"""Differential tests: legacy vs ported task-binding module (DOD-03..08).

For IDENTICAL initial states, existing bindings, task/phase/cycle/board
values, event sequences and duplicate/replacement situations both the frozen
legacy module and the ported curaops.buildroom.task_binding module are
executed and compared on:
- return value,
- exception type + exact text,
- the FULL state before/after every step,
- ordering,
- idempotency,
- duplicate/replacement behaviour,
- all bindings and references,
- external side effects (none by design in this module).

No live ~/.hermes / kanban / sqlite state is used.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy/buildroom/source"))

import curaops.buildroom.task_binding as new_mod  # noqa: E402
import buildroom_task_binding as legacy_mod  # noqa: E402

VALID = dict(
    task_id="t_deadbeef", board="audit-remediation", phase="REVIEWER",
    cycle=49, created_at="2026-07-15T20:00:00+00:00",
)


def _run_call(mod, fn: str, *args, **kwargs):
    state_before = copy.deepcopy(args[0]) if args and isinstance(args[0], dict) else None
    try:
        result = getattr(mod, fn)(*args, **kwargs)
        outcome = ("OK", result)
    except Exception as exc:  # noqa: BLE001 — differential capture
        outcome = (type(exc).__name__, str(exc))
    state_after = copy.deepcopy(args[0]) if args and isinstance(args[0], dict) else None
    return {"before": state_before, "outcome": outcome, "after": state_after}


# -- TaskBinding validation (constructor) -----------------------------------

VALIDATION_CASES = [
    ("valid", VALID, "OK"),
    ("task_id_non_hex", {**VALID, "task_id": "x123"}, "KANBAN_TASK_ID_INVALID"),
    ("task_id_t_xyz", {**VALID, "task_id": "t_xyz"}, "KANBAN_TASK_ID_INVALID"),
    ("board_upper", {**VALID, "board": "Audit"}, "KANBAN_BOARD_INVALID"),
    ("board_underscore", {**VALID, "board": "audit_remediation"}, "KANBAN_BOARD_INVALID"),
    ("phase_lower", {**VALID, "phase": "reviewer"}, "BUILDROOM_PHASE_INVALID"),
    ("phase_dash", {**VALID, "phase": "RE-VIEWER"}, "BUILDROOM_PHASE_INVALID"),
    ("cycle_zero", {**VALID, "cycle": 0}, "BUILDROOM_CYCLE_INVALID"),
    ("cycle_neg", {**VALID, "cycle": -1}, "BUILDROOM_CYCLE_INVALID"),
    ("created_empty", {**VALID, "created_at": ""}, "TASK_BINDING_CREATED_AT_REQUIRED"),
]


@pytest.mark.parametrize("name,kwargs,expect", VALIDATION_CASES)
def test_differential_constructor(name, kwargs, expect):
    def run(mod):
        try:
            b = mod.TaskBinding(**kwargs)
            return ("OK", b.to_dict())
        except Exception as exc:
            return (type(exc).__name__, str(exc))

    legacy = run(legacy_mod)
    new = run(new_mod)
    assert legacy == new, f"{name}: Legacy {legacy} != New {new}"
    if expect != "OK":
        assert legacy[0] == "ValueError" and legacy[1] == expect


def test_to_dict_filters_none_and_empty():
    kwargs = {**VALID, "evidence_path": None, "repo": "peekxd"}
    assert legacy_mod.TaskBinding(**kwargs).to_dict() == new_mod.TaskBinding(**kwargs).to_dict()
    d = new_mod.TaskBinding(**kwargs).to_dict()
    assert "evidence_path" not in d and "repo" in d


# -- store / binding_for_phase / clear ---------------------------------------

STORE_CASES = [
    ("store_fresh", {}, VALID),
    ("store_replace", {"task_bindings": {"REVIEWER": {"task_id": "t_old", "board": "x"}}}, VALID),
    ("store_legacy_survives", {"task_ids": {"REVIEWER": "t_old"}, "task_boards": {"REVIEWER": "b"}}, VALID),
]


@pytest.mark.parametrize("name,initial,kwargs", STORE_CASES)
def test_differential_store(name, initial, kwargs):
    l = _run_call(legacy_mod, "store_task_binding", copy.deepcopy(initial),
                  legacy_mod.TaskBinding(**kwargs))
    n = _run_call(new_mod, "store_task_binding", copy.deepcopy(initial),
                  new_mod.TaskBinding(**kwargs))
    assert l == n, f"store {name}: Legacy != New"


def test_differential_store_invalid_bindings_type():
    l = _run_call(legacy_mod, "store_task_binding", {"task_bindings": "str"},
                  legacy_mod.TaskBinding(**VALID))
    n = _run_call(new_mod, "store_task_binding", {"task_bindings": "str"},
                  new_mod.TaskBinding(**VALID))
    assert l == n
    assert l["outcome"] == ("ValueError", "TASK_BINDINGS_INVALID")


BIND_CASES = [
    ("current_schema", {"cycle": 49, "task_bindings": {"REVIEWER": dict(VALID)}}, "REVIEWER", {}),
    ("raw_not_dict", {"task_bindings": {"REVIEWER": "x"}}, "REVIEWER", {}),
    ("legacy_with_board", {"cycle": 48, "task_ids": {"REVIEWER": "t_deadbeef"},
                           "task_boards": {"REVIEWER": "audit-remediation"}}, "REVIEWER", {}),
    ("legacy_no_board", {"task_ids": {"REVIEWER": "t_deadbeef"}}, "REVIEWER", {}),
    ("legacy_invalid_task_id", {"task_ids": {"REVIEWER": "t_old"},
                                "task_boards": {"REVIEWER": "b"}}, "REVIEWER", {}),
    ("allow_legacy_false", {"task_ids": {"REVIEWER": "t_deadbeef"}}, "REVIEWER",
     {"allow_legacy": False}),
    ("empty_state", {}, "REVIEWER", {}),
    ("legacy_last_run", {"cycle": 5, "last_run": "2026-01-01T00:00:00+00:00",
                         "task_ids": {"REVIEWER": "t_deadbeef"},
                         "task_boards": {"REVIEWER": "b"}}, "REVIEWER", {}),
]


@pytest.mark.parametrize("name,initial,phase,kwargs", BIND_CASES)
def test_differential_binding_for_phase(name, initial, phase, kwargs):
    l = _run_call(legacy_mod, "binding_for_phase", copy.deepcopy(initial), phase, **kwargs)
    n = _run_call(new_mod, "binding_for_phase", copy.deepcopy(initial), phase, **kwargs)
    # normalize TaskBinding objects to comparable form
    def norm(res):
        if res[0] == "OK" and res[1] is not None:
            return (res[0], res[1].to_dict())
        return res
    l["outcome"], n["outcome"] = norm(l["outcome"]), norm(n["outcome"])
    assert l == n, f"binding {name}: Legacy != New"


def test_differential_clear():
    initial = {
        "cycle": 49,
        "task_bindings": {"REVIEWER": dict(VALID)},
        "task_ids": {"REVIEWER": "t_deadbeef"},
        "task_boards": {"REVIEWER": "audit-remediation"},
        "other_phase": "keep-me",
    }
    l = _run_call(legacy_mod, "clear_task_binding", copy.deepcopy(initial), "REVIEWER")
    n = _run_call(new_mod, "clear_task_binding", copy.deepcopy(initial), "REVIEWER")
    l["outcome"] = (l["outcome"][0], l["outcome"][1].to_dict() if l["outcome"][1] else None)
    n["outcome"] = (n["outcome"][0], n["outcome"][1].to_dict() if n["outcome"][1] else None)
    assert l == n
    assert "REVIEWER" not in l["after"]["task_bindings"]
    assert "REVIEWER" not in l["after"]["task_ids"]
    assert "REVIEWER" not in l["after"]["task_boards"]
    assert l["after"]["other_phase"] == "keep-me"  # fremde Keys unberührt


# -- kanban_argv -------------------------------------------------------------

ARGV_CASES = [
    ("task_op", "show", VALID, {}, []),
    ("task_op_no_binding", "show", None, {}, []),
    ("board_op", "create", None, {"board": "audit-remediation"}, []),
    ("board_op_no_board", "create", None, {}, []),
    ("board_op_invalid", "create", None, {"board": "Bad"}, []),
    ("unsupported", "delete", VALID, {}, []),
    ("extra_args", "show", VALID, {}, ["--x", "1"]),
]


@pytest.mark.parametrize("name,op,binding_kwargs,kwargs,extra", ARGV_CASES)
def test_differential_kanban_argv(name, op, binding_kwargs, kwargs, extra):
    def run(mod):
        b = mod.TaskBinding(**binding_kwargs) if binding_kwargs else None
        try:
            return ("OK", mod.kanban_argv(op, b, **kwargs, extra=extra))
        except Exception as exc:
            return (type(exc).__name__, str(exc))

    legacy, new = run(legacy_mod), run(new_mod)
    assert legacy == new, f"argv {name}: Legacy != New"


def test_all_task_operations():
    ops = ("show", "runs", "log", "context", "complete", "block", "unblock",
           "archive", "comment")
    for op in ops:
        l = legacy_mod.kanban_argv(op, legacy_mod.TaskBinding(**VALID))
        n = new_mod.kanban_argv(op, new_mod.TaskBinding(**VALID))
        assert l == n
        assert n[:4] == ["hermes", "kanban", "--board", "audit-remediation"]
        assert n[4:] == [op, "t_deadbeef"]


# -- idempotency / duplicate / replacement ------------------------------------

def test_store_idempotent_and_replacement():
    for mod in (legacy_mod, new_mod):
        s = {}
        b = mod.TaskBinding(**VALID)
        mod.store_task_binding(s, b)
        first = copy.deepcopy(s)
        mod.store_task_binding(s, b)  # idempotent
        assert s == first
        # Replacement on same phase (valid hex task id)
        b2 = mod.TaskBinding(**{**VALID, "task_id": "t_0beef0"})
        mod.store_task_binding(s, b2)
        assert s["task_bindings"]["REVIEWER"]["task_id"] == "t_0beef0"
        assert len(s["task_bindings"]) == 1  # kein Duplicate-Key


def test_clear_idempotent():
    for mod in (legacy_mod, new_mod):
        s = {"task_bindings": {"REVIEWER": dict(VALID)}}
        mod.clear_task_binding(s, "REVIEWER")
        mod.clear_task_binding(s, "REVIEWER")  # no-op
        assert "REVIEWER" not in s["task_bindings"]


# -- side-effect / authority boundary -----------------------------------------

def test_no_external_side_effects_and_no_live_state():
    """Module must not touch files, kanban, sqlite, env, or live state."""
    for mod in (legacy_mod, new_mod):
        s = {"task_bindings": {}}
        mod.store_task_binding(s, mod.TaskBinding(**VALID))
        mod.binding_for_phase(s, "REVIEWER")
        mod.clear_task_binding(s, "REVIEWER")
        mod.kanban_argv("show", mod.TaskBinding(**VALID))
        # pure in-memory; no file/env/network side effect by construction
        assert s == {"task_bindings": {}}


def test_no_production_import_of_legacy():
    hits = []
    for py in (ROOT / "curaops").rglob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and "legacy" in stripped:
                hits.append(f"{py}:{i}: {stripped}")
    assert not hits, f"Produktions-Import aus legacy: {hits}"


def test_dod11_no_authority_dependencies():
    src = (ROOT / "curaops/buildroom/task_binding.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    code_lines, in_doc = [], False
    for l in lines:
        s = l.strip()
        if s.startswith('"""'):
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#"):
            continue
        code_lines.append(l)
    code = "\n".join(code_lines)
    for forbidden in ("litellm", "ai_stack", "ai-stack", "bws", "bitwarden",
                      "subprocess", "requests", "os.environ", "sqlite", "pathlib",
                      "open("):
        assert forbidden not in code, f"verbotene Abhängigkeit: {forbidden}"
