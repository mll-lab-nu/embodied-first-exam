"""Single-parameter appearance experiments must inherit the original route."""

import unittest
import numpy as np

from topogym.tasks.cast_coil.appearance import (
    PRESETS,
    create_template,
    coordinate_scale,
)
from topogym.tasks.cast_coil.geometry import CoilAssembly, geometry_report
from topogym.tasks.cast_coil.verification import (
    assembly_route,
    prototype_route,
    CompoundCollision,
    certify_motion,
)


class AppearanceChecks(unittest.TestCase):
    def test_each_preset_changes_one_parameter_of_original_seed(self):
        seed = CoilAssembly()
        for kind in PRESETS:
            t = create_template(kind)
            self.assertNotIn("inverse_design", t)
            self.assertEqual(
                t["appearance_design"]["seed_template_id"], seed.template["template_id"]
            )
            self.assertEqual(len(t["appearance_design"]["changed_parameters"]), 1)
            a = CoilAssembly(t)
            self.assertTrue(geometry_report(a)["passed"])
            for body, original in zip(a.bodies, seed.bodies):
                ratio = body.visual.volume / original.visual.volume
                self.assertGreaterEqual(ratio, 0.9 - 1e-9)
                self.assertLessEqual(ratio, 1.1 + 1e-9)

    def test_full_motion_is_affine_image_not_only_scaled_endpoints(self):
        seed = CoilAssembly()
        for kind in PRESETS:
            a = CoilAssembly(create_template(kind))
            scale = coordinate_scale(a.template)
            A = np.diag(scale)
            for old, new in zip(prototype_route(seed), assembly_route(a)):
                for u in np.linspace(0, 1, 13):
                    R, t = old.pose(u)
                    Rnew, tnew = new.pose(u)
                    np.testing.assert_allclose(Rnew, R, atol=1e-14)
                    np.testing.assert_allclose(A @ R, R @ A, atol=1e-14)
                    np.testing.assert_allclose(tnew, A @ t, atol=1e-14)

    def test_all_three_preserve_continuous_baseline_solution(self):
        for kind in PRESETS:
            a = CoilAssembly(create_template(kind))
            collision = CompoundCollision(*(b.boxes for b in a.bodies))
            self.assertTrue(
                all(
                    certify_motion(collision, m, margin_m=0.0002)["passed"]
                    for m in assembly_route(a)
                )
            )


if __name__ == "__main__":
    unittest.main()
