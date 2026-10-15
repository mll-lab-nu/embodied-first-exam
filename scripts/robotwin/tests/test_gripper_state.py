"""Unit tests of the RoboTwin tooling's gripper state (rcb_traj.Session.gripper_opening and the gripper clauses it
installs on the robot) on a stub robot, and of its hand-in row cap (RowCap): no simulator, no GPU.

    python3 -m unittest discover -s scripts/robotwin/tests          # needs numpy

The stub's set_gripper / plan_grippers follow RoboTwin's (envs/robot/robot.py, envs/robot/planner.py, envs/_base_task.py);
the gripper scale and finger joints are aloha-agilex's (assets/embodiments/aloha-agilex/config.yml).
The tooling source is the template task's tests/rcb_traj.py (scripts/robotwin_sync_shared.py copies it to every task).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tasks" / "robotwin_2_0_stack_blocks_two-privileged" / "tests" / "rcb_traj.py"
sys.dont_write_bytecode = True
os.environ["RCB_SESSION_LOG"] = ""
os.environ["RCB_AGENT_TRACE_DIR"] = ""
_spec = importlib.util.spec_from_file_location("rcb_traj_under_test", TOOL)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

SCALE = [-0.01, 0.045]          # aloha-agilex gripper_scale


class Joint:
    def __init__(self, name):
        self.name, self.drive_target, self.vel = name, 0.0, 0.0

    def get_name(self): return self.name
    def get_drive_target(self): return np.array([self.drive_target])
    def get_drive_velocity_target(self): return np.array([self.vel])
    def set_drive_target(self, v): self.drive_target = float(v)
    def set_drive_velocity_target(self, v): self.vel = float(v)


class Robot:
    """RoboTwin's Robot, reduced to the gripper: set_gripper, get_normal_real_gripper_val and the is_* clauses."""

    def __init__(self):
        for side, p in (("left", "fl"), ("right", "fr")):
            setattr(self, f"{side}_arm_joints", [Joint(f"{p}_joint{i}") for i in range(1, 7)])
            setattr(self, f"{side}_gripper", [(Joint(f"{p}_joint7"), 1.0, 0.0), (Joint(f"{p}_joint8"), 1.0, 0.0)])
            setattr(self, f"{side}_gripper_scale", list(SCALE))
            setattr(self, f"{side}_gripper_val", 0.0)
        self.left_entity = self.right_entity = object()

    def _real(self, side):
        g, sc = getattr(self, f"{side}_gripper"), getattr(self, f"{side}_gripper_scale")
        return float(np.clip((g[0][0].get_drive_target()[0] - sc[0]) / (sc[1] - sc[0]), 0, 1))

    def set_gripper(self, gripper_val, arm_tag, gripper_eps=0.1):
        gripper_val = np.clip(gripper_val, 0, 1)
        setattr(self, f"{arm_tag}_gripper_val", gripper_val)
        joints, sc, real = getattr(self, f"{arm_tag}_gripper"), getattr(self, f"{arm_tag}_gripper_scale"), self._real(arm_tag)
        if (gripper_val - real > gripper_eps and gripper_eps > 0) or (gripper_val - real < gripper_eps and gripper_eps < 0):
            gripper_val = real + gripper_eps
        real_val = sc[0] + gripper_val * (sc[1] - sc[0])
        for joint, mult, bias in joints:
            target = real_val * mult + bias
            joint.set_drive_velocity_target(np.clip(target - joint.drive_target, -1.0, 1.0) * 0.05)
            joint.set_drive_target(target)

    # RoboTwin's own clauses (what gripper_state="command" keeps)
    def is_left_gripper_open(self): return self.left_gripper_val > 0.8
    def is_right_gripper_open(self): return self.right_gripper_val > 0.8
    def is_left_gripper_open_half(self): return self.left_gripper_val > 0.45
    def is_right_gripper_open_half(self): return self.right_gripper_val > 0.45
    def is_left_gripper_close(self): return self.left_gripper_val < 0.2
    def is_right_gripper_close(self): return self.right_gripper_val < 0.2


def session(gripper_state="fingers"):
    """A Session around the stub robot, wired as Session.reset() does it (no scene)."""
    s = M.Session.__new__(M.Session)
    r = Robot()
    s.env = types.SimpleNamespace(robot=r)
    s.gripper_state = gripper_state
    s._joints = list(r.left_arm_joints) + [g[0] for g in r.left_gripper] + list(r.right_arm_joints) + [g[0] for g in r.right_gripper]
    if gripper_state == "fingers":
        s._install_gripper_predicates()
    return s, r


