"""Essential-task trust boundary and temporal regressions.

Logical feature witnesses below exercise only the judge. Physical successful
rollouts are independently replayed and recorded by the validation workflow.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import mujoco
import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "shared"))
from checker import Checker
from essential import FREE_TASKS, MODULES, initial_wrist
from runtime import Session


def specs():
    return json.loads((HERE / "essential_catalog.json").read_text())["tasks"]


def test_exactly_six_distinct_essential_mechanisms():
    tasks = specs()
    assert {task["id"] for task in tasks} == set(MODULES)
    assert len({task["mechanism"] for task in tasks}) == 6
    assert all(task["parameters"]["locked_wrist"] for task in tasks)


@pytest.mark.parametrize("task", list(MODULES))
def test_objects_are_passive_and_wrist_actions_are_locked(task):
    session = Session(task)
    try:
        model = session.model
        driven = {model.joint(int(j)).name for j in model.actuator_trnid[:, 0]}
        assert len(driven) == 28
        assert model.neq == 6
        assert np.all(model.actuator_trntype == mujoco.mjtTrn.mjTRN_JOINT)
        assert all(name.startswith("right_") or name.startswith("wrist_") for name in driven)
        np.testing.assert_array_equal(model.opt.gravity, [0, 0, -9.81])
        assert not np.any(session.data.qfrc_applied)
        assert not np.any(session.data.xfrc_applied)
        for axis in ("x", "y", "z", "rx", "ry", "rz"):
            equality = model.equality("fixed_wrist_" + axis)
            assert model.eq_type[equality.id] == mujoco.mjtEq.mjEQ_JOINT
            assert model.joint(int(model.eq_obj1id[equality.id])).name == "wrist_" + axis
        if task in FREE_TASKS:
            for name in session._moving_bodies:
                assert model.joint(name + "_free").type == mujoco.mjtJoint.mjJNT_FREE
                assert model.body_gravcomp[model.body(name).id] == 0
        action = session.hold_action()
        np.testing.assert_allclose(action[:6], initial_wrist(session.spec), atol=1e-12, rtol=0)
        for coordinate in range(6):
            altered = action.copy()
            altered[coordinate] += 1e-5
            with pytest.raises(ValueError, match="locks all six wrist"):
                session.step(altered)
            with pytest.raises(ValueError, match="locked wrist"):
                session.replay([altered])
    finally:
        session.close()


@pytest.mark.parametrize("task", list(MODULES))
def test_reset_and_observation_do_not_change_task_history(task):
    session = Session(task)
    try:
        before = session.state_sha()
        features = session.features()
        assert session.checker.required_features <= features.keys()
        assert all(np.isfinite(features[name]) for name in session.checker.required_features)
        for _ in range(5):
            session.features()
            session.state()
        assert session.state_sha() == before
        session.reset()
        assert session.state_sha() == before
    finally:
        session.close()


@pytest.mark.parametrize("task", list(MODULES))
def test_float32_client_rounding_never_commands_wrist_motion(task):
    session = Session(task)
    try:
        wire = session.hold_action().astype(np.float32).astype(np.float64)
        limits = session.model.actuator_ctrlrange
        wire = np.clip(wire, limits[:, 0], limits[:, 1])
        # The standard service may interpolate between canonical and wire values.
        canonical = np.asarray(initial_wrist(session.spec))
        wire[:6] = canonical + 0.5 * (wire[:6] - canonical)
        session.step(wire)
        np.testing.assert_array_equal(session.data.ctrl[:6], canonical)
        session.reset()
        # Raw float32 endpoints may round beyond a manufacturer's upper bound.
        upper = limits[:, 1].astype(np.float32).astype(np.float64)
        upper[:6] = canonical
        session.step(upper)
        np.testing.assert_array_equal(session.data.ctrl[6:], np.clip(upper, limits[:, 0], limits[:, 1])[6:])
    finally:
        session.close()


def sample(task, stage):
    checker = Checker(task)
    values = {name: 0.0 for name in checker.required_features}
    for bounds in (task.get("invariants", {}), stage.get("guards", {}), stage["bounds"]):
        for name, (low, high) in bounds.items():
            values[name] = ((low + high) / 2 if low is not None and high is not None
                            else low if low is not None else min(0, high) if high is not None else 0)
    return values


@pytest.mark.parametrize("task", specs(), ids=lambda task: task["id"])
def test_terminal_only_cannot_substitute_for_the_ordered_sequence(task):
    checker = Checker(task)
    values = sample(task, task["terminal"])
    if task["id"] == "essential_cube_reorient":
        # A real returned orientation is far from both preceding targets;
        # three zero geodesic errors cannot describe one physical pose.
        values.update(cube_error_1=np.pi / 2, cube_error_2=2 * np.pi / 3)
    for _ in range(200):
        checker.update(values)
    assert not checker.success


@pytest.mark.parametrize("task", specs(), ids=lambda task: task["id"])
def test_complete_temporal_fixture_and_interrupted_dwell(task):
    checker = Checker(task)
    first = task["stages"][0]
    values = sample(task, first)
    for _ in range(first["hold_steps"] - 1):
        checker.update(values)
    checker.update(values, window_valid=False)
    assert checker.stage_index == 0
    assert checker.stage_hold == 0
    for stage in task["stages"]:
        for _ in range(stage["hold_steps"]):
            checker.update(sample(task, stage))
    assert checker.stage_index == len(task["stages"])
    assert not checker.success
    for _ in range(task["terminal"]["hold_steps"]):
        checker.update(sample(task, task["terminal"]))
    assert checker.success


@pytest.mark.parametrize("finger", ["thumb", "index", "middle"])
def test_tripod_count_cannot_substitute_for_each_named_tip_in_band(finger):
    task = next(task for task in specs() if task["id"] == "essential_pen_regrasp")
    checker = Checker(task)
    for _ in range(task["stages"][0]["hold_steps"]):
        checker.update(sample(task, task["stages"][0]))
    assert checker.stage_index == 1
    values = sample(task, task["terminal"])
    # Five tips can contact the shaft while a different subset of three
    # contacts the band. A named writing finger outside it is insufficient.
    values.update(contacts=5.0, pen_grip_contacts=3.0)
    values["pen_grip_" + finger] = 0.0
    for _ in range(200):
        checker.update(values)
    assert checker.stage_index == 1
    assert not checker.success
