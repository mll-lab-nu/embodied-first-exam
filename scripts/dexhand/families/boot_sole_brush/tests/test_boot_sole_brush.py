"""Authoring tests for boot_sole_brush (run from the family folder: python -m pytest tests -q).

Needs DEXHAND_ASSET_DIR (Sharpa Wave) and the Wuji assets next to it (or WUJI_ASSET_DIR).
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

from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"


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
    actions, hand, _ = hands.read_trajectory(ORACLE, widths={"sharpa": 28, "wuji": 26}, max_rows=3000)
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
    rows[320:360, 6:] = 0.0  # open the hand over the tray, then resume the oracle
    st = s.replay(rows)
    assert st["failed"] and st["reason"] == "brush_dropped"


def test_hand_debris_contact_fails():
    s = Session(hand="sharpa")
    m, d = s.model, s.data
    clod = d.xpos[m.body("clod_1").id].copy()
    base = np.asarray(s.config["wrist_base"])
    row = s.initial_targets.copy()
    # sweep the open hand's fingertips through clod 1 (no brush)
    start = row.copy()
    start[0:3] = clod - base + np.array([0.0, -0.25, 0.04])
    st = None
    for k in range(200):
        u = min(1.0, k / 100)
        q = start.copy()
        q[2] = start[2] - 0.06 * min(1.0, k / 60)
        q[1] = start[1] + 0.10 * u
        st = s.step(np.clip(q, s.lo, s.hi))
        if st["done"]:
            break
    assert st["failed"] and st["reason"] in ("hand_touched_debris", "boot_displaced", "debris_outside_tray")


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
    assert s.action_dim == 26 and s.actuator_names[:6] == Session(hand="sharpa").actuator_names[:6]
    rows = np.repeat(s.initial_targets[None], 200, axis=0)
    a = replay_cli(tmp_path, rows, hand="wuji")
    b = replay_cli(tmp_path, rows, hand="wuji")
    assert not a["success"] and a["state_sha"] == b["state_sha"] and a["hand"] == "wuji"


def test_wuji_witness_succeeds(tmp_path):
    path = HERE / "solution/wuji/trajectory.npz"
    a = replay_cli(tmp_path, path=path)
    b = replay_cli(tmp_path, path=path)
    assert a["hand"] == "wuji" and a["success"] and b["success"] and a["state_sha"] == b["state_sha"]
    assert a["n_actions"] - a["steps"] >= 50


def test_release_in_air_and_catch_fails(oracle):
    """L1: opening the hand for a few controls while carrying the brush fails at once; re-gripping cannot recover."""
    s = Session(hand="sharpa")
    rows = oracle.copy()
    rows[300:306, 6:] = 0.0
    st = s.replay(rows)
    assert st["failed"] and st["reason"] == "brush_dropped"
    assert st["failure_detail"]["where"] == "released_in_air" and st["steps"] <= 306


def test_nan_and_out_of_range_rejected(tmp_path, oracle):
    rows = oracle.copy()
    rows[10, 3] = np.nan
    bad = tmp_path / "nan.npz"
    np.savez_compressed(bad, actions=rows, hand=np.array("sharpa"))
    r = replay_cli(tmp_path, path=bad)
    assert r["bad_trajectory"] == 1 and not r["success"]
    rows = oracle.copy()
    rows[10, 8] = 50.0
    r = replay_cli(tmp_path, rows)
    assert r["bad_trajectory"] == 1 and not r["success"]


def test_state_sha_ignores_prose():
    s = Session(hand="sharpa")
    config = dict(s.config, instruction="edited text", title="edited", cameras=[])
    t = Session(hand="sharpa", config=config)
    assert s.state_sha() == t.state_sha()
