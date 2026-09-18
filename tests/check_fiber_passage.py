"""Passage diagnostics distinguish passing through the hole from bypassing it."""
import unittest

import numpy as np

from topogym.tasks.fiber_bundling.assess_passage import final_crossings


class PassageChecks(unittest.TestCase):
    def crossings(self, points):
        points = np.asarray(points, dtype=float)[:, None, :]
        return final_crossings(np.arange(len(points)), points, np.zeros(3))

    def test_direct_passage(self):
        found, radius, times = self.crossings([[-1, .002, .003], [1, .002, .003]])
        self.assertTrue(found.all())
        self.assertAlmostEqual(radius[0], np.hypot(.002, .003))
        self.assertAlmostEqual(times[0], .5)

    def test_bypass_does_not_become_an_aperture_passage_by_moving_inward_afterward(self):
        found, radius, _ = self.crossings([[-1, .05, 0], [1, .05, 0], [1, 0, 0]])
        self.assertTrue(found.all())
        self.assertGreater(radius[0], .0135)

    def test_retracted_attempt_can_be_followed_by_valid_passage(self):
        found, radius, times = self.crossings([[-1, .05, 0], [1, .05, 0], [-1, 0, 0], [1, 0, 0]])
        self.assertTrue(found.all())
        self.assertEqual(radius[0], 0)
        self.assertAlmostEqual(times[0], 2.5)

    def test_no_forward_crossing_is_not_inferred_from_final_side(self):
        found, _, _ = self.crossings([[1, 0, 0], [2, 0, 0]])
        self.assertFalse(found.any())


if __name__ == "__main__":
    unittest.main()
