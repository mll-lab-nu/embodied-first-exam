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

WIDTHS = {"sharpa": 28, "wuji": 26}


def oracle(hand="sharpa"):
    path = HERE / "solution" / ("trajectory.npz" if hand == "sharpa" else f"{hand}/trajectory.npz")
    return hands.read_trajectory(path, widths=WIDTHS, max_rows=3000, task=TASK)[0]


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


@pytest.mark.parametrize("hand", ["sharpa", "wuji"])
def test_oracle_succeeds_with_slack_and_float32(hand):
    rows = oracle(hand)
    status = Session(hand=hand).replay(rows)
    assert status["success"] and status["strokes"] >= 6 and status["stage"] == 3
    assert len(rows) - status["steps"] >= 50
    assert Session(hand=hand).replay(rows.astype(np.float32).astype(np.float64))["success"]


@pytest.mark.parametrize("hand", ["sharpa", "wuji"])
def test_nop_fails_and_is_deterministic(hand):
    a, b = Session(hand=hand), Session(hand=hand)
    rows = np.repeat(a.initial_targets[None], 600, axis=0)
    sa, sb = a.replay(rows), b.replay(rows)
    assert not sa["success"] and sa["strokes"] == 0 and a.state_sha() == b.state_sha()


def test_truncation_and_five_strokes_fail():
    rows = oracle()
    full = Session().replay(rows)
    sixth = full["stroke_controls"][5]
    assert not Session().replay(rows[: sixth - 5])["success"]
    assert not Session().replay(rows[: full["steps"] - 1])["success"]


def test_knock_fails_fast_and_cannot_be_undone():
    rows = oracle()
    s = Session()
    third = s.replay(rows)["stroke_controls"][2]
    s.reset()
    for row in rows[: third + 10]:
        s.step(row)
    row = s.hold_action()
    row[6:] = 0.0
    origin = np.asarray(s.config["stage_origin"])
    for z in np.linspace(row[2], 1.25 - origin[2], 30):
        row[2] = z
        s.step(row)
    for x in np.linspace(row[0], 0.30 - origin[0], 30):
        row[0] = x
        s.step(row)
    for z in np.linspace(row[2], 1.05 - origin[2], 30):
        row[2] = z
        s.step(row)
    for x in np.linspace(row[0], row[0] + 0.3, 60):
        row[0] = x
        s.step(row)
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
    assert sharpa.action_dim == 28 and wuji.action_dim == 26
    assert sharpa.actuator_names[:6] == wuji.actuator_names[:6]
    for name in ("pump", "piston"):
        assert np.allclose(sharpa.data.xpos[sharpa.model.body(name).id], wuji.data.xpos[wuji.model.body(name).id])
    assert np.allclose(sharpa.model.actuator_ctrlrange[:6], wuji.model.actuator_ctrlrange[:6])


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
