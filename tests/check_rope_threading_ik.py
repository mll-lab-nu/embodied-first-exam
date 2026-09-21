"""Regression of the observed first-ring wrist-limit failure, using real FK/IK."""
from pathlib import Path
from types import SimpleNamespace
import unittest

from hydra import compose, initialize_config_dir
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.rope_threading.ik_plan import offline_controller
from topogym.tasks.rope_threading.reference_actions import ReferenceThreadingActions, ending_lift
from topogym.tasks.rope_threading.reference_ik import MarginAwareThreadingIK, relaxed_roll, free_hand_clearance


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT/"runs/environment-solvability/rope_threading/reference_motion_v1"


@unittest.skipUnless((REFERENCE/"reference_motion.npz").is_file(), "Offline reference unavailable")
class ThreadingIKChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cls.cfg = compose(config_name="rope_threading_damped20_compressible_fine_preview")
        cls.actions = ReferenceThreadingActions(REFERENCE)
        cls.controller = offline_controller(cls.cfg, cls.actions.reference["qpos"][0])

    def test_failing_phase_has_safe_ik_with_position_and_tool_axis_preserved(self):
        ik = MarginAwareThreadingIK(None, self.controller)
        for time in [80.66, 81.34, 81.35, 82.5, 91.5, 154.8, 192.88]:
            q, hands, _, _ = self.actions._sample(time)
            point, rotation = hands[1, :3]+[0, 0, .0009], Rotation.from_quat(hands[1, 3:], scalar_first=True)
            solution = ik.solve_reference("right", point, hands[1, 3:], q[8:14])
            actual_point, actual_rotation = ik.pose("right", solution)
            self.assertGreaterEqual(np.minimum(solution-ik.joint_limits[:, 0], ik.joint_limits[:, 1]-solution).min(), .02-1e-9)
            np.testing.assert_allclose(actual_point, point, atol=2e-7)
            np.testing.assert_allclose(actual_rotation.apply([1., 0., 0.]), rotation.apply([1., 0., 0.]), atol=2e-6)
            self.assertLess((rotation.inv()*actual_rotation).magnitude(), .021)

    def test_original_pose_is_not_mislabeled_as_exactly_feasible_with_margin(self):
        ik = MarginAwareThreadingIK(None, self.controller)
        q, hands, _, _ = self.actions._sample(90.)
        with self.assertRaisesRegex(ValueError, "Unreachable"):
            ik.solve("right", hands[1, :3]+[0, 0, .0009], hands[1, 3:], seed=q[8:14])

    def test_runtime_uses_margin_ik_at_the_observed_abort_time(self):
        actions = ReferenceThreadingActions(REFERENCE, speed=3.)
        actions.source_time, actions.last_time, actions.event_index = 81.34, 28.075, 2
        actions.ik = MarginAwareThreadingIK(None, self.controller)
        commands = {}
        actions.controller = SimpleNamespace(arms={side: SimpleNamespace(
            set_arm_qpos=lambda q, side=side: commands.__setitem__(side, q.copy()),
            set_gripper=lambda q: None) for side in ("left", "right")})
        actions.task = SimpleNamespace(layout=SimpleNamespace(transform=lambda p: p+[0, 0, .0009]))
        actions.update(28.08)
        self.assertAlmostEqual(actions.source_time, 81.355)
        self.assertEqual(actions.stage, "reference_10")
        limits = actions.ik.joint_limits
        self.assertGreaterEqual(np.minimum(commands["right"]-limits[:, 0], limits[:, 1]-commands["right"]).min(), .02-1e-9)

    def test_roll_correction_is_continuous_without_branch_wrap(self):
        limits = np.asarray(self.cfg.robot_control.robot.arm_joint_limits)[-1]
        values = np.linspace(limits[0], limits[0]+.1, 1001)
        adjusted = np.array([relaxed_roll(v, limits) for v in values])
        self.assertGreaterEqual(adjusted.min(), limits[0]+.02)
        self.assertTrue(np.all(np.diff(adjusted) >= 0))
        self.assertLessEqual(np.diff(adjusted).max(), np.diff(values).max()+1e-12)
        self.assertLess(abs(adjusted[-1]-values[-1]), 1e-8)

    def test_final_shared_table_adaptation_still_has_margin(self):
        ik = MarginAwareThreadingIK(None, self.controller)
        start = self.actions.summary["stages"][49]["start_s"]
        for time in [start, start+6., start+12., self.actions.cutoff]:
            q, hands, _, _ = self.actions._sample(time)
            target = hands[1, :3]+[0, 0, .0009]+ending_lift(time, start)
            result = ik.solve_reference("right", target, hands[1, 3:], q[8:14])
            point, _ = ik.pose("right", result)
            np.testing.assert_allclose(point, target, atol=2e-7)
            self.assertGreaterEqual(np.minimum(result-ik.joint_limits[:, 0], ik.joint_limits[:, 1]-result).min(), .02-1e-9)

    def test_clearance_detours_do_not_change_grasp_or_release_poses(self):
        stages = self.actions.summary["stages"]
        for event in self.actions.schedule:
            _, _, _, phase = self.actions._sample(event["time"])
            for side in ("left", "right"):
                np.testing.assert_array_equal(free_hand_clearance(event["time"], phase, stages, side), np.zeros(3))
        for phase in (40, 49):
            for time in (stages[phase]["start_s"], stages[phase]["end_s"]):
                np.testing.assert_array_equal(free_hand_clearance(time, phase, stages, "left"), np.zeros(3))


if __name__ == "__main__":
    unittest.main()
