#!/usr/bin/env python3
"""The tooling's physical-validity policy (rcb_topogym.py, tooling v15; before it the 2026-10-03 rules R1-R4): persistence
counters, thresholds, the forcing evidence, the breakdown attribution, the review evidence and the guards on synthetic
contact / IPC / particle states and fake robots. No Genesis, no physics: the lab replays in
docs/rcb/benchmarks/topogym.md are the physical evidence."""
import ast
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "harbor_templates/topogym/common")]
import rcb_topogym as M  # noqa: E402
from topogym.evaluation.task_metrics import ipc_integrity  # noqa: E402,F401 -- patched by name, like the families
from topogym.tasks.base import RigidTaskDefinition, TaskDefinition  # noqa: E402

DT = .0025
WINDOW = M.rule_window_ticks(DT, M.CONTACT_RULE["window_s"])
EVENT = M.rule_window_ticks(DT, M.FORCING["event_s"])                  # a forcing event's length (ticks)
ATTRIBUTION = M.rule_window_ticks(DT, M.FORCING["attribution_s"])


class ContactTask(RigidTaskDefinition):
    task_id = "rules_regression"

    def evaluate_state(self, state):
        _, _, quiet, failure = self.rigid_measurements(state)
        return bool(quiet and not failure), failure, {}


class RopeTask(TaskDefinition):
    task_id = "rope_rules_regression"
    physics_model = "fem_ipc"
    attachments = ()

    def evaluate_state(self, state):
        intact = ipc_integrity(state, ("rope",), self.attachments)
        return intact is True, "rope_volume_invalid" if intact is False else None, dict(
            evaluation_status="available" if intact is not None else "unavailable")


def links(*pairs):
    return [SimpleNamespace(idx=i, name=n, is_fixed=False, parent_idx=-1, geoms=()) for i, n in pairs]


CAPS = (10., 20.)           # the fake arm's two drive caps (N m)


def fake_session(task, entities, *, arm=False, effort=None):
    """A Session's surface for _install_rules: no robot, or (arm=True) one arm "arm" with two joints (caps CAPS), fingers
    10 / 11 and a base link 12; effort[0] is its drive effort row (the robot's efforts())."""
    sinks = []
    env = SimpleNamespace(_task=task, config=SimpleNamespace(physics_dt_s=DT), add_lifecycle_sink=sinks.append,
                          _robot=SimpleNamespace(description=SimpleNamespace(robot_id="fake", groups=())),
                          _world=SimpleNamespace(entities=entities))
    if arm:
        group = SimpleNamespace(arm_joints=("arm/j1", "arm/j2"), grasp=SimpleNamespace(
            finger_links=("finger_a", "finger_b"), contact_root_link=None))
        robot = SimpleNamespace(groups={"arm": group}, arms=["arm"], drive_force={"arm": CAPS + (5.,)},
                                entity=entities["robot"], arm_slice={"arm": slice(0, 2)},
                                efforts=lambda: np.asarray(effort[0], dtype=float))
    else:
        robot = SimpleNamespace(groups={}, arms=[], drive_force={}, entity=SimpleNamespace(links=[]))
    session = SimpleNamespace(env=env, robot=robot, table_z=lambda: None, n_steps=0, sinks=sinks, instability=None)

    def on_instability(info):
        if session.instability is None:
            session.instability = info
    session._on_instability = on_instability
    session.rules = M._install_rules(session)
    return session


def contact_state(step, depth, *, held=False, a=1, b=2, force=120., extra=(), finite=True):
    """One tick: piece (link 1) touches `b` (other = 2, a finger = 10) at `depth` metres with `force` N; held = both fingers
    on the piece (the finger contact at `depth`); extra = more (link_a, link_b, depth, force) contacts. The bodies move
    slowly (1 cm/s: never quiet, so ContactTask never succeeds)."""
    rows = [(a, b, depth, force)] if not held else [(10, 1, depth, force), (11, 1, 0., force)]
    rows += list(extra)
    bodies = {n: dict(position_m=[0., 0., .1] if finite else [float("nan")] * 3, quaternion_wxyz=[1., 0., 0., 0.],
                      linear_velocity_m_s=[.01, 0., 0.], angular_velocity_rad_s=[0.] * 3) for n in ("piece", "other")}
    return dict(physics_step=step, bodies=bodies, grasp=None, contacts=dict(
        link_a=np.array([r[0] for r in rows]), link_b=np.array([r[1] for r in rows]),
        penetration=np.array([r[2] for r in rows], dtype=float),
        force=np.array([[0., 0., r[3]] for r in rows], dtype=float)))


