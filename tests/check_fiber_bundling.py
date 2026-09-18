"""Geometry and task-contract checks before the separate Genesis contact probe."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.fiber_bundling.geometry import FiberLayout, segment_distance, shape_in_root_frame, write_bundle
from topogym.tasks.fiber_bundling.scene import FiberScene


class FiberBundlingChecks(unittest.TestCase):
    def test_seed_changes_shape_but_not_roots_and_keeps_lengths(self):
        layout = FiberLayout()
        a, b, c = layout.fibers(), layout.fibers(), replace(layout, seed=13).fibers()
        np.testing.assert_array_equal(a, b)
        self.assertGreater(float(np.max(np.abs(np.array(a)-c))), .005)
        np.testing.assert_array_equal(np.array(a)[:, 0], np.array(c)[:, 0])
        np.testing.assert_allclose(np.linalg.norm(np.diff(a, axis=1), axis=-1),
                                   layout.fiber_length_m/layout.fiber_segments, atol=1e-12)
        self.assertGreater(max(np.linalg.norm(p[:, 1:], axis=1).max() for p in a), layout.ring_inner_radius_m)

    def test_invalid_packing_and_aperture_are_rejected(self):
        for change in ({"fiber_count": 30}, {"fiber_count": 3.5}, {"root_spread_m": .001},
                       {"ring_inner_radius_m": .012}, {"ring_inner_radius_m": .03},
                       {"fiber_radius_m": .004}, {"seed": -1}, {"fiber_damping": float("nan")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(FiberLayout(), **change)

    def test_segment_distance_detects_crossings_and_parallel_separation(self):
        p = np.array
        self.assertAlmostEqual(segment_distance(p([0.,0,0]), p([1.,0,0]), p([.5,-1,0]), p([.5,1,0])), 0.)
        self.assertAlmostEqual(segment_distance(p([0.,0,0]), p([1.,0,0]), p([0.,2,0]), p([1.,2,0])), 2.)

    def test_dynamic_tree_has_free_trunk_and_only_passive_fiber_joints(self):
        layout = FiberLayout()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"bundle.xml"
            write_bundle(path, layout, layout.fibers())
            root = ET.parse(path).getroot()
        self.assertEqual(len(root.findall(".//freejoint")), 1)
        self.assertIsNone(root.find("actuator"))
        fibers = [b for b in root.findall(".//body") if b.get("name").startswith("fiber_")]
        self.assertEqual(len(fibers), layout.fiber_count*layout.fiber_segments)
        for body in fibers:
            self.assertEqual(body.find("joint").get("type"), "ball")
            self.assertEqual(body.find("joint").get("stiffness"), "0")
            self.assertEqual(body.find("geom").get("type"), "capsule")

    def test_fine_strands_are_not_grasp_targets(self):
        scene = FiberScene(None, FiberLayout(), None, None, {"graspable_links": ["trunk_00"]}, np.zeros(3))
        with self.assertRaises(ValueError):
            scene.grasp_target("fiber_00_00")

    def test_reset_exits_axially_then_bends_outward(self):
        layout = FiberLayout()
        paths = np.asarray(layout.fibers())
        tangents = np.diff(paths, axis=1)/(layout.fiber_length_m/layout.fiber_segments)
        np.testing.assert_allclose(tangents[:, :2, :], np.broadcast_to([1., 0., 0.], (8, 2, 3)), atol=1e-12)
        angles = np.degrees(np.arccos(np.clip(tangents[:, -1, 0], -1, 1)))
        self.assertTrue(np.all(angles >= layout.fan_angle_min_deg))
        self.assertTrue(np.all(angles <= layout.fan_angle_max_deg))
        radial = paths[:, :, 1:]-paths[:, :1, 1:]
        self.assertTrue(np.all(np.linalg.norm(radial[:, -1], axis=1) > .01))

    def test_bending_metric_ignores_trunk_rigid_motion(self):
        paths = np.asarray(FiberLayout().fibers())
        rotation = Rotation.from_euler("xyz", [.3, -.8, 1.7])
        moved = rotation.apply(paths.reshape(-1, 3)).reshape(paths.shape)+[.2, .8, .5]
        np.testing.assert_allclose(shape_in_root_frame(paths), shape_in_root_frame(moved), atol=1e-12)
        moved[0, -1] += [.01, 0, 0]
        self.assertGreater(np.linalg.norm(shape_in_root_frame(paths)-shape_in_root_frame(moved), axis=-1).max(), .009)


if __name__ == "__main__":
    unittest.main()
