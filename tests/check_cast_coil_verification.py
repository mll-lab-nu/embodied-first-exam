"""Verify collision certificates and reject endpoint-only false solutions."""
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.cast_coil.geometry import CoilAssembly
from topogym.tasks.cast_coil.physics_probe import target_at
from topogym.tasks.cast_coil.qualify import compare_profiles, evidence_matches_geometry
from topogym.tasks.cast_coil.verification import (
    VARIANTS, CompoundCollision, Motion, certify_motion, geometric_audit, prototype_route, shape_sensitivity_audit,
)


class CastCoilVerificationChecks(unittest.TestCase):
    def test_partial_pilot_results_cannot_qualify_the_full_suite(self):
        pilot = dict(cases=[dict(name="baseline_3x_route", passed=True)], config=dict(dt=.001))
        self.assertFalse(compare_profiles(pilot, pilot)["passed"])

    def test_cached_physics_cannot_qualify_a_changed_shape(self):
        assembly = CoilAssembly()
        geometry = {variant: geometric_audit(assembly) for variant in VARIANTS}
        profiles = {name: dict(config=dict(variants=VARIANTS)) for name in ("nominal", "half_dt")}
        with TemporaryDirectory() as directory:
            output = Path(directory)
            for profile in profiles:
                for variant in VARIANTS:
                    path = output/profile/"assets"/variant/"template.json"
                    path.parent.mkdir(parents=True)
                    path.write_text(json.dumps(assembly.template))
            self.assertTrue(evidence_matches_geometry(output, profiles, geometry))
            path = output/"nominal/assets/baseline_3x/template.json"
            changed = dict(assembly.template, band_width=7.5)
            path.write_text(json.dumps(changed))
            self.assertFalse(evidence_matches_geometry(output, profiles, geometry))

    def test_oriented_sat_detects_overlap_after_quarter_plane_rotation(self):
        cube = np.array([[[-1., -1., -1.], [1., 1., 1.]]])
        collision = CompoundCollision(cube, cube)
        R = Rotation.from_euler("z", 45, degrees=True).as_matrix()
        self.assertAlmostEqual(collision.gap(R, [2.6, 0., 0.]), 2.6-1-np.sqrt(2))
        self.assertLess(collision.gap(R, [2.3, 0., 0.]), 0)

    def test_clear_endpoints_do_not_certify_a_path_through_an_obstacle(self):
        a = np.array([[[2., 0., 0.], [3., 1., 1.]]])
        b = np.array([[[0., 0., 0.], [1., 1., 1.]]])
        collision = CompoundCollision(a, b)
        motion = Motion("tunnel", 1., np.eye(3), np.zeros(3), np.array([4., 0., 0.]))
        self.assertGreater(collision.gap(*motion.pose(0)), 0)
        self.assertGreater(collision.gap(*motion.pose(1)), 0)
        result = certify_motion(collision, motion, margin_m=.001)
        self.assertFalse(result["passed"])
        self.assertLess(result["witness"]["gap_m"], 0)

    def test_prototype_path_is_continuously_certified_but_not_official(self):
        result = geometric_audit(CoilAssembly())
        self.assertTrue(result["prototype_route_certified"])
        self.assertFalse(result["official_route_verified"])
        self.assertFalse(result["global_unsolvability_claim"])
        self.assertEqual(len(result["source"]["steps_zh"]), 8)
        self.assertEqual(len(result["route"]), 3)
        for segment in result["route"]:
            self.assertGreater(segment["certified_intervals"], 1)
            self.assertGreaterEqual(segment["certified_separation_lower_bound_m"], segment["margin_m"])
        self.assertFalse(result["opposite_turn_negative_control"]["passed"])
        self.assertTrue(all(not r["passed"] for r in result["straight_extraction_controls"]))

    def test_similarity_scale_preserves_route_margin(self):
        a, b = geometric_audit(CoilAssembly(scale=2)), geometric_audit(CoilAssembly(scale=3))
        for x, y in zip(a["route"], b["route"]):
            self.assertAlmostEqual(y["minimum_sample_sat_gap_m"]/x["minimum_sample_sat_gap_m"], 1.5)

    def test_valid_initial_geometry_does_not_qualify_an_altered_shape_route(self):
        for result in shape_sensitivity_audit():
            self.assertTrue(result["initial_geometry_valid"])
            self.assertFalse(result["existing_route_reusable"])
            self.assertFalse(result["qualified_variant"])
            self.assertFalse(result["global_unsolvability_claim"])

    def test_controller_feedforward_matches_material_point_derivative(self):
        assembly = CoilAssembly()
        route = prototype_route(assembly)
        center = np.array([.001, .004, -.003])
        for seconds in (.35, 1.9, 3.3, 5.7):
            R, p, v, w, _ = target_at(route, seconds)
            eps = 1e-5
            R0, p0, *_ = target_at(route, seconds-eps)
            R1, p1, *_ = target_at(route, seconds+eps)
            numerical = (p1+R1@center-p0-R0@center)/(2*eps)
            np.testing.assert_allclose(v+np.cross(w, R@center), numerical, atol=1e-8)
        for junction in (0., 1.5, 4.5, 7.):
            _, _, v, w, _ = target_at(route, junction)
            np.testing.assert_allclose(v, 0., atol=1e-12)
            np.testing.assert_allclose(w, 0., atol=1e-12)


if __name__ == "__main__":
    unittest.main()
