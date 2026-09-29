"""Panda port, observation boundary and extraction/release verdict regressions."""
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from topogym.agent_bridge.adapters import CounterTask
from topogym.agent_bridge.panda_contract import PandaPort, validate_action
from topogym.agent_bridge.registry import factory_for
from topogym.agent_bridge.robot_adapter import RigidRobotAdapter, StableVerdict
from topogym.agent_bridge.session import Session
from topogym.tasks.hedgehog_in_cage.agent_adapter import HedgehogAdapter, configuration
from topogym.tasks.hedgehog_in_cage.agent_spec import describe_task
from topogym.tasks.cast_keyhole.agent_adapter import KeyholeAdapter


class ContractChecks(unittest.TestCase):
    def setUp(self):
        self.cfg, self.seed = configuration()
        self.spec = describe_task(self.cfg)

    def test_public_facts_have_three_views_and_no_object_configuration(self):
        self.cfg.task.scale = 99
        self.cfg.task.initial_pose.position_m = [99., 99., 99.]
        self.assertEqual(self.spec, describe_task(self.cfg))
        self.assertEqual(self.spec["cameras"], ["agentview", "front_oblique", "wrist"])
        self.assertEqual(self.spec["robot"]["arms"], ["arm"])
        self.assertEqual(len(self.spec["robot"]["home_qpos"]), 7)
        self.assertEqual(self.spec["camera_calibration"]["wrist"]["parent_link"], "hand")
        self.assertNotIn("differs", self.spec["camera_calibration"]["wrist"]["world_pose"])
        self.assertFalse(self.spec["perception"]["reference_images_provided"])
        self.assertFalse(self.spec["perception"]["object_geometry_provided"])
        for private in ("initial_pose", "template_sha256", "template.json", "agent_initial_state.json", "runs/"):
            self.assertNotIn(private, json.dumps(self.spec))

    def test_single_arm_joint_limits_and_half_aperture(self):
        schema = self.spec["action_schema"]
        validate_action({}, schema)
        validate_action({"arm": {"qpos": self.seed["arm_qpos"], "gripper": .04}}, schema)
        for action in ({"right": {"gripper": .037}}, {"arm": {}}, {"reset": True},
                       {"arm": {"attach": "hedgehog_ball"}}, {"arm": {"qpos": [0.]*6}},
                       {"arm": {"qpos": [0.]*7}}, {"arm": {"qpos": [float("nan")]*7}},
                       {"arm": {"gripper": True}}, {"arm": {"gripper": .08}},
                       {"arm": {"gripper": -.001}}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_action(action, schema)

    def test_port_sets_targets_without_advancing_physics(self):
        controller = Mock(arm_dofs=list(range(7)))
        port = PandaPort(controller)
        port.set_arm_qpos(self.seed["arm_qpos"])
        np.testing.assert_array_equal(controller.robot.control_dofs_position.call_args.args[0], self.seed["arm_qpos"])
        self.assertEqual(controller.robot.control_dofs_position.call_args.args[1], list(range(7)))
        port.set_gripper(.01)
        controller.set_gripper.assert_called_once_with(.01, steps=0)
        controller.scene.step.assert_not_called()
        controller.robot.set_qpos.assert_not_called()
        self.assertIs(port.arms["arm"], port)

    def test_registry_and_robot_runtime_shared_with_dual_arm(self):
        self.assertTrue(issubclass(HedgehogAdapter, RigidRobotAdapter))
        self.assertIs(HedgehogAdapter.step, KeyholeAdapter.step)
        self.assertEqual(factory_for("hedgehog_in_cage", "cpu", "rasterizer").func.__module__,
                         "topogym.tasks.hedgehog_in_cage.agent_adapter")

    def test_missing_single_arm_view_rejected_before_ready(self):
        class MissingView(CounterTask):
            def describe(self):
                return dict(super().describe(), robot={"arms": ["arm"]})
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, "canonical views"):
            Session(MissingView, Path(root)/"episode")


