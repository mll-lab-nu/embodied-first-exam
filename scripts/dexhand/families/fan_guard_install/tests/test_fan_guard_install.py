"""Authoring tests for fan_guard_install (run with the pinned MuJoCo env; DEXHAND_ASSET_DIR / WUJI_ASSET_DIR set).

python -m pytest scripts/dexhand/families/fan_guard_install/tests -q
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import mujoco
import numpy as np
import pytest

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

from runtime import Session  # noqa: E402

SOLUTION = FAMILY / "solution/trajectory.npz"


def rows():
    with np.load(SOLUTION) as archive:
        return archive["actions"].copy()


def replay_cli(path, tmp_path, *extra):
    out = tmp_path / "result.json"
    subprocess.run([sys.executable, "replay.py", "--task", "fan_guard_install", "--traj", str(path), "--out", str(out),
                    *extra], cwd=FAMILY, check=True, capture_output=True)
    return json.loads(out.read_text())


def save(path, actions, hand="sharpa", **extra):
    np.savez_compressed(path, actions=np.asarray(actions, dtype=np.float64), hand=np.array(hand),
                        task=np.array("fan_guard_install"), **extra)
    return path


def test_oracle_succeeds_twice_with_identical_hash_and_slack(tmp_path):
    first = replay_cli(SOLUTION, tmp_path)
    second = replay_cli(SOLUTION, tmp_path)
    assert first["success"] and second["success"]
    assert first["state_sha"] == second["state_sha"]
    assert first["n_actions"] - first["steps"] >= 50


def test_oracle_float32_rows_succeed(tmp_path):
    path = save(tmp_path / "f32.npz", rows().astype(np.float32).astype(np.float64))
    assert replay_cli(path, tmp_path)["success"]


@pytest.mark.parametrize("cut", [600, 1590, 2370, 2484])
def test_partial_trajectories_fail(cut, tmp_path):
    result = replay_cli(save(tmp_path / "cut.npz", rows()[:cut]), tmp_path)
    assert not result["success"]


def test_nop_fails_and_forged_members_are_ignored(tmp_path):
    s = Session()
    nop = np.tile(s.initial_targets, (200, 1))
    result = replay_cli(save(tmp_path / "nop.npz", nop, success=np.array(True), reward=np.array(1.0)), tmp_path)
    assert not result["success"] and result["bad_trajectory"] == 0


def test_drop_and_catch_fails_at_once(tmp_path):
    actions = rows()
    open_q = np.load(FAMILY / "tools/seeds/open.npy")
    actions[1290:1293, 6:] = open_q[6:]  # fingers open for 3 rows while the lifted guard is being turned
    result = replay_cli(save(tmp_path / "drop.npz", actions), tmp_path)
    assert result["reason"] == "guard_dropped" and result["steps"] < 1310


def test_wrong_width_or_hand_label_is_a_bad_trajectory(tmp_path):
    assert replay_cli(save(tmp_path / "w.npz", rows(), hand="wuji"), tmp_path)["bad_trajectory"] == 1
    assert replay_cli(save(tmp_path / "n.npz", rows()[:, :27]), tmp_path)["bad_trajectory"] == 1


def test_wuji_composes_with_the_same_wrist_stage_and_deterministic_nop():
    sharpa, wuji = Session(), Session(hand="wuji")
    assert wuji.action_dim == 26 and sharpa.action_dim == 28
    assert wuji.actuator_names[:6] == sharpa.actuator_names[:6]
    assert np.allclose(wuji.model.actuator_ctrlrange[:6], sharpa.model.actuator_ctrlrange[:6])
    nop = np.tile(wuji.initial_targets, (100, 1))
    a = wuji.replay(nop)
    other = Session(hand="wuji")
    b = other.replay(nop)
    assert not a["success"] and not a["failed"] and not b["success"]
    assert wuji.state_sha() == other.state_sha()


def test_snapshot_restore_is_bit_exact():
    s = Session()
    actions = rows()
    for row in actions[:300]:
        s.step(row)
    snap = s.snapshot()
    for row in actions[300:400]:
        s.step(row)
    expected = s.state_sha()
    s.restore(snap)
    for row in actions[300:400]:
        s.step(row)
    assert s.state_sha() == expected


def test_knock_into_the_fan_fails_fast(tmp_path):
    actions = rows()
    for i in range(1750, len(actions)):  # after the guard hangs in the lower clips: drive the hand into the fan
        actions[i] = actions[1749]
        actions[i, 0] = actions[1749, 0] + min(1.0, (i - 1750) / 60) * 0.25
    result = replay_cli(save(tmp_path / "knock.npz", actions), tmp_path)
    assert not result["success"] and result["reason"] in ("fan_displaced", "fan_tipped", "guard_hit_fan_body")


def test_all_clips_start_open_and_an_open_clip_blocks_stage_two():
    from geometry import OPEN

    s = Session()
    assert np.allclose(s.data.qpos[s.clip_qadr], OPEN)
    for row in rows()[:2480]:
        s.step(row)
    assert s.checker.stage == 2
    for clip in range(4):
        snap = s.snapshot()
        s.data.qpos[s.clip_qadr[clip]] = OPEN
        mujoco.mj_forward(s.model, s.data)
        feats = s.checker.evaluate(s.data, s.steps + 1)
        assert s.checker.stage < 2, clip
        assert feats["clips_locked"] == 3
        s.restore(snap)


def test_non_finite_and_out_of_range_rows_are_bad_trajectories(tmp_path):
    bad = rows()[:20].copy()
    bad[5, 10] = np.nan
    assert replay_cli(save(tmp_path / "nan.npz", bad), tmp_path)["bad_trajectory"] == 1
    far = rows()[:20].copy()
    far[5, 0] = 5.0
    assert replay_cli(save(tmp_path / "range.npz", far), tmp_path)["bad_trajectory"] == 1


def test_trusted_service_accepts_an_empty_episode(tmp_path):
    result = replay_cli(save(tmp_path / "empty.npz", np.zeros((0, 28))), tmp_path, "--trusted-service")
    assert result["bad_trajectory"] == 0 and not result["success"] and result["steps"] == 0
