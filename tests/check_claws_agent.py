"""Claw public contract and adversarial private evaluator checks."""
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import numpy as np
import trimesh

from topogym.agent_bridge.aloha_contract import validate_action
from topogym.agent_bridge.registry import factory_for
from topogym.agent_bridge.robot_adapter import StableVerdict
from topogym.tasks.cast_keyhole.agent_adapter import KeyholeAdapter
from topogym.tasks.interlocked_claws.agent_adapter import ClawsAdapter, configuration
from topogym.tasks.interlocked_claws.agent_spec import describe_task
from topogym.tasks.interlocked_claws.collision import ClawCollision


class ContractChecks(unittest.TestCase):
    def test_initialization_uses_static_facts_and_spec_has_no_private_geometry(self):
        read = Path.open

        def guarded(path, *args, **kwargs):
            if path.name == "recorded_motion.json" or "runs" in path.parts:
                raise AssertionError(f"Attempted solution read: {path}")
            return read(path, *args, **kwargs)

        with patch.object(Path, "open", guarded):
            cfg = configuration()
            spec = describe_task(cfg)
        cfg.task.variant = "private_changed_geometry"
        cfg.task.seed = 99
        self.assertEqual(spec, describe_task(cfg))
        self.assertEqual(spec["cameras"], ["cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"])
        self.assertEqual(spec["control_dt_s"], .002)
        self.assertEqual(spec["physics_substeps"], 4)
        self.assertEqual(spec["robot"]["source_base_adapter_z_translation_m"], 0.)
        self.assertFalse(spec["physics_qualified"])
        self.assertFalse(spec["perception"]["object_geometry_provided"])
        for private in ("initial_piece_poses", "inverse_grasp", "reference_scene.json", "recorded_motion", "runs/", "source_manifest"):
            self.assertNotIn(private, json.dumps(spec))
        self.assertIn("松开", spec["task_goal"])
        self.assertIn("支架", spec["success_rule"])

    def test_static_seed_hash_mismatch_is_rejected(self):
        with patch("topogym.tasks.interlocked_claws.agent_adapter.REFERENCE_SHA256", "invalid"):
            with self.assertRaisesRegex(ValueError, "checksum"):
                configuration()

    def test_runtime_is_reused_with_bounded_dual_arm_actions(self):
        self.assertIs(ClawsAdapter.step, KeyholeAdapter.step)
        self.assertIs(ClawsAdapter._apply, KeyholeAdapter._apply)
        self.assertEqual(factory_for("interlocked_claws", "cpu", "rasterizer").func.__module__,
                         "topogym.tasks.interlocked_claws.agent_adapter")
        schema = describe_task(configuration())["action_schema"]
        validate_action({}, schema)
        validate_action({"left": {"qpos": [0.]*6}, "right": {"gripper": .037}}, schema)
        for action in ({"reset": True}, {"arm": {"gripper": .01}}, {"left": {"attach": "claw_0"}},
                       {"left": {"qpos": [float("nan")]*6}}, {"right": {"gripper": .04}}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_action(action, schema)


class Body:
    def __init__(self, idx, pos):
        self.base_link_idx, self.pos = idx, np.array(pos, dtype=float)
        self.vel, self.ang = np.zeros(3), np.zeros(3)
    def get_pos(self): return self.pos
    def get_quat(self): return np.array([1., 0., 0., 0.])
    def get_vel(self): return self.vel
    def get_ang(self): return self.ang


class EvaluatorChecks(unittest.TestCase):
    def setUp(self):
        self.adapter = a = ClawsAdapter.__new__(ClawsAdapter)
        self.orange, self.blue = Body(10, [0, 0, .2]), Body(11, [.3, 0, .2])
        self.support = Body(40, [0, 0, .1])
        a.task = NS(bodies=dict(claw_0=self.orange, claw_1=self.blue),
                    tabletop=NS(frames=NS(table_surface_origin=[0., 0., 0.])))
        a.robot = Mock()
        a.robot.get_qpos.return_value = np.zeros(16)
        a.bodylinks, a.robotlinks, a.table = {10, 11}, {20, 21}, 30
        a.fixtures, a.obstacles = {40, 41}, {40, 41, 42}
        a.fixture_bodies, a.fixed_poses = [self.support], [(self.support.pos.copy(), self.support.get_quat())]
        a.registrations = []
        a.meshes = [trimesh.creation.box(extents=[.1]*3), trimesh.creation.box(extents=[.02]*3)]
        a.collision = ClawCollision(NS(bodies=[NS(mesh=m) for m in a.meshes]))
        # Include both orderings to check signed forces, not merely magnitudes.
        self.contacts = dict(link_a=np.array([40, 11]), link_b=np.array([10, 41]),
            penetration=np.zeros(2), force=np.array([[0., 0., 2.], [0., 0., -2.]]))

    def verdict(self):
        return self.adapter._failure_and_goal(self.contacts)

    def test_both_parts_must_be_released_supported_and_separated(self):
        self.assertEqual(self.verdict(), (None, True))
        self.adapter.registrations = [(20, 10)]
        self.assertEqual(self.verdict(), (None, False))
        self.adapter.registrations = []
        self.contacts["force"][1] = 0
        self.assertEqual(self.verdict(), (None, False))
        self.contacts["force"][1, 2] = -2
        self.blue.pos[0] = .075  # 15 mm surface/AABB gap is insufficient.
        self.assertEqual(self.verdict(), (None, False))

    def test_table_robot_and_downward_forces_cannot_satisfy_support(self):
        for peer in (30, 20):
            self.contacts["link_a"][0] = peer
            self.assertEqual(self.verdict(), (None, False))
        self.contacts["link_a"][0] = 40
        self.contacts["force"][0, 2] = -2
        self.assertEqual(self.verdict(), (None, False))

    def test_triangle_intersection_and_full_containment_fail_without_engine_contacts(self):
        self.blue.pos[0] = .05
        self.assertIn("0.15 mm", self.verdict()[0])
        self.blue.pos[0] = 0
        self.assertIn("contained", self.verdict()[0])

    def test_motion_restarts_contiguous_window_and_failure_latches(self):
        v = StableVerdict(.002, duration=1.)
        for tick in range(1, 500):
            self.assertEqual(v.update(tick, self.verdict()[1])["status"], "running")
        self.blue.vel[0] = .006
        self.assertFalse(self.verdict()[1])
        v.update(500, self.verdict()[1])
        self.assertEqual(v.stable_ticks, 0)
        self.blue.vel[0], self.blue.ang[0] = 0, .06
        self.assertFalse(self.verdict()[1])
        self.blue.ang[0] = 0
        for tick in range(501, 1000):
            self.assertEqual(v.update(tick, self.verdict()[1])["status"], "running")
            v.update(tick, True)  # Repeated reads cannot accumulate simulated time.
        self.assertEqual(v.update(1000, self.verdict()[1])["status"], "succeeded")
        failed = StableVerdict(.002, duration=1.)
        failed.update(1, False, "contact failure")
        self.assertEqual(failed.update(1000, True)["status"], "failed")

    def test_native_contact_fixed_support_and_nonfinite_states_fail(self):
        for pair in ((10, 40), (20, 21), (20, 30), (20, 42)):
            self.contacts["link_a"][0], self.contacts["link_b"][0] = pair
            self.contacts["penetration"][0] = .0011
            self.assertIn("1 mm", self.verdict()[0])
        self.contacts["penetration"][0] = 0
        self.support.pos[0] = .001
        self.assertIn("fixture moved", self.verdict()[0])
        self.support.pos[0] = 0
        self.blue.pos[2] = -.2
        self.assertIn("fell", self.verdict()[0])
        self.blue.pos[2] = float("nan")
        self.assertIn("Non-finite", self.verdict()[0])
        self.blue.pos[2] = .2
        self.adapter.robot.get_qpos.return_value[0] = float("nan")
        self.assertIn("Non-finite", self.verdict()[0])


if __name__ == "__main__":
    unittest.main()
