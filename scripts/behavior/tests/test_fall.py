"""Unit tests of BEHAVIOR-1K's fall rule (the tooling's up_z / FallWatch, OmniGibson's Falling held for FALL_HOLD_STEPS)
on synthetic poses: no simulator, no GPU.

    python3 -m unittest discover -s scripts/behavior/tests          # needs numpy (the tooling imports it)

The tooling source is the template twin's environment/rcb_behavior.py, which the generator copies into every task.
"""
from __future__ import annotations

import importlib.util
import math
import os
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tasks" / "behavior-picking-up-trash-i00-privileged" / "environment" / "rcb_behavior.py"
sys.dont_write_bytecode = True
os.environ["RCB_SESSION_LOG"] = ""             # the tooling's interaction log: off in tests
os.environ["RCB_SESSION_LOG_KEEP"] = ""
_spec = importlib.util.spec_from_file_location("rcb_behavior_under_test", TOOL)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def axis_quat(axis, angle):
    s = math.sin(angle / 2.0)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(angle / 2.0))


def base_quat(rx, ry, rz, root_yaw=0.0):
    """The R1Pro's base_link: an upright world-fixed root (any yaw), then the virtual joints rx, ry, rz in chain order."""
    q = axis_quat((0, 0, 1), root_yaw)
    for axis, ang in (((1, 0, 0), rx), ((0, 1, 0), ry), ((0, 0, 1), rz)):
        q = qmul(q, axis_quat(axis, ang))
    return q


def rotated_up_z(q):
    x, y, z, w = q
    return qmul(qmul(q, (0.0, 0.0, 1.0, 0.0)), (-x, -y, -z, w))[2]


def tilted(deg, axis="ry"):
    a = math.radians(deg)
    return M.up_z(base_quat(a if axis == "rx" else 0.0, a if axis == "ry" else 0.0, 0.4))


class UpZ(unittest.TestCase):
    def test_upstream_defaults(self):
        # OmniGibson 3.9.2 Falling(fall_height=0.03, topple=True, tilt_tolerance=0.75); 10 s at 30 Hz
        self.assertEqual((M.FALL_HEIGHT_M, M.FALL_TILT_TOLERANCE, M.FALL_HOLD_STEPS), (0.03, 0.75, 300))
        self.assertAlmostEqual(math.degrees(math.acos(M.FALL_TILT_TOLERANCE)), 41.41, places=2)
        self.assertTrue(M.FALL_REASON.startswith("failure: "))

    def test_matches_rotation_and_virtual_joints(self):
        rng = random.Random(0)
        for _ in range(2000):
            rx, ry, rz, yaw = (rng.uniform(-math.pi, math.pi) for _ in range(4))
            q = base_quat(rx, ry, rz, root_yaw=yaw)
            self.assertAlmostEqual(M.up_z(q), rotated_up_z(q), places=10)
            self.assertAlmostEqual(M.up_z(q), math.cos(rx) * math.cos(ry), places=10)

    def test_yaw_only_and_scaling(self):
        self.assertAlmostEqual(M.up_z(base_quat(0, 0, 2.5, root_yaw=-1.0)), 1.0, places=12)
        q = base_quat(0.3, -0.5, 1.0)
        self.assertAlmostEqual(M.up_z([2.0 * v for v in q]), M.up_z(q), places=12)
        self.assertTrue(math.isnan(M.up_z((0, 0, 0, 0))))


class Falling(unittest.TestCase):
    def test_tilt_threshold(self):
        for axis in ("rx", "ry"):
            for deg, want in ((0, False), (20, False), (41.0, False), (41.8, True), (63, True), (93, True), (145, True), (180, True)):
                self.assertEqual(M.FallWatch.falling(0.005, tilted(deg, axis)), want, (axis, deg))

    def test_below_floor(self):
        self.assertFalse(M.FallWatch.falling(0.005, 1.0))        # the R1Pro's base_link at rest
        self.assertFalse(M.FallWatch.falling(-0.029, 1.0))
        self.assertTrue(M.FallWatch.falling(-0.031, 1.0))
        self.assertTrue(M.FallWatch.falling(0.55, 1.0, floor_z=0.6))

    def test_nan_never_counts(self):
        self.assertFalse(M.FallWatch.falling(float("nan"), float("nan")))


