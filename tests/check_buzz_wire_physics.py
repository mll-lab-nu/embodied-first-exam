"""Regression checks for fixture control coordinates and evidence timelines."""

import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.buzz_wire_3d.geometry import generate_assets
from topogym.tasks.buzz_wire_3d.physics import PhysicsSettings, wrench_command
from topogym.tasks.buzz_wire_3d.render import physics_signature, select_frames


class BuzzWirePhysicsChecks(unittest.TestCase):
    def test_rotated_ring_receives_restoring_body_torque(self):
        # At a 90-degree world yaw, a world-X correction is body -Y.
        # Passing world torque straight to a free joint drives the wrong axis.
        rotation = Rotation.from_euler("z", 90, degrees=True)
        target = Rotation.from_rotvec([0.1, 0.0, 0.0]) * rotation
        zero = np.zeros(3)
        command = wrench_command(
            PhysicsSettings(),
            0.0,
            zero,
            np.eye(3) * 0.001,
            zero,
            rotation,
            zero,
            zero,
            zero,
            target,
            zero,
            zero,
        )
        np.testing.assert_allclose(command[3:], [0.0, -0.0225, 0.0], atol=1e-12)

    def test_gravity_support_in_any_orientation(self):
        rotation = Rotation.from_euler("xyz", [31, -23, 65], degrees=True)
        com = np.array([0.022, 0.0, 0.0])
        zero = np.zeros(3)
        command = wrench_command(
            PhysicsSettings(),
            0.12,
            com,
            np.eye(3) * 0.001,
            zero,
            rotation,
            zero,
            zero,
            zero,
            rotation,
            zero,
            zero,
        )
        # Net torque about COM must vanish when the controller holds still.
        net = rotation.apply(command[3:]) - np.cross(rotation.apply(com), command[:3])
        np.testing.assert_allclose(net, zero, atol=1e-12)
        np.testing.assert_allclose(command[:3], [0.0, 0.0, 0.12 * 9.81], atol=1e-12)

    def test_wrench_limits(self):
        s = PhysicsSettings()
        zero = np.zeros(3)
        q = Rotation.from_euler("xyz", [22, 70, 31], degrees=True)
        command = wrench_command(
            s,
            0.12,
            np.array([0.02, 0.0, 0.0]),
            np.eye(3) * 0.001,
            zero,
            q,
            zero,
            zero,
            np.ones(3) * 100,
            Rotation.identity(),
            np.ones(3) * 100,
            np.ones(3) * 100,
        )
        self.assertLessEqual(np.abs(command[:3]).max(), s.max_force_N)
        self.assertLessEqual(np.abs(command[3:]).max(), s.max_torque_Nm)

    def test_video_uses_only_uniform_measured_states(self):
        rows = [dict(time_s=i * 0.02, step=i * 5) for i in range(51)]
        self.assertEqual(
            [r["step"] for r in select_frames(rows, 25)], list(range(0, 251, 10))
        )
        with self.assertRaisesRegex(ValueError, "not represented"):
            select_frames(rows, 30)
        with self.assertRaises(ValueError):
            select_frames(rows[1:], 25)

    def test_visual_colors_do_not_change_physics(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            generate_assets(folder)
            path = folder / "wand.urdf"
            before = physics_signature(path)
            tree = ET.parse(path)
            palette = {}
            for material in tree.findall(".//visual/material"):
                color = material.find("color").get("rgba")
                name = material.get("name")
                self.assertEqual(palette.setdefault(name, color), color)
                material.set("name", "renamed_" + name)
            self.assertEqual(len(palette), 2)
            tree.write(path)
            self.assertEqual(before, physics_signature(path))
            tree.find(".//collision/geometry/cylinder").set("radius", "0.5")
            tree.write(path)
            self.assertNotEqual(before, physics_signature(path))


if __name__ == "__main__":
    unittest.main()
