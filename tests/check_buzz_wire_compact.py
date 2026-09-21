"""Compact geometry preserves motifs; wood/metal meshes retain collision solids."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
import trimesh

from topogym.tasks.buzz_wire_3d.compact import scaled_layout
from topogym.tasks.buzz_wire_3d.geometry import (
    BuzzWireLayout,
    SpatialWire,
    generate_assets,
)
from topogym.tasks.buzz_wire_3d.robot_render import physics_signature
from topogym.tasks.buzz_wire_3d.verification import ClearanceOracle


class CompactBuzzWireChecks(unittest.TestCase):
    def test_toy_plinth_and_mounts_fit_conservative_collision_covers(self):
        from topogym.tasks.buzz_wire_3d.appearance import plinth_layers
        from topogym.tasks.buzz_wire_3d.robot_plan import config
        from omegaconf import OmegaConf

        size = np.array([0.5201, 0.3689, 0.0175])
        for mesh in plinth_layers(size):
            self.assertTrue(mesh.is_watertight and mesh.is_convex)
            self.assertTrue(np.all(abs(mesh.vertices) <= size / 2 + 1e-12))
        layout = replace(
            scaled_layout(
                BuzzWireLayout(
                    **OmegaConf.to_container(config().task.geometry, resolve=True)
                ),
                0.7,
            ),
            finish="toy_wood_copper",
            end_stop_shape="block_mount",
            end_stop_radius_m=0.023,
            mount_size_m=(0.030, 0.030, 0.014),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wire, _ = generate_assets(root, layout)
            stops = [row for row in wire.fixed_capsules() if row[3] == "stop"]
            collisions = ET.parse(root / "wire.urdf").findall(".//collision")[-2:]
            for (center, _, radius, _), node in zip(stops, collisions):
                exported = np.fromstring(node.find("geometry/box").get("size"), sep=" ")
                position = np.fromstring(node.find("origin").get("xyz"), sep=" ")
                np.testing.assert_allclose(position, center)
                self.assertLessEqual(np.linalg.norm(exported / 2), radius)
                self.assertGreater(
                    min(exported[:2]) / 2,
                    layout.loop_radius_m - layout.loop_tube_radius_m,
                )
            base = trimesh.load(root / "base_wood.glb", force="mesh")
            self.assertTrue(np.all((base.visual.uv >= 0) & (base.visual.uv <= 1)))
            self.assertEqual(
                len(ET.parse(root / "base.urdf").findall(".//collision")), 2
            )

    def test_uniform_scale_preserves_track_tool_and_stages(self):
        original = BuzzWireLayout()
        compact = scaled_layout(original, 0.7)
        before, after = SpatialWire(original), SpatialWire(compact)
        np.testing.assert_allclose(after.rail, before.rail * 0.7, atol=1e-12)
        np.testing.assert_allclose(after.positions, before.positions * 0.7, atol=1e-12)
        self.assertEqual(list(after.sections), list(before.sections))
        self.assertAlmostEqual(after.length, before.length * 0.7)
        for left, right in zip(original.tool_capsules(), compact.tool_capsules()):
            np.testing.assert_allclose(
                np.r_[right[0], right[1], right[2]],
                np.r_[left[0], left[1], left[2]] * 0.7,
            )
        # New end posts must participate in collision checks, not just the render.
        with_posts = SpatialWire(
            replace(compact, post_radius_m=0.011, post_height_m=0.04)
        )
        posts = [row for row in with_posts.fixed_capsules() if row[3] == "post"]
        self.assertEqual(len(posts), 2)
        from scipy.spatial.transform import Rotation

        self.assertLess(
            ClearanceOracle(with_posts).clearance(posts[0][0], Rotation.identity()), 0
        )

    def test_materials_have_uvs_and_wire_collision_is_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = scaled_layout(BuzzWireLayout(), 0.7)
            _, old = generate_assets(root / "legacy", layout)
            _, new = generate_assets(
                root / "wood", replace(layout, finish="wood_metal")
            )
            self.assertEqual(
                physics_signature(root / "legacy/wire.urdf"),
                physics_signature(root / "wood/wire.urdf"),
            )
            self.assertNotEqual(old["wand_mass_kg"], new["wand_mass_kg"])
            for name in ("base_wood", "posts_wood", "handle_wood"):
                mesh = trimesh.load(root / f"wood/{name}.glb", force="mesh")
                self.assertIsNotNone(mesh.visual.material.baseColorTexture)
                self.assertGreater(np.ptp(mesh.visual.uv), 0.1)
            for name in ("rail_metal", "ring_copper"):
                mesh = trimesh.load(root / f"wood/{name}.glb", force="mesh")
                self.assertGreater(mesh.visual.material.metallicFactor, 0.8)
            for name in ("wire", "wand"):
                a = ET.parse(root / f"legacy/{name}.urdf").findall(".//collision")
                b = ET.parse(root / f"wood/{name}.urdf").findall(".//collision")
                for node in a + b:
                    node.tail = None
                self.assertEqual(
                    [ET.tostring(x) for x in a], [ET.tostring(x) for x in b]
                )


if __name__ == "__main__":
    unittest.main()
