"""Unit tests of BEHAVIOR-1K's fall rule (the tooling's up_z / FallWatch, OmniGibson's Falling held for FALL_HOLD_STEPS)
on synthetic poses, and its success rule (REST_*: goal + release + rest for 1 s, the settle window SETTLE_STEPS), the
simulator-breakdown check (BREAKDOWN_*) and the side-effect-free status() on a stand-in simulator: no simulator, no GPU.

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

import numpy as np

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

    def __array__(self, dtype=None, copy=None):
        return self.x if dtype is None else self.x.astype(dtype)


class SessionStep(unittest.TestCase):
    """Session.step's order on a scripted simulator: the success rule first, then the fall rule; either ends the episode."""

    def session(self, poses, goal_at=None):
        import types
        s = object.__new__(M.Session)
        steps = {"n": 0}

        def ev_step():
            steps["n"] += 1
            s.env.task.success = goal_at is not None and steps["n"] >= goal_at
            return s.env.task.success, False

        def pose():
            pos, quat = poses[min(steps["n"], len(poses)) - 1]
            return _T(pos), _T(quat)
        s.th = types.SimpleNamespace(as_tensor=_T)
        s.action_dim, s.task = 25, "picking_up_trash"
        s.ev = types.SimpleNamespace(step=ev_step)
        s.env = types.SimpleNamespace(episode_steps=0, task=types.SimpleNamespace(success=False, object_scope={}))
        s.robot = types.SimpleNamespace(get_position_orientation=pose, get_linear_velocity=lambda: [0.0, 0.0, 0.0],
                                        get_joint_positions=lambda: [0.0] * 28, _ag_obj_in_hand={})
        s._policy = types.SimpleNamespace(next=None)
        s._recording, s._stepped, s._last_action, s.episode_done = None, False, None, False
        s._fall, s.end_reason = M.FallWatch(hold=5), None
        s._rest, s._rest_info, s.breakdown, s.goal_objects = M.RestWatch(M.REST_STEPS), {"held": [], "moving": []}, None, []
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
        s = self.session([lying] * 40, goal_at=1)               # the success window closes on the step the fall hold does
        s._fall = M.FallWatch(hold=M.REST_STEPS)
        self.assertEqual(len(self.run_steps(s, 40)), M.REST_STEPS)
        self.assertTrue(s.episode_done)
        self.assertIsNone(s.end_reason)                         # ended by the goal, not by the fall
        self.assertFalse(s._fall.fallen)

    def test_wobble_does_not_end(self):
        up, down = ((0, 0, 0.005), (0, 0, 0, 1)), ((0, 0, 0.3), base_quat(math.radians(80), 0.0, 0.0))
        s = self.session(([down] * 4 + [up]) * 6)
        self.assertEqual(self.run_steps(s, 30), [False] * 30)
        self.assertFalse(s.episode_done)


# ------------------------------------------------------------------------------------------------ the success rule
# (2026-10-14) REST_* / SETTLE_STEPS / BREAKDOWN_* and the side-effect-free status() on a stand-in simulator.
GOAL = [["forall", ["?can__of__soda.n.01", "-", "can__of__soda.n.01"], ["inside", "?can__of__soda.n.01", "?ashcan.n.01_1"]]]


class _State:
    """An object state with OmniGibson's value cache (BaseObjectState: _cache, _changed, _last_t_updated)."""
    def __init__(self):
        self._cache, self._changed, self._last_t_updated = {}, {}, -1


class _Obj:
    def __init__(self, name):
        self.name, self.v, self.p = name, np.zeros(3), np.zeros(3)
        self.states = {"Inside": _State()}
    def get_linear_velocity(self): return self.v
    def get_position_orientation(self): return self.p, np.array([0.0, 0.0, 0.0, 1.0])


class _Robot(_Obj):
    def __init__(self):
        super().__init__("robot")
        self._ag_obj_in_hand = {"left": None, "right": None}
        self.controller_action_idx = {"base": [0, 1, 2]}
    def get_joint_positions(self): return np.zeros(28)


class _Task:
    def __init__(self, scope):
        self.success = False; self.object_scope = scope
        self.compiled_task = type("C", (), {"conditions": type("D", (), {"parsed_goal_conditions": GOAL})()})()


class _Metric:
    """The challenge's q_score metric: its aggregate() evaluates predicates, which fills the object states' caches."""
    def __init__(self, objs): self.objs = objs
    def aggregate(self, env):
        for o in self.objs:
            o.states["Inside"]._cache[("x",)] = {"value": True, "t": env.episode_steps}
            o.states["Inside"]._changed[(0, "x")] = True
            o.states["Inside"]._last_t_updated = env.episode_steps
        return {"q_score": {"final": 1.0 if env.task.success else 0.5}}


class _Ev:
    def __init__(self, sess, goal_at):
        self.s, self.goal_at = sess, goal_at
        self.metrics = []
    def step(self):
        env = self.s.env; env.episode_steps += 1
        env.task.success = self.goal_at is not None and env.episode_steps >= self.goal_at
        return env.task.success, False


