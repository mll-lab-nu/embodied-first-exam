"""Authoring tests for envelope_letter_insert (not shipped to task directories).

Run from the family folder:  DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand python -m pytest -q tests
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import replay  # noqa: E402
from runtime import Session  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"


def fresh_replay(path, tmp_path, name, *extra):
    out = tmp_path / f"{name}.json"
    subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", "envelope_letter_insert", "--traj", str(path),
                    "--out", str(out), *extra], check=True, cwd=tmp_path, capture_output=True)
    return json.loads(out.read_text())


@pytest.fixture(scope="module")
def oracle():
    return replay.load_trajectory(ORACLE)[0]


@pytest.fixture(scope="module")
def session():
    s = Session(hand="sharpa")
    yield s
    s.close()


def test_oracle_two_fresh_replays_identical(tmp_path):
    a = fresh_replay(ORACLE, tmp_path, "a")
    b = fresh_replay(ORACLE, tmp_path, "b")
    assert a["success"] and b["success"] and a["bad_trajectory"] == 0
    assert a["state_sha"] == b["state_sha"]
    assert a["n_actions"] - a["steps"] >= 50  # slack: success well before the last row
    assert a["stage"] == 3


def test_oracle_float32_rows(session, oracle):
    status = session.replay(oracle.astype(np.float32).astype(np.float64))
    assert status["success"]


def test_nop_fails(session):
    status = session.replay(np.repeat(session.hold_action()[None], 400, axis=0))
    assert not status["success"] and status["stage"] == 0


@pytest.mark.parametrize("stage_name", ["letter_at_mouth", "letter_inserted", "released_hold"])
def test_truncation_before_each_stage_fails(session, oracle, stage_name):
    steps = session.replay(oracle)["stage_steps"]
    status = session.replay(oracle[: steps[stage_name] - 1])
    assert not status["success"]


def test_knock_letter_off_desk_fails_fast_and_is_permanent(session, oracle):
    sys.path.insert(0, str(HERE / "tools"))
    import make_negatives

    rows, status = make_negatives.knock_off("letter_off_desk")
    assert status["failed"] and status["reason"] in ("letter_left_workspace", "letter_dropped", "letter_below_desk")
    after = session.replay(np.vstack([rows, oracle]))
    assert not after["success"] and after["reason"] == status["reason"]
    assert after["steps"] == status["steps"]


def test_envelope_shoved_fails_fast():
    sys.path.insert(0, str(HERE / "tools"))
    import make_negatives

    _rows, status = make_negatives.knock_off("envelope_shoved")
    assert status["failed"] and status["reason"] == "envelope_displaced"


def test_forged_members_are_ignored(tmp_path, session):
    path = tmp_path / "forged.npz"
    nop = np.repeat(session.hold_action()[None], 200, axis=0)
    np.savez(path, actions=nop, hand=np.array("sharpa"), success=np.array(True), reward=np.array(1.0),
             letter_pos=np.zeros(3))
    result = fresh_replay(path, tmp_path, "forged")
    assert not result["success"] and result["bad_trajectory"] == 0


@pytest.mark.parametrize("case", ["wrong_width", "nan", "out_of_range", "wrong_task", "shadow_member"])
def test_bad_archives_are_rejected(tmp_path, oracle, case):
    import io
    import zipfile

    path = tmp_path / f"{case}.npz"
    if case == "wrong_width":
        np.savez(path, actions=oracle, hand=np.array("wuji"))
    elif case == "nan":
        bad = oracle.copy()
        bad[3, 2] = np.nan
        np.savez(path, actions=bad)
    elif case == "out_of_range":
        bad = oracle.copy()
        bad[3, 8] = 50.0
        np.savez(path, actions=bad)
    elif case == "wrong_task":
        np.savez(path, actions=oracle, task=np.array("assemble_hamburger"))
    else:
        buf = io.BytesIO()
        np.save(buf, oracle)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("actions.npy", buf.getvalue())
            archive.writestr("actions", buf.getvalue())
    result = fresh_replay(path, tmp_path, case)
    assert result["bad_trajectory"] == 1 and not result["success"]


def test_wuji_loads_nop_fails_and_is_deterministic(tmp_path):
    s = Session(hand="wuji")
    assert s.action_dim == 26 and s.actuator_names[:6] == Session(hand="sharpa").actuator_names[:6]
    path = tmp_path / "wuji_nop.npz"
    s.save_trajectory(np.repeat(s.hold_action()[None], 150, axis=0), path)
    a = fresh_replay(path, tmp_path, "wa")
    b = fresh_replay(path, tmp_path, "wb")
    assert not a["success"] and a["hand"] == "wuji" and a["state_sha"] == b["state_sha"]


@pytest.mark.parametrize("penetration_bound", [None, 1.0])
def test_letter_pressed_through_the_front_wall_fails_fast(oracle, penetration_bound):
    """Reviewer EL-1: the letter laid on top of the envelope (setup by a qpos edit after reset) and pressed down
    through the front wall must fail fast (interpenetration guard, and the wall-slab guard on its own) and never
    count as inserted."""
    import mujoco

    s = Session(hand="sharpa")
    if penetration_bound is not None:
        s.checker.max_penetration = penetration_bound  # exercise the wall-slab guard alone
    m, d = s.model, s.data
    lo, hi = m.actuator_ctrlrange.T

    def lin(row, col, delta, n):
        r = np.repeat(row[None], n, 0)
        r[:, col] += np.linspace(0, delta, n)
        return r

    base = oracle[:145] + np.r_[0, 0.30, np.zeros(26)]
    seq = [base, lin(base[-1], 2, -0.10, 80), lin(base[-1] - np.r_[0, 0, 0.10, np.zeros(25)], 2, 0.12, 40)]
    cur = seq[-1][-1].copy()
    top = base[-1].copy()
    top[2] += 0.02
    for sx, sy in ((-0.07, -0.04), (-0.07, 0.04)):
        tgt = top.copy()
        tgt[0] += sx
        tgt[1] += sy
        seq += [np.linspace(cur, tgt, 40), lin(tgt, 2, -0.12, 80)]
        seq.append(lin(seq[-1][-1], 2, 0.14, 40))
        cur = seq[-1][-1].copy()
    seq.append(np.repeat(cur[None], 150, 0))
    rows = np.clip(np.concatenate(seq), lo, hi)
    s.reset()
    qa = m.jnt_qposadr[m.body("letter").jntadr[0]]
    d.qpos[qa: qa + 3] = [0.485, 0.16, 0.70 + s.checker.ceiling + 0.0008 + 0.001 + 0.0002]
    mujoco.mj_forward(m, d)
    for r in rows:
        s.step(r)
        if s.done:
            break
    status = s.status()
    assert status["failed"] and not status["success"] and status["stage"] == 0
    assert status["reason"] in ("letter_envelope_penetration", "letter_through_envelope")
