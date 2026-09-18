"""Check the geometric acceptance boundary, including between-frame collisions."""
import importlib.util
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.horseshoe_ring.geometry import load_template
from topogym.tasks.horseshoe_ring.witness_motion import fold_transforms, interpolate

HAS_FCL = importlib.util.find_spec("fcl") is not None
if HAS_FCL:
    from topogym.tasks.horseshoe_ring.experiments import straight_path
    from topogym.tasks.horseshoe_ring.solvability import WitnessModel, certify_path


@unittest.skipUnless(HAS_FCL, "Run witness certification tests with .venv-gs121 (python-fcl)")
class WitnessChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = WitnessModel()
        template = load_template()
        template["target_ring"]["centerline_radius"] = 35.
        cls.large = WitnessModel(template)

    def test_large_ring_has_a_continuous_extraction_witness(self):
        result = certify_path(self.large, straight_path())
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["minimum_interval_clearance_lower_bound_m"], .0002)
        self.assertTrue(result["goal"]["separated"])
        self.assertFalse(result["robot_execution_verified"])
        self.assertFalse(result["dynamic_execution_verified"])

    def test_clear_endpoints_do_not_hide_a_collision_between_frames(self):
        path = straight_path()
        self.assertTrue(all(self.original.distances(q).min() > .0002 for q in path))
        self.assertTrue(self.original.separated_goal(path[-1])["separated"])
        result = certify_path(self.original, path)
        self.assertFalse(result["passed"])
        self.assertFalse(result["continuous_collision_free"])
        self.assertEqual(result["failures"][0]["reason"], "clearance_below_margin")

    def test_partial_safe_motion_is_not_an_extraction(self):
        result = certify_path(self.original, straight_path()[:2])
        self.assertTrue(result["continuous_collision_free"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["goal"]["separated"])

    def test_cannot_start_from_an_already_free_ring(self):
        result = certify_path(self.large, straight_path()[1:])
        self.assertFalse(result["passed"])
        self.assertFalse(result["initial_matches_template"])

    def test_uniform_motion_bound_covers_the_interpolated_surfaces(self):
        a = np.r_[.3, -.01, .02, 0., Rotation.from_euler("xyz", [.2, -.4, .1]).as_quat()]
        b = np.r_[2.4, .04, -.02, .03, Rotation.from_euler("xyz", [-.8, .2, .6]).as_quat()]
        bounds = self.original.motion_bounds(a, b)
        for group, mesh in enumerate(self.original.group_meshes):
            # Sample actual cover vertices, including the ends of each rigid group.
            points = mesh.vertices[::max(1, len(mesh.vertices)//250)]
            for lo, hi in [(0., .5), (.25, .35), (.5, 1.)]:
                r0, p0 = fold_transforms(interpolate(a, b, lo), self.original.pivot)[group]
                r1, p1 = fold_transforms(interpolate(a, b, hi), self.original.pivot)[group]
                travel = np.linalg.norm(points@r1.T+p1-points@r0.T-p0, axis=1).max()
                self.assertLessEqual(travel, (hi-lo)*bounds[group]+1e-12)

    def test_invalid_quaternions_are_rejected(self):
        for quaternion in ([0., 0., 0., 0.], [0., 0., 0., 2.]):
            with self.assertRaises(ValueError):
                fold_transforms([0., 0., 0., 0., *quaternion])


if __name__ == "__main__":
    unittest.main()
