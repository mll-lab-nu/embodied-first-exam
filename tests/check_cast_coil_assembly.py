"""Assembly starts separated in both axes and ends assembled after release."""

import unittest
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.cast_coil.assembly_task import (
    initial_poses,
    motions,
    goal_metrics,
    xy_surface_gaps,
    ASSEMBLY_PHASES,
)
from topogym.tasks.cast_coil.geometry import CoilAssembly
from topogym.tasks.cast_coil.robot_archive import qualify_report, REQUIRED_PHASES
from tests.check_cast_coil_robot import completed_recording


class AssemblyChecks(unittest.TestCase):
    def test_separated_initial_state_and_continuous_reverse_route(self):
        assembly = CoilAssembly()
        initial = initial_poses(
            assembly,
            np.array([0, 0.05, 0.051]),
            Rotation.from_euler("z", 90, degrees=True),
        )
        self.assertGreater(min(xy_surface_gaps(assembly, initial)), 0.01)
        for body, (r, p) in zip(assembly.bodies, initial):
            self.assertAlmostEqual(
                (r.apply(body.visual.vertices) + p)[:, 2].min(), 0, places=12
            )
        route, certificates = motions(assembly, initial)
        self.assertTrue(all(c["passed"] for c in certificates))
        for a, b in zip(route, route[1:]):
            for x, y in zip(a.pose(1), b.pose(0)):
                np.testing.assert_allclose(x, y, atol=1e-14)
        r, t = route[-1].pose(1)
        np.testing.assert_allclose(r, np.eye(3), atol=1e-14)
        np.testing.assert_allclose(t, np.zeros(3), atol=1e-14)

    def test_only_one_separated_axis_is_rejected(self):
        with self.assertRaises(ValueError):
            initial_poses(CoilAssembly(), np.zeros(3), Rotation.identity(), [0, 0.2])

    def test_nearby_wrong_orientation_is_not_assembled(self):
        self.assertFalse(
            goal_metrics(
                np.zeros(3),
                Rotation.identity(),
                np.zeros(3),
                Rotation.from_euler("y", 90, degrees=True),
            )["goal_assembled"]
        )
        self.assertFalse(
            goal_metrics(
                np.zeros(3),
                Rotation.identity(),
                np.array([0.02, 0, 0]),
                Rotation.identity(),
            )["goal_assembled"]
        )

    def test_old_successful_disassembly_cannot_qualify_as_assembly(self):
        r = completed_recording()
        r["objective"] = "assemble"
        with self.assertRaises(ValueError):
            qualify_report(r)
        r.update(
            goal_assembled=True,
            final_relative_position_error_m=0.0001,
            final_relative_rotation_error_rad=0.001,
            initial_xy_surface_gap_m=[0.08, 0.078],
        )
        phases = (
            REQUIRED_PHASES
            - {
                "prototype_slide",
                "prototype_quarter_turn",
                "prototype_extract",
                "place_silver",
                "place_gold",
            }
        ) | ASSEMBLY_PHASES
        r["phases"] = [dict(name=p) for p in phases]
        qualify_report(r)
        r["initial_xy_surface_gap_m"] = [0, 0.1]
        with self.assertRaises(ValueError):
            qualify_report(r)


if __name__ == "__main__":
    unittest.main()