class Hold(unittest.TestCase):
    def test_hold_reached_on_the_300th_step(self):
        w = M.FallWatch()
        for i in range(299):
            self.assertFalse(w.update(0.23, tilted(63)), i)
        self.assertTrue(w.update(0.23, tilted(63)))
        self.assertEqual(w.fallen_step, 300)

    def test_self_righting_topples_never_count(self):
        w = M.FallWatch()
        for deg, steps in ((81.3, 99), (61.3, 128), (50.2, 95), (60.3, 12)):   # short topples recorded in agent runs
            for _ in range(steps):
                w.update(0.3, tilted(deg))
            w.update(0.005, 1.0)
        self.assertFalse(w.fallen)
        self.assertEqual(w.run, 0)

    def test_latched_until_reset(self):
        w = M.FallWatch(hold=2)
        w.update(0.2, tilted(90)); w.update(0.2, tilted(90))
        self.assertTrue(w.fallen)
        self.assertTrue(w.update(0.005, 1.0))
        w.reset()
        self.assertEqual((w.fallen, w.run, w.fallen_step, w.steps), (False, 0, None, 0))

    def test_upright_robot_never_falls(self):
        rng = random.Random(1)
        w = M.FallWatch(hold=1)
        for _ in range(20000):                   # tilted up to 40 deg in any direction, the base up to 0.3 m high
            a, b = rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45)
            if math.degrees(math.acos(math.cos(a) * math.cos(b))) <= 40.0:
                w.update(rng.uniform(-0.02, 0.3), M.up_z(base_quat(a, b, rng.uniform(-3, 3))))
        self.assertFalse(w.fallen)


class _T:
    """The few torch tensor methods Session.step uses, on numpy."""
    def __init__(self, x):
        import numpy as np
        self.x = np.asarray(x)
    def flatten(self):
        return _T(self.x.reshape(-1))
    def numel(self):
        return int(self.x.size)
    def clone(self):
        return _T(self.x.copy())
    def tolist(self):
        return self.x.tolist()

    def __getitem__(self, i):
        return self.x[i]


class SessionStep(unittest.TestCase):
    """Session.step's order on a scripted simulator: the BDDL goal first, then the fall rule; either ends the episode."""

    def session(self, poses, goal_at=None):
        import types
        s = object.__new__(M.Session)
        steps = {"n": 0}

        def ev_step():
            steps["n"] += 1
            return (goal_at is not None and steps["n"] >= goal_at), False

        def pose():
            pos, quat = poses[min(steps["n"], len(poses)) - 1]
            return _T(pos), _T(quat)
        s.th = types.SimpleNamespace(as_tensor=_T)
        s.action_dim, s.task = 25, "picking_up_trash"
        s.ev = types.SimpleNamespace(step=ev_step)
        s.env = types.SimpleNamespace(episode_steps=0)
        s.robot = types.SimpleNamespace(get_position_orientation=pose)
        s._policy = types.SimpleNamespace(next=None)
        s._recording, s._stepped, s._last_action, s.episode_done = None, False, None, False
        s._fall, s.end_reason = M.FallWatch(hold=5), None
        return s

    def run_steps(self, s, n):
        ends = []
        for _ in range(n):
            term, trunc = s.step([0.0] * 25)
            ends.append(bool(term or trunc))
            if term or trunc:
                break
        return ends

    def test_fall_ends_the_episode_after_the_hold(self):
        lying = ((0.0, 0.0, 0.25), base_quat(0.0, math.radians(93), 0.0))
        s = self.session([((0, 0, 0.005), (0, 0, 0, 1))] * 3 + [lying] * 20)
        ends = self.run_steps(s, 20)
        self.assertEqual(len(ends), 3 + 5)                      # upright 3 steps, then the 5-step hold
        self.assertTrue(s.episode_done and s._fall.fallen)
        self.assertEqual(s.end_reason, M.FALL_REASON)
        with self.assertRaisesRegex(M.PrimitiveError, "fell over"):
            s.step([0.0] * 25)

    def test_goal_on_the_same_step_wins(self):
        lying = ((0.0, 0.0, 0.25), base_quat(math.radians(70), 0.0, 0.0))
        s = self.session([lying] * 10, goal_at=5)               # the goal holds on the step the hold would be reached
        self.assertEqual(len(self.run_steps(s, 10)), 5)
        self.assertTrue(s.episode_done)
        self.assertIsNone(s.end_reason)                         # ended by the goal, not by the fall
        self.assertFalse(s._fall.fallen)

    def test_wobble_does_not_end(self):
        up, down = ((0, 0, 0.005), (0, 0, 0, 1)), ((0, 0, 0.3), base_quat(math.radians(80), 0.0, 0.0))
        s = self.session(([down] * 4 + [up]) * 6)
        self.assertEqual(self.run_steps(s, 30), [False] * 30)
        self.assertFalse(s.episode_done)


if __name__ == "__main__":
    unittest.main()
