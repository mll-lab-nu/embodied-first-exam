"""Authoring tests of the sweep_dustpan family (quick: no full-length episode; see tools/ for those).

    cd robot_coding_bench
    PYTHONPATH=scripts/dexhand/families/sweep_dustpan:scripts/dexhand/shared \
    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand MUJOCO_GL=egl \
    python -m pytest -q scripts/dexhand/families/sweep_dustpan/tests

Full-length evidence (positive oracle, bit-exact check, physical negatives with videos) is produced by
tools/bitexact.py, tools/make_negatives.py and the task's own grader; see README.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import mujoco
import numpy as np
import pytest

FAMILY = Path(__file__).resolve().parents[1]
SHARED = FAMILY.parents[1] / "shared"
sys.path[:0] = [str(FAMILY), str(SHARED)]

import hands  # noqa: E402
from runtime import Session  # noqa: E402

PROVENANCE = json.loads((FAMILY / "provenance.json").read_text())


@pytest.fixture(scope="module")
def sharpa():
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def oracle():
    sys.path.insert(0, str(SHARED / "solution"))
    from solution_parts import load

    rows, hand = load(FAMILY / "solution")
    return np.ascontiguousarray(rows, dtype=np.float64), hand


def replay_cli(tmp_path, archive: Path, *extra) -> dict:
    out = tmp_path / (archive.stem + ".json")
    env = dict(os.environ, PYTHONPATH=f"{FAMILY}:{SHARED}")
    done = subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", "sweep_dustpan", "--traj", str(archive),
                           "--out", str(out), *extra], env=env, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(out.read_text())


def test_layout_and_accepted_initial_state(sharpa, oracle):
    actions, hand = oracle
    assert hand == "sharpa" and actions.shape == (PROVENANCE["native_steps"] + 16000, 58)
    assert np.all(actions[PROVENANCE["native_steps"]:] == actions[PROVENANCE["native_steps"] - 1])
    assert sharpa.action_dim == 58 and sharpa.actuator_names[0] == "SHOULDER_PITCH_L_J1_target"
    assert sharpa.actuator_names[14].startswith("l_hand_") and sharpa.actuator_names[36].startswith("r_hand_")
    assert sharpa.physics_sha() == PROVENANCE["native_initial_state_sha256"]
    assert np.array_equal(sharpa.hold_action(), actions[0])
    assert sharpa.cameras() == ["overview", "work", "pan", "side"]
    assert sharpa.status()["done"] is False and sharpa.status()["in_pan"] == 0


def test_hand_selection():
    with pytest.raises(ValueError):
        Session(hand="allegro")
    with pytest.raises(ValueError):
        Session(task="essential_cube_layer")


def test_snapshot_restore_is_exact(sharpa, oracle):
    actions, _ = oracle
    sharpa.reset()
    sharpa.step_many(actions[:400])
    snap = sharpa.snapshot()
    sharpa.step_many(actions[400:800])
    first = sharpa.state_sha()
    sharpa.restore(snap)
    sharpa.step_many(actions[400:800])
    assert sharpa.state_sha() == first
    replayed = Session()
    replayed.replay(actions[:800])
    assert replayed.state_sha() == first
    replayed.close()


def test_open_broom_hand_fails_fast(sharpa):
    sharpa.reset()
    row = sharpa.hold_action()
    row[36:58] = np.clip(0.0, sharpa.ctrl_range[36:58, 0], sharpa.ctrl_range[36:58, 1])
    status = sharpa.step_many(np.repeat(row[None], 6000, axis=0))
    assert status["failed"] and status["reason"] in (
        "broom_dropped", "tool_slipped_in_hand", "tool_pressed_by_other_robot_link"), status
    assert status["steps"] < 6000
    assert sharpa.step(row)["steps"] == status["steps"]  # no-op after done


def _fixture_step(session, edit):
    """Checker fixture: edit a free body's pose in a scratch state, then take one native step."""
    session.reset()
    edit(session.model, session.data)
    mujoco.mj_forward(session.model, session.data)
    return session.step(session.hold_action())


def test_checker_fixture_debris_outside_workspace(sharpa):
    def edit(model, data):
        adr = model.jnt_qposadr[model.joint("debris_3_free").id]
        data.qpos[adr] = 1.2

    status = _fixture_step(sharpa, edit)
    assert status["failed"] and status["reason"] == "debris_left_workspace:debris_3"


def test_checker_fixture_robot_touching_debris(sharpa):
    """A piece pressed into a fingertip registers a direct robot contact (the piece is also far above the floor,
    which is reported first)."""

    def edit(model, data):
        adr = model.jnt_qposadr[model.joint("debris_1_free").id]
        data.qpos[adr : adr + 3] = data.site("r_hand_index_fingertip").xpos

    status = _fixture_step(sharpa, edit)
    assert status["failed"] and bool(sharpa.checker.state["direct"][1])


def test_checker_fixture_contained_pieces_are_recognized(sharpa):
    """All six pieces placed on the pan floor: containment and pan contact are recognized, but no success
    (pan on the floor, no bristle contact, no terminal hold)."""

    def edit(model, data):
        pan = data.body("dustpan")
        for i in range(6):
            adr = model.jnt_qposadr[model.joint(f"debris_{i}_free").id]
            data.qpos[adr : adr + 3] = pan.xpos + np.array([-0.15 + 0.06 * i, 0.0, 0.016])
            data.qpos[adr + 3 : adr + 7] = [1, 0, 0, 0]

    _fixture_step(sharpa, edit)
    sharpa.hold(200)
    features = sharpa.features()
    assert sum(d["inside_pan"] for d in features["debris"].values()) == 6
    assert sharpa.status()["success"] is False and not features["terminal_valid"]


