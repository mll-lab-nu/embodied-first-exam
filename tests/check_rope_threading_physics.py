"""Regression for the base/rope overlap and conservative substep certificates."""
from pathlib import Path
import unittest

from hydra import compose, initialize_config_dir
import mujoco
import numpy as np

from topogym.robot.assets import robot_asset
from topogym.tasks.rope_threading.diagnostics import ClearanceSurfaceCCD
from topogym.tasks.knot_untying.diagnostics import SurfaceCCD

ROOT = Path(__file__).resolve().parents[1]


class ThreadingPhysicsChecks(unittest.TestCase):
    def test_reference_robot_height_is_restored_without_changing_default(self):
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            original = compose(config_name="aloha_lab_preview")
            threading = compose(config_name="rope_threading_preview")
        a = mujoco.MjModel.from_xml_path(robot_asset(original.robot_control))
        b = mujoco.MjModel.from_xml_path(robot_asset(threading.robot_control))
        self.assertEqual(a.nq, b.nq)
        for side in ("left", "right"):
            np.testing.assert_allclose(a.body(f"{side}/base_link").pos[2], 0, atol=1e-12)
            np.testing.assert_allclose(b.body(f"{side}/base_link").pos[2], .0209, atol=1e-12)
        np.testing.assert_array_equal(a.jnt_range, b.jnt_range)
        np.testing.assert_array_equal(a.body_mass, b.body_mass)

    def test_small_safe_steps_are_certified_but_tunnelling_is_rejected(self):
        upper = np.array([[-.02, -.02, .002], [.02, -.02, .002], [0., .02, .002]])
        vertices = np.vstack((upper, upper-[0, 0, .002]))
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        fast, full = ClearanceSurfaceCCD(vertices, faces), SurfaceCCD(vertices, faces)
        try:
            current = vertices.copy()
            current[:3, 2] -= .0001
            self.assertTrue(fast.step(current))
            self.assertTrue(full.step(current))
            self.assertEqual(fast.certified_intervals, 1)
            current[:3, 2] = -.002
            self.assertFalse(fast.step(current))
            self.assertFalse(full.step(current))
            self.assertEqual(fast.full_ccd_queries, 1)
        finally:
            fast.close()
            full.close()

    def test_cumulative_motion_cannot_reuse_an_exhausted_clearance(self):
        vertices = np.array([[-.02, -.02, .002], [.02, -.02, .002], [0., .02, .002],
                             [-.02, -.02, 0.], [.02, -.02, 0.], [0., .02, 0.]])
        checker = ClearanceSurfaceCCD(vertices, np.array([[0, 1, 2], [3, 4, 5]]))
        try:
            for i in range(1, 11):
                current = vertices.copy()
                current[:3, 2] -= i*.0001
                self.assertTrue(checker.step(current))
            self.assertGreater(checker.full_ccd_queries, 0)
            self.assertEqual(checker.checks, 10)
        finally:
            checker.close()


if __name__ == "__main__":
    unittest.main()