def rope_state(step, ratio, *, valid=True, residual=0.):
    return dict(physics_step=step, ipc=dict(native_valid=valid, volume_ratio={"rope": dict(minimum=ratio, maximum=1.)},
                                            attachment_residual_m={"stitch": residual}))


class PureRules(unittest.TestCase):
    def test_window_is_a_quarter_second_of_ticks(self):
        self.assertEqual(WINDOW, 100)
        self.assertEqual(M.rule_window_ticks(.025, .25), 10)

    def test_contact_thresholds_are_strict_and_counters_reset(self):
        counts, verdict = M.contact_rule_tick({}, .001, .002, WINDOW)        # exactly at the sustained limits
        self.assertEqual((counts, verdict), ({}, None))
        counts = {}
        for _ in range(WINDOW - 1):
            counts, verdict = M.contact_rule_tick(counts, .0015, 0., WINDOW)
            self.assertIsNone(verdict)
        counts, verdict = M.contact_rule_tick(counts, .0015, 0., WINDOW)
        self.assertEqual(verdict, "sustained")
        counts, verdict = M.contact_rule_tick({"over": 99}, .0009, 0., WINDOW)
        self.assertEqual((counts, verdict), ({}, None))                       # a break restarts the window
        self.assertEqual(M.contact_rule_tick({}, .0031, 0., WINDOW)[1], "deep")
        self.assertEqual(M.contact_rule_tick({}, .003, 0., WINDOW)[1], None)
        self.assertEqual(M.contact_rule_tick({}, 0., .0041, WINDOW)[1], "held_deep")
        self.assertEqual(M.contact_rule_tick({"held_over": 99}, 0., .0025, WINDOW), ({"held_over": 100}, "held_sustained"))

    def test_soft_counters_per_entity(self):
        counts = M.soft_rule_tick({}, {"rope": -.1, "cord": .5}, {"a": .003, "b": .001})
        self.assertEqual(counts, {"inverted": {"rope": 1}, "stretched": {"a": 1}})
        counts = M.soft_rule_tick(counts, {"rope": 0., "cord": .5}, {"a": .0005})
        self.assertEqual(counts, {"inverted": {"rope": 2}})
        self.assertEqual(M.soft_rule_tick(counts, {"rope": .2}, {}), {})
        self.assertEqual(M.soft_rule_tick({}, {"rope": float("nan")}, {"a": float("inf")}), {})

    def test_history_validation(self):
        M._validate_rules_history({"contact": {"over": 3}, "soft": {"inverted": {"rope": 2}}, "forced": 7})
        for bad in ({"contact": {"over": 0}}, {"contact": {"over": 1.5}}, {"other": {}}, {"soft": {"inverted": 3}},
                    {"contact": {"x": 1}}, [], {"soft": []}, {"contact": None}, {"stop": {"left": 4}},
                    {"forced": 0}, {"forced": 1.5}, {"forced": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                M._validate_rules_history(bad)

    def test_policy_numbers(self):
        self.assertEqual((EVENT, ATTRIBUTION), (200, 100))
        self.assertGreater(M.BREAKDOWN_PENETRATION_M, M.CONTACT_RULE["held_deep_m"])
        self.assertTrue(0. < M.FORCING["near_cap"] <= 1. and M.FORCING["contact_n"] > 0.)
        self.assertFalse(hasattr(M, "PROTECTIVE_STOP"))           # forcing is evidence only (the user, 2026-10-04)


def rigid_entities():
    robot = SimpleNamespace(links=links((10, "finger_a"), (11, "finger_b"), (12, "base")))
    return {"piece": SimpleNamespace(links=links((1, "piece")), n_dofs=6), "other": SimpleNamespace(links=links((2, "other")), n_dofs=0),
            "robot": robot}


class RigidContactEvidence(unittest.TestCase):
    """Layer 4: task-contact depth is evidence (review events), never an episode end; Layer 3: deeper than
    BREAKDOWN_PENETRATION_M, or a non-finite state, is a simulator breakdown."""

    def setUp(self, arm=False):
        entities = rigid_entities()
        self.task = ContactTask()
        self.task.local_vertices = {"piece": np.zeros((1, 3)), "other": np.zeros((1, 3))}
        self.task.bind(entities)
        self.task._finger_links_by_hand = {"arm": (10, 11)}
        self.task.initialize(contact_state(0, 0.))
        self.effort = [np.zeros(2)]
        self.session = fake_session(self.task, entities, arm=arm, effort=self.effort)
        self.step = 0

    def tick(self, depth, **kw):
        self.step += 1
        return self.task.update(contact_state(self.step, depth, **kw), DT)

    def test_deep_and_sustained_contacts_never_end_the_episode(self):
        for depth in (.0034, .0099, .0029):
            self.assertFalse(self.tick(depth).terminated)
        for _ in range(3 * WINDOW):
            self.assertFalse(self.tick(.0015).terminated)
        self.assertFalse(self.tick(.0045, held=True).terminated)

    def test_review_events_merge_consecutive_ticks(self):
        self.assertIsNone(self.session.monitor.review())
        self.tick(.0034); self.tick(.0041); self.tick(.0005)              # one deep event over two ticks
        for _ in range(WINDOW + 4):
            self.tick(.0015)                                               # then a sustained one (from the window on)
        review = self.session.monitor.review()
        self.assertEqual((review["pending"], review["count"], review["max_depth_mm"]), (True, 2, 4.1))
        deep, sustained = review["events"]
        self.assertEqual((deep["kind"], deep["ticks"], deep["depth_mm"], deep["force_n"]), ("deep", 2, 4.1, 120.))
        self.assertEqual(deep["bodies"], ["the piece", "the other"])
        self.assertEqual((sustained["kind"], sustained["ticks"], sustained["physics_step"]), ("sustained", 5, 3 + WINDOW))
        for sink in self.session.sinks:
            sink({"kind": "rewind"})
        self.assertIsNone(self.session.monitor.review())                    # the episode's own evidence

    def test_held_finger_review_limits(self):
        self.tick(.0039, held=True)
        self.assertIsNone(self.session.monitor.review())
        self.tick(.0041, held=True)
        self.assertEqual(self.session.monitor.review()["events"][0]["kind"], "held_deep")

    def test_counters_follow_rewind_and_vanish_when_zero(self):
        for _ in range(50):
            self.tick(.0015)
        saved = self.task.get_state()
        for _ in range(40):
            self.tick(.0015)
        self.task.set_state(saved)                        # what Env._restore does on a rewind
        self.assertEqual(self.task.task_state, {"rcb_rules": {"contact": {"over": 50}}})
        self.setUp()
        self.tick(.0005)
        self.assertEqual(self.task.task_state, {})          # no counter: the history is the family's own

    def test_safety_monitor_reports_against_limits(self):
        for _ in range(10):
            self.tick(.0015)
        report = self.session.monitor.read()
        self.assertEqual(report["task_contact_mm"]["max"], 1.5)
        self.assertEqual(report["task_contact_mm"]["review_above"], 3.0)
        self.assertEqual(report["task_contact_mm"]["review_if_above_for_s"], [1.0, .25])
        self.assertEqual(report["task_contact_mm"]["breakdown_above"], 10.0)
        self.assertAlmostEqual(report["task_contact_mm"]["longest_above_s"], 10 * DT)
        self.assertEqual(self.session.monitor.read()["task_contact_mm"]["max"], 0.)    # since the previous read
        self.assertEqual(self.session.monitor.read(episode=True)["task_contact_mm"]["max"], 1.5)
        for sink in self.session.sinks:
            sink({"kind": "rewind"})
        self.assertEqual(self.session.monitor.read(episode=True)["task_contact_mm"]["max"], 0.)

    def test_extreme_penetration_without_forcing_is_a_simulator_instability(self):
        result = self.tick(.0101)
        self.assertTrue(result.terminated)
        self.assertEqual(result.reason, M.SIMULATOR_INSTABILITY)
        ev = self.session.instability
        self.assertEqual((ev["kind"], ev["depth_mm"], ev["bodies"], ev["physics_step"]),
                         ("extreme_penetration", 10.1, ["the piece", "the other"], 1))
        self.assertIn("interpenetrated 10.1 mm", M.breakdown_words(ev))
        self.setUp()
        self.assertFalse(self.tick(.0099).terminated)

    def test_a_non_finite_state_is_a_simulator_instability(self):
        result = self.tick(0., finite=False)
        self.assertEqual(result.reason, M.SIMULATOR_INSTABILITY)
        self.assertEqual(self.session.instability["kind"], "non_finite_state")

    def test_malformed_history_is_rejected(self):
        with self.assertRaises(ValueError):
            self.task.validate_task_state({"rcb_rules": {"contact": {"over": -1}}})


class Forcing(RigidContactEvidence):
    """Layer 4: an arm drive at FORCING["near_cap"] of its cap or more while the arm or a part it holds presses on something
    with FORCING["contact_n"] or more is forcing; a run of it for FORCING["event_s"] is a forcing event in the evidence. It
    never ends the episode; within FORCING["attribution_s"] after it a breakdown is the agent's (forced_breakdown)."""
    FORCE = M.FORCING["contact_n"] + 5.

    def setUp(self):
        super().setUp(arm=True)

    def press(self, *, frac=1., force=None, depth=0., held=False):
        """One tick: the finger (10) presses on the other body (2) with `force`, the arm's first drive at `frac` of its cap;
        held = both fingers on the piece (1), which presses on the other body."""
        self.effort[0] = np.array([frac * CAPS[0], 0.])
        force = self.FORCE if force is None else force
        if held:
            return self.tick(0., held=True, force=100., extra=[(1, 2, depth, force)])
        return self.tick(depth, a=10, b=2, force=force)

    def test_forcing_is_recorded_and_never_ends_the_episode(self):
        self.assertIsNone(self.session.monitor.forcing())
        for _ in range(3 * EVENT):
            self.assertFalse(self.press().terminated)
        forcing = self.session.monitor.forcing()
        self.assertEqual((forcing["count"], forcing["longest_s"]), (1, 3 * EVENT * DT))
        e = forcing["events"][0]
        self.assertEqual((e["arm"], e["joint"], e["fraction"], e["cap_nm"], e["ticks"], e["max_force_n"]),
                         ("arm", "j1", 1., 10., 3 * EVENT, self.FORCE))
        self.assertEqual((e["pressing"], e["on"], e["physics_step"]), ("the gripper's finger", "the other", EVENT))
        report = self.session.monitor.read(episode=True)["forcing"]
        self.assertEqual((report["events"], report["longest_forcing_s"], report["max_drive_fraction_while_pressing"]),
                         (1, 3 * EVENT * DT, 1.))
        self.assertNotIn("stop", (self.task.task_state.get("rcb_rules") or {}))

    def test_below_the_cap_fraction_or_the_contact_force_is_no_forcing(self):
        for _ in range(2 * EVENT):
            self.assertFalse(self.press(frac=M.FORCING["near_cap"] - .01).terminated)
            self.assertFalse(self.press(force=M.FORCING["contact_n"] - 1.).terminated)
        self.effort[0] = np.array([CAPS[0], CAPS[1]])                     # at the cap in free air
        for _ in range(2 * EVENT):
            self.assertFalse(self.tick(0., a=1, b=2, force=500.).terminated)    # the piece alone on the other body
        self.assertIsNone(self.session.monitor.forcing())
        self.assertEqual(self.session.monitor.read(episode=True)["forcing"]["longest_forcing_s"], 0.)

    def test_a_break_ends_an_event_and_a_short_run_records_none(self):
        for _ in range(EVENT - 1):
            self.press()
        self.press(frac=.1)
        self.assertIsNone(self.session.monitor.forcing())                  # 199 ticks: no event
        for _ in range(EVENT):
            self.press()
        self.press(frac=.1)
        for _ in range(EVENT + 5):
            self.press()
        forcing = self.session.monitor.forcing()
        self.assertEqual((forcing["count"], [e["ticks"] for e in forcing["events"]]), (2, [EVENT, EVENT + 5]))

    def test_a_held_piece_pressing_counts_its_own_grip_does_not(self):
        self.effort[0] = np.array([CAPS[0], 0.])
        for _ in range(2 * EVENT):                                          # gripping hard, nothing else touched
            self.assertFalse(self.tick(0., held=True, force=500.).terminated)
        self.assertIsNone(self.session.monitor.forcing())
        for _ in range(EVENT):
            self.assertFalse(self.press(held=True).terminated)
        e = self.session.monitor.forcing()["events"][0]
        self.assertEqual((e["pressing"], e["on"]), ("the piece it holds", "the other"))

    def test_a_breakdown_within_the_window_after_forcing_is_the_agents(self):
        for _ in range(10):
            self.press()
        for _ in range(ATTRIBUTION - 1):
            self.assertFalse(self.press(frac=0.).terminated)                   # forcing stopped 99 ticks ago
        result = self.tick(.012)
        self.assertTrue(result.reason.startswith("forced_breakdown: the simulation broke down (the piece and the other "
                                                 "interpenetrated 12.0 mm"), result.reason)
        self.assertIn("right after forcing: the arm's j1 drive was at 100 %", result.reason)
        self.assertIn("(0.25 s before)", result.reason)
        self.assertIsNone(self.session.instability)
        self.assertIsNone(self.session.monitor.forcing())                  # 10 ticks: forcing, but no event

    def test_a_breakdown_later_than_the_window_is_a_simulator_instability(self):
        for _ in range(10):
            self.press()
        for _ in range(ATTRIBUTION):
            self.press(frac=0.)
        self.assertEqual(self.tick(.012).reason, M.SIMULATOR_INSTABILITY)

    def test_a_breakdown_while_forcing_and_a_forced_particle_blow_up(self):
        self.assertTrue(self.press(depth=.011).reason.startswith("forced_breakdown:"))
        self.setUp()
        M._guard_particle_speeds(self.task, self.session._on_instability)      # the Session installs it before the rules
        self.press()
        state = contact_state(self.step + 1, 0.)
        state["particles"] = {"blanket": dict(velocity_m_s=np.array([[0., 0., 30.]]), position_m=np.zeros((1, 3)))}
        result = self.task.update(state, DT)
        self.assertTrue(result.reason.startswith("forced_breakdown: the simulation broke down (a blanket particle moved at "
                                                 "30 m/s (limit 20 m/s))"), result.reason)
        self.setUp()
        M._guard_particle_speeds(self.task, self.session._on_instability)
        state = contact_state(1, 0.)
        state["particles"] = {"blanket": dict(velocity_m_s=np.array([[0., 0., 30.]]), position_m=np.zeros((1, 3)))}
        self.assertEqual(self.task.update(state, DT).reason, M.SIMULATOR_INSTABILITY)
        self.assertEqual(self.session.instability["kind"], "particle_speed")

    def test_the_forcing_memory_follows_rewind(self):
        for _ in range(5):
            self.press()
        saved = self.task.get_state()
        self.assertEqual(saved["task_state"]["rcb_rules"], {"forced": ATTRIBUTION})
        for _ in range(ATTRIBUTION + 10):
            self.press(frac=0.)                                             # the memory runs out
        self.assertNotIn("rcb_rules", self.task.task_state)
        self.task.set_state(saved)                                          # a rewind restores it
        self.step = 5
        self.assertTrue(self.tick(.012).reason.startswith("forced_breakdown:"))


class SoftIntegrityRule(unittest.TestCase):
    def setUp(self):
        self.task = RopeTask()
        self.task.initialize(rope_state(0, .9))
        self.session = fake_session(self.task, {"rope": SimpleNamespace(links=())})
        self.step = 0

    def tick(self, ratio, **kw):
        self.step += 1
        return self.task.update(rope_state(self.step, ratio, **kw), DT)

    def test_transient_inversion_is_unavailable_then_fails_after_the_window(self):
        for _ in range(WINDOW - 1):
            result = self.tick(-.05)
            self.assertFalse(result.terminated)
            self.assertEqual(result.evaluation_status, "unavailable")
        result = self.tick(-.05)
        self.assertTrue(result.terminated)
        self.assertTrue(result.reason.startswith("rope_volume_invalid: the rope stayed crushed for 0.25 s"), result.reason)

    def test_recovery_restarts_the_window(self):
        for _ in range(WINDOW - 1):
            self.tick(0.)
        self.assertFalse(self.tick(.3).terminated)
        self.assertNotIn("rcb_rules", self.task.task_state)
        for _ in range(WINDOW - 1):
            self.assertFalse(self.tick(-.2).terminated)

    def test_native_invalid_state_is_a_simulator_breakdown(self):
        result = self.tick(.9, valid=False)
        self.assertTrue(result.terminated)
        self.assertEqual(result.reason, M.SIMULATOR_INSTABILITY)
        self.assertEqual(self.session.instability["kind"], "soft_solver_invalid")

    def test_attachment_stretch_persistence(self):
        self.task.attachments = ("stitch",)
        for _ in range(WINDOW - 1):
            self.assertFalse(self.tick(.9, residual=.0031).terminated)
        result = self.tick(.9, residual=.0031)
        self.assertTrue(result.terminated)
        self.assertIn("stayed stretched by 3.1 mm (limit 2 mm) for 0.25 s", result.reason)

    def test_the_reason_names_the_persisted_cause(self):
        self.task.attachments = ("stitch",)
        for k in range(WINDOW):
            result = self.tick(-.05 if k >= WINDOW - 3 else .9, residual=.0031)     # a late, brief inversion
        self.assertIn("attachment stitch stayed stretched", result.reason)

    def test_outside_an_evaluation_topogym_verdict_is_unchanged(self):
        self.assertIs(ipc_integrity(rope_state(1, -.1), ("rope",)), False)     # no R2 evaluation in progress
        self.assertIs(ipc_integrity(rope_state(1, .5), ("rope",)), True)


class TableGuard(unittest.TestCase):
    def guard(self):
        g = object.__new__(M._TableGuard)
        events = []
        g.s = SimpleNamespace(robot=SimpleNamespace(arm_slice={"arm": slice(0, 2)}, grip_index={"arm": 2}), n_steps=0,
                              last_guard=None, monitor=SimpleNamespace(guard=events.append))
        g.table, g.limit, g.points, g.count, g.events = 0., M.TABLE_GUARD_MARGIN_M, {"arm": [("tip", None)]}, 0, []
        g.calls = 0

        def lowest(row):         # the lowest z falls 0.1 m per rad of joint 1 and 0.2 m per m of closing (a Robotiq)
            g.calls += 1
            row = np.asarray(row)
            return {"arm": .1 - .1 * float(row[1]) - .2 * (.05 - float(row[2]))}
        g.lowest = lowest
        return g, events

    def test_stops_on_the_commanded_path_and_replays_unchanged(self):
        g, events = self.guard()
        previous, target = np.array([.3, .5, .05]), np.array([.6, 1.5, .02], dtype=np.float32).astype(np.float64)
        out = g.apply(target, previous)
        self.assertAlmostEqual(g.lowest(out)["arm"], M.TABLE_GUARD_MARGIN_M, delta=1e-5)
        f = (out[1] - previous[1]) / (target[1] - previous[1])
        np.testing.assert_allclose(out[:2], previous[:2] + (target[:2] - previous[:2]) * f, atol=1e-6)   # the arm path
        self.assertEqual(out[2], target[2])                                              # the gripper command as given
        np.testing.assert_array_equal(out, out.astype(np.float32).astype(np.float64))     # a float32 row, as recorded
        self.assertEqual(len(events), 1)
        self.assertIs(g.apply(out, previous), out)                                       # the replayed row: unchanged
        self.assertIsNone(g.s.last_guard)

    def test_closing_alone_is_never_stopped(self):
        g, _ = self.guard()
        previous = np.array([0., .9, .05])                                               # 10 mm above the tabletop
        closing = np.array([0., .9, 0.])                                                 # closing alone reaches 0 mm
        self.assertIs(g.apply(closing, previous), closing)

    def test_below_may_rise_but_not_sink_and_idle_arms_skip_kinematics(self):
        g, _ = self.guard()
        below = np.array([0., 1.2, .05])                                                 # 2 cm below the tabletop
        up = np.array([0., 1.1, .05])
        self.assertIs(g.apply(up, below), up)
        down = g.apply(np.array([0., 1.3, .05]), below)
        self.assertAlmostEqual(down[1], 1.2, delta=1e-4)                                 # held at its current height
        calls, same = g.calls, below.copy()
        self.assertIs(g.apply(same, below), same)                                         # nothing moved: no kinematics
        self.assertEqual(g.calls, calls)


class ChainKinematics(unittest.TestCase):
    """_ChainFK against a hand-computed chain: a fixed root placed at (0.1, 0, 1), a revolute link about z with its
    joint anchor 0.2 m along the link's x, and a prismatic link along x. (On lab it matched Genesis' own FK to 7e-16 m
    for ALOHA and Panda + Robotiq, 200 random poses each.)"""

    def chain(self):
        import types
        if "genesis" not in sys.modules:
            try:
                import genesis  # noqa: F401
            except ImportError:
                fake = types.ModuleType("genesis")
                fake.JOINT_TYPE = SimpleNamespace(FIXED=0, REVOLUTE=1, PRISMATIC=2)
                sys.modules["genesis"] = fake
        import genesis as gs
        F = lambda a: SimpleNamespace(to_numpy=lambda a=np.asarray(a, dtype=float): a.copy())  # noqa: E731
        info = SimpleNamespace(pos=F([[0., 0., 0.], [.3, 0., 0.], [.1, 0., 0.]]),
                               quat=F([[1., 0., 0., 0.], [1., 0., 0., 0.], [1., 0., 0., 0.]]),
                               parent_idx=F([-1, 0, 1]), is_fixed=F([1, 0, 0]),
                               joint_start=F([0, 1, 2]), joint_end=F([1, 2, 3]))
        joints = SimpleNamespace(type=F([int(gs.JOINT_TYPE.FIXED), int(gs.JOINT_TYPE.REVOLUTE), int(gs.JOINT_TYPE.PRISMATIC)]),
                                 q_start=F([0, 0, 1]), dof_start=F([0, 0, 1]), pos=F([[0., 0., 0.], [.2, 0., 0.], [0., 0., 0.]]))
        dofs = SimpleNamespace(motion_ang=F([[0., 0., 1.], [0., 0., 0.]]), motion_vel=F([[0., 0., 0.], [1., 0., 0.]]))
        solver = SimpleNamespace(links_info=info, joints_info=joints, dofs_info=dofs,
                                 _rigid_global_info=SimpleNamespace(qpos0=F([.1, 0.])),
                                 links_state=SimpleNamespace(pos=F([[.1, 0., 1.], [0., 0., 0.], [0., 0., 0.]]),
                                                             quat=F([[1., 0., 0., 0.]] * 3)))
        entity = SimpleNamespace(_solver=solver, link_start=0, link_end=3, q_start=0,
                                 links=[SimpleNamespace(idx=i, name=n) for i, n in enumerate(("root", "turn", "slide"))])
        return M._ChainFK(entity)

    def test_matches_the_hand_computed_chain(self):
        fk = self.chain()
        theta, d = .7, .05
        T = fk(np.array([.1 + theta, d]))                  # q measured from qpos0, as Genesis does
        R = np.array([[math.cos(theta), -math.sin(theta), 0.], [math.sin(theta), math.cos(theta), 0.], [0., 0., 1.]])
        anchor = np.array([.1, 0., 1.]) + np.array([.3, 0., 0.]) + np.array([.2, 0., 0.])
        turn = anchor - R @ np.array([.2, 0., 0.])          # the link rotates about its joint anchor
        np.testing.assert_allclose(T["root"][:3, 3], [.1, 0., 1.])
        np.testing.assert_allclose(T["turn"][:3, 3], turn, atol=1e-12)
        np.testing.assert_allclose(T["turn"][:3, :3], R, atol=1e-12)
        np.testing.assert_allclose(T["slide"][:3, 3], turn + R @ np.array([.1 + d, 0., 0.]), atol=1e-12)


def server_functions(names, namespace):
    """The real service functions without the server's module-level GPU start (as test-post-merge-repairs.py)."""
    path = ROOT / "harbor_templates/topogym/limited/environment/sim/server.py"
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return [namespace[n] for n in names]


class ServiceGuards(unittest.TestCase):
    def namespace(self, ik=None):
        steps = []
        S = SimpleNamespace(cmd=np.zeros(3), last_guard=None)
        S.hold_action = lambda: S.cmd.copy()

        def ctrl_step(a, rec, *, row_start=False, notes=None, ri=None):
            steps.append((np.asarray(a, dtype=np.float64).copy(), row_start))
            S.cmd = np.asarray(a, dtype=np.float32).astype(np.float64)
            return False
        ns = dict(np=np, math=math, S=S, ctrl_step=ctrl_step, ARMS=["arm"], ARM={"arm": (slice(0, 2), 2)}, N=3,
                  LAYOUT=["j1", "j2", "arm_gripper"], CTRL_HZ=40., M=M, LIM_ARR=np.array([[-3., 3.], [-3., 3.], [0., .08]]),
                  clip_joint_row=lambda row, clipped, ri: row,
                  L=SimpleNamespace(Recorder=object, control_periods=lambda dt, hz: int(round(dt * hz))))
        if ik is not None:
            S.ik = ik
            S.ik_jump = lambda arm, q: (float(np.max(np.abs(np.asarray(q) - S.cmd[:2]))), "j1")
        return ns, steps, S

    def test_compliant_rows_are_unchanged(self):
        ns, steps, _ = self.namespace()
        run, = server_functions(["run_joint_position"], ns)
        clipped = []
        run(np.array([[.12, -.08, .05]]), .1, "linear", None, clipped)
        self.assertEqual(len(steps), 4)
        for k, (a, _) in enumerate(steps, 1):
            np.testing.assert_array_equal(a[:2], np.array([.12, -.08]) * (k / 4))        # the old interpolation, bit for bit
        self.assertEqual(clipped, [])

    def test_fast_rows_take_the_steps_they_need(self):
        ns, steps, S = self.namespace()
        run, = server_functions(["run_joint_position"], ns)
        clipped = []
        run(np.array([[.2, 0., .05], [.2, 0., 0.]]), 1 / 40, "linear", None, clipped)
        moves = [a[0] for a, _ in steps[:5]]
        np.testing.assert_allclose(np.diff([0.] + moves), .04, atol=1e-6)
        self.assertEqual(steps[0][0][2], .05)                                             # the gripper switches at the row
        self.assertEqual([r for _, r in steps].count(True), 2)                             # two rows started
        self.assertAlmostEqual(S.cmd[0], .2, places=6)
        self.assertEqual(len(clipped), 1)
        self.assertIn("this row took 5 control steps", clipped[0]["reason"])
        ns, steps, _ = self.namespace()
        run, = server_functions(["run_joint_position"], ns)
        clipped = []
        run(np.array([[.1, 0., .05]]), .1, "hold", None, clipped)
        np.testing.assert_allclose([a[0] for a, _ in steps], [.04, .08, .1, .1], atol=1e-6)
        self.assertIn("at once", clipped[0]["reason"])

    def test_ik_jumps_are_refused(self):
        ns, steps, _ = self.namespace(ik=lambda arm, pos, quat: (np.array([.8, 0.]), 0., 0.))
        run, = server_functions(["run_ee_pose"], ns)
        plan, clipped = [], []
        run(np.array([[.3, 0., 1., 1., 0., 0., 0., .05]]), None, plan, clipped)
        self.assertTrue(plan[0]["arm"].startswith("refused: the IK solution is 0.80 rad from the current joints on j1"))
        self.assertTrue(all(np.array_equal(a[:2], [0., 0.]) for a, _ in steps))           # the arm holds
        ns, steps, S = self.namespace(ik=lambda arm, pos, quat: (np.array([.3, 0.]), 0., 0.))
        run, = server_functions(["run_ee_pose"], ns)
        plan = []
        run(np.array([[.3, 0., 1., 1., 0., 0., 0., .05]]), None, plan, [])
        self.assertEqual(plan[0]["arm"], "Success")
        self.assertAlmostEqual(S.cmd[0], .3, places=6)


class InstructionText(unittest.TestCase):
    def test_rule_numbers_match_the_tooling(self):
        import topogym_rules as R
        self.assertEqual(R.CONTACT_RULE, M.CONTACT_RULE)
        self.assertEqual(R.SOFT_RULE, M.SOFT_RULE)
        self.assertEqual(R.FORCING, M.FORCING)
        self.assertEqual(R.BREAKDOWN_PENETRATION_M, M.BREAKDOWN_PENETRATION_M)
        self.assertEqual(R.PARTICLE_SPEED_LIMIT_M_S, M.PARTICLE_SPEED_LIMIT_M_S)
        self.assertEqual(R.TABLE_GUARD_MARGIN_M, M.TABLE_GUARD_MARGIN_M)
        self.assertEqual(R.table_guard_words(), M.table_guard_words())
        self.assertEqual(R.FAIL_STRINGS["all"], [f'"{M.FORCED_BREAKDOWN}: <what>"'])
        self.assertFalse(any("forced" in s and "breakdown" not in s for v in R.FAIL_STRINGS.values() for s in v))
        import json
        for fam in ("interlocked_claws", "knot_untying", "blanket_flatten"):
            slug = fam.replace("_", "-")
            inst = json.loads((ROOT / f"tasks/topogym-{slug}-easy-i00-privileged/environment/instance.json").read_text())
            for limited in (False, True):
                text = " ".join(R.grader_details(fam, inst, limited=limited))
                self.assertNotIn("protective", text)
                self.assertIn("Forcing is recorded, not judged", text)
                self.assertIn("does not end the episode", text)
        text = (ROOT / "scripts/topogym_mk_limited.py").read_text()
        self.assertIn(f"{M.JOINT_STEP_LIMIT_RAD:g} rad per control step", text)
        self.assertIn(f"{M.IK_JUMP_LIMIT_RAD:g} rad from the current joints", text)


if __name__ == "__main__":
    unittest.main()
