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
    st = s.replay(r[: 620])
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
    assert s.action_dim == 52 and s.actuator_names[12].startswith("r_wuji_") and s.actuator_names[-1].startswith("l_wuji_")
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
    s = Session()
    ix = _layout(s)
    r = rows()[:700].copy()
    start = r[-1].copy()
    seq = []
    for k in range(1, 41):  # bring the right hand down beside the hopper, then sweep it through the grinder
        row = start.copy()
        u = k / 40
        row[ix["right_wrist_x_act"]] += u * (0.36 - start[ix["right_wrist_x_act"]])
        row[ix["right_wrist_y_act"]] += u * (-0.16 - start[ix["right_wrist_y_act"]])
        row[ix["right_wrist_z_act"]] += u * (0.93 - start[ix["right_wrist_z_act"]])
        seq.append(row)
    for k in range(1, 61):
        row = seq[-1].copy()
        row[ix["right_wrist_y_act"]] = -0.16 + k * 0.006
        seq.append(row)
    st = s.replay(np.vstack([r, np.asarray(seq), np.tile(seq[-1], (100, 1))]))
    assert st["failed"] and st["reason"] in ("grinder_slid", "grinder_tipped") and st["steps"] < 860
    # the failure is permanent: later rows are not executed
    assert s.step(seq[-1])["steps"] == st["steps"]


@pytest.mark.skipif(not ORACLE.exists(), reason="oracle rows not built")
def test_counterhold_released_mid_crank_fails():
    s = Session()
    r = rows().copy()
    left = [i for i, n in enumerate(s.actuator_names) if n.startswith("left_") and "wrist" not in n]
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
