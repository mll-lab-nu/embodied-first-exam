"""Authoring tests for boot_sole_brush (run from the family folder: python -m pytest tests -q).

Needs DEXHAND_ASSET_DIR (Sharpa Wave) and the Wuji assets next to it (or WUJI_ASSET_DIR). The robot is the Tianji Marvin
arm rig (14 arm targets, then the left and the right hand's fingers); ``arm_ik`` (authoring only) drives the arm here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[1] / "shared"))

from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"
WIDTHS = {"sharpa": 58, "wuji": 54}
RIGHT_FINGERS = slice(36, 58)  # sharpa layout: left arm 0-6, right arm 7-13, left fingers 14-35, right fingers 36-57


def replay_cli(tmp_path, actions=None, hand="sharpa", path=None, extra=()):
    if path is None:
        path = tmp_path / "traj.npz"
        hands.write_trajectory(path, actions, hand=hand, task="boot_sole_brush")
    out = tmp_path / f"out_{len(list(tmp_path.iterdir()))}.json"
    subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", "boot_sole_brush", "--traj", str(path),
                    "--out", str(out), *extra], cwd=HERE, check=True, capture_output=True)
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def oracle():
    actions, hand, _ = hands.read_trajectory(ORACLE, widths=WIDTHS, max_rows=3000)
    assert hand == "sharpa"
    return actions


def test_oracle_two_fresh_replays_identical(tmp_path, oracle):
    a = replay_cli(tmp_path, path=ORACLE)
    b = replay_cli(tmp_path, path=ORACLE)
    assert a["success"] and b["success"] and a["state_sha"] == b["state_sha"]
    assert a["stage"] == 3 and a["clods_in_tray"] == 6
    assert a["n_actions"] - a["steps"] >= 50  # slack after success


def test_oracle_float32(oracle):
    s = Session(hand="sharpa")
    assert s.replay(oracle.astype(np.float32).astype(np.float64))["success"]


def test_nop_fails(oracle):
    s = Session(hand="sharpa")
    st = s.replay(np.repeat(s.initial_targets[None], 3000, axis=0))
    assert not st["success"] and st["reason"] == "episode_budget"


def test_truncations_fail(oracle):
    s = Session(hand="sharpa")
    success_step = s.replay(oracle)["steps"]
    for rows in (1000, success_step - 1):
        st = s.replay(oracle[:rows])
        assert not st["success"] and not st["done"]


def test_brush_drop_is_permanent(oracle):
    s = Session(hand="sharpa")
    rows = oracle.copy()
    rows[620:660, RIGHT_FINGERS] = 0.0  # open the hand while carrying the brush over the tray, then resume the oracle
    st = s.replay(rows)
    assert st["failed"] and st["reason"] == "brush_dropped"


def test_hand_debris_contact_fails():
    import arm_ik

    s = Session(hand="sharpa")
    m, d = s.model, s.data
    ik = arm_ik.ArmIK(m, "right")
    root = m.body("wrist_stage").id
    tip = m.geom("right_middle_fingertip_collision").id
    pos0, R0 = d.xpos[root].copy(), d.xmat[root].reshape(3, 3).copy()
    offset = d.geom_xpos[tip] - pos0  # fingertip relative to the hand root (orientation is held)
    clod = d.xpos[m.body("clod_1").id].copy()
    above = clod - offset + np.array([0.0, -0.06, 0.08])
    sweep = clod - offset + np.array([0.0, -0.06, 0.002])
    row = s.initial_targets.copy()
    q = row[s.layout["arm"]["right"]].copy()
    st = None
    # carry the open hand (no brush) above clod 1, lower the fingertips to the sole and sweep them through the clod
    for k in range(400):
        if k < 150:
            goal = pos0 + (above - pos0) * min(1.0, k / 120)
        elif k < 230:
            goal = above + (sweep - above) * min(1.0, (k - 150) / 60)
        else:
            goal = sweep + np.array([0.0, 0.12 * min(1.0, (k - 230) / 100), 0.0])
        q, _, _ = ik.solve(goal, R0, q0=q)
        row[s.layout["arm"]["right"]] = q
        st = s.step(np.clip(row, s.lo, s.hi))
        if st["done"]:
            break
    assert st["failed"] and st["reason"] in ("hand_touched_debris", "boot_displaced", "debris_outside_tray")


def test_robot_collision_fails():
    """The parked left arm folded into the torso: arm/stand contacts end the episode at once."""
    s = Session(hand="sharpa")
    row = s.initial_targets.copy()
    target = row.copy()
    target[3] = -2.4  # left ELBOW_YAW_L_J4
    st = None
    for k in range(200):
        st = s.step(np.clip(row + (target - row) * min(1.0, k / 150), s.lo, s.hi))
        if st["done"]:
            break
    assert st["failed"] and st["reason"] == "robot_collision"


def test_oracle_has_no_robot_contacts(oracle):
    """Only the working right hand touches the world: no arm, stand or parked-hand contact (checked after every
    control here; the checker fails the episode on such a contact in any physics substep)."""
    from scene import robot_parts

    s = Session(hand="sharpa")
    m, d = s.model, s.data
    _, rest = robot_parts(m)
    rest_g = np.isin(m.geom_bodyid, sorted(rest))
    hits = 0
    for row in oracle:
        s.step(row)
        n = d.ncon
        g = d.contact.geom[:n][d.contact.efc_address[:n] >= 0]
        hits += int(np.sum(rest_g[g[:, 0]] | rest_g[g[:, 1]]))
        if s.done:
            break
    assert s.success and hits == 0


def test_wrong_width_and_forged_members(tmp_path, oracle):
    bad = tmp_path / "bad.npz"
    np.savez_compressed(bad, actions=oracle, hand=np.array("wuji"), task=np.array("boot_sole_brush"))
    r = replay_cli(tmp_path, path=bad)
    assert r["bad_trajectory"] == 1 and not r["success"]
    forged = tmp_path / "forged.npz"
    np.savez_compressed(forged, actions=oracle[:500], hand=np.array("sharpa"), success=np.array(True))
    r = replay_cli(tmp_path, path=forged)
    assert r["bad_trajectory"] == 0 and not r["success"]


def test_wuji_composes_nop_and_deterministic(tmp_path):
    s = Session(hand="wuji")
    assert s.action_dim == 54 and s.actuator_names[:14] == Session(hand="sharpa").actuator_names[:14]
    rows = np.repeat(s.initial_targets[None], 200, axis=0)
    a = replay_cli(tmp_path, rows, hand="wuji")
    b = replay_cli(tmp_path, rows, hand="wuji")
    assert not a["success"] and a["state_sha"] == b["state_sha"] and a["hand"] == "wuji"


def test_release_in_air_and_catch_fails(oracle):
    """L1: opening the hand for a few controls while carrying the brush fails at once; re-gripping cannot recover."""
    s = Session(hand="sharpa")
    rows = oracle.copy()
    rows[600:606, RIGHT_FINGERS] = 0.0
    st = s.replay(rows)
    assert st["failed"] and st["reason"] == "brush_dropped"
    assert st["failure_detail"]["where"] == "released_in_air" and st["steps"] <= 606


def test_nan_and_out_of_range_rejected(tmp_path, oracle):
    rows = oracle.copy()
    rows[10, 3] = np.nan
    bad = tmp_path / "nan.npz"
    np.savez_compressed(bad, actions=rows, hand=np.array("sharpa"))
    r = replay_cli(tmp_path, path=bad)
    assert r["bad_trajectory"] == 1 and not r["success"]
    rows = oracle.copy()
    rows[10, 40] = 50.0
    r = replay_cli(tmp_path, rows)
    assert r["bad_trajectory"] == 1 and not r["success"]


def test_state_sha_ignores_prose():
    s = Session(hand="sharpa")
    config = dict(s.config, instruction="edited text", title="edited", cameras=[])
    t = Session(hand="sharpa", config=config)
    assert s.state_sha() == t.state_sha()
