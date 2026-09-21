"""Measured robot collision regressions missed by the earlier rigid report."""
import json
from pathlib import Path
import unittest

from hydra import compose, initialize_config_dir
import numpy as np

from topogym.tasks.rope_threading.feedback_paths import MeasuredHandoffPlanner
from topogym.tasks.rope_threading.reference_preflight import model_with_fixtures
from topogym.tasks.rope_threading.robot_mesh_guard import MeasuredRobotMeshGuard


ROOT = Path(__file__).resolve().parents[1]


class MeasuredRobotMeshChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cls.cfg = compose(config_name="rope_threading_damped20_compressible_fine_preview")
        cls.fixture = json.loads((ROOT/"tests/fixtures/rope_threading_robot_contacts.json").read_text())
        cls.model = model_with_fixtures(cls.cfg)

    def test_real_finger_intersection_is_rejected(self):
        case = self.fixture["finger_intersection"]
        guard = MeasuredRobotMeshGuard(self.model)
        with self.assertRaisesRegex(RuntimeError, "robot_triangle_intersection"):
            guard.check(case["qpos"], case["time_s"])
        self.assertFalse(guard.report()["passed"])

    def test_convex_only_overlap_does_not_fake_a_triangle_collision(self):
        case = self.fixture["base_convex_only"]
        guard = MeasuredRobotMeshGuard(self.model)
        guard.check(case["qpos"], case["time_s"])
        self.assertTrue(guard.report()["passed"])
        self.assertGreater(guard.convex_false_positives, 0)

    def test_early_left_detour_clears_observed_base_intersection(self):
        case = self.fixture["base_intersection"]
        q = np.asarray(case["qpos"])
        with self.assertRaisesRegex(RuntimeError, "robot_triangle_intersection"):
            MeasuredRobotMeshGuard(self.model).check(q, case["time_s"])
        planner = MeasuredHandoffPlanner(self.cfg, q)
        p, r = planner.ik.pose("left", q[:6])
        u = (case["source_time_s"]-41.2)/3.
        delta = np.array([.01*max(0., 1.-u*u)**3, 0., 0.])
        q[:6] = planner.ik.solve("left", p+delta, r.as_quat(scalar_first=True), seed=q[:6])
        guard = MeasuredRobotMeshGuard(self.model)
        guard.check(q, case["time_s"])
        self.assertTrue(guard.report()["passed"])


if __name__ == "__main__":
    unittest.main()
