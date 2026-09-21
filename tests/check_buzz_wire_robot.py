"""Compact robot geometry: valid export, clearance, endpoint and physical limits."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import mujoco
import fcl
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from topogym.tasks.buzz_wire_3d.geometry import (
    BuzzWireLayout,
    SpatialWire,
    generate_assets,
)
from topogym.tasks.buzz_wire_3d.robot_plan import (
    Kinematics,
    RobotAudit,
    config,
    manager,
)
from topogym.tasks.buzz_wire_3d.verification import verify_route


class CompactBuzzWireChecks(unittest.TestCase):
    def test_signed_search_distance_includes_deeper_overlapping_pairs(self):
        robot = manager(
            [fcl.CollisionObject(fcl.Sphere(0.020), fcl.Transform([0.0, 0.0, 0.0]))]
        )
        fixture = manager(
            [
                fcl.CollisionObject(
                    fcl.Sphere(0.005), fcl.Transform([0.024999, 0.0, 0.0])
                ),
                fcl.CollisionObject(
                    fcl.Sphere(0.005), fcl.Transform([0.0, 0.018, 0.0])
                ),
            ]
        )
        self.assertAlmostEqual(
            RobotAudit.distance(robot, fixture, signed=True), -0.007, places=6
        )

    @classmethod
    def setUpClass(cls):
        cls.cfg = config()
        cls.layout = BuzzWireLayout(
            **OmegaConf.to_container(cls.cfg.task.geometry, resolve=True)
        )
        cls.route = SpatialWire(cls.layout)

    def test_entire_tilted_ring_path_has_positive_clearance(self):
        report = verify_route(self.route)
        self.assertTrue(report["passed"], report)
        self.assertGreater(report["minimum_continuous_clearance_lower_bound_m"], 0.001)
        self.assertEqual(report["linking_numbers"], [1])
        self.assertLess(self.route.rail[:, 2].max(), 0.27)
        self.assertGreater(report["best_fit_plane_rms_m"], 0.04)

    def test_box_export_is_parseable_and_inside_clearance_cover(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            _, report = generate_assets(path, self.layout)
            model = mujoco.MjModel.from_xml_path(str(path / "wand.urdf"))
            self.assertGreater(model.ngeom, 64)
            self.assertTrue(
                np.all(np.linalg.eigvalsh(report["wand_inertia_kg_m2"]) > 0)
            )
            tree = ET.parse(path / "wand.urdf")
            box = tree.find(".//collision/geometry/box")
            size = np.fromstring(box.get("size"), sep=" ")
            np.testing.assert_allclose(size, [0.0436, 0.014, 0.010])
            a, b, radius, _ = self.layout.tool_capsules()[-1]
            r = Rotation.from_euler("x", self.layout.grip_flat_roll_deg, degrees=True)
            for y in [-size[1] / 2, size[1] / 2]:
                for z in [-size[2] / 2, size[2] / 2]:
                    offset = r.apply([0, y, z])
                    self.assertLessEqual(np.linalg.norm(offset), radius + 1e-12)
            self.assertAlmostEqual(np.linalg.norm(b - a), size[0])

    def test_release_is_after_all_bends_on_terminal_post(self):
        poses = np.array(
            [
                self.route.pose(float(u))[0]
                for u in np.linspace(self.cfg.robot_demo.release_progress, 1, 200)
            ]
        )
        self.assertLess(
            np.linalg.norm(poses[:, :2] - poses[-1, :2], axis=1).max(), 0.001
        )
        self.assertTrue(np.all(np.diff(poses[:, 2]) <= 1e-8))
        self.assertLess(np.linalg.norm(self.route.rail[-1, :2] - poses[-1, :2]), 1e-4)

    def test_invalid_tilt_profiles_are_rejected(self):
        for knots in (
            [[0, 0], [1, 90]],
            [[0, 0], [0.7, 2], [0.6, 3], [1, 0]],
            [[0.1, 0], [1, 0]],
        ):
            with self.subTest(knots=knots), self.assertRaises(ValueError):
                SpatialWire(replace(self.layout, normal_tilt_knots=knots))

    def test_robot_keeps_original_physical_joint_limits(self):
        kin = Kinematics(self.cfg)
        self.assertAlmostEqual(kin.limits[6, 0], -2.8973)
        self.assertAlmostEqual(kin.limits[6, 1], 2.8973)
        self.assertAlmostEqual(kin.limits[3, 1], -0.0698)
        q = np.asarray(self.cfg.robot_demo.initial_arm_qpos)
        self.assertTrue(np.all(q > kin.limits[:, 0]))
        self.assertTrue(np.all(q < kin.limits[:, 1]))


if __name__ == "__main__":
    unittest.main()