def test_wuji_start_keeps_the_frozen_scene_and_holds_the_tools(tmp_path):
    """Wuji Hand 2.2: declared pre-grasp (fingers only), both tools held past the 1.2 s grip check, deterministic."""
    first = Session(hand="wuji")
    sharpa_reset = np.load(FAMILY / "assets/reset.npz")
    m = first.model
    wuji_joints = {m.joint(i).name: i for i in range(m.njnt)}
    for name, adr, dim in zip(sharpa_reset["joint_names"], sharpa_reset["joint_qposadr"], sharpa_reset["joint_qposdim"]):
        if str(name) in wuji_joints:  # every arm, tool, debris and bristle coordinate of the Sharpa start
            j = wuji_joints[str(name)]
            ours = first.data.qpos[m.jnt_qposadr[j]:m.jnt_qposadr[j] + int(dim)]
            assert np.array_equal(ours, sharpa_reset["initial_qpos"][int(adr):int(adr) + int(dim)]), name
    assert first.action_dim == 54 and first.actuator_names[14] == "l_wuji_l_THJ0"
    rows = np.repeat(first.hold_action()[None], 4000, axis=0)  # 2 s: past the 1.2 s settling period
    status = first.replay(rows)
    assert not status["failed"] and min(first.checker.state["min_contacts"].values()) >= 2
    second = Session(hand="wuji")
    second.replay(rows)
    assert first.state_sha() == second.state_sha()
    path = tmp_path / "wuji.npz"
    first.save_trajectory(rows[:200], path)
    result = replay_cli(tmp_path, path)
    assert result["success"] is False and result["bad_trajectory"] == 0 and result["hand"] == "wuji"
    first.close()
    second.close()


def test_wuji_start_file_must_not_move_the_frozen_scene(tmp_path, monkeypatch):
    """A reset_wuji.npz that changes a frozen non-finger coordinate is refused."""
    import runtime
    saved = dict(np.load(FAMILY / runtime.WUJI_RESET))
    saved["initial_qpos"] = saved["initial_qpos"].copy()
    m = Session(hand="wuji", allow_unsupported_hand=True).model
    saved["initial_qpos"][m.jnt_qposadr[m.joint("broom_free").id]] += 0.01  # move the broom by 1 cm
    fake = tmp_path / "reset_wuji.npz"
    np.savez(fake, **saved)
    monkeypatch.setattr(runtime, "WUJI_RESET", str(fake))
    with pytest.raises(ValueError, match="frozen coordinate"):
        Session(hand="wuji")


@pytest.mark.parametrize(
    "name, arrays",
    [
        ("bad_width", lambda r: dict(actions=r[:, :57])),
        ("sharpa_rows_wuji_label", lambda r: dict(actions=r, hand=np.array("wuji"))),
        ("wuji_width_sharpa_label", lambda r: dict(actions=r[:, :54], hand=np.array("sharpa"))),
        ("wuji_width_no_label", lambda r: dict(actions=r[:, :54])),
        ("unknown_hand", lambda r: dict(actions=r, hand=np.array("allegro"))),
        ("other_task", lambda r: dict(actions=r, task=np.array("essential_cube_layer"))),
        ("names_reversed", lambda r: dict(actions=r, actuator_names=np.array(["x"] * 58))),
        ("nan", lambda r: dict(actions=np.where(np.arange(r.size).reshape(r.shape) == 5, np.nan, r))),
        ("out_of_range", lambda r: dict(actions=r + np.eye(len(r), 58)[:, :58] * 10)),
        ("empty", lambda r: dict(actions=r[:0])),
        ("empty_hand", lambda r: dict(actions=r, hand=np.array([], dtype="<U6"))),
        ("int_hand", lambda r: dict(actions=r, hand=np.array(3))),
        ("three_d", lambda r: dict(actions=r[None])),
        ("complex", lambda r: dict(actions=r.astype(complex))),
    ],
)
def test_bad_archives_are_rejected_cleanly(tmp_path, oracle, name, arrays):
    rows = oracle[0][:50]
    path = tmp_path / f"{name}.npz"
    np.savez(path, **arrays(rows))
    result = replay_cli(tmp_path, path)
    assert result["success"] is False and result["bad_trajectory"] == 1


def test_raw_and_garbage_archives(tmp_path):
    import zipfile

    raw = tmp_path / "raw.npz"
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("actions", np.zeros((10, 58)).tobytes())
    garbage = tmp_path / "garbage.npz"
    garbage.write_bytes(b"not a zip")
    for path in (raw, garbage):
        result = replay_cli(tmp_path, path)
        assert result["success"] is False and result["bad_trajectory"] == 1


def test_object_array_is_never_unpickled(tmp_path):
    path = tmp_path / "object.npz"
    np.savez(path, actions=np.array([[1, 2], [3]], dtype=object))
    result = replay_cli(tmp_path, path)
    assert result["bad_trajectory"] == 1


def test_forged_members_are_ignored(tmp_path, sharpa):
    path = tmp_path / "forged.npz"
    rows = np.repeat(sharpa.hold_action()[None], 100, axis=0)
    np.savez(path, actions=rows, success=np.array(1), in_pan=np.array(6), state_sha=np.array("0" * 64))
    result = replay_cli(tmp_path, path)
    assert result["success"] is False and result["bad_trajectory"] == 0 and result["steps"] == 100


def test_row_limit(tmp_path):
    with pytest.raises(hands.HandError):
        path = tmp_path / "long.npz"
        np.savez(path, actions=np.zeros((160_001, 58)))
        hands.read_trajectory(path, widths={"sharpa": 58, "wuji": 54}, max_rows=160_000, max_bytes=96_000_000)
