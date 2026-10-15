"""Authoring tests of the vacuum_bin_reseat family (trust boundary, negatives, oracle, both hands).

    cd robot_coding_bench
    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand \
    python -m pytest -q scripts/dexhand/families/vacuum_bin_reseat/tests

The oracle tests replay the full 869-control episode in fresh processes (about 15 s each).
"""

from __future__ import annotations

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
SHARED = FAMILY.parents[1] / "shared"
sys.path[:0] = [str(FAMILY), str(SHARED)]

import hands  # noqa: E402
from runtime import Session  # noqa: E402

TASK = "vacuum_bin_reseat"
ORACLE = FAMILY / "solution" / "trajectory.npz"
OPEN_UNDER = np.array([0.0, 0.0, 0.0, 0, 0.0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, -0.1, 0, 0, 0, 0, -0.1, 0, 0, 0])


@pytest.fixture(scope="module")
def sharpa():
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def rows():
    with np.load(ORACLE, allow_pickle=False) as archive:
        return np.asarray(archive["actions"], dtype=np.float64)


def replay_cli(tmp_path, archive: Path, *extra) -> dict:
    out = tmp_path / (archive.stem + ".json")
    env = dict(os.environ, PYTHONPATH=f"{FAMILY}:{SHARED}")
    done = subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", TASK, "--traj", str(archive),
                           "--out", str(out), *extra], env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(out.read_text())


def save(tmp_path, name, actions, hand="sharpa", **members):
    path = tmp_path / f"{name}.npz"
    np.savez_compressed(path, actions=np.asarray(actions), hand=np.array(hand), **members)
    return path


# ---------------------------------------------------------------------------------------------- model
def test_only_the_hand_is_actuated(sharpa):
    m = sharpa.model
    assert sharpa.hand == "sharpa" and m.nu == 28 and sharpa.action_dim == 28
    assert m.nmocap == 0 and m.neq == 0
    joints = [m.joint(int(j)).name for j in m.actuator_trnid[:, 0]]
    assert all(name.startswith(("wrist_", "right_")) for name in joints)
    assert m.joint("vacuum_free").type == mujoco.mjtJoint.mjJNT_FREE
    assert m.joint("container_free").type == mujoco.mjtJoint.mjJNT_FREE
    button = m.joint("button_depression")
    assert button.type == mujoco.mjtJoint.mjJNT_SLIDE and m.jnt_stiffness[button.id] > 0
    assert not np.any(sharpa.data.xfrc_applied) and not np.any(sharpa.data.qfrc_applied)


def test_reset_is_settled_and_seated(sharpa):
    sharpa.reset()
    f = sharpa.features()
    assert f["seat_distance_m"] < 1e-6 and f["seat_angle_rad"] < 1e-5 and f["button_travel_m"] < 0.0005
    for _ in range(50):
        sharpa.step(sharpa.hold_action())
    f = sharpa.features()
    assert f["seat_distance_m"] < 1e-4 and f["body_displacement_m"] < 1e-4
    assert not sharpa.done and sharpa.status()["stage"] == 0


def bridge_rise(session, newtons, seconds, press=False):
    """Probe only (never part of a trajectory): pull the seated bin straight up (vacuum frame) and return the largest
    rise of its latch bridge relative to the vacuum body."""
    m, d, ch = session.model, session.data, session.checker
    session.reset()
    up = d.xmat[ch.vac].reshape(3, 3)[:, 2]
    bridge, button = m.geom("container_latch_bridge").id, m.body("release_button").id

    def height():
        rv = d.xmat[ch.vac].reshape(3, 3)
        return float((rv.T @ (d.geom_xpos[bridge] - d.xpos[ch.vac]))[2])

    start, rise = height(), 0.0
    for _ in range(int(seconds / m.opt.timestep)):
        d.xfrc_applied[ch.bin, :3] = newtons * up
        if press:
            d.xfrc_applied[button, :3] = [0, 0, -8.0]
        mujoco.mj_step(m, d)
        rise = max(rise, height() - start)
    d.xfrc_applied[:] = 0
    session.reset()
    return rise


def test_latch_retains_a_straight_lift_until_the_button_is_pressed():
    probe = Session()
    # Button up: tooth + lip hold the top; a 10 N pull lifts the whole vacuum instead (without the lip 2.8 N sufficed).
    assert bridge_rise(probe, 10.0, 1.0) < 0.005
    # Button pressed: the top tilts out from under the lip and 3 N lifts the bin away.
    assert bridge_rise(probe, 3.0, 1.0, press=True) > 0.03


def test_state_sha_ignores_text_but_not_physics():
    config = json.loads((FAMILY / "task.json").read_text())
    a = Session(config=dict(config))
    b = Session(config=dict(config, description="edited prose", instruction="edited prose"))
    assert a.state_sha() == b.state_sha()
    changed = json.loads(json.dumps(config))
    changed["checker"]["seat_tolerance_m"] = 0.004
    assert Session(config=changed).state_sha() != a.state_sha()


def test_asset_manifest_is_checked(tmp_path, monkeypatch):
    import scene

    manifest = json.loads((scene.ASSETS / "manifest.json").read_text())
    assert set(manifest["files"]) == {"vacuum_scene.xml", "initial_state.npz"}
    scene.verify_assets()


# ---------------------------------------------------------------------------------------------- verdicts
def test_oracle_succeeds_in_fresh_processes_and_float32(tmp_path, rows):
    first = replay_cli(tmp_path, ORACLE)
    second = replay_cli(tmp_path, ORACLE)
    assert first["success"] and second["success"] and first["reason"] == "success"
    assert first["state_sha"] == second["state_sha"]
    assert first["stage"] == 3 and first["steps"] <= len(rows) - 50  # success leaves >= 50 slack rows
    rounded = replay_cli(tmp_path, save(tmp_path, "f32", rows.astype(np.float32), task=np.array(TASK)))
    assert rounded["success"]