def stand_in_session(goal_at=None):
    """A Session on the stand-in: Session.__init__ needs Isaac, so its state is set here the way __init__ sets it."""
    s = M.Session.__new__(M.Session)
    cans = {f"can__of__soda.n.01_{i}": _Obj(f"can{i}") for i in (1, 2, 3)}
    scope = {**cans, "ashcan.n.01_1": _Obj("ashcan"), "floor.n.01_1": _Obj("floor"), "agent.n.01_1": None}
    s.task, s.robot = "picking_up_trash", _Robot()
    s.env = type("E", (), {})(); s.env.task = _Task(scope); s.env.episode_steps = 0
    s.env.scene = type("S", (), {"objects": list(scope.values())[:5]})()
    s.ev = _Ev(s, goal_at); s.ev.metrics = [_Metric(list(cans.values()))]
    s._policy = type("P", (), {"next": None})()
    s._recording, s.episode_done, s._last_action, s._stepped = None, False, None, False
    s._fall = M.FallWatch(M.FALL_HOLD_STEPS, 0.0); s._rest = M.RestWatch(M.REST_STEPS)
    s._rest_info = {"held": [], "moving": []}; s.breakdown = None; s.end_reason = None
    s._resets, s.action_dim = 0, 25
    s.th = type("TH", (), {"as_tensor": staticmethod(lambda a: _Arr(np.asarray(a, dtype=np.float32)))})()
    s.goal_objects = M.goal_object_names([n for n in scope if not n.startswith("agent.")], M.goal_tokens(GOAL))
    s.state_sha = lambda: "sha"
    s.hold_action = lambda: np.zeros(25, np.float32)
    s.cans = cans
    return s


class _Arr(np.ndarray):
    """The bits of a torch tensor Session.step() uses on its action."""
    def __new__(cls, a): return np.asarray(a).view(cls)
    def flatten(self): return np.asarray(self).reshape(-1).view(_Arr)
    def numel(self): return int(self.size)
    def clone(self): return self.copy()


