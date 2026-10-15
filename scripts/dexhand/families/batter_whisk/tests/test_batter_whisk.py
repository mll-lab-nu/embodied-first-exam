"""Authoring tests: positive replays, negative controls, fail-fast cases and the trajectory trust boundary.

Run from the family folder (about 1-2 minutes):
    cd scripts/dexhand/families/batter_whisk && python -m pytest -q tests/test_batter_whisk.py
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import mujoco  # noqa: E402

from replay import load_trajectory  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

SOLUTION = HERE / "solution/trajectory.npz"
WUJI_SOLUTION = HERE / "solution/wuji/trajectory.npz"
WIDTHS = {"sharpa": 28, "wuji": 26}


def rows(path=SOLUTION):
    actions, hand, _ = hands.read_trajectory(path, widths=WIDTHS, max_rows=4000, task="batter_whisk")
    return np.asarray(actions, dtype=np.float64), hand


def replay_cli(path, *extra):
    """Fresh-process replay through the CLI the graders use; returns the result JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        done = subprocess.run([sys.executable, str(HERE / "replay.py"), "--task", "batter_whisk", "--traj", str(path),
                               "--out", str(out), *extra], cwd=HERE, capture_output=True, text=True, timeout=900)
        assert done.returncode == 0, done.stderr[-2000:]
        return json.loads(out.read_text())


def write(path, actions, hand="sharpa", **extra):
    np.savez(path, actions=np.asarray(actions), hand=np.array(hand), **extra)
    return path


class SceneTests(unittest.TestCase):
    def test_only_robot_is_actuated(self):
        for hand, width in WIDTHS.items():
            s = Session(hand=hand)
            self.assertEqual(s.action_dim, width)
            self.assertEqual(s.model.nmocap, 0)
            self.assertEqual(s.model.neq, 0)
            self.assertEqual(s.actuator_names[:6], [f"wrist_{n}_act" for n in ("x", "y", "z", "rx", "ry", "rz")])
            for body in ("bowl", "whisk"):
                joint = s.model.body(body).jntadr[0]
                self.assertEqual(s.model.jnt_type[joint], mujoco.mjtJoint.mjJNT_FREE)
            driven = {s.model.joint(j).name for j in s.model.actuator_trnid[:, 0]}
            self.assertFalse(driven & {"bowl_free", "whisk_free"})
            s.close()

    def test_reset_holds_the_whisk_for_both_hands(self):
        for hand in WIDTHS:
            s = Session(hand=hand)
            w = s.model.body("whisk").id
            start = s.data.xpos[w].copy()
            for _ in range(100):
                s.step(s.hold_action())
            self.assertFalse(s.done, hand)
            self.assertLess(np.linalg.norm(s.data.xpos[w] - start), 0.01, hand)
            self.assertGreater(s.features()["hand_whisk"], 0, hand)
            s.close()

    def test_state_sha_ignores_texts(self):
        s = Session()
        sha = s.state_sha()
        config = json.loads(json.dumps(s.config))
        config["instruction"] = "edited"
        config["cameras"][0]["fovy"] = 10
        other = Session(config=config)
        self.assertEqual(other.state_sha(), sha)


