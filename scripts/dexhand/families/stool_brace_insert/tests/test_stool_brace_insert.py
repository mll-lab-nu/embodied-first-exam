"""Authoring tests of stool_brace_insert: positive, nop, partial, drop/knock fail-fast, forged archives, widths, Wuji.

Run from the repository root with the pinned MuJoCo environment (about three minutes; every replay is real physics):
    DEXHAND_ASSET_DIR=images/dexhand/assets/hand python3 -m pytest -q scripts/dexhand/families/stool_brace_insert/tests
Fixture tests place parts directly to probe the predicate; they test the verdict, not robot solvability.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import mujoco
import numpy as np
import pytest

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
SHARED = REPO / "scripts/dexhand/shared"
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
sys.path[:0] = [str(FAMILY), str(SHARED)]

from replay import MAX_ROWS, load_trajectory, replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = np.load(FAMILY / "solution/trajectory.npz")["actions"]
SUCCESS_STEP = 2806  # the oracle replay ends with success after this many controls
TASK = "stool_brace_insert"


def place(s, name, pos=None, quat=None):
    adr = s.model.joint(name + "_free").qposadr[0]
    if pos is not None:
        s.data.qpos[adr : adr + 3] = pos
    if quat is not None:
        s.data.qpos[adr + 3 : adr + 7] = quat
    mujoco.mj_forward(s.model, s.data)


def hold(s, n):
    for _ in range(n):
        s.step(s.hold_action())
        if s.done:
            break
    return s.status()


def write(path, actions, **members):
    np.savez_compressed(path, actions=np.asarray(actions), **members)
    return path


# ------------------------------------------------------------------ model and positive episode
def test_only_robot_is_actuated():
    s = Session()
    assert s.hand == "sharpa" and s.model.nu == 28 and s.action_dim == 28
    assert s.model.nmocap == 0 and s.model.neq == 0
    names = [s.model.joint(j).name for j in s.model.actuator_trnid[:, 0]]
    assert all(n.startswith(("wrist_", "right_")) for n in names)
    for part in ("lower_frame", "upper_frame", "brace", "rail_1", "rail_2", "rail_3"):
        assert s.model.joint(part + "_free").type == mujoco.mjtJoint.mjJNT_FREE
    assert not np.any(s.data.xfrc_applied) and not np.any(s.data.qfrc_applied)
    st = s.status()
    assert st["stage"] == 0 and st["seated_interfaces"] == 3 and not st["done"]


def test_oracle_succeeds_and_truncation_fails():
    s = Session()
    cut = 2535  # mid-way through lowering the opposite side frame
    for row in ORACLE[:cut]:
        s.step(row)
    assert not s.done and s.status()["stage"] == 3
    for row in ORACLE[cut:]:
        s.step(row)
        if s.done:
            break
    st = s.status()
    assert st["success"] and st["reason"] == "success" and st["steps"] == SUCCESS_STEP, st
    assert st["seated_interfaces"] == 8 and st["stage"] == 4
    assert len(ORACLE) - SUCCESS_STEP >= 50  # slack after success
    # Rows after success are not executed.
    sha = s.state_sha()
    s.step(ORACLE[-1])
    assert s.state_sha() == sha and s.steps == SUCCESS_STEP


def test_float32_rows_succeed():
    s = Session()
    st = s.replay(ORACLE.astype(np.float32).astype(np.float64))
    assert st["success"] and st["steps"] == SUCCESS_STEP


# ------------------------------------------------------------------ partial completion and fail-fast
def test_nop_fails_and_replays_exactly(tmp_path):
    s = Session()
    path = write(tmp_path / "nop.npz", np.tile(s.hold_action(), (120, 1)), hand=np.array("sharpa"),
                 success=np.array(True), reward=np.array(1.0), config=np.array(json.dumps({"seat_depth_m": 0})))
    first, second = replay(path), replay(path)
    assert not first["success"] and first["reason"] == "" and first["stage"] == 0
    assert first["state_sha"] == second["state_sha"]
    assert first["initial_sha"] == s.initial_sha


def test_one_seated_brace_dowel_is_not_success():
    s = Session()
    lower = s.data.body("lower_frame")
    entry = s.data.site("lower_frame_leg_m_b0_entry").xpos.copy()
    # Brace standing seated in the empty lower bore (tip_p down), frame never placed.
    place(s, "brace", entry + [0, 0, 0.13], quat=[0, 1, 0, 0])
    s.checker.stage = 1
    st = hold(s, 120)
    assert st["stage"] == 2 and st["seated_interfaces"] == 4
    assert not st["success"] and not st["failed"], st
    assert lower is not None
    # A fully seated brace whose upper dowel has no frame on it never completes the assembly.
    assert st["ends"]["brace_m"]["seated"] is False


def test_assembled_fixture_succeeds_only_after_the_hold():
    s = Session()
    entry = s.data.site("lower_frame_leg_m_b0_entry").xpos.copy()
    place(s, "brace", entry + [0, 0, 0.13], quat=[0, 1, 0, 0])
    lower = s.data.body("lower_frame").xpos.copy()
    place(s, "upper_frame", lower + [0, 0, 0.29])
    s.checker.stage = 3  # the fixture skips the physical lifts; the predicate itself is under test
    for k in range(49):
        s.step(s.hold_action())
        assert not s.success, k
    st = hold(s, 60)
    assert st["success"] and st["seated_interfaces"] == 8 and 50 <= st["steps"] <= 100, st


def test_brace_mid_air_release_fails_at_once():
    s = Session()
    for row in ORACLE[:505]:  # brace carried above the frame
        s.step(row)
    assert s.status()["stage"] == 1 and not s.done
    release = ORACLE[504].copy()
    release[6:] = s.initial_targets[6:]
    for _ in range(40):
        s.step(release)
        if s.done:
            break
    assert s.failure == "brace_dropped" and s.failure_detail["control"] <= 510, s.failure_detail
    # Later rows (even the oracle's) cannot undo the failure.
    sha = s.state_sha()
    for row in ORACLE[505:520]:
        s.step(row)
    assert s.state_sha() == sha and not s.success


def test_free_fall_without_contact_fails():
    s = Session()
    place(s, "brace", s.data.body("brace").xpos + [0, 0, 0.10])
    st = hold(s, 20)
    assert st["reason"] == "brace_dropped" and st["failure_detail"]["control"] <= 3, st


def test_knocked_rail_fails_fast():
    s = Session()
    tilt = np.array([np.cos(0.1), np.sin(0.1), 0, 0])  # 11.5 deg about x
    place(s, "rail_1", quat=tilt)
    st = hold(s, 5)
    assert st["reason"] == "rail_knocked" and st["failure_detail"]["control"] == 0, st


def test_displaced_lower_frame_fails_fast():
    s = Session()
    for name in ("lower_frame", "rail_1", "rail_2", "rail_3"):
        place(s, name, s.data.body(name).xpos + [0.04, 0, 0])
    st = hold(s, 5)
    assert st["reason"] == "lower_frame_displaced" and st["failure_detail"]["control"] == 0, st


def test_part_below_table_or_outside_workspace_fails():
    s = Session()
    place(s, "upper_frame", [1.40, 0.5, 0.80])
    assert hold(s, 3)["reason"] == "left_workspace"
    s = Session()
    place(s, "brace", [0.57, -0.33, 0.70])
    assert hold(s, 3)["reason"] in ("below_table_top", "brace_dropped")


# ------------------------------------------------------------------ trust boundary
def test_forged_members_are_ignored(tmp_path):
    s = Session()
    path = write(tmp_path / "forged.npz", np.tile(s.hold_action(), (30, 1)), success=np.array(True),
                 state_sha=np.array("0" * 64), stage=np.array(4), verdict=np.array(json.dumps({"success": True})))
    result = replay(path)
    assert not result["success"] and result["stage"] == 0 and result["state_sha"] != "0" * 64


def test_ambiguous_or_corrupt_members_are_rejected(tmp_path):
    s = Session()
    good, other = io.BytesIO(), io.BytesIO()
    np.save(good, np.tile(s.hold_action(), (3, 1)))
    np.save(other, np.tile(s.hold_action(), (9, 1)))
    path = tmp_path / "ambiguous.npz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("actions.npy", good.getvalue())
        archive.writestr("actions", other.getvalue())
    with pytest.raises(ValueError):
        replay(path)
    path.write_bytes(b"PK\x03\x04 truncated")
    with pytest.raises(ValueError):
        replay(path)
    with pytest.raises(ValueError):
        replay(write(tmp_path / "two_hands.npz", np.tile(s.hold_action(), (3, 1)), hand=np.array(["sharpa", "wuji"])))
    with pytest.raises(ValueError):
        replay(write(tmp_path / "task.npz", np.tile(s.hold_action(), (3, 1)), task=np.array("assemble_hamburger")))
    names = list(s.actuator_names)
    names[0], names[1] = names[1], names[0]
    with pytest.raises(ValueError):
        replay(write(tmp_path / "names.npz", np.tile(s.hold_action(), (3, 1)), actuator_names=np.array(names)))


def test_width_nan_range_and_row_limit_are_rejected(tmp_path):
    s = Session()
    for width in (26, 27, 29):
        with pytest.raises(ValueError):
            load_trajectory(write(tmp_path / f"w{width}.npz", np.zeros((5, width))))
    bad = np.tile(s.hold_action(), (3, 1))
    bad[1, 7] = np.nan
    with pytest.raises(ValueError):
        load_trajectory(write(tmp_path / "nan.npz", bad))
    far = np.tile(s.hold_action(), (3, 1))
    far[0, 2] = 5.0
    with pytest.raises(ValueError):
        replay(write(tmp_path / "range.npz", far))
    with pytest.raises(ValueError):
        load_trajectory(write(tmp_path / "long.npz", np.tile(s.hold_action(), (MAX_ROWS + 1, 1))))
    with pytest.raises(ValueError):
        load_trajectory(write(tmp_path / "empty.npz", np.zeros((0, 28))))


def test_cli_reports_bad_trajectory_with_exit_zero(tmp_path):
    out = tmp_path / "out.json"
    path = write(tmp_path / "bad.npz", np.zeros((4, 28)), hand=np.array("wuji"))
    proc = subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", TASK, "--traj", str(path), "--out",
                           str(out)], capture_output=True, text=True, cwd=str(FAMILY), timeout=600)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(out.read_text())
    assert result["bad_trajectory"] == 1 and result["success"] is False


# ------------------------------------------------------------------ Wuji
def test_wuji_loads_on_the_same_stage_and_nop_fails(tmp_path):
    sharpa, wuji = Session(hand="sharpa"), Session(hand="wuji")
    assert (sharpa.action_dim, wuji.action_dim) == (28, 26)
    assert sharpa.actuator_names[:6] == wuji.actuator_names[:6]
    assert np.array_equal(sharpa.model.actuator_ctrlrange[:6], wuji.model.actuator_ctrlrange[:6])
    assert np.array_equal(sharpa.initial_targets[:6], wuji.initial_targets[:6])
    assert all(name.startswith("r_wuji_") for name in wuji.actuator_names[6:])
    path = tmp_path / "wuji_nop.npz"
    hands.write_trajectory(path, np.tile(wuji.hold_action(), (100, 1)), hand="wuji", task=TASK)
    first, second = replay(path), replay(path)
    assert first["hand"] == "wuji" and not first["success"] and first["reason"] == ""
    assert first["state_sha"] == second["state_sha"]
    with pytest.raises(ValueError):  # Sharpa-width rows labelled wuji
        replay(write(tmp_path / "mislabel.npz", np.tile(sharpa.hold_action(), (3, 1)), hand=np.array("wuji")))
    with pytest.raises(ValueError):  # Wuji-width rows labelled sharpa
        replay(write(tmp_path / "mislabel2.npz", np.tile(wuji.hold_action(), (3, 1)), hand=np.array("sharpa")))


def test_snapshot_restore_is_exact():
    s = Session()
    for row in ORACLE[:200]:
        s.step(row)
    snap = s.snapshot()
    for row in ORACLE[200:260]:
        s.step(row)
    sha = s.state_sha()
    s.restore(snap)
    for row in ORACLE[200:260]:
        s.step(row)
    assert s.state_sha() == sha
