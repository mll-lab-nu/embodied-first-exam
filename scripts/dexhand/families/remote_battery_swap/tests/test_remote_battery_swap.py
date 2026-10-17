"""Authoring tests: oracle, negative controls, fail-fast, predicate fixtures and the trajectory trust boundary.

Run from the family folder (DEXHAND_ASSET_DIR / WUJI_ASSET_DIR must point at the hand assets outside the image):
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY))

from replay import load_trajectory, replay  # noqa: E402
from runtime import Session  # noqa: E402
from scene import hands  # noqa: E402

ORACLE = FAMILY / "solution/trajectory.npz"
TASK = "remote_battery_swap"
WIDTHS = {"sharpa": 58, "wuji": 54}
# Marvin arm layout (sharpa): left arm J1..J7 = 0..6, right arm J1..J7 = 7..13, left fingers 14..35, right 36..57
RIGHT_J2 = 8
PINCH = slice(36, 45)  # right thumb + index


def oracle_rows():
    actions, hand, _ = hands.read_trajectory(ORACLE, widths=WIDTHS, max_rows=6000, task=TASK)
    return actions, hand


def fresh_replay(path, *extra):
    """replay.py in a fresh process (the graders' path); returns its JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        proc = subprocess.run([sys.executable, str(FAMILY / "replay.py"), "--task", TASK, "--traj", str(path),
                               "--out", str(out), *extra], cwd=FAMILY, capture_output=True, text=True, timeout=900)
        assert proc.returncode == 0, proc.stderr[-2000:]
        return json.loads(out.read_text())


def cell_quat(yaw_deg):
    q = (Rotation.from_euler("z", yaw_deg, degrees=True) * Rotation.from_euler("y", 90, degrees=True)).as_quat()
    return [float(q[3]), float(q[0]), float(q[1]), float(q[2])]


def settled_fixture(**edits):
    """A test instance with edited initial object poses (instance definition only), hand parked high, settled."""
    config = json.loads((FAMILY / "task.json").read_text())
    config.update(copy.deepcopy(edits))
    s = Session(config=config)
    hold = s.hold_action()  # the arm holds its start pose, the hand 0.18 m above the table
    for _ in range(60):
        s.step(hold)
    return s


class OracleTests(unittest.TestCase):
    def test_oracle_two_fresh_replays_identical_with_slack(self):
        first, second = fresh_replay(ORACLE), fresh_replay(ORACLE)
        for result in (first, second):
            self.assertTrue(result["success"], result.get("reason"))
            self.assertEqual(result["stage"], 4)
            self.assertEqual(result["bad_trajectory"], 0)
        self.assertEqual(first["state_sha"], second["state_sha"])
        # success is reached well before the last row (hold rows appended as slack)
        self.assertLessEqual(first["steps"] + 50, first["n_actions"])

    def test_float32_rows_succeed(self):
        actions, _ = oracle_rows()
        status = Session().replay(actions.astype(np.float32).astype(np.float64))
        self.assertTrue(status["success"], status["reason"])


