"""Single-wire metrics distinguish real alignment from bypassing the ring."""
import unittest

import numpy as np

from topogym.tasks.fiber_bundling.geometry import FiberLayout
from topogym.tasks.fiber_bundling.single_strand import strand_metrics


class SingleStrandChecks(unittest.TestCase):
    def setUp(self):
        self.layout = FiberLayout()
        self.paths = np.asarray(self.layout.fibers())
        self.ring = np.array([.28, 0., 0.])

    def test_a_tip_beyond_the_ring_is_not_enough(self):
        paths = self.paths+[0., .050, 0.]
        metric = strand_metrics(paths, self.ring, self.layout)
        self.assertGreater(metric["tip_beyond_ring_m"], 0)
        self.assertFalse(metric["crosses_aperture"])
        self.assertFalse(metric["fits_aperture_projection"])

    def test_straight_wire_fits_but_outward_tip_does_not(self):
        curved = strand_metrics(self.paths, self.ring, self.layout)
        self.assertTrue(curved["crosses_aperture"])
        self.assertFalse(curved["fits_aperture_projection"])
        self.paths[0, :, 0] = np.linspace(.24, .32, 11)
        self.paths[0, :, 1:] = [.008, 0.]
        straight = strand_metrics(self.paths, self.ring, self.layout)
        self.assertTrue(straight["crosses_aperture"])
        self.assertTrue(straight["fits_aperture_projection"])
        self.assertAlmostEqual(straight["tip_angle_deg"], 0.)
        self.assertAlmostEqual(straight["axial_reach_m"], .08)

    def test_metrics_do_not_depend_on_display_world_offset(self):
        shift = np.array([-.24, .4, .66])
        a = strand_metrics(self.paths, self.ring, self.layout)
        b = strand_metrics(self.paths+shift, self.ring+shift, self.layout)
        for key in ("tip_angle_deg", "root_frame_tip_angle_deg", "axial_reach_m", "radial_envelope_m"):
            self.assertAlmostEqual(a[key], b[key])


if __name__ == "__main__":
    unittest.main()
