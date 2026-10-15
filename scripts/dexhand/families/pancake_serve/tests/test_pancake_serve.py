"""Authoring tests for pancake_serve (run from the family folder: python -m pytest tests -q).

Slow cases replay full episodes; set PANCAKE_FAST=1 to run only the archive-validation cases.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np
import pytest

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = FAMILY / "solution/trajectory.npz"
SLOW = pytest.mark.skipif(os.environ.get("PANCAKE_FAST") == "1", reason="full-episode replay")


def replay_cli(tmp_path, traj, *extra):
    out = tmp_path / "result.json"
    subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", "pancake_serve", "--traj", str(traj),
                    "--out", str(out), *extra], check=True, cwd=tmp_path, capture_output=True)
    return json.loads(out.read_text())


def oracle_rows(path=ORACLE):
    return hands.read_trajectory(path, widths={"sharpa": 58, "wuji": 54}, max_rows=3000)[0]


@SLOW
def test_oracle_succeeds_twice_with_identical_hash(tmp_path):
    first = replay_cli(tmp_path, ORACLE)
    second = replay_cli(tmp_path, ORACLE)
    assert first["success"] and second["success"] and first["state_sha"] == second["state_sha"]
    assert first["n_actions"] - first["steps"] >= 50  # slack rows after success


@SLOW
def test_float32_rows_succeed():
    rows = oracle_rows().astype(np.float32).astype(np.float64)
    assert Session().replay(rows)["success"]


@SLOW
@pytest.mark.parametrize("hand", ["sharpa", "wuji"])
def test_nop_fails(hand):
    s = Session(hand=hand)
    status = s.replay(np.tile(s.hold_action(), (400, 1)))
    assert not status["success"] and status["stage"] == 0
    assert not status["hand_holds_spatula"]  # the turner rests on the counter until it is picked up


@SLOW
def test_truncated_oracle_is_partial():
    status = Session().replay(oracle_rows()[:950])
    assert not status["success"] and status["stage"] == 2


@SLOW
def test_one_row_short_of_the_hold_fails():
    s = Session()
    full = s.replay(oracle_rows())
    short = s.replay(oracle_rows()[: full["steps"] - 1])
    assert full["success"] and not short["success"]


@SLOW
def test_drop_fails_fast_and_later_rows_cannot_undo_it():
    rows = oracle_rows()
    s = Session()
    for row in rows[:770]:  # lifted on the blade
        s.step(row)
    assert s.checker.stage >= 1
    tipped = rows[769].copy()
    tipped[13] -= 0.9  # roll the right wrist (WRIST_ROLL_R_J7) hard: the pancake slides off
    for _ in range(80):
        s.step(tipped)
        if s.done:
            break
    assert s.failure in ("pancake_dropped", "pancake_touched_by_hand")
    steps = s.steps
    s.step(rows[800])
    assert s.steps == steps and not s.success


def test_reset_is_deterministic():
    a, b = Session(), Session()
    assert a.state_sha() == b.state_sha()
    assert Session(hand="wuji").state_sha() == Session(hand="wuji").state_sha()


def test_state_sha_ignores_instruction_text():
    s = Session()
    sha = s.state_sha()
    s.config = dict(s.config, instruction="changed prose")
    assert s.state_sha() == sha


def test_wrong_width_and_hand_label_rejected(tmp_path):
    rows = oracle_rows()[:10]
    bad = tmp_path / "bad.npz"
    hands.write_trajectory(bad, rows, hand="wuji", task="pancake_serve")  # 58-wide rows labelled wuji
    result = replay_cli(tmp_path, bad)
    assert result["bad_trajectory"] == 1 and not result["success"]


def test_nan_and_out_of_range_rejected(tmp_path):
    rows = oracle_rows()[:10].copy()
    rows[3, 7] = np.nan
    bad = tmp_path / "nan.npz"
    np.savez(bad, actions=rows)
    assert replay_cli(tmp_path, bad)["bad_trajectory"] == 1
    rows = oracle_rows()[:10].copy()
    rows[2, 7] = 5.0  # right shoulder pitch beyond its range
    hands.write_trajectory(bad, rows, hand="sharpa", task="pancake_serve")
    assert replay_cli(tmp_path, bad)["bad_trajectory"] == 1


def test_forged_members_ignored_or_rejected(tmp_path):
    rows = oracle_rows()[:5]
    forged = tmp_path / "forged.npz"
    np.savez(forged, actions=rows, success=np.array(True), reward=np.array(1.0))
    result = replay_cli(tmp_path, forged)
    assert not result["success"]
    shadow = tmp_path / "shadow.npz"
    hands.write_trajectory(shadow, rows, hand="sharpa", task="pancake_serve")
    with zipfile.ZipFile(shadow, "a") as archive:
        archive.writestr("actions", b"junk")
    assert replay_cli(tmp_path, shadow)["bad_trajectory"] == 1
