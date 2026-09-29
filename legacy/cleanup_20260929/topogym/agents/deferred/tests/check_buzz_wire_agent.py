"""Static episode boundaries, friction-only commands and adversarial scoring."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.agent_bridge.panda_contract import validate_action
from topogym.agent_bridge.registry import factory_for
from topogym.agent_bridge.robot_adapter import StableVerdict
from topogym.tasks.buzz_wire_3d.agent_adapter import BuzzWireAdapter, RailTraversal, configuration
from topogym.tasks.buzz_wire_3d.agent_scene import load_seed, prepare_scene
from topogym.tasks.buzz_wire_3d.agent_spec import describe_task
from topogym.tasks.hedgehog_in_cage.agent_adapter import HedgehogAdapter


class ContractChecks(unittest.TestCase):
    def test_startup_inputs_have_no_reference_motion_and_public_spec_has_no_geometry(self):
        original = Path.open

        def guarded(path, *args, **kwargs):
            if path.name in ("robot_seed.json", "reference_path.npz", "plan.json", "frames.json") or "runs" in path.parts:
                raise AssertionError(f"Attempted reference read: {path}")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", guarded), tempfile.TemporaryDirectory() as folder:
            cfg, seed = configuration()
            static = prepare_scene(folder)
            self.assertFalse(hasattr(static, "pose"))
            self.assertEqual({p.name for p in Path(folder).iterdir()}, {"wire.urdf", "wand.urdf", "initial_state.json"})
            spec = describe_task(cfg)
        cfg.task.geometry.loop_radius_m = 99
        cfg.task.origin_xy_m = [99, 99]
        self.assertEqual(spec, describe_task(cfg))
        self.assertEqual(spec["cameras"], ["agentview", "front_oblique", "wrist"])
        self.assertEqual(spec["control_dt_s"], .004)
        self.assertEqual(spec["physics_substeps"], 16)
        self.assertEqual(spec["robot"]["gripper_controller"]["max_driver_torque_nm"], 2.5)
        self.assertFalse(spec["physics_qualified"])
        self.assertFalse(spec["perception"]["object_geometry_provided"])
        for private in ("rail_local_m", "initial_wand", "normal_tilt_knots", "initial_state.json", "robot_seed", "reference_path"):
            self.assertNotIn(private, json.dumps(spec))
        validate_action({"arm": {"qpos": seed["initial_arm_qpos"], "gripper": 0.}}, spec["action_schema"])
        self.assertEqual(factory_for("buzz_wire_3d", "cpu", "rasterizer").func.__module__,
                         "topogym.tasks.buzz_wire_3d.agent_adapter")

    def test_static_assets_are_pinned_and_rail_matches_actual_collisions(self):
        seed = load_seed()
        with tempfile.TemporaryDirectory() as folder:
            static = prepare_scene(folder)
            tree = ET.parse(Path(folder)/"wire.urdf")
            cylinders = [e for e in tree.findall(".//collision") if e.find("geometry/cylinder") is not None]
            self.assertEqual(len(cylinders), len(static.rail)-1)
            for node, first, last in zip(cylinders, static.rail[:-1], static.rail[1:]):
                origin, cylinder = node.find("origin"), node.find("geometry/cylinder")
                position = np.fromstring(origin.get("xyz"), sep=" ")
                rotation = Rotation.from_euler("xyz", np.fromstring(origin.get("rpy"), sep=" "))
                offset = rotation.apply([0., 0., float(cylinder.get("length"))/2])
                np.testing.assert_allclose(position-offset, first, atol=2e-11)
                np.testing.assert_allclose(position+offset, last, atol=2e-11)
                self.assertAlmostEqual(float(cylinder.get("radius")), seed["geometry"]["wire_radius_m"])
            wand = ET.parse(Path(folder)/"wand.urdf")
            self.assertAlmostEqual(float(wand.find(".//inertial/mass").get("value")), seed["geometry_report"]["wand_mass_kg"])
        with patch("topogym.tasks.buzz_wire_3d.agent_scene.SEED_SHA256", "wrong"):
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_seed()

    def test_shared_runtime_never_arms_assistance_for_friction_only_task(self):
        self.assertIs(BuzzWireAdapter.step, HedgehogAdapter.step)
        self.assertIs(BuzzWireAdapter._apply, HedgehogAdapter._apply)
        a = BuzzWireAdapter.__new__(BuzzWireAdapter)
        arm = Mock(current_gripper_qpos=.02)
        a.ctrl = NS(arms={"arm": arm})
        a.candidates, a.registrations, a.attempt_grasp = set(), [], {"arm": False}
        a.hands, a.targets = {"arm": 20}, {"arm": np.zeros(7)}
        a._replace = Mock()
        a._apply({"arm": {"gripper": 0.}})
        self.assertFalse(a.attempt_grasp["arm"])
        a._apply({"arm": {"gripper": .04}})
        a._replace.assert_not_called()
        arm.set_gripper.assert_called_with(.04)


RAIL = np.array([[-.2, 0, .03], [-.2, 0, .10], [-.2, 0, .20],
                 [0, 0, .3], [.2, 0, .20], [.2, 0, .10], [.2, 0, .03]])


def tracker():
    return RailTraversal(RAIL, .022, .01, np.array([-.2, 0, .07]), np.array([0., 0., 1.]))


def advance_to_end(t):
    for s in np.arange(t.last_s+.01, t.arc[-1]-.015, .01):
        i = min(np.searchsorted(t.arc, s, side="right")-1, len(RAIL)-2)
        direction = (RAIL[i+1]-RAIL[i])/t.lengths[i]
        p = RAIL[i]+(s-t.arc[i])*direction
        failure = t.update(p, direction)
        if failure:
            raise AssertionError(failure)


class TraversalChecks(unittest.TestCase):
    def test_endpoint_shortcut_and_loss_of_link_are_rejected(self):
        t = tracker()
        self.assertIn("jump", t.update(np.array([.2, 0, .07]), np.array([0., 0., 1.])))
        self.assertIn("threaded", t.update(np.array([0., 0, .07]), np.array([0., 0., 1.])))
        self.assertFalse(t.terminal_reached)

    def test_continuous_traversal_accepts_backtracking_then_all_bends(self):
        t = tracker()
        self.assertIsNone(t.update(np.array([-.2, 0, .06]), np.array([0., 0., 1.])))
        advance_to_end(t)
        self.assertTrue(t.terminal_reached)
        self.assertGreater(t.last_s, t.arc[-1]-.05)


class Body:
    def __init__(self, link, pos):
        self.base_link_idx, self.pos = link, np.array(pos, dtype=float)
        self.vel, self.ang = np.zeros(3), np.zeros(3)
    def get_pos(self): return self.pos
    def get_quat(self): return np.array([1., 0., 0., 0.])
    def get_vel(self): return self.vel
    def get_ang(self): return self.ang


class EvaluatorChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        a = self.adapter = BuzzWireAdapter.__new__(BuzzWireAdapter)
        self.wand, self.wire, self.base = Body(10, [-.2, 0, .07]), Body(30, [0, 0, 0]), Body(31, [0, 0, 0])
        a.task = NS(wand=self.wand, wire=self.wire, origin=np.zeros(3))
        a.fixed = [(x, x.pos.copy(), x.get_quat()) for x in (self.wire, self.base)]
        a.traversal, a.rail = tracker(), RAIL
        a.robot = Mock()
        a.robot.get_qpos.return_value = np.zeros(15)
        a.robotlinks, a.fixtures, a.fingers = {20, 21, 22}, {30, 31, 32}, {"arm": {20, 21}}
        a.mass, a.com, a.inertia = .03, np.zeros(3), np.eye(3)*1e-6
        a.passive_energy, a.registrations, a.tick, a.last_audit_tick = None, [], 0, -1
        a.evidence_path = Path(self.temp.name)/"audit.jsonl"
        self.contacts = dict(link_a=np.array([], dtype=int), link_b=np.array([], dtype=int),
            penetration=np.zeros(0), force=np.empty((0, 3)))

    def verdict(self):
        return self.adapter._failure_and_goal(self.contacts)

    def contact(self, a, b, penetration=1e-5, force=(0., 0., .3)):
        self.contacts = dict(link_a=np.array([a]), link_b=np.array([b]),
            penetration=np.array([penetration]), force=np.array([force]))

    def terminal(self):
        advance_to_end(self.adapter.traversal)
        self.wand.pos[:] = [.2, 0, .055]
        self.contact(30, 10)

    def test_touch_fails_at_start_even_if_released(self):
        self.assertEqual(self.verdict(), (None, False))
        self.contact(30, 10)
        self.assertIn("Wire touch", self.verdict()[0])

    def test_goal_requires_terminal_support_release_and_speed_limits(self):
        self.terminal()
        self.assertEqual(self.verdict(), (None, True))
        self.contacts["force"][0, 2] = -.3
        self.assertEqual(self.verdict(), (None, False))
        self.contacts["force"][0, 2] = .3
        self.wand.vel[0] = .003
        self.assertEqual(self.verdict(), (None, False))
        self.wand.vel[0], self.wand.ang[0] = 0., .03
        self.assertEqual(self.verdict(), (None, False))
        self.wand.ang[0] = 0
        self.contact(20, 10)  # Still held: cannot claim success.
        self.assertEqual(self.verdict(), (None, False))
        self.contact(32, 10)  # Table cannot substitute for the terminal stop.
        self.assertEqual(self.verdict(), (None, False))

    def test_terminal_touch_while_held_and_deep_contact_fail(self):
        self.terminal()
        self.contacts = dict(link_a=np.array([30, 20]), link_b=np.array([10, 10]),
            penetration=np.ones(2)*1e-5, force=np.array([[0., 0., .3], [.1, 0., 0.]]))
        self.assertIn("Wire touch", self.verdict()[0])
        self.contact(30, 10, .0006)
        self.assertIn("0.5 mm", self.verdict()[0])

    def test_robot_forbidden_contact_and_passive_energy_growth_fail(self):
        self.contact(20, 31, .0003)
        self.assertIn("0.2 mm", self.verdict()[0])
        self.contact(22, 10)
        self.assertIn("non-pad", self.verdict()[0])
        self.terminal()
        self.assertEqual(self.verdict(), (None, True))
        self.wand.pos[2] += .004
        self.assertIn("1 mJ", self.verdict()[0])

    def test_fixed_toy_fall_and_nonfinite_state_fail(self):
        self.wire.pos[0] = .001
        self.assertIn("Fixed", self.verdict()[0])
        self.wire.pos[0] = 0
        self.wand.pos[2] = -.2
        self.assertIn("fell", self.verdict()[0])
        self.wand.pos[2] = float("nan")
        self.assertIn("Non-finite", self.verdict()[0])

    def test_terminal_hold_requires_one_contiguous_simulated_second(self):
        self.terminal()
        verdict = StableVerdict(.004, duration=1.)
        for tick in range(1, 250):
            self.assertEqual(verdict.update(tick, self.verdict()[1])["status"], "running")
            verdict.update(tick, self.verdict()[1])
        self.assertEqual(verdict.update(250, self.verdict()[1])["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
