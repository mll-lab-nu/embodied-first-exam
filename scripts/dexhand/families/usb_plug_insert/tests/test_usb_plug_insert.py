"""Authoring tests: positive oracle, negative controls, fail-fast, trust boundary and hand selection for usb_plug_insert.

Run from the repository root (about 4 minutes on one core):

    DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand OPENBLAS_NUM_THREADS=1 \
        python -m pytest -q scripts/dexhand/families/usb_plug_insert/tests
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[3]
SHARED = REPO / "scripts/dexhand/shared"
os.environ.setdefault("DEXHAND_ASSET_DIR", str(REPO / "images/dexhand/assets/hand"))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
for path in (str(SHARED), str(FAMILY)):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
for name in ("runtime", "replay", "hands", "scene", "checker"):
    sys.modules.pop(name, None)

import hands  # noqa: E402  (shared copy, as in a generated task)
from runtime import Session  # noqa: E402

TASK = "usb_plug_insert"
ORACLE = FAMILY / "solution/trajectory.npz"
SUCCESS_STEP = 1475
RIGHT = slice(36, 58)  # right-hand finger columns of a Sharpa row (after 14 arm and 22 left-hand targets)
KNOCK = 1060           # after the insertion (stage 2 reached at about control 1,040)
ORACLE_SHA = "c18aa345626c7752fdbcea593086867c0cc2b06c7320996c1c709af4695d265c"


def oracle_rows() -> np.ndarray:
    return hands.read_trajectory(ORACLE, widths={"sharpa": 58, "wuji": 54}, max_rows=3000, task=TASK)[0]


def run_replay(traj: Path, *extra: str) -> tuple[dict, int]:
    """replay.py in a fresh process, laid out like a task directory (family files + shared hands.py)."""
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "out.json"
        env = dict(os.environ, PYTHONPATH=f"{FAMILY}{os.pathsep}{SHARED}", PYTHONDONTWRITEBYTECODE="1")
        env.pop("DEXHAND_HAND", None)
        done = subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", TASK, "--traj", str(traj),
                               "--out", str(out), *extra], env=env, capture_output=True, text=True, timeout=900)
        return (json.loads(out.read_text()) if out.is_file() else {}), done.returncode


def save(folder: str, name: str, rows, hand="sharpa", **members) -> Path:
    path = Path(folder) / name
    if members:
        np.savez_compressed(path, actions=np.asarray(rows), hand=np.array(hand), **members)
    else:
        hands.write_trajectory(path, rows, hand=hand, task=TASK)
    return path


class OracleTest(unittest.TestCase):
    def test_oracle_succeeds_with_slack_and_identical_hashes(self):
        first, rc1 = run_replay(ORACLE)
        second, rc2 = run_replay(ORACLE)
        self.assertEqual((rc1, rc2), (0, 0))
        for result in (first, second):
            self.assertTrue(result["success"], result.get("reason"))
            self.assertEqual(result["steps"], SUCCESS_STEP)
            self.assertEqual(result["stage"], 3)
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["state_sha"], ORACLE_SHA)
        self.assertGreaterEqual(first["n_actions"] - first["steps"], 100)  # unexecuted slack rows

    def test_float32_rows_succeed(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = oracle_rows().astype(np.float32).astype(np.float64)
            result, rc = run_replay(save(folder, "f32.npz", rows))
            self.assertEqual(rc, 0)
            self.assertTrue(result["success"], result.get("reason"))


class NegativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = oracle_rows()

    def replay_in_process(self, rows):
        session = Session(TASK)
        status = session.replay(rows)
        session.close()
        return status

    def test_nop_fails(self):
        status = self.replay_in_process(np.repeat(self.rows[:1], 600, axis=0))
        self.assertFalse(status["success"])
        self.assertEqual(status["stage"], 0)

    def test_truncated_before_release_fails(self):
        status = self.replay_in_process(self.rows[:1100])  # inserted (stage 2), release/hold incomplete
        self.assertFalse(status["success"])
        self.assertEqual(status["stage"], 2)

    def test_one_row_short_of_hold_fails(self):
        status = self.replay_in_process(self.rows[:SUCCESS_STEP - 1])
        self.assertFalse(status["success"])
        self.assertEqual(status["released_hold_controls"], 49)

    def test_drop_fails_fast_at_the_drop(self):
        rows = np.concatenate([self.rows[:330], np.repeat(self.rows[329:330], 200, axis=0)])
        rows[330:, RIGHT] = np.asarray(Session(TASK).initial_targets[RIGHT])  # open the hand mid-transport
        status = self.replay_in_process(rows)
        self.assertEqual(status["reason"], "plug_dropped")
        self.assertLessEqual(status["steps"], 335)

    def test_drop_then_resume_oracle_cannot_recover(self):
        rows = np.concatenate([self.rows[:330], np.repeat(self.rows[329:330], 20, axis=0), self.rows[330:]])
        rows[330:350, RIGHT] = np.asarray(Session(TASK).initial_targets[RIGHT])
        status = self.replay_in_process(rows)
        self.assertFalse(status["success"])
        self.assertTrue(status["failed"])

    def test_hub_knock_fails_fast(self):
        rows = np.concatenate([self.rows[:KNOCK], np.repeat(self.rows[KNOCK - 1:KNOCK], 150, axis=0)])
        rows[KNOCK:, 7] += np.r_[np.linspace(0, 0.25, 100), np.full(50, 0.25)]  # right shoulder J1 drags the seated plug
        status = self.replay_in_process(rows)
        self.assertIn(status["reason"], ("hub_displaced", "hub_tipped"))
        self.assertLess(status["steps"], KNOCK + 150)

    def test_post_success_rows_are_not_executed(self):
        rows = np.concatenate([self.rows[:SUCCESS_STEP], np.repeat(self.rows[:1], 200, axis=0)])
        status = self.replay_in_process(rows)
        self.assertTrue(status["success"])
        self.assertEqual(status["steps"], SUCCESS_STEP)


class TrustBoundaryTest(unittest.TestCase):
    def test_rejected_archives_are_bad_trajectories(self):
        rows = oracle_rows()[:50]
        with tempfile.TemporaryDirectory() as folder:
            nan = rows.copy()
            nan[3, 7] = np.nan
            wrong = Path(folder) / "wrong_width.npz"
            np.savez_compressed(wrong, actions=rows[:, :57], hand=np.array("sharpa"))
            nan_path = Path(folder) / "nan.npz"
            np.savez_compressed(nan_path, actions=nan, hand=np.array("sharpa"))
            label = Path(folder) / "sharpa_rows_as_wuji.npz"
            np.savez_compressed(label, actions=rows, hand=np.array("wuji"))
            task = Path(folder) / "other_task.npz"
            np.savez_compressed(task, actions=rows, hand=np.array("sharpa"), task=np.array("assemble_hamburger"))
            shadow = Path(folder) / "shadow.npz"
            np.savez_compressed(shadow, actions=rows)
            with zipfile.ZipFile(shadow, "a") as archive:
                archive.writestr("actions", b"forged")
            out_of_range = Path(folder) / "range.npz"
            far = rows.copy()
            far[0, 10] = 50.0
            np.savez_compressed(out_of_range, actions=far, hand=np.array("sharpa"))
            for path in (wrong, nan_path, label, task, shadow, out_of_range):
                result, rc = run_replay(path)
                self.assertEqual(rc, 0, path.name)
                self.assertEqual(result.get("bad_trajectory"), 1, path.name)
                self.assertFalse(result["success"], path.name)

    def test_forged_success_member_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forged.npz"
            np.savez_compressed(path, actions=oracle_rows()[:100], hand=np.array("sharpa"), success=np.array(True),
                                stage=np.array(3))
            result, rc = run_replay(path)
            self.assertEqual(rc, 0)
            self.assertEqual(result["bad_trajectory"], 0)
            self.assertFalse(result["success"])


class HandTest(unittest.TestCase):
    def test_wuji_loads_with_same_stage_and_nop_is_deterministic_failure(self):
        sharpa, wuji = Session(TASK), Session(TASK, hand="wuji")
        self.assertEqual((sharpa.action_dim, wuji.action_dim), (58, 54))
        self.assertEqual(sharpa.actuator_names[:14], wuji.actuator_names[:14])
        np.testing.assert_array_equal(sharpa.model.actuator_ctrlrange[:14], wuji.model.actuator_ctrlrange[:14])
        rows = np.repeat(wuji.initial_targets[None], 150, axis=0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wuji_nop.npz"
            wuji.save_trajectory(rows, path)
            first, _ = run_replay(path)
            second, _ = run_replay(path)
        self.assertEqual((first["hand"], first["success"], first["bad_trajectory"]), ("wuji", False, 0))
        self.assertEqual(first["state_sha"], second["state_sha"])

    def test_unknown_hand_is_refused(self):
        with self.assertRaises(ValueError):
            Session(TASK, hand="allegro")


if __name__ == "__main__":
    unittest.main()