def test_nop_and_partials_fail(tmp_path, sharpa, rows):
    nop = replay_cli(tmp_path, save(tmp_path, "nop", np.tile(sharpa.hold_action(), (300, 1))))
    assert not nop["success"] and nop["stage"] == 0
    removed = replay_cli(tmp_path, save(tmp_path, "removed", rows[:700]))
    assert not removed["success"] and removed["stage"] == 1
    held = replay_cli(tmp_path, save(tmp_path, "held", rows[:800]))
    assert not held["success"] and held["stage"] == 2  # reseated but the hand still holds it
    short = replay_cli(tmp_path, save(tmp_path, "short", rows[: first_success(rows) - 1]))
    assert not short["success"]


def first_success(rows):
    s = Session()
    return s.replay(rows)["steps"]


def test_no_release_press_never_counts(tmp_path, rows):
    lifted = rows.copy()
    lifted[:255, 2] = np.minimum(lifted[:255, 2] + 0.06, 0.4)  # the poke never reaches the button
    result = replay_cli(tmp_path, save(tmp_path, "nopress", lifted))
    assert not result["success"] and result["stage"] == 0


def test_drop_and_catch_fails_fast(tmp_path, rows):
    dropped = list(rows[:640])
    for _ in range(3):
        row = rows[639].copy()
        row[6:] = OPEN_UNDER
        row[2] -= 0.04
        dropped.append(row)
    dropped += list(rows[640:])
    result = replay_cli(tmp_path, save(tmp_path, "dropcatch", np.asarray(dropped)))
    assert not result["success"] and result["reason"] == "bin_dropped"
    assert result["failure_detail"]["control"] <= 643


def test_knocking_the_vacuum_fails_fast(tmp_path, sharpa):
    start = sharpa.hold_action().copy()
    knock = []
    for i in range(60):
        row = start.copy()
        row[0], row[1], row[2] = 0.15, -0.30, start[2] - 0.33 * min(1, (i + 1) / 30)
        knock.append(row)
    for i in range(80):
        row = knock[-1].copy()
        row[1] = -0.30 + 0.6 * min(1, (i + 1) / 40)
        knock.append(row)
    result = replay_cli(tmp_path, save(tmp_path, "knock", np.asarray(knock)))
    assert not result["success"] and result["reason"] == "vacuum_body_disturbed"
    assert result["steps"] < len(knock)


# ---------------------------------------------------------------------------------------------- trust boundary
def test_forged_members_are_ignored_or_rejected(tmp_path, sharpa):
    hold = np.tile(sharpa.hold_action(), (40, 1))
    ignored = replay_cli(tmp_path, save(tmp_path, "claims", hold, success=np.array(True), stage=np.array(3)))
    assert ignored["bad_trajectory"] == 0 and not ignored["success"]
    for name, members in {
        "wrong_task": {"task": np.array("assemble_hamburger")},
        "wrong_names": {"actuator_names": np.array(["x"] * 28)},
    }.items():
        assert replay_cli(tmp_path, save(tmp_path, name, hold, **members))["bad_trajectory"] == 1
    shadow = tmp_path / "shadow.npz"
    with zipfile.ZipFile(shadow, "w") as archive:
        archive.writestr("actions", b"not an array")
        with archive.open("actions.npy", "w") as stream:
            np.lib.format.write_array(stream, hold)
    assert replay_cli(tmp_path, shadow)["bad_trajectory"] == 1


@pytest.mark.parametrize("case", ["wide", "narrow", "nan", "range", "empty", "too_many", "object"])
def test_malformed_actions_are_bad_trajectories(tmp_path, sharpa, case):
    hold = np.tile(sharpa.hold_action(), (20, 1))
    actions = {
        "wide": np.hstack([hold, np.zeros((20, 1))]),
        "narrow": hold[:, :26],  # wuji width under the sharpa label
        "nan": np.where(np.arange(28) == 7, np.nan, hold),
        "range": hold + np.eye(1, 28, 3) * 10,
        "empty": np.zeros((0, 28)),
        "too_many": np.tile(sharpa.hold_action(), (3001, 1)),
        "object": np.array([[object()] * 28], dtype=object),
    }[case]
    path = tmp_path / f"{case}.npz"
    if case == "object":
        np.savez(path, actions=actions, hand=np.array("sharpa"))
    else:
        save(tmp_path, case, actions)
    result = replay_cli(tmp_path, path)
    assert result["bad_trajectory"] == 1 and not result["success"]


# ---------------------------------------------------------------------------------------------- wuji
def test_wuji_loads_with_the_same_stage_and_nop_fails(tmp_path, sharpa):
    wuji = Session(hand="wuji")
    assert wuji.action_dim == 26 and wuji.actuator_names[:6] == sharpa.actuator_names[:6]
    assert wuji.actuator_names[6].startswith("r_wuji_")
    assert np.allclose(wuji.model.actuator_ctrlrange[:6], sharpa.model.actuator_ctrlrange[:6])
    path = save(tmp_path, "wuji_nop", np.tile(wuji.hold_action(), (100, 1)), hand="wuji")
    a, b = replay_cli(tmp_path, path), replay_cli(tmp_path, path)
    assert not a["success"] and a["hand"] == "wuji" and a["state_sha"] == b["state_sha"]
    sharpa_rows = save(tmp_path, "sharpa_as_wuji", np.tile(sharpa.hold_action(), (10, 1)), hand="wuji")
    assert replay_cli(tmp_path, sharpa_rows)["bad_trajectory"] == 1
    assert hands.canonical("wuji") == "wuji"
