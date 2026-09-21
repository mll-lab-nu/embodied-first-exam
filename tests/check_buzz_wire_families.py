"""Multistage export contracts, original morphology and reusable pose witnesses."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.buzz_wire_3d.family_plan import construct, search
from topogym.tasks.buzz_wire_3d.geometry import BuzzWireLayout, SpatialWire
from topogym.tasks.buzz_wire_3d.verification import verify_route


class FamilyGeometryChecks(unittest.TestCase):
    def test_double_arch_identity_and_release_posts(self):
        from scipy.signal import find_peaks

        from topogym.tasks.buzz_wire_3d.compact import scaled_layout

        _, layout, _ = construct("F1")
        route = SpatialWire(scaled_layout(layout, 0.7))
        peaks, _ = find_peaks(route.rail[:, 2], prominence=0.050)
        valleys, _ = find_peaks(-route.rail[:, 2], prominence=0.050)
        self.assertEqual(len(peaks), 2)
        self.assertEqual(len(valleys), 1)
        self.assertGreater(np.ptp(route.rail[:, 1]), 0.069)
        np.testing.assert_allclose(route.rail[peaks, 2], 0.175, atol=0.0001)
        np.testing.assert_allclose(route.rail[valleys, 2], 0.056, atol=0.0001)
        self.assertEqual(
            list(route.sections),
            ["start_post", "arch_1", "valley_1", "arch_2", "finish_post"],
        )
        # The playable route covers both crests and the valley; release happens
        # on a descending straight post with room for passive gravity settling.
        self.assertGreater(route.sections["arch_1"]["end_progress"], 0)
        self.assertLess(route.sections["arch_2"]["end_progress"], 1)
        np.testing.assert_allclose(route.positions[-1, :2], route.rail[-1, :2])
        np.testing.assert_allclose(route.positions[-1, :2], route.positions[-2, :2])
        self.assertLess(route.positions[-1, 2], route.positions[-2, 2])

    def test_pose_reference_cannot_substitute_different_wire_solids(self):
        _, layout, _ = construct("F2", 0.018)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            reference = path / "reference.json"
            reference.write_text(
                json.dumps({"layout": asdict(replace(layout, wire_radius_m=0.0015))})
            )
            with self.assertRaisesRegex(ValueError, "identical physical geometry"):
                search(
                    "F2",
                    path / "rejected",
                    samples=2,
                    smoothing_m=0.018,
                    pose_reference=reference,
                )

    def test_stage_order_and_supported_endpoints(self):
        for family, stages in [
            ("F2", ["entry_comb", "layered_eight", "front_vertical_w"]),
            ("F3", ["entry_comb", "upright_w", "side_omega", "tilted_coil"]),
        ]:
            with self.subTest(family=family):
                cfg, layout, spec = construct(family)
                route = SpatialWire(layout)
                self.assertEqual(
                    list(route.sections),
                    ["start_post", *stages, "exit_bend", "finish_post"],
                )
                self.assertLess(route.rail[:, 2].max(), 0.30)
                self.assertGreater(route.length, 2.5)
                self.assertEqual(cfg.robot_demo.release_progress, 1.0)
                np.testing.assert_allclose(
                    route.positions[-1, :2], route.rail[-1, :2], atol=1e-5
                )
                self.assertEqual(layout.loop_radius_m, 0.022)
                self.assertEqual(layout.grip_length_m, 0.0436)

    def test_authored_pose_knots_interpolate_without_changing_wire(self):
        _, layout, _ = construct("F2")
        rotations = Rotation.from_euler(
            "z", np.array([0, 60, 90])[:, None], degrees=True
        )
        knots = [
            [u, *q] for u, q in zip([0, 0.5, 1], rotations.as_quat()[:, [3, 0, 1, 2]])
        ]
        original = SpatialWire(layout)
        edited = SpatialWire(replace(layout, orientation_knots_wxyz=knots))
        np.testing.assert_array_equal(original.rail, edited.rail)
        r = Rotation.from_quat(edited.pose(0.5)[1][[1, 2, 3, 0]])
        self.assertLess((r.inv() * rotations[1]).magnitude(), 1e-4)

    def test_malformed_authored_inputs_rejected(self):
        _, layout, _ = construct("F3")
        for bad in [
            replace(layout, authored_controls_m=[[0, 0, 0]] * 4),
            replace(layout, authored_section_ends=[["a", 1.5]]),
            replace(layout, authored_section_ends=[["a", 1], ["a", 2]]),
            replace(layout, orientation_knots_wxyz=[[0, 1, 0, 0, 0], [1, 2, 0, 0, 0]]),
            replace(
                layout, orientation_knots_wxyz=[[0.1, 1, 0, 0, 0], [1, 1, 0, 0, 0]]
            ),
        ]:
            with self.assertRaises(ValueError):
                bad.validate()

    def test_ring_center_offsets_do_not_move_the_wire_or_supports(self):
        _, layout, _ = construct("F2", 0.018)
        original = SpatialWire(layout)
        shifted = SpatialWire(
            replace(
                layout,
                center_offset_knots_m=[
                    [0, 0, 0, 0],
                    [0.5, 0.004, -0.003, 0],
                    [1, 0, 0, 0],
                ],
            )
        )
        np.testing.assert_array_equal(shifted.rail, original.rail)
        self.assertEqual(shifted.sections, original.sections)
        np.testing.assert_allclose(shifted.pose(0)[0], original.pose(0)[0])
        np.testing.assert_allclose(shifted.pose(1)[0], original.pose(1)[0])
        np.testing.assert_allclose(
            shifted.pose(0.5)[0] - original.pose(0.5)[0], [0.004, -0.003, 0], atol=1e-6
        )
        for offsets in (
            [[0, 0, 0, 0], [1, 0.016, 0, 0]],
            [[0.1, 0, 0, 0], [1, 0, 0, 0]],
            [[0, 0, 0, 0], [0.5, 0, 0, 0], [0.4, 0, 0, 0], [1, 0, 0, 0]],
        ):
            with self.assertRaises(ValueError):
                replace(layout, center_offset_knots_m=offsets).validate()

    def test_continuous_check_rejects_an_obstacle_between_clear_rotations(self):
        layout = BuzzWireLayout(clearance_cover_m=0.0005)
        center = np.array([0.0, 0.0, 0.20])
        rail = np.array([[0.0, 0.0, 0.05], [0.0, 0.0, 0.35], [0.1, 0.0, 0.05]])
        fixed = [(rail[0], rail[1], layout.wire_radius_m, "guide")]
        route = SimpleNamespace(
            layout=layout,
            rail=rail,
            positions=np.array([center, center]),
            rotations=Rotation.from_euler("z", np.array([-0.6, 0.6])[:, None]),
            fixed_capsules=lambda: fixed,
        )
        clear = verify_route(route)
        self.assertTrue(clear["checks"]["continuous_tool_clearance"])
        self.assertGreater(clear["adaptive_midpoint_evaluations"], 0)
        obstacle = center + [0.08, 0.0, 0.0]
        fixed.append((obstacle, obstacle, 0.002, "obstacle"))
        blocked = verify_route(route)
        self.assertFalse(blocked["checks"]["continuous_tool_clearance"])
        self.assertLess(blocked["minimum_pose_clearance_lower_bound_m"], 0.0)


if __name__ == "__main__":
    unittest.main()
