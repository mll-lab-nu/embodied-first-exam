"""Independent clearance checks used by the physical stability experiment."""
import unittest

import numpy as np

from topogym.tasks.fiber_bundling.geometry import FiberLayout, segment_distance
from topogym.tasks.fiber_bundling.validation import pair_clearances


class ClearanceChecks(unittest.TestCase):
    def test_parallel_finite_rods_and_crossing(self):
        rods = np.array([[[0.,0.,0.], [1.,0.,0.]], [[0.,.1,0.], [1.,.1,0.]]])
        self.assertAlmostEqual(pair_clearances(rods, .01)[0,1], .08)
        rods[1] = [[.5,-.5,0.], [.5,.5,0.]]
        self.assertAlmostEqual(pair_clearances(rods, .01)[0,1], -.02)

    def test_vectorized_clearance_matches_scalar_exact_distance(self):
        radius = .0012
        paths = np.asarray(FiberLayout().fibers())
        actual = pair_clearances(paths, radius)
        for i, j in ((0,1), (1,4), (0,7), (2,6)):
            a, b = paths[i,:-1].copy(), paths[i,1:]
            c, d = paths[j,:-1].copy(), paths[j,1:]
            a[0] += 2.5*radius*(b[0]-a[0])/np.linalg.norm(b[0]-a[0])
            c[0] += 2.5*radius*(d[0]-c[0])/np.linalg.norm(d[0]-c[0])
            expected = min(segment_distance(x,y,z,w) for x,y in zip(a,b) for z,w in zip(c,d))-2*radius
            self.assertAlmostEqual(actual[i,j], expected, places=12)
        np.testing.assert_allclose(actual, actual.T)
        self.assertTrue(np.isinf(np.diag(actual)).all())


if __name__ == "__main__":
    unittest.main()
