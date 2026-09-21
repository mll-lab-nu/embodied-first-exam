"""Spatial wire feasibility, negative controls, and exported collision identity."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from hydra import compose, initialize_config_dir
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.buzz_wire_3d.geometry import (
    BuzzWireLayout,
    SpatialWire,
    generate_assets,
)
from topogym.tasks.buzz_wire_3d.verification import ClearanceOracle, verify_route


class SpatialBuzzWireChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wire = SpatialWire()
        cls.report = verify_route(cls.wire)

    def test_entire_tool_continuously_fits_and_stays_threaded(self):
        self.assertTrue(self.report["passed"], self.report)
        self.assertGreater(
            self.report["minimum_continuous_clearance_lower_bound_m"], 0.010
        )
        self.assertEqual(self.report["linking_numbers"], [1])
        self.assertGreater(self.report["best_fit_plane_rms_m"], 0.05)
        self.assertFalse(self.report["physical_execution_verified"])
        self.assertFalse(self.report["robot_reachability_verified"])

    def test_wall_touch_and_wrong_orientation_are_rejected(self):
        oracle = ClearanceOracle(self.wire)
        p, q = self.wire.pose(0.5)
        r = Rotation.from_quat(q[[1, 2, 3, 0]])
        self.assertGreater(oracle.clearance(p, r), 0.01)
        self.assertLess(oracle.clearance(p + r.apply([0.024, 0, 0]), r), 0)
        self.assertLess(
            oracle.clearance(p, r * Rotation.from_euler("y", 90, degrees=True)), 0
        )

    def test_flattened_and_low_routes_do_not_qualify(self):
        flat = verify_route(SpatialWire(replace(BuzzWireLayout(), depth_scale=0.001)))
        self.assertFalse(flat["passed"])
        self.assertFalse(flat["checks"]["genuinely_spatial"])
        low = verify_route(SpatialWire(replace(BuzzWireLayout(), height_scale=0.1)))
        self.assertFalse(low["passed"])
        self.assertFalse(low["checks"]["continuous_tool_clearance"])

    def test_bad_apertures_end_stops_footprints_and_inputs_rejected(self):
        for values in [
            dict(wire_radius_m=0.03),
            dict(end_stop_radius_m=0.01),
            dict(base_size_m=(0.3, 0.3, 0.05)),
            dict(height_scale=float("nan")),
            dict(rail_segment_m=0.08),
            dict(end_reserve_m=10.0),
            dict(template_id="unknown"),
            dict(spiral_exit_roll_deg=float("nan")),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                SpatialWire(replace(BuzzWireLayout(), **values))
        for u in [-0.01, 1.01, float("nan")]:
            with self.assertRaises(ValueError):
                self.wire.pose(u)

    def test_exported_capsules_match_the_verified_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            wire, report = generate_assets(folder)
            for filename, capsules in [
                ("wire.urdf", wire.fixed_capsules()),
                ("wand.urdf", wire.layout.tool_capsules()),
            ]:
                root = ET.parse(folder / filename)
                self.assertEqual(len(root.findall("link")), 1)
                self.assertEqual(root.findall("joint"), [])
                collisions = iter(root.findall(".//collision"))
                for a, b, r, _ in capsules:
                    expected = []
                    if np.linalg.norm(b - a) > 1e-12:
                        node = next(collisions)
                        cylinder = node.find("geometry/cylinder")
                        self.assertAlmostEqual(float(cylinder.get("radius")), r)
                        self.assertAlmostEqual(
                            float(cylinder.get("length")), np.linalg.norm(b - a)
                        )
                        origin = node.find("origin")
                        center = np.fromstring(origin.get("xyz"), sep=" ")
                        rotation = Rotation.from_euler(
                            "xyz", np.fromstring(origin.get("rpy"), sep=" ")
                        )
                        np.testing.assert_allclose(center, (a + b) / 2, atol=1e-10)
                        np.testing.assert_allclose(
                            rotation.apply([0, 0, 1]),
                            (b - a) / np.linalg.norm(b - a),
                            # acos-based URDF axes lose tiny lateral components
                            # on the long vertical runs; <0.2 nm at segment scale.
                            atol=2e-8,
                        )
                        expected = [a, b]
                    else:
                        expected = [a]
                    for point in expected:
                        node = next(collisions)
                        self.assertAlmostEqual(
                            float(node.find("geometry/sphere").get("radius")), r
                        )
                        np.testing.assert_allclose(
                            np.fromstring(node.find("origin").get("xyz"), sep=" "),
                            point,
                            atol=1e-10,
                        )
                self.assertIsNone(next(collisions, None))
            self.assertGreater(report["wand_mass_kg"], 0)
            self.assertTrue(
                np.all(np.linalg.eigvalsh(report["wand_inertia_kg_m2"]) > 0)
            )
            stored = np.load(folder / "reference_path.npz")
            np.testing.assert_allclose(stored["positions"], wire.positions)
            np.testing.assert_allclose(
                stored["quaternions_wxyz"], wire.rotations.as_quat()[:, [3, 0, 1, 2]]
            )

    def test_reference_frames_and_configuration_restore(self):
        for i in range(0, len(self.wire.progress), 40):
            p, q = self.wire.pose(float(self.wire.progress[i]))
            np.testing.assert_allclose(p, self.wire.positions[i])
            normal = Rotation.from_quat(q[[1, 2, 3, 0]]).apply([0, 0, 1])
            if 0 < i < len(self.wire.progress) - 1:
                direction = self.wire.positions[i + 1] - self.wire.positions[i - 1]
                direction /= np.linalg.norm(direction)
                np.testing.assert_allclose(normal, direction, atol=0.002)
        with initialize_config_dir(
            version_base="1.3",
            config_dir=str(Path(__file__).resolve().parents[1] / "configs"),
        ):
            cfg = compose(config_name="buzz_wire_3d_preview")
        from omegaconf import OmegaConf

        restored = SpatialWire(
            BuzzWireLayout(**OmegaConf.to_container(cfg.task.geometry, resolve=True))
        )
        np.testing.assert_array_equal(restored.rail, self.wire.rail)
        np.testing.assert_array_equal(restored.positions, self.wire.positions)
        self.assertFalse(cfg.run.include_robot)

    def test_optional_flat_stop_stays_captive_inside_clearance_cover(self):
        layout = replace(BuzzWireLayout(), end_stop_shape="flat_finish")
        with tempfile.TemporaryDirectory() as directory:
            wire, _ = generate_assets(directory, layout)
            stop = [c for c in wire.fixed_capsules() if c[3] == "stop"][-1]
            node = ET.parse(Path(directory) / "wire.urdf").findall(".//collision")[-1]
            cylinder = node.find("geometry/cylinder")
            radius = float(cylinder.get("radius"))
            half_height = float(cylinder.get("length")) / 2
            self.assertGreater(radius, layout.loop_radius_m - layout.loop_tube_radius_m)
            self.assertLessEqual(np.hypot(radius, half_height), stop[2])
            np.testing.assert_allclose(
                np.fromstring(node.find("origin").get("xyz"), sep=" "), stop[0]
            )
        for bad in (
            replace(layout, end_stop_thickness_m=0.10),
            replace(layout, end_stop_radius_m=0.0232),
        ):
            with self.assertRaises(ValueError):
                bad.validate()

    def test_spiral_exit_requires_grip_clearance(self):
        unturned = SpatialWire(replace(BuzzWireLayout(), spiral_exit_roll_deg=0.0))
        report = verify_route(unturned)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["continuous_tool_clearance"])
        self.assertLess(report["minimum_pose_clearance_lower_bound_m"], 0.0)
        self.assertEqual(
            list(self.wire.sections),
            ["horizontal_switchbacks", "vertical_switchbacks", "spiral"],
        )

    def test_previous_slalom_remains_reproducible(self):
        old = SpatialWire(
            replace(
                BuzzWireLayout(),
                template_id="spatial_slalom_v1",
                base_size_m=(0.84, 0.64, 0.05),
            )
        )
        self.assertAlmostEqual(old.length, 1.8690504482929389, places=10)
        self.assertTrue(verify_route(old)["passed"])


if __name__ == "__main__":
    unittest.main()
