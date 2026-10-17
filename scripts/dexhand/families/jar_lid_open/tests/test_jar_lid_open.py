"""Authoring tests: actuation boundary, passive thread, oracles, negatives, trust boundary, Wuji composition.

Run with DEXHAND_ASSET_DIR pointing at the prepared Sharpa asset folder (Wuji assets beside it):
    python -m pytest scripts/dexhand/families/jar_lid_open/tests/test_jar_lid_open.py
"""

from __future__ import annotations

import io
import math
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from replay import replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import RELEASE_ANGLE, STOP_ANGLE, arm_rig  # noqa: E402

ORACLE = HERE / "solution/trajectory.npz"
WUJI_ORACLE = HERE / "solution/wuji/trajectory.npz"


def oracle_rows():
    with np.load(ORACLE, allow_pickle=False) as archive:
        return archive["actions"].copy()


class TaskTests(unittest.TestCase):
    def test_only_robot_is_actuated(self):
        for hand, width in (("sharpa", 58), ("wuji", 54)):
            s = Session(hand=hand)
            self.assertEqual(s.model.nu, width)
            self.assertEqual(s.model.nmocap, 0)
            self.assertEqual(s.model.neq, 0)
            self.assertEqual(s.robot, "marvin-bimanual-sharpa-wave")
            self.assertEqual(s.actuator_names[:14], arm_rig.ARM_ACTUATORS)
            joints = [s.model.joint(int(j)).name for j in s.model.actuator_trnid[:, 0]]
            self.assertFalse(any(name.startswith(("jar", "lid")) for name in joints))
            for name in ("jar_free", "lid_free"):
                self.assertEqual(s.model.joint(name).type, mujoco.mjtJoint.mjJNT_FREE)
            self.assertEqual(s.model.njnt - 2, len(set(joints)))

    def wrench_trial(self, lid_wrench, jar_wrench, steps):
        """Mechanism probe with test wrenches (never part of the task): returns (lid turn, lid rise)."""
        s = Session()
        lid, jar = s.checker.lid, s.checker.jar
        for _ in range(25):
            s.step(s.hold_action())
        z0 = s.checker.relative_pose(s.data)[1][2]
        turn0 = s.checker.turn
        for i in range(steps):
            ramp = min(1.0, (i + 1) / 25)
            s.data.xfrc_applied[lid] = np.asarray(lid_wrench) * ramp
            s.data.xfrc_applied[jar] = np.asarray(jar_wrench) * ramp
            mujoco.mj_step(s.model, s.data)
            s.checker.substep(s.data, 0, i)
        return s.checker.turn - turn0, s.checker.relative_pose(s.data)[1][2] - z0

    def test_closed_lid_cannot_be_pulled_off(self):
        turn, rise = self.wrench_trial([0, 0, 40, 0, 0, 0], [0, 0, -41, 0, 0, 0], 500)
        self.assertLess(rise, 0.001)
        self.assertLess(abs(turn), 0.05)

    def test_clockwise_turn_jams(self):
        turn, _ = self.wrench_trial([0, 0, 0, 0, 0, -0.3], [0, 0, 0, 0, 0, 0.3], 500)
        self.assertGreater(turn, -0.2)

    def test_counter_clockwise_turn_releases(self):
        turn, rise = self.wrench_trial([0, 0, 0.6, 0, 0, 0.02], [0, 0, -1, 0, 0, -0.02], 400)
        self.assertGreater(turn, RELEASE_ANGLE)
        self.assertGreater(rise, 0.03)

    def test_oracle_succeeds_with_slack_and_float32(self):
        rows = oracle_rows()
        s = Session()
        status = s.replay(rows)
        self.assertTrue(status["success"], status["reason"])
        self.assertEqual(status["stage"], 3)
        self.assertLessEqual(status["steps"], len(rows) - 50)
        self.assertTrue(s.replay(rows.astype(np.float32).astype(np.float64))["success"])

    def test_fresh_replays_are_identical(self):
        first, second = replay(ORACLE), replay(ORACLE)
        self.assertTrue(first["success"])
        self.assertEqual(first["state_sha"], second["state_sha"])

    def test_nop_and_truncations_fail(self):
        s = Session()
        rows = oracle_rows()
        self.assertFalse(s.replay(np.tile(s.initial_targets, (len(rows), 1)))["success"])
        success_step = s.replay(rows)["steps"]
        for cut in (200, 450, 700, success_step - 1):
            status = s.replay(rows[:cut])
            self.assertFalse(status["success"], cut)
            self.assertFalse(status["failed"], cut)

    def test_drop_fails_fast(self):
        s = Session()
        rows = oracle_rows().copy()
        right = np.arange(s.model.nu)[s.layout["fingers"]["right"]]
        rows[740:, right] = rows[-1, right]  # open the right hand's fingers while the lid is carried
        status = s.replay(rows)
        self.assertEqual(status["reason"], "lid_dropped")
        self.assertLess(status["steps"], 760)

    def test_knock_fails_fast(self):
        s = Session()
        rows = oracle_rows()[:180].copy()
        swing = np.tile(rows[-1], (150, 1))
        swing[:, 8] += 0.4 * np.minimum(1.0, np.arange(1, 151) / 60)  # right shoulder roll sweeps the hand sideways
        status = s.replay(np.vstack([rows, swing]))
        self.assertIn(status["reason"], ("jar_tipped", "jar_slid"))

    def test_trust_boundary(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            forged = Path(tmp) / "forged.npz"
            np.savez_compressed(forged, actions=np.tile(s.initial_targets, (20, 1)), hand=np.array("sharpa"),
                                success=np.array(True))
            self.assertFalse(replay(forged)["success"])
            wrong = Path(tmp) / "wrong.npz"
            np.savez_compressed(wrong, actions=np.tile(s.initial_targets, (20, 1)), hand=np.array("wuji"))
            with self.assertRaises(ValueError):
                replay(wrong)
            with self.assertRaises(ValueError):
                replay(ORACLE, expected_hand="wuji")

    def test_archive_abuse_is_rejected(self):
        s = Session()
        rows = np.tile(s.initial_targets, (20, 1))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            nan = rows.copy()
            nan[3, 7] = np.nan
            np.savez_compressed(tmp / "nan.npz", actions=nan)
            np.savez_compressed(tmp / "width.npz", actions=rows[:, :57])
            np.savez_compressed(tmp / "objects.npz", actions=np.array([[None] * 58] * 2, dtype=object))
            np.savez_compressed(tmp / "outside.npz", actions=rows + 10.0)
            np.savez_compressed(tmp / "task.npz", actions=rows, task=np.array("assemble_hamburger"))
            np.savez_compressed(tmp / "names.npz", actions=rows, actuator_names=np.array(s.actuator_names[::-1]))
            np.savez_compressed(tmp / "hand.npz", actions=rows, hand=np.array("left_claw"))
            buffer = io.BytesIO()
            np.save(buffer, rows)
            with zipfile.ZipFile(tmp / "shadow.npz", "w") as archive:
                archive.writestr("actions.npy", buffer.getvalue())
                archive.writestr("actions", b"success")
            for name in ("nan", "width", "objects", "outside", "task", "names", "hand", "shadow"):
                with self.assertRaises(ValueError, msg=name):
                    replay(tmp / f"{name}.npz")

    def test_wuji_oracle_succeeds_and_replays_identically(self):
        first, second = replay(WUJI_ORACLE), replay(WUJI_ORACLE)
        self.assertEqual(first["hand"], "wuji")
        self.assertTrue(first["success"], first["reason"])
        self.assertEqual(first["state_sha"], second["state_sha"])
        self.assertLessEqual(first["steps"], first["n_actions"] - 50)

    def test_wuji_reset_is_deterministic_and_nop_fails(self):
        shas = []
        for _ in range(2):
            w = Session(hand="wuji")
            self.assertEqual(w.action_dim, 54)
            for _ in range(300):
                w.step(w.hold_action())
            self.assertFalse(w.done)
            self.assertFalse(w.status()["success"])
            shas.append(w.state_sha())
        self.assertEqual(shas[0], shas[1])

    def test_release_window_geometry(self):
        self.assertAlmostEqual(RELEASE_ANGLE, 1.0 + 0.0015 / 0.0304)
        self.assertGreater(STOP_ANGLE - RELEASE_ANGLE, 0.15)
        self.assertLess(STOP_ANGLE, math.pi / 2)


if __name__ == "__main__":
    unittest.main()
