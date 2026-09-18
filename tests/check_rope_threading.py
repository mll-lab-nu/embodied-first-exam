"""Reference fidelity, open collision apertures, and material-direction checks."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import trimesh

from topogym.tasks.rope_threading.geometry import (ThreadingLayout, generate_assets, ring_mesh,
                                                 route_crossings, surface_intersects_ring_disk)
from topogym.tasks.rope_threading.reference import REFERENCE


class ThreadingChecks(unittest.TestCase):
    def test_withdrawn_robot_surface_must_clear_finite_aperture(self):
        ring = dict(center_m=[0, 0, 0], normal=[0, 0, 1], radius_m=.075, tube_radius_m=.006)
        faces = np.array([[0, 1, 2]])
        # The crossing segment spans the hole even though its endpoints are outside.
        spanning = np.array([[-.2, 0, -.1], [-.2, 0, .1], [.4, 0, 0]])
        self.assertTrue(surface_intersects_ring_disk(spanning, faces, ring))
        self.assertFalse(surface_intersects_ring_disk(spanning+[0, .2, 0], faces, ring))
        coplanar = np.array([[-.2, -.2, 0], [.2, -.2, 0], [0, .4, 0]])
        self.assertTrue(surface_intersects_ring_disk(coplanar, faces, ring))
        self.assertFalse(surface_intersects_ring_disk(coplanar+[0, 0, .002], faces, ring))

    def test_source_dimensions_and_initial_clearance(self):
        with tempfile.TemporaryDirectory() as folder:
            report = generate_assets(folder)
            self.assertAlmostEqual(report["rope_length_m"], 1.1, places=10)
            self.assertEqual(report["initial_crossings"], [])
            self.assertGreater(report["minimum_fixture_gap_lower_bound_m"], .12)
            self.assertAlmostEqual(report["table_surface_gap_m"], .0003, places=10)
            rope = trimesh.load(Path(folder)/"rope.obj", process=False, force="mesh")
            self.assertTrue(rope.is_volume)
            self.assertEqual(rope.euler_number, 2)
            for i in range(1, 4):
                obj = Path(folder)/f"R{i}.obj"
                self.assertIn(f"mtllib R{i}.mtl", obj.read_text())
                self.assertTrue((Path(folder)/f"R{i}.mtl").is_file())
                for kind in ("base", "stand"):
                    support = trimesh.load(Path(folder)/f"R{i}_{kind}.obj", process=False, force="mesh")
                    self.assertTrue(support.is_volume)
                    if kind == "base":
                        self.assertAlmostEqual(support.bounds[0, 2], 0., places=8)

    def test_reference_frame_and_material_order(self):
        source = json.loads(REFERENCE.read_text())
        p = np.asarray(source["rope_nodes_m"])
        self.assertEqual(p.shape, (81, 3))
        np.testing.assert_allclose(np.linalg.norm(np.diff(p, axis=0), axis=1), 1.1/80, atol=1e-12)
        self.assertLess(p[0, 0], p[-1, 0])
        self.assertEqual(source["target_material_order"], ["R1-", "R2+", "R3+"])
        self.assertEqual(source["source_initial_crossings"], [0, 0, 0])
        shift = (-.1356786, 0., .9205429)
        layout = ThreadingLayout(translation_m=shift)
        np.testing.assert_allclose(layout.centerline()[::4], p+shift, atol=1e-12)
        for actual, expected in zip(layout.rings(), ([.075, -.019, .331], [.01, .17, .31], [.09, .315, .28])):
            np.testing.assert_allclose(actual["center_m"], np.asarray(expected)+shift, atol=1e-12)
            basis = np.column_stack([actual[k] for k in ("basis_u", "basis_v", "normal")])
            np.testing.assert_allclose(basis.T@basis, np.eye(3), atol=1e-10)
            self.assertAlmostEqual(np.linalg.det(basis), 1., places=10)

    def test_collision_apertures_are_open_in_all_three_orientations(self):
        for ring in ThreadingLayout().rings():
            mesh = ring_mesh(ring)
            self.assertTrue(mesh.is_volume)
            self.assertEqual(mesh.euler_number, 0)
            center, n, u = (np.asarray(ring[k]) for k in ("center_m", "normal", "basis_u"))
            origins = [center+.12*n, center+.075*u+.12*n]
            hits = mesh.ray.intersects_any(ray_origins=origins, ray_directions=[-n, -n])
            np.testing.assert_array_equal(hits, [False, True])
            # The capsule stand reaches the ring's angle-zero SIDE attachment.
            top = np.asarray(ring["stand"]["position"])+[0, 0, ring["stand"]["size"][1]+.0009]
            np.testing.assert_allclose(top, center+.075*u, atol=1e-12)

    def test_signed_crossings_and_tangent_rejection(self):
        ring = ThreadingLayout().rings()[2]
        center, n, u = (np.asarray(ring[k]) for k in ("center_m", "normal", "basis_u"))
        forward = [center-.1*n, center, center+.1*n]
        self.assertEqual([h["sign"] for h in route_crossings(forward, [ring], .004)], [1])
        self.assertEqual([h["sign"] for h in route_crossings(forward[::-1], [ring], .004)], [-1])
        self.assertEqual(route_crossings([center+.1*n, center, center+.1*n], [ring], .004), [])
        self.assertEqual(route_crossings(np.asarray(forward)+.2*u, [ring], .004), [])
        with self.assertRaises(ValueError):
            route_crossings([[0, 0, np.nan], [0, 0, 1]], [ring])

    def test_invalid_mesh_parameters(self):
        for values in (dict(rope_subdivisions=0), dict(radial_segments=3),
                       dict(rope_subdivisions=True), dict(translation_m=(0, np.nan, 0))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ThreadingLayout(**values)


if __name__ == "__main__":
    unittest.main()
