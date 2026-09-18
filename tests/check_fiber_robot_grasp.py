"""Regression for open-jaw assistance and non-simultaneous finger contacts."""
import unittest
import time
from types import SimpleNamespace

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.fiber_bundling.robot_sequence import RobotSequence, bundle_fit, grasp_health, touching_grasp_fingers
from topogym.tasks.fiber_bundling.geometry import FiberLayout, shape_in_root_frame


class GraspChecks(unittest.TestCase):
    def observe(self, touching, gap=(.012, .012), loss=0.):
        return grasp_health({25, 31}, touching, gap, loss, .002, .015, .1)

    def test_open_gripper_cannot_carry_cable_on_constraint_alone(self):
        # Observed in an early robot attempt after colliding with the cradle.
        _, problem = self.observe({25, 31}, gap=(.0428, .0428))
        self.assertIsNotNone(problem)

    def test_alternating_contacts_do_not_make_a_bilateral_grasp(self):
        loss = 0.
        for i in range(51):
            loss, problem = self.observe({25} if i % 2 else {31}, loss=loss)
        self.assertIsNotNone(problem)

    def test_brief_contact_flicker_recovers(self):
        loss, problem = self.observe(set(), loss=.05)
        self.assertIsNone(problem)
        loss, problem = self.observe({25, 31}, loss=loss)
        self.assertEqual(loss, 0.)
        self.assertIsNone(problem)

    def test_unrelated_contacts_do_not_qualify(self):
        _, problem = self.observe({25, 77, 82}, loss=.1)
        self.assertIsNotNone(problem)

    def test_current_contacts_on_adjacent_working_segments_are_a_grasp(self):
        touched = touching_grasp_fingers([102, 31], [25, 103], {102, 103, 104}, {25, 31})
        self.assertEqual(touched, {25, 31})
        self.assertIsNone(self.observe(touched)[1])

    def test_remote_coarse_or_fine_contact_cannot_replace_a_finger(self):
        for other in (105, 180):
            touched = touching_grasp_fingers([103, other], [25, 31], {102, 103, 104}, {25, 31})
            self.assertIsNotNone(self.observe(touched, loss=.1)[1])

    def test_adjacent_contact_rule_still_rejects_temporal_union(self):
        loss = 0.
        for i in range(51):
            touched = touching_grasp_fingers([102 if i%2 else 103], [25 if i%2 else 31], {102,103,104}, {25,31})
            loss, problem = self.observe(touched, loss=loss)
        self.assertIsNotNone(problem)

    def test_regrasp_does_not_jump_to_world_axis(self):
        runner = RobotSequence.__new__(RobotSequence)
        link_rot = Rotation.from_euler("y", -13., degrees=True)
        hand_rot = Rotation.from_euler("y", 150., degrees=True)
        hand_pos = np.array([-.13, .4, 1.3])
        runner.grasp_link = SimpleNamespace(get_pos=lambda: np.array([-.08, .4, 1.21]),
            get_quat=lambda: link_rot.as_quat()[[3, 0, 1, 2]])
        runner.c = SimpleNamespace(hand_pos=lambda: hand_pos,
            hand_quat=lambda: hand_rot.as_quat()[[3, 0, 1, 2]])
        runner.last_status = {"roots_m": np.array([[0., .4, 1.23]])}
        runner.args = SimpleNamespace(dt=.002, motion_scale=1.)
        runner.calibrate_grasp(np.array([0., 0., .065]))
        commands = []
        runner.command_hand = lambda pos, rot: commands.append((pos, rot))
        runner.step = lambda: None
        runner.finish_phase = lambda: None
        runner.move_cable("hold_after_regrasp", seconds=.01)
        pos, rot = commands[0]
        np.testing.assert_allclose(pos, hand_pos, atol=1e-12)
        self.assertLess((rot*hand_rot.inv()).magnitude(), 1e-12)


