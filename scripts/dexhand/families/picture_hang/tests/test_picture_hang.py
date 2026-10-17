"""Authoring tests for picture_hang: model invariants, oracle, negatives, trust boundary, Wuji.

Run from the family folder with the hand assets available (DEXHAND_ASSET_DIR / WUJI_ASSET_DIR):
    python -m pytest -q tests/test_picture_hang.py
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import json
import tempfile
import zipfile

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE)]

import mujoco  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import replay as R  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"


@pytest.fixture(scope="module")
def oracle():
    actions, hand, _ = R.load_trajectory(ORACLE)
    assert hand == "sharpa"
    return actions


@pytest.fixture(scope="module")
def oracle_result():
    return R.replay(ORACLE)


def save(rows, hand="sharpa", **extra):
    tmp = Path(tempfile.mkdtemp()) / "t.npz"
    if extra:
        np.savez_compressed(tmp, actions=np.asarray(rows), hand=np.array(hand), **extra)
    else:
        hands.write_trajectory(tmp, rows, hand=hand, task="picture_hang")
    return tmp


def test_only_arms_and_fingers_are_actuated():
    from scene import arm_rig

    sharpa = Session()
    for hand, width in (("sharpa", 58), ("wuji", 54)):
        s = Session(hand=hand)
        m = s.model
        assert m.nu == width == s.action_dim
        assert m.nmocap == 0 and m.neq == 0
        joints = [m.joint(int(j)).name for j in m.actuator_trnid[:, 0]]
        assert joints[:14] == arm_rig.ARM_JOINTS["left"] + arm_rig.ARM_JOINTS["right"]
        assert not any(j.startswith(("picture", "l_ring", "r_ring")) for j in joints)
        assert m.joint("picture_free").type == mujoco.mjtJoint.mjJNT_FREE
        # The Marvin arms (servo gains, ranges) are the same for both hands.
        assert np.allclose(m.actuator_gainprm[:14, 0], sharpa.model.actuator_gainprm[:14, 0])
        assert np.allclose(m.actuator_ctrlrange[:14], sharpa.model.actuator_ctrlrange[:14])
        assert s.robot.startswith("marvin-bimanual-")


def test_oracle_succeeds_with_slack_and_is_deterministic(oracle, oracle_result):
    again = R.replay(ORACLE)
    assert oracle_result["success"] and again["success"]
    assert oracle_result["state_sha"] == again["state_sha"]
    assert oracle_result["stage"] == 3
    assert len(oracle) - oracle_result["steps"] >= 50


def test_float32_rows_still_succeed(oracle):
    assert R.replay(save(oracle.astype(np.float32).astype(np.float64)))["success"]


def test_nop_and_truncations_fail(oracle, oracle_result):
    s = Session()
    assert not R.replay(save(np.repeat(s.initial_targets[None], 600, 0)))["success"]
    for cut in (300, 530, oracle_result["steps"] - 1):
        r = R.replay(save(oracle[:cut]))
        assert not r["success"], cut


def test_drop_mid_carry_fails_fast(oracle):
    s = Session()
    rows = oracle.copy()
    rows[250:] = s.initial_targets  # both arms return to the open start pose mid-carry: the frame is dropped
    r = R.replay(save(rows))
    assert not r["success"] and r["reason"] == "picture_unsupported"
    assert 250 < r["steps"] <= 260 and r["steps"] < len(rows)


def test_released_unthreaded_frame_is_not_hanging():
    """A frame resting on the hook lips (rings above the saddles, not threaded) never counts as engaged."""
    s = Session()
    m, d = s.model, s.data
    adr = m.jnt_qposadr[m.joint("picture_free").id]
    # Ring wire centred on the lip axis (x = 0.728) with its arc on the lip top: inside the loop in y-z, but not
    # between the lip and the wall.
    d.qpos[adr:adr + 3] = [0.728 - 0.033, 0.0, 1.373 - 0.478]
    mujoco.mj_forward(m, d)
    for side in "lr":
        ok, local = s.checker.threaded(d, side)
        assert not ok and local[0] > 0.0045
    # The same pose 3 mm further toward the wall is threaded.
    d.qpos[adr] += 0.003
    mujoco.mj_forward(m, d)
    assert all(s.checker.threaded(d, side)[0] for side in "lr")


def test_threaded_geometry_accepts_the_hung_pose(oracle_result):
    final = oracle_result["final"]
    assert final["threaded"] == {"l": True, "r": True}
    assert min(final["hook_load_share"].values()) >= 0.2
    assert final["hand_contacts"] == 0


def test_forged_metadata_and_wrong_width_are_rejected(oracle):
    forged = save(oracle[:10], success=np.array(True), state_sha=np.array("x"))
    assert not R.replay(forged)["success"]  # extra members are ignored, the rows decide
    with pytest.raises(Exception):
        R.load_trajectory(save(oracle, hand="wuji"))  # 58-wide rows labelled wuji
    with pytest.raises(Exception):
        R.load_trajectory(save(oracle[:, :54]))
    bad = save(oracle.copy())
    with zipfile.ZipFile(bad, "a") as z:
        z.writestr("actions", b"shadow")
    with pytest.raises(Exception):
        R.load_trajectory(bad)


def test_replay_cli_reports_bad_trajectory_with_exit_zero(tmp_path):
    bad = tmp_path / "bad.npz"
    bad.write_bytes(b"not a zip")
    out = tmp_path / "r.json"
    proc = subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", "picture_hang", "--traj", str(bad),
                           "--out", str(out)], cwd=HERE, capture_output=True, text=True)
    assert proc.returncode == 0
    result = json.loads(out.read_text())
    assert result["bad_trajectory"] == 1 and not result["success"]


def test_wuji_nop_is_deterministic_and_fails():
    s = Session(hand="wuji")
    rows = np.repeat(s.initial_targets[None], 300, 0)
    a, b = R.replay(save(rows, hand="wuji")), R.replay(save(rows, hand="wuji"))
    assert not a["success"] and a["state_sha"] == b["state_sha"] and a["hand"] == "wuji"


def test_wuji_fingers_flex_toward_the_frame():
    s = Session(hand="wuji")
    m, d = s.model, s.data
    for side, sign in (("r", 1.0), ("l", -1.0)):
        site = m.site(f"{side}_wuji_{side}_index_finger_tip").id
        joint = m.actuator_trnid[s.actuator_names.index(f"{side}_wuji_{side}_FFJ0"), 0]
        s.reset()  # the arm start pose: both palms face the frame (fingers down)
        before = d.site_xpos[site].copy()
        d.qpos[m.jnt_qposadr[joint]] = 1.0
        mujoco.mj_forward(m, d)
        assert sign * (d.site_xpos[site][1] - before[1]) > 0.05


def test_nan_and_out_of_range_rows_are_bad_trajectories(oracle):
    rows = oracle[:20].copy()
    rows[5, 3] = np.nan
    tmp = Path(tempfile.mkdtemp()) / "nan.npz"
    np.savez_compressed(tmp, actions=rows, hand=np.array("sharpa"))
    with pytest.raises(Exception):
        R.load_trajectory(tmp)
    rows = oracle[:20].copy()
    rows[5, 0] = 5.0  # arm joint target far outside its +-3.11 rad range
    with pytest.raises(R.BadTrajectory):
        R.replay(save(rows))


def test_knock_off_after_engagement_fails_fast():
    """Hang the frame, open the hands, grab it again before the hold completes, lift it off the saddles, pull it
    away from the wall and let go: the episode fails (fell_off_hook) at that moment."""
    sys.path[:0] = [str(HERE / "tools"), str(HERE.parents[1] / "shared")]
    import arm_author
    import controller as C

    s = arm_author.proxy(Session(), "sharpa", rest=arm_author.REST)  # old stage rows -> Marvin arm rows (IK)
    c = C.Controller(s, arm_author.ARM_PARAMS["sharpa"])
    p = c.p
    c.ramp(1.0, "approach", squeeze=p["open_in"], thumb=1.0)
    c.ramp(1.0, "squeeze", squeeze=p["squeeze_in"], curl=p["curl"])
    c.ramp(1.0, "lift", z=c.cmd["z"] + p["lift"])
    c.ramp(3.0, "carry", x=p["x0"] + 0.15, z=p["z0"] + 0.195)
    c.servo(2.0, "align", z_target=p["window_z"], until=c.aligned)
    c.servo(6.0, "insert", z_target=p["window_z"], x_target=p["insert_ring_x"], until=c.inserted, max_rate=0.0004)
    c.servo(3.0, "lower", z_target=p["window_z"] - p["rest_drop"], x_target=p["insert_ring_x"], pitch_lock=False,
            until=c.loaded, max_rate=0.0004)
    assert s.status()["stage"] == 2
    c.ramp(0.6, "release", squeeze=0.03)
    c.ramp(0.2, "regrasp", squeeze=p["squeeze_in"])
    c.ramp(0.5, "knock", z=c.cmd["z"] + 0.03)
    c.ramp(0.5, "knock", x=c.cmd["x"] - 0.04)
    c.ramp(0.3, "let go", squeeze=0.0)
    c.ramp(1.0, "after")
    st = s.status()
    assert not st["success"] and st["reason"] == "fell_off_hook"
    assert st["failure_detail"]["substep"] is not None