class Body:
    def __init__(self, idx, pos):
        self.base_link_idx = idx
        self.pos = np.array(pos, dtype=float)
        self.vel, self.ang = np.zeros(3), np.zeros(3)
    def get_pos(self): return self.pos
    def get_quat(self): return np.array([1., 0., 0., 0.])
    def get_vel(self): return self.vel
    def get_ang(self): return self.ang


class EvaluatorChecks(unittest.TestCase):
    def setUp(self):
        self.adapter = a = HedgehogAdapter.__new__(HedgehogAdapter)
        self.ball, self.cage = Body(10, [.3, 0, .01]), Body(11, [0, 0, .2])
        a.task = NS(hedgehog=self.ball, cage=self.cage,
                    tabletop=NS(frames=NS(table_surface_origin=[0., 0., 0.])))
        a.cfg = NS(env=NS(world=NS(table=NS(size=[2., 2., .1]))))
        a.cage_pos, a.cage_quat = self.cage.pos.copy(), self.cage.get_quat()
        a.cage_bounds = np.array([[-.1, -.1, 0], [.1, .1, .4]])
        a.ball_vertices = np.array([[-.01]*3, [.01]*3])
        a.robotlinks, a.table, a.fixtures = {20, 21}, 30, {11, 30, 31}
        a.registrations, a.rest_origin = [], None
        self.contacts = dict(link_a=np.array([10]), link_b=np.array([30]),
                             penetration=np.array([0.]), force=np.array([[0., 0., 1.]]))

    def reached(self):
        return self.adapter._failure_and_goal(self.contacts)

    def test_goal_requires_outside_cage_release_and_table_support(self):
        self.assertEqual(self.reached(), (None, True))
        self.adapter.registrations = [(20, 10)]
        self.assertEqual(self.reached(), (None, False))
        self.adapter.registrations = []
        self.contacts["link_b"][0] = 20
        self.assertEqual(self.reached(), (None, False))
        self.contacts["link_b"][0] = 30
        self.ball.pos[0] = 0  # Contained in cage, despite having table contact.
        self.assertEqual(self.reached(), (None, False))
        self.ball.pos[0] = 1.1  # Outside table footprint.
        self.assertEqual(self.reached(), (None, False))

    def test_motion_and_accumulated_drift_restart_two_second_window(self):
        self.ball.vel[0] = .002
        self.assertEqual(self.reached(), (None, False))
        self.ball.vel[0], self.ball.ang[0] = 0, .01
        self.assertEqual(self.reached(), (None, False))
        self.ball.ang[0] = 0
        verdict = StableVerdict(.005, duration=2.)
        for tick in range(1, 400):
            self.assertEqual(verdict.update(tick, self.reached()[1])["status"], "running")
        self.ball.pos[0] += .0003
        self.assertEqual(verdict.update(400, self.reached()[1])["status"], "running")
        self.assertEqual(verdict.stable_ticks, 0)
        for tick in range(401, 800):
            self.assertEqual(verdict.update(tick, self.reached()[1])["status"], "running")
            verdict.update(tick, self.reached()[1])  # Reading again cannot accrue time.
        self.assertEqual(verdict.update(800, self.reached()[1])["status"], "succeeded")

    def test_penetration_fixed_cage_and_invalid_state_fail(self):
        self.contacts["link_b"][0] = 11
        self.contacts["penetration"][0] = .0002
        self.assertIn("0.15 mm", self.reached()[0])
        self.contacts["link_a"][0] = 20
        self.assertIn("0.15 mm", self.reached()[0])
        self.contacts["link_b"][0] = 21
        self.contacts["penetration"][0] = .002
        self.assertIn("1 mm", self.reached()[0])
        self.contacts["penetration"][0] = 0
        self.cage.pos[0] += .001
        self.assertIn("Fixed cage", self.reached()[0])
        self.cage.pos[0] = 0
        self.ball.pos[2] = -.2
        self.assertIn("fell", self.reached()[0])
        self.ball.pos[2] = float("nan")
        self.assertIn("Non-finite", self.reached()[0])


if __name__ == "__main__":
    unittest.main()
