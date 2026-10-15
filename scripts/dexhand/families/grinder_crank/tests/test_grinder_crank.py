"""Authoring tests for the grinder_crank family (run with pytest from this folder's parent).

Needs DEXHAND_ASSET_DIR (Sharpa Wave assets; the Wuji folder is found as its sibling) and MuJoCo 3.4.0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

from runtime import Session  # noqa: E402
import replay as replay_module  # noqa: E402

ORACLE = FAMILY / "solution/trajectory.npz"
WUJI_ORACLE = FAMILY / "solution/wuji/trajectory.npz"


def rows():
    return np.load(ORACLE)["actions"]


def fresh_replay(path, tmp_path, *extra):
    out = tmp_path / f"r{len(list(tmp_path.iterdir()))}.json"
    subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", "grinder_crank", "--traj", str(path),
                    "--out", str(out), *extra], check=True, cwd=FAMILY, capture_output=True)
    return json.loads(out.read_text())


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle rows not built")
def test_oracle_two_fresh_replays_identical(tmp_path):
    a, b = fresh_replay(ORACLE, tmp_path), fresh_replay(ORACLE, tmp_path)
    assert a["success"] and b["success"] and a["state_sha"] == b["state_sha"]
    assert a["n_actions"] - a["steps"] >= 50  # slack after success


def test_nop_fails():
    s = Session()
    st = s.replay(np.tile(s.initial_targets, (400, 1)))
    assert not st["success"] and st["stage"] == 0


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle rows not built")
def test_truncated_before_hold_fails():
    s = Session()
    r = rows()
    st = s.replay(r[: 860])  # 720 deg reached, hands released, the 50-control hold not complete yet
    assert st["stage"] == 1 and not st["success"]


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle rows not built")
def test_float32_rows_succeed():
    s = Session()
    assert s.replay(rows().astype(np.float32).astype(np.float64))["success"]


def test_wrong_width_and_forged_members(tmp_path):
    s = Session()
    bad = tmp_path / "bad.npz"
    np.savez(bad, actions=np.zeros((10, 52)), hand=np.asarray("sharpa"))
    r = fresh_replay(bad, tmp_path)
    assert r["bad_trajectory"] == 1 and not r["success"]
    forged = tmp_path / "forged.npz"
    np.savez(forged, actions=np.tile(s.initial_targets, (20, 1)), hand=np.asarray("sharpa"),
             success=np.asarray(True), reward=np.asarray(1.0))
    r = fresh_replay(forged, tmp_path)
    assert r["bad_trajectory"] == 0 and not r["success"]


def test_wuji_composes_and_nop_fails():
    s = Session(hand="wuji")
    assert s.action_dim == 54 and s.actuator_names[14].startswith("l_wuji_") and s.actuator_names[-1].startswith("r_wuji_")
    rows = np.tile(s.initial_targets, (200, 1))
    st = s.replay(rows)
    assert not st["success"] and not st["failed"]
    s2 = Session(hand="wuji")
    s2.replay(rows)
    assert s2.state_sha() == s.state_sha()


def test_snapshot_restore_is_exact():
    s = Session()
    rows = np.tile(s.initial_targets, (60, 1))
    for r in rows[:30]:
        s.step(r)
    snap = s.snapshot()
    for r in rows[30:]:
        s.step(r)
    end = s.state_sha()
    s.restore(snap)
    for r in rows[30:]:
        s.step(r)
    assert s.state_sha() == end


def _layout(session):
    return {n: i for i, n in enumerate(session.actuator_names)}


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle rows not built")
def test_knock_over_fails_fast_at_the_step():
    """Mid-crank, swing the pinching right arm to its parked pose: the grinder is dragged and the episode fails at
    once."""
    from scene import arm_rig

    s = Session()
    r = rows()[:700].copy()
    start = r[-1].copy()
    park = np.asarray(arm_rig.PARK["right"])
    seq = []
    for k in range(1, 41):
        row = start.copy()
        row[7:14] = start[7:14] + (k / 40) * (park - start[7:14])
        seq.append(row)
    st = s.replay(np.vstack([r, np.asarray(seq), np.tile(seq[-1], (100, 1))]))
    assert st["failed"] and st["reason"] in ("grinder_slid", "grinder_tipped", "grinder_lifted", "grinder_spun",
                                             "robot_collision") and st["steps"] < 760
    # the failure is permanent: later rows are not executed
    assert s.step(seq[-1])["steps"] == st["steps"]


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle rows not built")
def test_counterhold_released_mid_crank_fails():
    s = Session()
    r = rows().copy()
    left = [i for i, n in enumerate(s.actuator_names) if n.startswith("left_")]  # left-hand finger targets
    for i in range(420, len(r)):
        r[i, left] = max(0.0, 1 - (i - 420) / 20) * rows()[420, left]
    st = s.replay(np.clip(r, s.lo, s.hi))
    assert st["failed"] and not st["success"]


def test_nan_and_out_of_range_rows_are_bad_trajectories(tmp_path):
    s = Session()
    bad = np.tile(s.initial_targets, (10, 1))
    bad[3, 5] = np.nan
    path = tmp_path / "nan.npz"
    np.savez(path, actions=bad, hand=np.asarray("sharpa"))
    r = fresh_replay(path, tmp_path)
    assert r["bad_trajectory"] == 1 and not r["success"]
    far = np.tile(s.initial_targets, (10, 1))
    far[0, 0] = 5.0
    path = tmp_path / "range.npz"
    np.savez(path, actions=far, hand=np.asarray("sharpa"))
    r = fresh_replay(path, tmp_path)
    assert r["bad_trajectory"] == 1 and not r["success"]


@pytest.mark.skipif(not WUJI_ORACLE.exists(), reason="wuji rows not built")
def test_wuji_oracle_succeeds(tmp_path):
    a, b = fresh_replay(WUJI_ORACLE, tmp_path), fresh_replay(WUJI_ORACLE, tmp_path)
    assert a["success"] and b["success"] and a["hand"] == "wuji" and a["state_sha"] == b["state_sha"]
