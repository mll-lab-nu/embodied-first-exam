"""Authoring tests for bicycle_pump_stroke (pytest; needs DEXHAND_ASSET_DIR or the repository's prepared assets)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from runtime import TASK, Session  # noqa: E402
from scene import hands  # noqa: E402

WIDTHS = {"sharpa": 58, "wuji": 54}


def oracle(hand="sharpa"):
    path = HERE / "solution" / ("trajectory.npz" if hand == "sharpa" else f"{hand}/trajectory.npz")
    return hands.read_trajectory(path, widths=WIDTHS, max_rows=5000, task=TASK)[0]


def replay_cli(tmp_path, rows, hand="sharpa", **extra):
    traj = tmp_path / "t.npz"
    if extra:
        np.savez_compressed(traj, actions=rows, hand=np.array(hand), **extra)
    else:
        hands.write_trajectory(traj, rows, hand=hand, task=TASK)
    out = tmp_path / "r.json"
    subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", TASK, "--traj", str(traj), "--out", str(out)],
                   check=True, cwd=HERE, stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


ORACLE_HANDS = ["sharpa"] + (["wuji"] if (HERE / "solution/wuji/trajectory.npz").is_file() else [])


@pytest.mark.parametrize("hand", ORACLE_HANDS)
def test_oracle_succeeds_with_slack_and_float32(hand):
    rows = oracle(hand)
    status = Session(hand=hand).replay(rows)
    assert status["success"] and status["strokes"] >= 28 and status["stage"] == 5
    assert status["head_connected"] and status["head_disconnected"]
    assert len(rows) - status["steps"] >= 50
    assert Session(hand=hand).replay(rows.astype(np.float32).astype(np.float64))["success"]


@pytest.mark.parametrize("hand", ["sharpa", "wuji"])
def test_nop_fails_and_is_deterministic(hand):
    a, b = Session(hand=hand), Session(hand=hand)
    rows = np.repeat(a.initial_targets[None], 600, axis=0)
    sa, sb = a.replay(rows), b.replay(rows)
    assert not sa["success"] and sa["strokes"] == 0 and a.state_sha() == b.state_sha()


def test_truncation_and_27_strokes_fail():
    rows = oracle()
    full = Session().replay(rows)
    last = full["stroke_controls"][27]
    short = Session().replay(rows[: last - 5])
    assert not short["success"] and short["strokes"] == 27
    assert not Session().replay(rows[: full["steps"] - 1])["success"]


def test_knock_fails_fast_and_cannot_be_undone():
    rows = oracle()
    s = Session()
    third = s.replay(rows)["stroke_controls"][2]
    s.reset()
    for row in rows[: third + 10]:
        s.step(row)
    row = rows[third + 9].copy()
    for i in range(1, 151):  # the right shoulder rolls sideways while the hand still grips the handle
        knock = row.copy()
        knock[8] += 0.4 * min(1.0, i / 60)
        s.step(knock)
    assert s.status()["reason"] in ("pump_tipped", "pump_displaced", "pump_lifted")
    for r in rows[third + 10:]:
        s.step(r)
    assert not s.status()["success"]


def test_snapshot_restore_is_exact():
    rows = oracle()
    s = Session()
    for r in rows[:300]:
        s.step(r)
    snap = s.snapshot()
    for r in rows[300:400]:
        s.step(r)
    sha = s.state_sha()
    s.restore(snap)
    for r in rows[300:400]:
        s.step(r)
    assert s.state_sha() == sha


def test_replay_cli_rejects_wrong_width_and_ignores_forged_members(tmp_path):
    rows = oracle()
    bad = replay_cli(tmp_path, rows, hand="wuji")
    assert bad["bad_trajectory"] == 1 and not bad["success"]
    nop = np.repeat(rows[:1], 300, axis=0)
    forged = replay_cli(tmp_path, nop, success=np.array(True), reward=np.array(1.0))
    assert not forged["success"] and forged["bad_trajectory"] == 0


def test_rows_out_of_range_are_rejected(tmp_path):
    rows = oracle().copy()
    rows[10, 2] = 5.0
    result = replay_cli(tmp_path, rows)
    assert result["bad_trajectory"] == 1


def test_nan_rows_are_rejected(tmp_path):
    rows = oracle().copy()
    rows[5, 7] = np.nan
    result = replay_cli(tmp_path, rows, task=np.array(TASK))  # written with numpy directly (the writer refuses NaN)
    assert result["bad_trajectory"] == 1 and not result["success"]


def test_hand_label_mismatch_with_trusted_hand_is_rejected(tmp_path):
    traj = tmp_path / "t.npz"
    hands.write_trajectory(traj, oracle(), hand="sharpa", task=TASK)
    out = tmp_path / "r.json"
    subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", TASK, "--traj", str(traj), "--out", str(out),
                    "--trusted-service", "--hand", "wuji"], check=True, cwd=HERE, stdout=subprocess.DEVNULL)
    assert json.loads(out.read_text())["bad_trajectory"] == 1


def test_ambiguous_member_is_rejected(tmp_path):
    import zipfile

    traj = tmp_path / "t.npz"
    hands.write_trajectory(traj, oracle(), hand="sharpa", task=TASK)
    with zipfile.ZipFile(traj, "a") as archive:
        archive.writestr("actions", b"shadow")
    out = tmp_path / "r.json"
    subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", TASK, "--traj", str(traj), "--out", str(out)],
                   check=True, cwd=HERE, stdout=subprocess.DEVNULL)
    assert json.loads(out.read_text())["bad_trajectory"] == 1


def test_wuji_scene_matches_sharpa_scene_except_the_hand():
    sharpa, wuji = Session(), Session(hand="wuji")
    assert sharpa.action_dim == 58 and wuji.action_dim == 54
    assert sharpa.actuator_names[:14] == wuji.actuator_names[:14]
    assert sharpa.robot == wuji.robot == "marvin-bimanual-sharpa-wave"
    for name in ("pump", "piston"):
        assert np.allclose(sharpa.data.xpos[sharpa.model.body(name).id], wuji.data.xpos[wuji.model.body(name).id])
    assert np.allclose(sharpa.model.actuator_ctrlrange[:14], wuji.model.actuator_ctrlrange[:14])


@pytest.mark.parametrize("shift, rotation, expected", [
    ((0.031, 0.0, 0.0), None, "pump_displaced"),
    ((0.0, -0.031, 0.0), None, "pump_displaced"),
    ((0.0, 0.0, 0.021), None, "pump_lifted"),
    ((0.0, 0.0, -0.50), None, "pump_below_table"),
    ((0.0, 0.0, 0.0), 0.27, "pump_tipped"),
    ((0.029, 0.0, 0.019), 0.25, None),
])
def test_fail_fast_thresholds_on_a_scratch_state(shift, rotation, expected):
    """The invariant thresholds, checked on a scratch copy of the reset state (never inside an episode)."""
    import mujoco

    s = Session()
    data = mujoco.MjData(s.model)
    data.qpos[:] = s.data.qpos
    adr = s.model.jnt_qposadr[s.model.joint("pump_free").id]
    data.qpos[adr:adr + 3] += shift
    if rotation is not None:
        data.qpos[adr + 3:adr + 7] = [np.cos(rotation / 2), np.sin(rotation / 2), 0, 0]
    mujoco.mj_forward(s.model, data)
    violation = s.checker.violation(data)
    assert (violation[0] if violation else None) == expected


def test_strokes_count_only_through_a_connected_head():
    """Checker logic on a scratch copy of the reset state (never inside an episode): strokes before the head is seated
    and locked do not count; a connected head pulled off or unlocked fails the episode."""
    import mujoco

    s = Session()
    c = s.checker
    data = mujoco.MjData(s.model)
    data.qpos[:] = s.data.qpos
    piston = s.model.jnt_qposadr[s.model.joint("piston_extension").id]
    head = s.model.jnt_qposadr[s.model.joint("head_slide").id]
    lever = s.model.jnt_qposadr[s.model.joint("lever_angle").id]

    def stroke(step):
        for q in (0.0, 0.2):            # handle fully down (depth 0.20 m), then back up (depth 0)
            data.qpos[piston] = q
            mujoco.mj_forward(s.model, data)
            c.substep(data, step, 0)

    mujoco.mj_forward(s.model, data)
    c.reset(data)
    stroke(0)
    assert c.strokes == 0 and not c.connected
    data.qpos[head] = -0.0175           # seated but still unlocked
    stroke(1)
    assert c.strokes == 0 and not c.connected
    data.qpos[lever] = 1.65             # locked: connected from now on
    stroke(2)
    assert c.connected and c.strokes == 1
    data.qpos[lever] = 1.40             # sagging lock: still connected, but strokes no longer count
    stroke(3)
    assert c.strokes == 1 and c.failure is None
    data.qpos[lever] = 1.0              # opened before the tire is inflated
    mujoco.mj_forward(s.model, data)
    c.substep(data, 4, 0)
    assert c.failure == "head_disconnected"


def test_disconnect_stage_order():
    """After the strokes/pressure: pulling the head off while locked fails; unlock then pull off latches the stage."""
    import mujoco

    s = Session()
    c = s.checker
    head = s.model.jnt_qposadr[s.model.joint("head_slide").id]
    lever = s.model.jnt_qposadr[s.model.joint("lever_angle").id]
    for forced in (True, False):
        data = mujoco.MjData(s.model)
        data.qpos[:] = s.data.qpos
        mujoco.mj_forward(s.model, data)
        c.reset(data)
        data.qpos[head], data.qpos[lever] = -0.0175, 1.65
        mujoco.mj_forward(s.model, data)
        c.substep(data, 0, 0)
        c.strokes = c.required          # inflated (scratch state)
        if forced:
            data.qpos[head] = -0.010       # pulled 7.5 mm back while still locked
            mujoco.mj_forward(s.model, data)
            c.substep(data, 1, 0)
            assert c.failure == "head_forced_off"
        else:
            data.qpos[lever] = 0.3         # unlocked first
            mujoco.mj_forward(s.model, data)
            c.substep(data, 1, 0)
            assert c.failure is None and not c.disconnected
            data.qpos[head] = -0.004       # then pulled 13.5 mm back off the stem
            mujoco.mj_forward(s.model, data)
            c.substep(data, 2, 0)
            assert c.failure is None and c.disconnected