class SuccessRule(unittest.TestCase):
    def test_goal_objects_are_the_goals_instances_and_categories(self):
        s = stand_in_session()
        self.assertEqual(sorted(s.goal_objects), ["ashcan.n.01_1", "can__of__soda.n.01_1", "can__of__soda.n.01_2", "can__of__soda.n.01_3"])
        self.assertEqual(M.goal_object_names(["half__hard-boiled_egg.n.01_1", "plate.n.04_1", "knife.n.01_1"],
                                             M.goal_tokens([["ontop", "?half__hard-boiled_egg.n.01_1", "?plate.n.04_1"]])),
                         ["half__hard-boiled_egg.n.01_1", "plate.n.04_1"])

    def test_the_first_frame_is_not_success(self):
        s = stand_in_session(goal_at=5)
        for _ in range(5 + M.REST_STEPS - 2):
            self.assertEqual(s.step(np.zeros(25)), (False, False))
        self.assertFalse(s.succeeded); self.assertTrue(s.status()["goal"]); self.assertFalse(s.status()["success"])
        self.assertEqual(s.step(np.zeros(25)), (True, False))          # the window closes: REST_STEPS steps of goal
        self.assertTrue(s.succeeded and s.episode_done)
        self.assertEqual(s.env.episode_steps, 5 + M.REST_STEPS - 1)
        self.assertEqual(s.status()["goal_first_step"], 5)               # the old rule's step, reported for re-grades

    def test_a_held_goal_object_is_not_success(self):
        s = stand_in_session(goal_at=1)
        s.robot._ag_obj_in_hand["left"] = s.cans["can__of__soda.n.01_2"]
        for _ in range(3 * M.REST_STEPS):
            s.step(np.zeros(25))
        st = s.status()
        self.assertTrue(st["goal"]); self.assertFalse(st["success"]); self.assertEqual(st["goal_objects_held"], ["can__of__soda.n.01_2"])
        s.robot._ag_obj_in_hand["left"] = None                         # released: the window starts now
        for _ in range(M.REST_STEPS):
            s.step(np.zeros(25))
        self.assertTrue(s.succeeded)

    def test_a_moving_goal_object_is_not_success(self):
        s = stand_in_session(goal_at=1)
        s.cans["can__of__soda.n.01_1"].v = np.array([0.0, 0.0, -0.3])
        for _ in range(2 * M.REST_STEPS):
            s.step(np.zeros(25))
        self.assertFalse(s.succeeded); self.assertEqual(s.status()["goal_objects_moving"], ["can__of__soda.n.01_1"])
        s.cans["can__of__soda.n.01_1"].v = np.array([0.0, 0.0, 0.01])   # below REST_SPEED_M_S: at rest
        for _ in range(M.REST_STEPS):
            s.step(np.zeros(25))
        self.assertTrue(s.succeeded)

    def test_a_held_object_outside_the_goal_does_not_matter(self):
        s = stand_in_session(goal_at=1)
        s.robot._ag_obj_in_hand["right"] = _Obj("knife")
        for _ in range(M.REST_STEPS):
            s.step(np.zeros(25))
        self.assertTrue(s.succeeded)

    def test_settle_closes_a_window_the_actions_left_open(self):
        s = stand_in_session(goal_at=10)
        st = s.replay(np.zeros((12, 25), np.float32))                  # the goal holds for the last 3 rows only
        self.assertTrue(st["success"]); self.assertEqual(st["settle_steps"], M.REST_STEPS - 3)
        s = stand_in_session(goal_at=None)
        st = s.replay(np.zeros((12, 25), np.float32))                  # no goal: the whole settle window, then not success
        self.assertFalse(st["success"]); self.assertEqual(st["settle_steps"], M.SETTLE_STEPS)
        self.assertEqual(stand_in_session().settle(), 0)                        # nothing stepped: nothing to settle

    def test_status_leaves_the_object_state_caches_as_they_were(self):
        s = stand_in_session(goal_at=None)
        for _ in range(4):
            s.step(np.zeros(25))
        can = s.cans["can__of__soda.n.01_1"].states["Inside"]
        before = (dict(can._cache), dict(can._changed), can._last_t_updated)
        st = s.status()
        self.assertEqual(st["q_score"], 0.5)                           # the metric ran and filled the caches ...
        self.assertEqual((can._cache, can._changed, can._last_t_updated), before)   # ... which are restored

    def test_breakdown_ends_the_episode(self):
        s = stand_in_session(goal_at=None)
        s.step(np.zeros(25))
        s.robot.p = np.array([0.0, 0.0, 1.7e16])
        self.assertEqual(s.step(np.zeros(25)), (True, False))
        st = s.status()
        self.assertTrue(st["breakdown"] and s.episode_done); self.assertFalse(st["success"])
        self.assertTrue(st["end_reason"].startswith(M.BREAKDOWN_REASON))
        s = stand_in_session(goal_at=None)
        s.robot.v = np.array([np.nan, 0.0, 0.0])
        self.assertEqual(s.step(np.zeros(25)), (True, False)); self.assertIn("not finite", s.breakdown)
        s = stand_in_session(goal_at=None)                                      # a goal object far away, checked every 30 steps
        s.cans["can__of__soda.n.01_3"].p = np.array([0.0, 0.0, -2e4])
        n = 0
        while not s.episode_done:
            s.step(np.zeros(25)); n += 1
        self.assertEqual(n, M.BREAKDOWN_OBJECT_EVERY); self.assertIn("can__of__soda.n.01_3", s.breakdown)

    def test_rest_watch(self):
        w = M.RestWatch(3)
        for g, r, st in ((1, 1, 1), (1, 0, 1), (1, 1, 1), (1, 1, 1)):
            self.assertFalse(w.update(bool(g), bool(r), bool(st)))
        self.assertTrue(w.update(True, True, True)); self.assertEqual(w.done_step, 5)
        self.assertTrue(w.update(False, True, True))                   # latched until reset()
        w.reset(); self.assertFalse(w.done)



class StableHashes(unittest.TestCase):
    """(2026-10-14, item 16) The tooling's stable hashes: a set of simulator objects iterates in the same order whatever
    their memory addresses, so a replay updates object states and applies transition rules in the live run's order."""

    def test_set_order_follows_names_not_addresses(self):
        import types
        mods = {"omnigibson": types.ModuleType("omnigibson"), "omnigibson.prims": types.ModuleType("omnigibson.prims"),
                "omnigibson.prims.prim_base": types.ModuleType("omnigibson.prims.prim_base"),
                "omnigibson.systems": types.ModuleType("omnigibson.systems"),
                "omnigibson.systems.system_base": types.ModuleType("omnigibson.systems.system_base"),
                "omnigibson.transition_rules": types.ModuleType("omnigibson.transition_rules")}

        class BasePrim:
            def __init__(self, name): self._name = name

        class BaseSystem(BasePrim):
            pass

        class BaseTransitionRule:
            pass
        mods["omnigibson.prims.prim_base"].BasePrim = BasePrim
        mods["omnigibson.systems.system_base"].BaseSystem = BaseSystem
        mods["omnigibson.transition_rules"].BaseTransitionRule = BaseTransitionRule
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            M._stable_hashes()
            names = [f"firewood_{i}" for i in range(40)] + ["newspaper", "cigar_lighter", "fireplace"]
            orders = []
            for pad in (0, 1, 7, 333):                    # different allocation histories: different addresses
                junk = [object() for _ in range(pad)]
                objs = [BasePrim(n) for n in names]
                orders.append([o._name for o in set(objs)])
                del junk
            self.assertTrue(all(o == orders[0] for o in orders), orders)
            a, b = BasePrim("x"), BasePrim("x")
            self.assertNotEqual(a, b)                    # equality stays identity
            self.assertEqual(len({a, b}), 2)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

if __name__ == "__main__":
    unittest.main()
