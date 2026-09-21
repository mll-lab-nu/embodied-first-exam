"""A compound clamp needs a loaded path through both pads and every body."""
import unittest
from types import SimpleNamespace

import numpy as np

from topogym.tasks.horseshoe_ring.physical_motion import PhysicalMotion


class CompoundGraspTests(unittest.TestCase):
    def clamp(self, edges):
        motion = PhysicalMotion.__new__(PhysicalMotion)
        motion.fingers = {"right": {1, 2}}
        motion.task = SimpleNamespace(bodies={
            "lower": SimpleNamespace(base_link_idx=10),
            "upper": SimpleNamespace(base_link_idx=11)})
        motion.contacts = lambda: dict(
            link_a=np.array([a for a, b, f in edges]),
            link_b=np.array([b for a, b, f in edges]),
            force=np.array([[f, 0., 0.] for a, b, f in edges]))
        return motion

    def test_both_shoes_between_opposite_pads(self):
        motion = self.clamp([(1, 10, .2), (10, 11, 1.), (11, 2, .3)])
        self.assertTrue(motion.grasp_connected("right", ["lower", "upper"]))

    def test_dangling_shoe_is_not_clamped(self):
        motion = self.clamp([(1, 10, .2), (10, 2, .3), (10, 11, 1.)])
        self.assertFalse(motion.grasp_connected("right", ["lower", "upper"]))

    def test_unloaded_geometric_touch_is_not_a_grasp(self):
        motion = self.clamp([(1, 10, .2), (10, 11, 0.), (11, 2, .3)])
        self.assertFalse(motion.grasp_connected("right", ["lower", "upper"]))

    def test_table_support_does_not_replace_a_pad(self):
        motion = self.clamp([(1, 10, .2), (10, 11, 1.), (11, 99, 3.)])
        self.assertFalse(motion.grasp_connected("right", ["lower", "upper"]))


if __name__ == "__main__":
    unittest.main()