class NegativeTests(unittest.TestCase):
    def test_only_robot_is_actuated(self):
        s = Session()
        self.assertEqual(s.model.nu, 58)
        self.assertEqual(s.robot, "marvin-bimanual-sharpa-wave")
        self.assertEqual(s.model.nmocap, 0)
        self.assertEqual(s.model.neq, 0)
        self.assertTrue(all(n.endswith(("_J1", "_J2", "_J3", "_J4", "_J5", "_J6", "_J7")) or
                            n.startswith(("left_", "right_")) for n in s.joint_names))
        for name in ("remote", "tray", "old_cell", "new_cell"):
            self.assertEqual(s.model.joint(name + "_free").type, mujoco.mjtJoint.mjJNT_FREE)
        slide = s.model.joint("cover_slide").id
        self.assertNotIn(slide, set(s.model.actuator_trnid[:, 0].tolist()))
        self.assertGreater(s.model.dof_frictionloss[s.model.jnt_dofadr[slide]], 0)

    def test_nop_fails_and_is_deterministic(self):
        s = Session()
        rows = np.tile(s.hold_action(), (300, 1))
        first, second = s.replay(rows), None
        sha = s.state_sha()
        second = s.replay(rows)
        self.assertFalse(first["success"])
        self.assertFalse(first["failed"])
        self.assertEqual(first["stage"], 0)
        self.assertEqual(sha, s.state_sha())
        self.assertEqual(second["steps"], 300)

    def test_truncated_before_cover_closed_fails(self):
        actions, _ = oracle_rows()
        s = Session()
        closed = s.replay(actions)["stage_steps"]["cover_closed"]
        status = s.replay(actions[: closed - 60])
        self.assertFalse(status["success"])
        self.assertEqual(status["stage"], 3)
        self.assertFalse(status["conditions"]["cover_closed"])

    def test_one_row_short_of_hold_fails(self):
        actions, _ = oracle_rows()
        s = Session()
        full = s.replay(actions)
        short = s.replay(actions[: full["steps"] - 1])
        self.assertTrue(full["success"])
        self.assertFalse(short["success"])
        self.assertEqual(short["hold_steps"], s.config["checker"]["hold_steps"] - 1)

    def test_drop_mid_carry_fails_fast_and_later_rows_do_not_run(self):
        actions, _ = oracle_rows()
        rows = actions.copy()
        rows[720:, PINCH] = actions[480, PINCH]  # open the pinch mid-carry, several cm above the table
        s = Session()
        status = s.replay(rows)
        self.assertEqual(status["reason"], "cell_dropped")
        self.assertEqual(status["failure_detail"]["cell"], "old_cell")
        self.assertIn("unsupported", status["failure_detail"]["why"])  # caught by the 0.5 m/s no-contact rule
        self.assertEqual(status["steps"], status["failure_detail"]["control"] + 1)
        self.assertLess(status["steps"], len(rows))

    def test_release_from_three_centimetres_fails(self):
        # opening the pinch while the gray cell is still about 3 cm above the tray floor is a drop (reviewer RB-1):
        # the cell touches nothing and falls faster than 0.5 m/s before it lands; the 4 cm free-fall bound alone
        # would let it through
        actions, _ = oracle_rows()
        s = Session()
        s.reset()
        k, height = None, None
        for i, row in enumerate(actions[:1000]):
            s.step(row)
            tray_floor = s.data.xpos[s.model.body("tray").id][2] + 0.003
            h = s.data.xpos[s.model.body("old_cell").id][2] - 0.007 - tray_floor
            if i > 800 and h < 0.031:
                k, height = i + 1, h
                break
        opened = np.repeat(actions[k - 1:k], 60, axis=0)
        opened[:, PINCH] = actions[480, PINCH]
        status = s.replay(np.concatenate([actions[:k], opened]))
        self.assertTrue(0.02 < height < 0.04, height)
        self.assertEqual(status["reason"], "cell_dropped", status.get("failure_detail"))
        self.assertIn("unsupported", status["failure_detail"]["why"])

    def test_knocked_remote_fails_fast(self):
        # while the hand pinches the gray cell in the remote, the right shoulder rolls 0.6 rad over 80 controls
        actions, _ = oracle_rows()
        row = actions[599].copy()
        sweep = [row + np.eye(len(row))[RIGHT_J2] * 0.6 * t for t in np.linspace(0, 1, 80)]
        status = Session().replay(np.concatenate([actions[:600], np.asarray(sweep)]))
        self.assertIn(status["reason"], ("remote_tipped", "remote_displaced"))

    def test_latch_holds_the_door_without_the_tab_pressed(self):
        # the index pad pushes the thumb tab's front edge toward -x without pressing the tab: the hook stays in front
        # of the latch stop and the door does not open (tools/negatives.py, authoring controller)
        sys.path.insert(0, str(FAMILY / "tools"))
        import negatives

        with tempfile.TemporaryDirectory() as tmp:
            status = negatives.force_door(Path(tmp) / "force.npz")
            result = fresh_replay(Path(tmp) / "force.npz")
        self.assertLess(status["cover_slide_m"], 0.002)
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], 0)

    def test_object_dropped_on_the_table_fails(self):
        # the gray cell may never touch the table: a test instance that starts it just above the table top
        s = settled_fixture(old_cell_pos=[0.10, 0.20, 0.312])
        self.assertEqual(s.failure, "cell_dropped")


