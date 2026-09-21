"""R2 failure-snapshot regression, including unsafe handoff counterexamples."""
import json
from pathlib import Path
import unittest

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.rope_threading.feedback_ik_plan import (
    GRASP_OFFSET, grasp_pose, plan_handoff, screen_plan,
)
from topogym.tasks.rope_threading.reference_preflight import model_with_fixtures


ROOT = Path(__file__).resolve().parents[1]


class FeedbackHandoffChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cls.cfg = compose(config_name="rope_threading_damped20_fine_full_observation")
        cls.snapshot = json.loads((ROOT/"tests/fixtures/rope_threading_r2_handoff.json").read_text())
        cls.plan = plan_handoff(cls.cfg, cls.snapshot, np.array(cls.snapshot["join_qpos"]), dt=.04)

    def test_whole_handoff_including_joint_branch_join_is_clear(self):
        report = screen_plan(self.cfg, self.plan)
        self.assertTrue(report["sampled_kinematic_checks_passed"], report)
        self.assertGreater(report["worst_contact"]["distance_m"], .0018)
        self.assertLess(report["maximum_join_joint_difference_rad"], 1e-6)
        self.assertFalse(report["physical_execution_verified"])
        self.assertFalse(report["automatically_executable"])
        self.assertTrue(self.plan["predicted_tail"])

    def test_direct_joint_join_collides_despite_matching_end_poses(self):
        model = model_with_fixtures(self.cfg)
        data = mujoco.MjData(model)
        start = self.plan["qpos"][np.flatnonzero(self.plan["stage"] == "dual_hold_check")[0]]
        end = self.plan["qpos"][-1]
        minimum = 0.
        for u in np.linspace(0, 1, 101):
            data.qpos[:] = end
            data.qpos[8:14] = start[8:14]*(1-u)+end[8:14]*u
            mujoco.mj_forward(model, data)
            minimum = min([minimum]+[float(c.dist) for c in data.contact])
        self.assertLess(minimum, -.001)

    def test_shared_full_open_command_is_unsafe_before_withdrawal(self):
        model = model_with_fixtures(self.cfg)
        data = mujoco.MjData(model)
        index = np.flatnonzero(self.plan["stage"] == "left_small_unpinch")[-1]
        data.qpos[:] = self.plan["qpos"][index]
        data.qpos[6:8] = .037
        mujoco.mj_forward(model, data)
        self.assertLess(min([0.]+[float(c.dist) for c in data.contact]), -.001)

    def test_grasp_uses_measured_position_and_tail_direction(self):
        point = np.array([.02, .19, .35])
        tangent = Rotation.from_euler("z", .12).apply(self.snapshot["tangent"])
        position, rotation = grasp_pose(point, tangent)
        np.testing.assert_allclose(position+rotation.apply(GRASP_OFFSET), point, atol=1e-12)
        np.testing.assert_allclose(rotation.apply([0, 0, 1]), -tangent/np.linalg.norm(tangent), atol=1e-12)
        for bad in ([0, 0, 0], [0, 1, 0], [float("nan"), 0, 1]):
            with self.assertRaises(ValueError):
                grasp_pose(point, bad)

    def test_partial_post_pivot_observation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "both post-pivot"):
            plan_handoff(self.cfg, self.snapshot, np.array(self.snapshot["join_qpos"]),
                         post_pivot_tip=np.array(self.snapshot["tip"]))


if __name__ == "__main__":
    unittest.main()