def plan_and_run(s, r, side, target, rows=None):
    """Base_Task.set_gripper + the control loop of Base_Task.take_dense_action: 200 planned values, 100 held."""
    now = getattr(r, f"{side}_gripper_val")
    vals = np.linspace(now, target, 200)
    per_step = (target - now) / 200
    for v in list(vals) + [vals[-1]] * 100:
        r.set_gripper(v, side, per_step)
        if rows is not None:
            rows.append(s._current_row())


class GripperState(unittest.TestCase):
    def test_action_layout(self):
        s, _ = session()
        self.assertEqual(s.action_dim, 34)
        self.assertIn("finger joints' position targets", s.action_layout)

    def test_forged_row_does_not_open(self):
        """The reviewed false pass: finger targets closed on the block, gripper-command columns set to 1."""
        s, r = session()
        row = np.zeros(34)
        row[[6, 7, 14, 15]] = SCALE[0]          # finger position targets: closed
        row[32:34] = 1.0                        # "gripper command": open
        s._apply_row(row)
        self.assertEqual((r.left_gripper_val, r.right_gripper_val), (1.0, 1.0))
        self.assertFalse(r.is_left_gripper_open() or r.is_right_gripper_open())
        self.assertTrue(r.is_left_gripper_close() and r.is_right_gripper_close())
        self.assertEqual(s.gripper_opening("left"), (0.0, 0.0))

    def test_command_mode_keeps_robotwins_rule(self):
        """gripper_state="command" (the standard service): RoboTwin's own clauses, untouched."""
        s, r = session("command")
        row = np.zeros(34); row[[6, 7, 14, 15]] = SCALE[0]; row[32:34] = 1.0
        s._apply_row(row)
        self.assertNotIn("is_left_gripper_open", vars(r))
        self.assertTrue(r.is_left_gripper_open() and r.is_right_gripper_open())

    def test_primitives_agree_with_the_command(self):
        """Open / close through RoboTwin's planned gripper motion: the fingers say what the command says."""
        for mode in ("fingers", "command"):
            s, r = session(mode)
            plan_and_run(s, r, "left", 1.0); plan_and_run(s, r, "right", 1.0)      # setup_demo: together_open_gripper
            self.assertTrue(r.is_left_gripper_open() and r.is_right_gripper_open(), mode)
            self.assertFalse(r.is_left_gripper_close(), mode)
            lo, hi = s.gripper_opening("left")
            self.assertAlmostEqual(lo, 1.0, places=9); self.assertAlmostEqual(hi, 1.0, places=9)
            plan_and_run(s, r, "left", 0.0)
            self.assertTrue(r.is_left_gripper_close() and not r.is_left_gripper_open(), mode)
            self.assertTrue(r.is_right_gripper_open(), mode)
            for target in (0.5, 0.9, 0.1, 1.0):     # the clauses agree with RoboTwin's on every planned target
                plan_and_run(s, r, "left", target)
                self.assertAlmostEqual(s.gripper_opening("left")[0], target, places=9)
                self.assertEqual(r.is_left_gripper_open(), target > 0.8, (mode, target))
                self.assertEqual(r.is_left_gripper_open_half(), target > 0.45, (mode, target))
                self.assertEqual(r.is_left_gripper_close(), target < 0.2, (mode, target))

    def test_recorded_rows_replay_to_the_same_state(self):
        s, r = session()
        rows: list = []
        plan_and_run(s, r, "left", 1.0, rows); plan_and_run(s, r, "right", 1.0, rows); plan_and_run(s, r, "left", 0.0, rows)
        live = (r.is_left_gripper_open(), r.is_left_gripper_close(), r.is_right_gripper_open(), r.is_right_gripper_close())
        self.assertEqual(live, (False, True, True, False))
        s2, r2 = session()
        for row in rows:
            s2._apply_row(row)
        again = (r2.is_left_gripper_open(), r2.is_left_gripper_close(), r2.is_right_gripper_open(), r2.is_right_gripper_close())
        self.assertEqual(again, live)
        self.assertEqual(s2.gripper_opening("left"), s.gripper_opening("left"))
        self.assertEqual(r2.left_gripper_val, r.left_gripper_val)        # the command value still round-trips (planning reads it)

    def test_a_single_command_does_not_open_at_once(self):
        """Robot.set_gripper(1.0) once moves the finger targets by 0.1: RoboTwin's value says open, the fingers do not."""
        s, r = session()
        r.set_gripper(1.0, "left")
        self.assertEqual(float(r.left_gripper_val), 1.0)
        self.assertFalse(r.is_left_gripper_open())
        for _ in range(12):
            r.set_gripper(1.0, "left")
        self.assertTrue(r.is_left_gripper_open())

    def test_fingers_that_disagree_are_neither_open_nor_closed(self):
        s, r = session()
        row = np.zeros(34); row[6], row[7] = SCALE[1], SCALE[0]; row[14] = row[15] = SCALE[1]
        s._apply_row(row)
        self.assertEqual(s.gripper_opening("left"), (0.0, 1.0))
        self.assertFalse(r.is_left_gripper_open() or r.is_left_gripper_close())
        self.assertTrue(r.is_right_gripper_open())

    def test_mimic_multiplier_and_bias(self):
        s, r = session()
        r.left_gripper = [(r.left_gripper[0][0], 1.0, 0.0), (r.left_gripper[1][0], -2.0, 0.01)]
        plan_and_run(s, r, "left", 1.0)
        lo, hi = s.gripper_opening("left")
        self.assertAlmostEqual(lo, 1.0, places=9); self.assertAlmostEqual(hi, 1.0, places=9)

    def test_bad_gripper_state(self):
        with self.assertRaises(ValueError):
            M.Session("stack_blocks_two", gripper_state="flag")