class PredicateTests(unittest.TestCase):
    def setUp(self):
        base = json.loads((FAMILY / "task.json").read_text())
        remote = np.asarray(base["remote_pos"])
        tray = np.asarray(base["tray_pos"])
        self.slot = (remote + np.asarray(base["slot_center_local"])).tolist()
        self.in_tray = [float(tray[0]), float(tray[1]), float(tray[2] + 0.011)]

    def conditions(self, new_pos, new_yaw, old_pos=None):
        s = settled_fixture(old_cell_pos=old_pos or self.in_tray, old_cell_quat=cell_quat(0),
                            new_cell_pos=new_pos, new_cell_quat=cell_quat(new_yaw))
        self.assertIsNone(s.failure)
        return s.features()["conditions"]

    def test_goal_arrangement_satisfies_conditions(self):
        c = self.conditions([self.slot[0], self.slot[1], self.slot[2] + 0.0005], 0)
        self.assertTrue(c["new_cell_seated"] and c["old_cell_in_tray"] and c["cover_closed"])

    def test_reversed_polarity_is_not_seated(self):
        c = self.conditions([self.slot[0], self.slot[1], self.slot[2] + 0.0005], 180)
        self.assertFalse(c["new_cell_seated"])

    def test_skewed_or_raised_cell_is_not_seated(self):
        self.assertFalse(self.conditions([self.slot[0], self.slot[1], self.slot[2] + 0.01], 30)["new_cell_seated"])
        self.assertFalse(self.conditions([self.slot[0] + 0.02, self.slot[1], self.slot[2] + 0.012], 0)["new_cell_seated"])

    def test_stages_need_the_sequence(self):
        # goal arrangement from reset, but the door was never opened: no stage latches, no success
        s = settled_fixture(old_cell_pos=self.in_tray, old_cell_quat=cell_quat(0),
                            new_cell_pos=[self.slot[0], self.slot[1], self.slot[2] + 0.0005], new_cell_quat=cell_quat(0))
        for _ in range(100):
            s.step(s.hold_action())
        self.assertEqual(s.status()["stage"], 0)
        self.assertFalse(s.success)


class TrustBoundaryTests(unittest.TestCase):
    def write(self, path, **members):
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in members.items():
                buffer = io.BytesIO()
                np.lib.format.write_array(buffer, np.asarray(value), allow_pickle=False)
                archive.writestr(name, buffer.getvalue())

    def test_forged_members_are_ignored(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forged.npz"
            self.write(path, **{"actions.npy": np.tile(s.hold_action(), (60, 1)), "success.npy": np.array(True),
                                "stage.npy": np.array(4), "config.npy": np.array('{"checker": {}}')})
            result = fresh_replay(path)
        self.assertFalse(result["success"])
        self.assertEqual(result["bad_trajectory"], 0)

    def test_shadowing_raw_member_is_rejected(self):
        s = Session()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shadow.npz"
            self.write(path, **{"actions.npy": np.tile(s.hold_action(), (60, 1)), "actions": np.zeros((5, 58))})
            result = fresh_replay(path)
        self.assertEqual(result["bad_trajectory"], 1)
        self.assertFalse(result["success"])

    def test_wrong_width_hand_label_nan_and_range_are_rejected(self):
        actions, _ = oracle_rows()
        with tempfile.TemporaryDirectory() as tmp:
            cases = {}
            cases["wrong_width"] = actions[:, :28]  # the old floating-stage width
            cases["sharpa_rows_as_wuji"] = actions
            nan = actions[:10].copy()
            nan[3, 7] = np.nan
            cases["nan"] = nan
            far = actions[:10].copy()
            far[2, 0] = 5.0
            cases["out_of_range"] = far
            for name, rows in cases.items():
                path = Path(tmp) / f"{name}.npz"
                if name == "sharpa_rows_as_wuji":
                    self.write(path, **{"actions.npy": rows, "hand.npy": np.array("wuji")})
                else:
                    self.write(path, **{"actions.npy": rows})
                result = fresh_replay(path)
                self.assertEqual(result["bad_trajectory"], 1, name)
                self.assertFalse(result["success"], name)
            with self.assertRaises(Exception):
                load_trajectory(Path(tmp) / "nan.npz")

    def test_hand_mismatch_with_trusted_service_is_rejected(self):
        result = fresh_replay(ORACLE, "--trusted-service", "--hand", "wuji")
        self.assertEqual(result["bad_trajectory"], 1)


class WujiTests(unittest.TestCase):
    def test_wuji_loads_on_the_same_arms_and_nop_fails_deterministically(self):
        s = Session(hand="wuji")
        self.assertEqual(s.action_dim, 54)
        self.assertEqual(s.actuator_names[:14], Session().actuator_names[:14])
        rows = np.tile(s.hold_action(), (200, 1))
        first = s.replay(rows)
        sha = s.state_sha()
        s.replay(rows)
        self.assertFalse(first["success"])
        self.assertFalse(first["failed"])
        self.assertEqual(sha, s.state_sha())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wuji_nop.npz"
            s.save_trajectory(rows, path)
            a, b = fresh_replay(path), fresh_replay(path)
        self.assertEqual(a["hand"], "wuji")
        self.assertFalse(a["success"])
        self.assertEqual(a["state_sha"], b["state_sha"])


if __name__ == "__main__":
    unittest.main()
