"""Reject sampled-only and initially detached independent-body witnesses."""
from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np

from topogym.tasks.horseshoe_ring.geometry import load_template
from topogym.tasks.horseshoe_ring.independent_motion import IndependentWitness, interpolate


class IndependentChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1]/"assets/tasks/horseshoe_ring/tutorial_structure_v2/template.json"
        cls.model = IndependentWitness(load_template(path))
        cls.initial = {n: dict(pos=p.tolist(), quat=[0., 0., 0., 1.])
                       for n, p in zip(cls.model.names, cls.model.centers)}

    def test_safe_partial_motion_does_not_certify_extraction(self):
        end = deepcopy(self.initial)
        for pose in end.values():
            pose["pos"][2] += .003
        report = self.model.certify([self.initial, end])
        self.assertTrue(report["continuous_collision_free"])
        self.assertFalse(report["passed"])
        self.assertFalse(report["goal"]["separated"])

    def test_clear_endpoints_cannot_hide_ring_crossing_horseshoe(self):
        end = deepcopy(self.initial)
        end["target_ring"]["pos"][0] += .35
        self.assertGreater(self.model.distances(end).min(), .0001)
        self.assertTrue(self.model.goal(end)["separated"])
        report = self.model.certify([self.initial, end])
        self.assertFalse(report["passed"])
        self.assertFalse(report["continuous_collision_free"])
        self.assertTrue(report["failures"])

    def test_detached_start_and_nonunit_quaternion_are_rejected(self):
        end = deepcopy(self.initial)
        end["target_ring"]["pos"][0] += .35
        self.assertFalse(self.model.certify([end, end])["initial_matches_template"])
        end["target_ring"]["quat"][-1] = 2
        with self.assertRaisesRegex(ValueError, "unit length"):
            self.model.certify([self.initial, end])

    def test_interpolation_bounds_cover_all_surface_points(self):
        end = deepcopy(self.initial)
        end["chain_upper_1"]["pos"][0] += .015
        end["chain_upper_1"]["quat"] = [0, 0, np.sin(.7), np.cos(.7)]
        middle = interpolate(self.initial, end, .5)
        np.testing.assert_allclose(self.model.motion_bounds(self.initial, middle),
                                   self.model.motion_bounds(self.initial, end)/2, atol=1e-12)

    def test_solvable_v3_is_not_a_straight_slide_control(self):
        path = Path(__file__).resolve().parents[1]/"assets/tasks/horseshoe_ring/tutorial_solvable_v3/template.json"
        model = IndependentWitness(load_template(path))
        initial = {n: dict(pos=p.tolist(), quat=[0., 0., 0., 1.])
                   for n, p in zip(model.names, model.centers)}
        end = deepcopy(initial)
        end["target_ring"]["pos"][0] += .35
        self.assertTrue(model.goal(end)["separated"])
        self.assertGreater(model.distances(end).min(), .0001)
        report = model.certify([initial, end])
        self.assertFalse(report["passed"])
        self.assertFalse(report["continuous_collision_free"])


if __name__ == "__main__":
    unittest.main()