class ReplayTests(unittest.TestCase):
    def test_oracle_succeeds_twice_with_identical_hash_and_slack(self):
        first, second = replay_cli(SOLUTION), replay_cli(SOLUTION)
        self.assertTrue(first["success"] and second["success"])
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertEqual(first["stage"], 4)
        self.assertGreaterEqual(first["n_actions"] - first["steps"], 50)

    def test_float32_rows_succeed(self):
        actions, _ = rows()
        self.assertTrue(Session().replay(actions.astype(np.float32).astype(np.float64))["success"])

    def test_wuji_oracle_succeeds(self):
        actions, hand = rows(WUJI_SOLUTION)
        self.assertEqual(hand, "wuji")
        self.assertTrue(Session(hand="wuji").replay(actions)["success"])

    def test_nop_fails_for_both_hands(self):
        for hand in WIDTHS:
            s = Session(hand=hand)
            st = s.replay(np.tile(s.hold_action(), (600, 1)))
            self.assertFalse(st["success"])
            self.assertEqual(st["stage"], 0)

    def test_truncated_rows_fail(self):
        actions, _ = rows()
        s = Session()
        success = s.replay(actions)["steps"]
        for cut in (500, 700, success - 1):
            st = s.replay(actions[:cut])
            self.assertFalse(st["success"], cut)
            self.assertFalse(st["done"], cut)

    def test_drop_fails_at_once(self):
        actions, _ = rows()
        dropped = actions.copy()
        dropped[200:, 6:] = 0.0  # open every finger while whisking
        st = Session().replay(dropped)
        self.assertEqual(st["reason"], "whisk_dropped")
        self.assertLess(st["steps"], 300)

    def test_drop_and_catch_fails(self):
        actions, _ = rows()
        caught = actions.copy()
        caught[550:554, 6:] = 0.0  # let go for four controls over the bowl, then close again
        st = Session().replay(caught)
        self.assertEqual(st["reason"], "whisk_dropped")
        self.assertEqual(st["failure_detail"]["contact"], "falling_unsupported")

    def test_knocking_the_bowl_fails(self):
        actions, _ = rows()
        knocked = actions.copy()
        knocked[230:260, 0] += np.linspace(0, 0.05, 30)
        knocked[260:, 0] += 0.05
        st = Session().replay(knocked)
        self.assertIn(st["reason"], ("bowl_tipped", "bowl_moved"))

    def test_later_rows_are_not_executed(self):
        actions, _ = rows()
        s = Session()
        st = s.replay(actions)
        sha = s.state_sha()
        tail = np.vstack([actions[: st["steps"]], np.tile(actions[0], (40, 1))])
        self.assertEqual(s.replay(tail)["steps"], st["steps"])
        self.assertEqual(s.state_sha(), sha)


class TrustBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.actions, _ = rows()

    def tearDown(self):
        self.tmp.cleanup()

    def bad(self, path, *extra):
        result = replay_cli(path, *extra)
        self.assertFalse(result["success"])
        self.assertEqual(result["bad_trajectory"], 1, result)

    def test_wrong_width_and_hand_label(self):
        self.bad(write(self.dir / "label.npz", self.actions, hand="wuji"))
        self.bad(write(self.dir / "narrow.npz", self.actions[:, :26]))
        self.bad(write(self.dir / "unknown.npz", self.actions, hand="shadow"))

    def test_non_finite_and_out_of_range(self):
        nan = self.actions.copy()
        nan[3, 2] = np.nan
        self.bad(write(self.dir / "nan.npz", nan))
        far = self.actions.copy()
        far[3, 9] = 9.0
        self.bad(write(self.dir / "range.npz", far))

    def test_metadata_mismatch(self):
        self.bad(write(self.dir / "task.npz", self.actions, task=np.array("assemble_hamburger")))
        self.bad(write(self.dir / "names.npz", self.actions, actuator_names=np.array(["x"] * 28)))
        self.bad(write(self.dir / "rows.npz", np.tile(self.actions[0], (4001, 1))))
        self.bad(SOLUTION, "--hand", "wuji")

    def test_forged_members_are_ignored(self):
        path = write(self.dir / "forged.npz", np.tile(self.actions[0], (60, 1)), success=np.array(True),
                     reward=np.array(1.0), config=np.array(json.dumps({"predicate": {"revolutions_required": 0}})))
        result = replay_cli(path)
        self.assertFalse(result["success"])
        self.assertEqual(result["bad_trajectory"], 0)
        actions, hand, _ = load_trajectory(path)
        self.assertEqual(hand, "sharpa")


if __name__ == "__main__":
    unittest.main()