class RowCap(unittest.TestCase):
    """The hand-in cap: the verifier grades at most MAX_T rows (tests/grade.py), so the tool refuses to save or to replay
    more. Before 2026-10-13 it did both, and a 209,233-row trajectory that replayed to success here was graded 0."""

    def session(self):
        s, _ = session()                                  # the stub robot's 16 joints (34 columns); no scene: reset / step / status are stand-ins
        s.task, s.seed, s.expected_sha = "stack_blocks_two", 0, ""
        s.calls = []
        s.reset = lambda: s.calls.append("reset")
        s.step = lambda row=None: s.calls.append("step")
        s.status = lambda: {"success": False, "sim_steps": s.calls.count("step"), "state_sha": "0" * 12}
        s._trace_kind = "rollout"
        return s

    def test_the_cap_is_the_verifiers(self):
        import re
        grade = (TOOL.parent / "grade.py").read_text()
        self.assertEqual(int(re.search(r"MAX_T = ([0-9_]+)", grade).group(1).replace("_", "")), M.MAX_T)
        self.assertEqual(M.MAX_T, 200_000)

    def test_save_refuses_a_trajectory_the_verifier_would_reject(self):
        import tempfile
        s = self.session()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "trajectory.npz")
            with self.assertRaises(ValueError) as e:
                s.save_trajectory(np.zeros((M.MAX_T + 1, 34)), path)
            self.assertIn("200,000 rows", str(e.exception)); self.assertIn("200,001 rows", str(e.exception))
            self.assertFalse(os.path.exists(path))        # nothing was written: no file that looks like a deliverable
            s.max_rows = 5
            s.save_trajectory(np.zeros((5, 34)), path)    # at the cap: saved
            self.assertEqual(np.load(path)["actions"].shape, (5, 34))
            with self.assertRaises(ValueError):
                s.save_trajectory(np.zeros((6, 34)), path)

    def test_replay_refuses_it_before_anything_runs(self):
        s = self.session()
        with self.assertRaises(ValueError) as e:
            s.replay(np.zeros((M.MAX_T + 1, 34)))
        self.assertIn("200,000 rows", str(e.exception))
        self.assertEqual(s.calls, [])                     # no reset, no step: no "success" for a file that cannot count
        out = s.replay(np.zeros((M.MAX_T, 34)))           # exactly the cap replays
        self.assertEqual((s.calls.count("reset"), out["sim_steps"]), (1, M.MAX_T))

    def test_record_stop_returns_the_rows_and_warns(self):
        import contextlib, io
        s = self.session(); s.max_rows = 3
        s.env = types.SimpleNamespace(check_success=lambda: False)
        s._recording = [np.zeros(34)] * 4
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            acts = s.record_stop()
        self.assertEqual(acts.shape, (4, 34))
        self.assertIn("at most 3 rows", err.getvalue()); self.assertIn("will refuse", err.getvalue())

    def test_no_cap_for_a_session_that_lifts_it(self):
        s = self.session(); s.max_rows = None             # the standard-mode service: an episode is not a hand-in
        self.assertEqual(s.replay(np.zeros((M.MAX_T + 1, 34)))["sim_steps"], M.MAX_T + 1)


if __name__ == "__main__":
    unittest.main()
