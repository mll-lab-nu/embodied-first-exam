"""Authoring tests of pot_shelf_transfer: positive, nop, partial, drop, forged metadata, wrong width, Wuji, snapshots.

Run from the repository root with the pinned MuJoCo environment (several minutes; every replay is real physics):
    DEXHAND_ASSET_DIR=images/dexhand/assets/hand DEXHAND_TIANJI_DIR=images/everyday_dexterity/assets/tianji \
    python3 -m pytest -q scripts/dexhand/families/pot_shelf_transfer/tests
The privileged grading path is exercised end to end: the family runtime is staged next to the shared grade.py exactly
as the generator lays out `tests/`, and the shared grader runs replay.py twice in fresh processes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
SHARED = REPO / "scripts/dexhand/shared"
TRACE = REPO.parent / "artifacts/scene-expansion-50/evidence/pot_transfer/trial-14/trajectory.npz"
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("DEXHAND_TIANJI_DIR", str(REPO / "images/everyday_dexterity/assets/tianji"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
sys.path[:0] = [str(FAMILY), str(SHARED)]

from runtime import Session  # noqa: E402

ORACLE = np.load(FAMILY / "solution/trajectory.npz")["actions"]
SUCCESS_ROW = 8602


@pytest.fixture(scope="module")
def staged(tmp_path_factory) -> Path:
    """The privileged tests/ layout: family runtime + shared hands.py, rcb_dexhand.py and grade.py."""
    folder = tmp_path_factory.mktemp("tests")
    manifest = json.loads((FAMILY / "family.json").read_text())
    for name in manifest["runtime"]["files"]:
        shutil.copy(FAMILY / name, folder / name)
    for name in manifest["runtime"]["dirs"]:
        shutil.copytree(FAMILY / name, folder / name, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("hands.py", "rcb_dexhand.py", "grade.py"):
        shutil.copy(SHARED / name, folder / name)
    (folder / "instance.json").write_text((FAMILY / "task.json").read_text())
    return folder


@pytest.fixture(scope="module")
def sharpa() -> Session:
    return Session(hand="sharpa")


def grade(staged: Path, trajectory: Path, tmp_path: Path) -> dict:
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(staged), RCB_VERIFIER_LOG_DIR=str(logs), RCB_TRAJECTORY=str(trajectory),
               RCB_TASK="pot_shelf_transfer")
    subprocess.run([sys.executable, str(staged / "grade.py")], check=True, env=env, cwd=staged)
    reward = json.loads((logs / "reward.json").read_text())
    assert (logs / "reward.txt").read_text().strip() == str(reward["success"])
    assert all(isinstance(value, (int, float)) for value in reward.values())  # Harbor needs numeric reward.json
    if (logs / "details.json").is_file():  # text diagnostics of the shared grader (hand, reason)
        reward.update(json.loads((logs / "details.json").read_text()))
    reward["replays"] = [json.loads((logs / f"replay{i}.json").read_text()) for i in (1, 2)
                         if (logs / f"replay{i}.json").is_file()]
    return reward


def save(path: Path, actions, **members) -> Path:
    np.savez_compressed(path, actions=np.asarray(actions), **{k: np.array(v) for k, v in members.items()})
    return path


# ---------------------------------------------------------------------------------------------------- positive
def test_oracle_scores_one_in_two_fresh_replays(staged, tmp_path):
    reward = grade(staged, FAMILY / "solution/trajectory.npz", tmp_path)
    assert reward["success"] == 1 and reward["deterministic"] == 1 and reward["infra_error"] == 0
    a, b = reward["replays"]
    assert a["state_sha"] == b["state_sha"] and a["steps"] == SUCCESS_ROW and a["stage"] == 2
    assert a["reason"] == "success" and a["hand"] == "sharpa" and reward["n_actions"] == len(ORACLE)


def test_wuji_reference_solution_scores_one_in_two_fresh_replays(staged, tmp_path):
    """solution/wuji/trajectory.npz (tools/wuji_gen.py): the packaged Wuji Hand 2.2 oracle."""
    reward = grade(staged, FAMILY / "solution/wuji/trajectory.npz", tmp_path)
    assert reward["success"] == 1 and reward["deterministic"] == 1 and reward["infra_error"] == 0
    a, b = reward["replays"]
    assert a["state_sha"] == b["state_sha"] == "2ac044592004d93953f70c54459112a149d0ea3f4a61fcc4ec68634b1049b069"
    assert a["reason"] == "success" and a["hand"] == "wuji" and a["steps"] == reward["n_actions"] == 8266


@pytest.mark.skipif(not TRACE.is_file(), reason="authoring trace not in this checkout")
def test_packaged_scene_reproduces_the_recorded_states(sharpa):
    trace = dict(np.load(TRACE))
    sharpa.reset()
    assert np.array_equal(sharpa.data.qpos, trace["qpos"][0])
    for step, row in enumerate(ORACLE[:1500], 1):
        sharpa.step(row)
        assert np.array_equal(sharpa.data.qpos, trace["qpos"][step]) and np.array_equal(sharpa.data.qvel,
                                                                                      trace["qvel"][step])


# ---------------------------------------------------------------------------------------------------- negatives
def test_missing_trajectory_is_zero(staged, tmp_path):
    reward = grade(staged, tmp_path / "absent.npz", tmp_path)
    assert reward["success"] == 0 and reward["missing_trajectory"] == 1 and reward["infra_error"] == 0


def test_nop_hold_never_succeeds(sharpa):
    sharpa.reset()
    hold = sharpa.hold_action()
    for _ in range(3000):
        status = sharpa.step(hold)
    assert not status["success"] and not status["failed"] and status["stage"] == 0
    assert abs(sharpa.features()["pot_position_m"][2] - 0.75) < 0.002  # the untouched pot stays on the worktop


@pytest.mark.parametrize("rows, expected_stage", [(6450, 1), (7300, 1), (8500, 1), (2000, 0)])
def test_partial_episodes_fail(sharpa, rows, expected_stage):
    """Carried but not placed; placed but still held; released but hold window incomplete; grasped but not lifted."""
    status = sharpa.replay(ORACLE[:rows])
    assert not status["success"] and not status["failed"] and status["stage"] == expected_stage
    assert status["steps"] == rows


def test_drop_fails_fast_and_is_permanent(sharpa):
    sharpa.reset()
    for row in ORACLE[:4200]:  # the pot is airborne, carried by both hands
        sharpa.step(row)
    assert sharpa.status()["stage"] == 1 and sharpa.features()["pot_position_m"][2] > 0.80
    opened = ORACLE[4199].copy()
    lo, hi = sharpa.actuator_ranges.T
    opened[14:] = np.clip(0.0, lo[14:], hi[14:])  # open every finger, keep the arms where they are
    for _ in range(1500):
        status = sharpa.step(opened)
        if status["done"]:
            break
    assert status["failed"] and not status["success"]
    assert status["reason"] in {"pot_dropped", "pot_fell", "pot_tipped", "pot_hit_environment", "robot_collision"}
    steps = status["steps"]
    for row in ORACLE[4200:4400]:  # later rows (even the good ones) cannot recover the episode
        status = sharpa.step(row)
    assert status["failed"] and status["steps"] == steps


def test_drop_trajectory_scores_zero(staged, sharpa, tmp_path):
    opened = ORACLE[4199].copy()
    lo, hi = sharpa.actuator_ranges.T
    opened[14:] = np.clip(0.0, lo[14:], hi[14:])
    traj = save(tmp_path / "drop.npz", np.vstack([ORACLE[:4200], np.repeat(opened[None, :], 800, axis=0)]),
                hand="sharpa")
    reward = grade(staged, traj, tmp_path)
    assert reward["success"] == 0 and reward["deterministic"] == 1 and reward.get("bad_trajectory", 0) == 0
    assert reward["reason"] in {"pot_dropped", "pot_fell", "pot_tipped", "pot_hit_environment", "robot_collision"}


# ---------------------------------------------------------------------------------------------------- archives
@pytest.mark.parametrize(
    "name, actions, members",
    [
        ("oracle-labelled-wuji", ORACLE, {"hand": "wuji"}),
        ("wuji-width-labelled-sharpa", ORACLE[:400, :54], {"hand": "sharpa"}),
        ("wrong-width-57", ORACLE[:400, :57], {}),
        ("unknown-hand", ORACLE[:400], {"hand": "robotiq"}),
        ("wrong-task", ORACLE[:400], {"hand": "sharpa", "task": "essential_cube_layer"}),
        ("non-finite", np.where(np.arange(58) == 3, np.nan, ORACLE[:400]), {}),
        ("out-of-range", ORACLE[:400] + np.where(np.arange(58) == 2, 9.0, 0.0), {}),
        ("too-many-rows", np.repeat(ORACLE[:1], 30001, axis=0), {}),
    ],
)
def test_rejected_archives_score_zero(staged, tmp_path, name, actions, members):
    reward = grade(staged, save(tmp_path / f"{name}.npz", actions, **members), tmp_path)
    assert reward["success"] == 0 and reward["bad_trajectory"] == 1 and reward["infra_error"] == 0


def test_crafted_archives_are_clean_rejections(staged, tmp_path):
    """Malformed archives must give reward 0 with bad_trajectory, never an infrastructure error."""
    cases = {
        "empty-hand": dict(actions=ORACLE[:50], hand=np.array([], dtype="<U5")),
        "empty-task": dict(actions=ORACLE[:50], task=np.array([], dtype="<U5")),
        "numeric-hand": dict(actions=ORACLE[:50], hand=np.array(3)),
        "one-dimensional": dict(actions=ORACLE[0]),
        "no-rows": dict(actions=np.zeros((0, 58))),
        "object-array": dict(actions=np.array([[None] * 58] * 3, dtype=object)),
    }
    for name, members in cases.items():
        path = tmp_path / f"{name}.npz"
        np.savez(path, **members)  # object arrays are pickled by np.savez; the reader never unpickles
        reward = grade(staged, path, tmp_path)
        assert reward["success"] == 0 and reward["infra_error"] == 0 and reward["bad_trajectory"] == 1, name
    garbage = tmp_path / "garbage.npz"
    garbage.write_bytes(b"PK\x03\x04 not a zip archive")
    reward = grade(staged, garbage, tmp_path)
    assert reward["success"] == 0 and reward["infra_error"] == 0 and reward["bad_trajectory"] == 1


def test_forged_success_members_are_ignored(staged, tmp_path):
    hold = np.repeat(ORACLE[:1], 600, axis=0)
    traj = save(tmp_path / "forged.npz", hold, hand="sharpa", success=True, reward=1, stage=2, final_qpos=np.zeros(65))
    reward = grade(staged, traj, tmp_path)
    assert reward["success"] == 0 and reward.get("bad_trajectory", 0) == 0 and reward["deterministic"] == 1


def test_wrong_actuator_names_rejected(staged, sharpa, tmp_path):
    names = list(reversed(sharpa.actuator_names))
    traj = save(tmp_path / "names.npz", ORACLE[:400], hand="sharpa", actuator_names=names)
    reward = grade(staged, traj, tmp_path)
    assert reward["success"] == 0 and reward["bad_trajectory"] == 1


# ---------------------------------------------------------------------------------------------------- Wuji
def test_wuji_composes_nop_is_zero_and_deterministic(staged, sharpa, tmp_path):
    wuji = Session(hand="wuji")
    assert wuji.action_dim == 54 and wuji.actuator_names[14].startswith("l_wuji_") and wuji.robot.endswith("2.2")
    assert wuji.actuator_names[:14] == sharpa.actuator_names[:14]  # same arms, same order
    assert np.array_equal(wuji.data.qpos[:7], sharpa.model.key("start").qpos[:7])
    hold = np.repeat(wuji.hold_action()[None, :], 1500, axis=0)
    reward = grade(staged, save(tmp_path / "wuji-hold.npz", hold, hand="wuji"), tmp_path)
    assert reward["success"] == 0 and reward["deterministic"] == 1 and reward["hand"] == "wuji"
    assert reward.get("bad_trajectory", 0) == 0 and reward["replays"][0]["reason"] == ""
    rng = np.random.default_rng(7)
    lo, hi = wuji.actuator_ranges.T
    random = np.clip(hold[:600] + rng.normal(0, 0.02, (600, 54)), lo, hi)
    reward = grade(staged, save(tmp_path / "wuji-random.npz", random, hand="wuji"), tmp_path)
    assert reward["deterministic"] == 1 and reward["success"] == 0


# ---------------------------------------------------------------------------------------------------- tooling
def test_snapshot_restore_is_bit_exact(sharpa):
    sharpa.reset()
    for row in ORACLE[:3000]:
        sharpa.step(row)
    snap = sharpa.snapshot()
    for row in ORACLE[3000:3300]:
        sharpa.step(row)
    first = sharpa.state_sha()
    sharpa.restore(snap)
    for row in ORACLE[3000:3300]:
        sharpa.step(row)
    assert sharpa.state_sha() == first and sharpa.steps == 3300


def test_invalid_rows_are_rejected_before_physics(sharpa):
    sharpa.reset()
    before = sharpa.state_sha()
    bad = ORACLE[:50].copy()
    bad[-1, 20] = 50.0
    with pytest.raises(ValueError):
        sharpa.replay(bad)
    with pytest.raises(ValueError):
        sharpa.step(ORACLE[0][:57])
    assert sharpa.state_sha() == before


def test_save_trajectory_round_trip(sharpa, tmp_path):
    import hands

    path = sharpa.save_trajectory(ORACLE[:10], tmp_path / "t.npz")
    actions, hand, _ = hands.read_trajectory(path, widths={"sharpa": 58, "wuji": 54}, max_rows=30000,
                                             task="pot_shelf_transfer")
    assert hand == "sharpa" and np.array_equal(actions, ORACLE[:10])
