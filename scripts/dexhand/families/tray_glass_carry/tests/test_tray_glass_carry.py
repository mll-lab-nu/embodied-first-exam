"""Authoring tests for tray_glass_carry (run from the family folder with DEXHAND_ASSET_DIR set)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

WIDTHS = {"sharpa": 56, "wuji": 52}


def oracle(name="trajectory.npz"):
    return hands.read_trajectory(HERE / "solution" / name, widths=WIDTHS, max_rows=3000)[0]


def replay_cli(path, tmp_path, tag):
    out = tmp_path / f"{tag}.json"
    subprocess.run([sys.executable, str(HERE / "replay.py"), "--traj", str(path), "--out", str(out)],
                   check=True, cwd=HERE, capture_output=True)
    return json.loads(out.read_text())


def test_layout_and_widths():
    for hand, width in WIDTHS.items():
        s = Session(hand=hand)
        assert s.action_dim == width
        assert s.actuator_names[:12] == [f"{side}_wrist_{a}_act" for side in "lr"
                                         for a in ("x", "y", "z", "rx", "ry", "rz")]
        s.close()


def test_oracle_two_fresh_replays(tmp_path):
    a = replay_cli(HERE / "solution/trajectory.npz", tmp_path, "a")
    b = replay_cli(HERE / "solution/trajectory.npz", tmp_path, "b")
    assert a["success"] and b["success"] and a["state_sha"] == b["state_sha"]
    assert a["n_actions"] - a["steps"] >= 50  # slack after success


def test_float32_rows_still_succeed():
    s = Session(hand="sharpa")
    assert s.replay(oracle().astype(np.float32).astype(np.float64))["success"]


@pytest.mark.parametrize("rows,stage", [(880, 2), (951, 2)])
def test_truncation_fails(rows, stage):
    s = Session(hand="sharpa")
    st = s.replay(oracle()[:rows])
    assert not st["success"] and st["stage"] == stage


def test_nop_fails_both_hands():
    for hand in WIDTHS:
        s = Session(hand=hand)
        first = s.replay(np.tile(s.hold_action(), (300, 1)))
        sha = s.state_sha()
        again = s.replay(np.tile(s.hold_action(), (300, 1)))
        assert not first["success"] and first["stage"] == 0 and sha == s.state_sha() and not again["success"]


def test_drop_mid_carry_is_permanent():
    s = Session(hand="sharpa")
    idx = {n: i for i, n in enumerate(s.actuator_names)}
    rows = list(oracle()[:470])
    for k in range(1, 11):
        r = rows[469].copy()
        r[idx["l_wrist_y_act"]] += 0.004 * k
        r[idx["r_wrist_y_act"]] -= 0.004 * k
        rows.append(r)
    rows += list(oracle()[480:])
    st = s.replay(np.asarray(rows))
    assert st["failed"] and st["reason"] == "object_dropped" and not st["success"]


def test_wrong_hand_label_rejected(tmp_path):
    path = tmp_path / "x.npz"
    hands.write_trajectory(path, oracle(), hand="wuji", task="tray_glass_carry")
    r = replay_cli(path, tmp_path, "x")
    assert r["bad_trajectory"] == 1 and not r["success"]


def test_wuji_success_if_present(tmp_path):
    path = HERE / "solution/wuji/trajectory.npz"
    if not path.is_file():
        pytest.skip("no Wuji trajectory")
    r = replay_cli(path, tmp_path, "w")
    assert r["success"] and r["hand"] == "wuji"


def test_knock_into_bottle_fails_fast():
    s = Session(hand="sharpa")
    idx = {n: i for i, n in enumerate(s.actuator_names)}
    rows = list(oracle()[:302])
    for k in range(1, 151):
        w = k / 150
        w = w * w * (3 - 2 * w)
        r = rows[301].copy()
        r[idx["l_wrist_x_act"]] += 0.42 * w
        r[idx["r_wrist_x_act"]] += 0.42 * w
        rows.append(r)
    st = s.replay(np.asarray(rows))
    assert st["failed"] and st["reason"] == "obstacle_contact" and st["stage"] == 1


def test_forged_members_are_ignored(tmp_path):
    s = Session(hand="sharpa")
    path = tmp_path / "forged.npz"
    np.savez_compressed(path, actions=np.tile(s.hold_action(), (60, 1)), hand=np.array("sharpa"),
                        success=np.array(True), reward=np.array(1.0), stage=np.array(3))
    r = replay_cli(path, tmp_path, "forged")
    assert not r["success"] and r["bad_trajectory"] == 0 and r["stage"] == 0


def test_shadowing_member_and_nan_rejected(tmp_path):
    rows = oracle()
    import zipfile
    shadow = tmp_path / "shadow.npz"
    hands.write_trajectory(shadow, rows, hand="sharpa", task="tray_glass_carry")
    with zipfile.ZipFile(shadow, "a") as archive:
        archive.writestr("actions", b"not an array")
    bad = rows.copy()
    bad[3, 0] = np.nan
    nan = tmp_path / "nan.npz"
    np.savez_compressed(nan, actions=bad, hand=np.array("sharpa"))
    for path in (shadow, nan):
        r = replay_cli(path, tmp_path, path.stem)
        assert r["bad_trajectory"] == 1 and not r["success"]


def test_wrong_width_rejected(tmp_path):
    path = tmp_path / "narrow.npz"
    np.savez_compressed(path, actions=oracle()[:, :52], hand=np.array("sharpa"))
    r = replay_cli(path, tmp_path, "narrow")
    assert r["bad_trajectory"] == 1


def test_wuji_loads_with_the_same_stages():
    s, w = Session(hand="sharpa"), Session(hand="wuji")
    assert s.actuator_names[:12] == w.actuator_names[:12]
    assert np.allclose(s.model.actuator_ctrlrange[:12], w.model.actuator_ctrlrange[:12])
    assert w.actuator_names[12].startswith("l_wuji_") and w.actuator_names[-1].startswith("r_wuji_")


def test_state_sha_ignores_instruction_text():
    import copy
    a = Session(hand="sharpa")
    config = copy.deepcopy(a.config)
    config["instruction"] = "edited prose"
    config["title"] = "another title"
    b = Session(hand="sharpa", config=config)
    assert a.state_sha() == b.state_sha()


def test_low_release_is_a_drop_not_a_catch():
    """Pulling the hooks out 8 mm above the counter: the unsupported tray falls faster than 0.2 m/s -> failure."""
    s = Session(hand="sharpa")
    idx = {n: i for i, n in enumerate(s.actuator_names)}
    rows = list(oracle()[:821])
    for j in range(1, 8):
        r = rows[820].copy()
        r[idx["l_wrist_y_act"]] += 0.006 * j
        r[idx["r_wrist_y_act"]] -= 0.006 * j
        rows.append(r)
    rows += [rows[-1]] * 150
    st = s.replay(np.asarray(rows))
    assert st["failed"] and st["reason"] == "object_dropped"