class FinalBundleChecks(unittest.TestCase):
    def setUp(self):
        self.layout = FiberLayout()
        roots = np.asarray(self.layout.fibers())[:, 0]
        self.paths = roots[:, None, :]+np.linspace(0, .08, 11)[None, :, None]*np.array([1., 0., 0.])

    def test_neighbor_can_change_more_than_old_limit_and_still_fit(self):
        before = shape_in_root_frame(self.paths)
        self.paths[1, :, 1] += np.linspace(0., .001, 11)
        runner = RobotSequence.__new__(RobotSequence)
        runner.last_status = {"fibers_m": self.paths}
        runner.task = SimpleNamespace(layout=self.layout)
        runner.spec = {"preparation_margin_m": .0003}
        runner.step_count, runner.args = 1, SimpleNamespace(dt=.002)
        runner.events, runner.shape_references, runner.shape_changes = [], {}, {}
        runner.save = lambda: None
        runner.record_preparation(0, before)
        self.assertGreater(runner.events[-1]["other_shape_changes_m"][1], .0005)
        self.assertTrue(runner.events[-1]["current_bundle_fit"]["all_fit"])
        self.assertTrue(runner.events[-1]["shape_changes_diagnostic_only"])

    def test_previously_ready_wire_must_be_checked_again(self):
        self.assertTrue(bundle_fit(self.paths, self.layout)["all_fit"])
        self.paths[0, :, 1] += np.linspace(0., .02, 11)
        fit = bundle_fit(self.paths, self.layout)
        self.assertFalse(fit["ready"][0])
        self.assertFalse(fit["all_fit"])

    def test_physics_step_records_large_change_without_stopping(self):
        runner = RobotSequence.__new__(RobotSequence)
        reference = shape_in_root_frame(self.paths)[0].copy()
        self.paths[0, :, 1] += np.linspace(0., .001, 11)
        state = dict(fibers_m=self.paths, coarse_m=np.zeros((2, 3)), failed=False,
                     max_root_error_m=0., threading={"max_attachment_error_m": 0.})
        runner.task = SimpleNamespace(scene=SimpleNamespace(step=lambda **kw: None),
            last_step_state=state, layout=self.layout, ring=SimpleNamespace(base_link_idx=99),
            contact_guard=SimpleNamespace(fine_links={}))
        runner.solver = SimpleNamespace(collider=SimpleNamespace(get_contacts=lambda: {
            "link_a": np.array([], dtype=int), "link_b": np.array([], dtype=int), "penetration": np.array([])}))
        runner.robot_ids, runner.fine_ids, runner.cable_ids = [], [], []
        runner.robot = SimpleNamespace(base_link_idx=98)
        runner.step_count, runner.args, runner.phase = 0, SimpleNamespace(dt=.002), "next_wire"
        runner.previous, runner.contact_counts, runner.holding = self.paths.copy(), {}, False
        runner.last_print = time.monotonic()
        runner.shape_references, runner.shape_changes = {0: reference}, {0: 0.}
        runner.maxima = dict.fromkeys(("fine_penetration_m", "coarse_penetration_m", "robot_fixture_penetration_m",
            "fine_pair_penetration_m", "root_error_m", "anchor_error_m", "fine_length_error_m", "point_displacement_per_step_m"), 0.)
        runner.spec = dict(fine_contact_penetration_limit_m=.0003, coarse_contact_penetration_limit_m=.0007,
            robot_fixture_penetration_limit_m=.0003, root_error_limit_m=1e-5, per_step_point_displacement_limit_m=.0012)
        runner.step()
        self.assertGreater(runner.shape_changes[0], .0005)

    def test_final_fit_uses_actual_ring_axis_including_cable_tilt(self):
        tilted = Rotation.from_euler("z", 25., degrees=True).apply(self.paths.reshape(-1, 3)).reshape(self.paths.shape)
        self.assertTrue(bundle_fit(tilted, self.layout)["all_fit"])
        ring = tilted[:, 0].mean(axis=0)
        self.assertFalse(bundle_fit(tilted, self.layout, ring_center=ring)["all_fit"])


if __name__ == "__main__":
    unittest.main()
