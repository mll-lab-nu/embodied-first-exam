"""Measured robot collision regressions missed by the earlier rigid report."""
import json
from pathlib import Path
import unittest
import subprocess
import sys
import textwrap

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

    def guard(self):
        guard = MeasuredRobotMeshGuard(self.model)
        self.addCleanup(guard.close)
        return guard

    def test_real_finger_intersection_is_rejected(self):
        case = self.fixture["finger_intersection"]
        guard = self.guard()
        with self.assertRaisesRegex(RuntimeError, "robot_triangle_intersection"):
            guard.check(case["qpos"], case["time_s"])
        self.assertFalse(guard.report()["passed"])

    def test_convex_only_overlap_does_not_fake_a_triangle_collision(self):
        case = self.fixture["base_convex_only"]
        guard = self.guard()
        guard.check(case["qpos"], case["time_s"])
        self.assertTrue(guard.report()["passed"])
        self.assertGreater(guard.convex_false_positives, 0)

    def test_early_left_detour_clears_observed_base_intersection(self):
        case = self.fixture["base_intersection"]
        q = np.asarray(case["qpos"])
        with self.assertRaisesRegex(RuntimeError, "robot_triangle_intersection"):
            self.guard().check(q, case["time_s"])
        planner = MeasuredHandoffPlanner(self.cfg, q)
        p, r = planner.ik.pose("left", q[:6])
        u = (case["source_time_s"]-41.2)/3.
        delta = np.array([.01*max(0., 1.-u*u)**3, 0., 0.])
        q[:6] = planner.ik.solve("left", p+delta, r.as_quat(scalar_first=True), seed=q[:6])
        guard = self.guard()
        guard.check(q, case["time_s"])
        self.assertTrue(guard.report()["passed"])

    def test_triangle_audit_runs_with_uipc_loaded_in_physics_parent(self):
        script = textwrap.dedent('''
            import uipc
            import json, sys
            from pathlib import Path
            from hydra import compose, initialize_config_dir
            from topogym.tasks.rope_threading.reference_preflight import model_with_fixtures
            from topogym.tasks.rope_threading.robot_mesh_guard import MeasuredRobotMeshGuard
            with initialize_config_dir(config_dir=str(Path.cwd()/"configs"), version_base="1.3"):
                cfg = compose(config_name="rope_threading_damped20_compressible_fine_preview")
            cases = json.loads(Path("tests/fixtures/rope_threading_robot_contacts.json").read_text())
            guard = MeasuredRobotMeshGuard(model_with_fixtures(cfg))
            try:
                case = cases["base_convex_only"]
                guard.check(case["qpos"], case["time_s"])
                guard.check(case["qpos"], case["time_s"]+.005)
                case = cases["finger_intersection"]
                try:
                    guard.check(case["qpos"], case["time_s"])
                except RuntimeError as exc:
                    assert "robot_triangle_intersection" in str(exc), str(exc)
                else:
                    raise AssertionError("Expected the recorded finger intersection")
                assert "ipctk" not in sys.modules
                process = guard.process
            finally:
                guard.close()
            assert not process.is_alive()
            print("isolated_native_geometry_checks_passed")
        ''')
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn("isolated_native_geometry_checks_passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
