"""Check the numerical search and reject empty-space official-route padding."""
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.cast_coil.geometry import CoilAssembly
from topogym.tasks.cast_coil.official_trial import PoseFamily, PrefixFamily, audit_candidate
from topogym.tasks.cast_coil.verification import CompoundCollision


class OfficialCoilTrialChecks(unittest.TestCase):
    def test_precomputed_sat_agrees_with_independent_pose_evaluator(self):
        assembly = CoilAssembly(scale=1.)
        boxes = [b.boxes/assembly.unit for b in assembly.bodies]
        rotations = np.concatenate((np.eye(3)[None], Rotation.from_euler('xyz', [[90, 0, 0], [0, -90, 0]], degrees=True).as_matrix(),
                                    Rotation.random(12, random_state=71).as_matrix()))
        translations = np.random.default_rng(71).uniform(-35, 35, (len(rotations), 3))
        reference = CompoundCollision(*boxes)
        family = PoseFamily(boxes, rotations)
        expected = [reference.gap(R, p) for R, p in zip(rotations, translations)]
        np.testing.assert_allclose(family.gaps(translations), expected, atol=1e-10)

    def test_coordinate_plane_guard_detects_complete_early_exit(self):
        cube = np.array([[[-1., -1., -1.], [1., 1., 1.]]])
        family = PoseFamily([cube, cube], np.repeat(np.eye(3)[None], 3, axis=0))
        gaps = family.separating_plane_gaps(np.array([[0, 0, 0], [3, 0, 0], [0, 0, -3]]))
        np.testing.assert_allclose(gaps, [-2, 1, 1])

    def test_collision_free_prefix_is_rejected_if_already_disassembled(self):
        assembly = CoilAssembly()
        family = PrefixFamily(assembly, -1, 1, 0, -1)
        # An unconstrained search found these poses by separating at step 3.
        values = [10.64513786684833, 11.993978472663704, 6.514384377905407,
                  39.454397997776965, -14.759427329794349, -16.665497347239654]
        result = audit_candidate(assembly, family, values)
        self.assertTrue(all(c['passed'] for c in result['continuous_certificates']))
        self.assertTrue(result['premature_full_separation'])
        self.assertFalse(result['prefix_passed'])
        self.assertFalse(result['full_eight_step_route_verified'])

    def test_four_moves_join_without_pose_jumps(self):
        family = PrefixFamily(CoilAssembly(), -1, 1, 0, 1)
        motions = family.motions([8., 10., 7., 12., 3., -13.])
        for first, second in zip(motions, motions[1:]):
            R1, p1 = first.pose(1.)
            R2, p2 = second.pose(0.)
            np.testing.assert_allclose(R1, R2, atol=1e-12)
            np.testing.assert_allclose(p1, p2, atol=1e-12)


if __name__ == '__main__':
    unittest.main()
