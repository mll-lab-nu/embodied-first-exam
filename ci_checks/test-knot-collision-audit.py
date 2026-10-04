#!/usr/bin/env python3
"""Analytic adversarial meshes and an independent FCL cross-check; no physics claim."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from topogym.planning.knot_untying.collision_audit import (ConvexCover, VolumeCheck, rigid_cover_vertices,
    surface_self_intersection, triangle_intersections)


class CollisionAuditTests(unittest.TestCase):
    def test_analytic_sphere_is_not_replaced_by_an_inscribed_mesh(self):
        # An octahedron's triangular shell misses the point (.6, .6, .1)
        # even though that point is strictly inside the native unit sphere.
        octahedron = np.vstack((np.eye(3), -np.eye(3)))
        cell = np.array([[.60, .60, .10], [.61, .60, .10], [.60, .61, .10], [.60, .60, .11]])
        self.assertIsNone(ConvexCover(octahedron).first_overlapping_tet(cell[None]))
        vertices, kind = rigid_cover_vertices('SPHERE', [1.], octahedron)
        self.assertEqual(kind, 'circumscribed_native_sphere_mesh')
        cover = ConvexCover(vertices)
        self.assertTrue(np.all(cover.support >= 1.))
        self.assertEqual(cover.first_overlapping_tet(cell[None]), 0)
        box, _ = rigid_cover_vertices('BOX', [2., 4., 6.], octahedron)
        np.testing.assert_array_equal(box.min(axis=0), [-1., -2., -3.])
        for kind, data in (('SPHERE', [-1.]), ('BOX', [1., -2., 1.]), ('CAPSULE', [1., 1.])):
            with self.assertRaises(ValueError): rigid_cover_vertices(kind, data, octahedron)

    def test_filled_volume_containment_in_both_directions_and_safe_separation(self):
        cube = np.array([[x, y, z] for x in (-1., 1.) for y in (-1., 1.) for z in (-1., 1.)])
        cover = ConvexCover(cube)
        tet = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.], [0., 0., .1]])
        self.assertEqual(cover.first_overlapping_tet(tet[None]), 0)
        # A small rigid body wholly inside a FEM cell has no crossing surface triangles.
        self.assertEqual(ConvexCover(cube*.001+.02).first_overlapping_tet(tet[None]), 0)
        self.assertIsNone(cover.first_overlapping_tet((tet+3.)[None]))
        self.assertTrue(cover.overlap(ConvexCover(cube*.01)))
        self.assertFalse(cover.overlap(ConvexCover(cube+3.)))

    def test_contact_roundoff_and_world_pose_cannot_produce_clearance_pass(self):
        cube = np.array([[x, y, z] for x in (-1., 1.) for y in (-1., 1.) for z in (-1., 1.)])
        cover = ConvexCover(cube)
        for offset in (2., 2.+1e-10):
            self.assertTrue(cover.overlap(ConvexCover(cube+[offset, 0., 0.])))
        self.assertFalse(cover.overlap(ConvexCover(cube+[2.+1e-7, 0., 0.])))
        angle = .713
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0.], [np.sin(angle), np.cos(angle), 0.], [0., 0., 1.]])
        self.assertFalse(cover.placed(rotation, [0., 0., 0.]).overlap(cover.placed(rotation, rotation @ [3., 0., 0.])))
        with self.assertRaises(ValueError): cover.placed(np.eye(3)*2., [0., 0., 0.])

    def test_filled_cell_sat_agrees_with_independent_fcl_convex_collision(self):
        import fcl
        from scipy.spatial import ConvexHull
        def native(vertices):
            hull = ConvexHull(vertices)
            triangles = hull.simplices.copy()
            normals = np.cross(vertices[triangles[:, 1]]-vertices[triangles[:, 0]],
                               vertices[triangles[:, 2]]-vertices[triangles[:, 0]])
            flip = np.einsum('ij,ij->i', normals, hull.equations[:, :3]) < 0
            triangles[flip] = triangles[flip, ::-1]
            faces = np.c_[np.full(len(triangles), 3), triangles].ravel()
            return fcl.CollisionObject(fcl.Convex(vertices, len(triangles), faces))
        rng = np.random.default_rng(16320)
        for _ in range(150):
            rigid = rng.normal(size=(12, 3))*.3
            tet = rng.normal(size=(4, 3))*.2+rng.uniform(-1., 1., size=3)
            expected = bool(fcl.collide(native(rigid), native(tet), fcl.CollisionRequest(), fcl.CollisionResult()))
            self.assertEqual(ConvexCover(rigid).first_overlapping_tet(tet[None]) is not None, expected)
            self.assertEqual(ConvexCover(rigid).overlap(ConvexCover(tet)), expected)

    def test_inversion_and_collapse_are_detected_independently_of_native_flag(self):
        p = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        check = VolumeCheck(p, [[0, 1, 2, 3]])
        self.assertEqual(check.measure(p)['minimum_volume_ratio'], 1.)
        q = p.copy(); q[3, 2] = -.2
        self.assertEqual(check.measure(q)['nonpositive_cells'], 1)
        q[3, 2] = 0.
        self.assertEqual(check.measure(q)['nonpositive_cells'], 1)
        with self.assertRaises(ValueError): VolumeCheck(q, [[0, 1, 2, 3]])

    def test_triangle_interior_crossing_without_any_contained_vertex(self):
        a = np.array([[-2., -1., 0.], [2., -1., 0.], [0., 2., 0.]])
        b = np.array([[0., -2., -1.], [0., 3., -1.], [0., .5, 2.]])
        self.assertTrue(triangle_intersections(a[None], b[None])[0])
        points = np.vstack((a, b)); faces = np.array([[0, 1, 2], [3, 4, 5]])
        self.assertEqual(surface_self_intersection(points, faces), [0, 1])
        b[:, 0] += 10
        self.assertFalse(triangle_intersections(a[None], b[None])[0])

    def test_coplanar_overlap_separation_and_edge_contact(self):
        a = np.array([[0., 0., 0.], [2., 0., 0.], [0., 2., 0.]])
        for offset, hit in (([.25, .25, 0.], True), ([3., 0., 0.], False), ([2., 0., 0.], True), ([0., 0., .001], False)):
            with self.subTest(offset=offset):
                self.assertEqual(bool(triangle_intersections(a[None], (a+offset)[None])[0]), hit)

    def test_conforming_neighbors_excluded_but_disconnected_overlap_is_not(self):
        p = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
        self.assertIsNone(surface_self_intersection(p, [[0, 1, 2], [0, 2, 3]]))
        self.assertEqual(surface_self_intersection(np.vstack((p[:3], p[:3])), [[0, 1, 2], [3, 4, 5]]), [0, 1])

    def test_invalid_mesh_and_resource_exhaustion_cannot_pass(self):
        p = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        with self.assertRaises(ValueError): surface_self_intersection(p, [[0, 0, 1]])
        with self.assertRaises(ValueError): surface_self_intersection(p, [[0, 1, 3]])
        with self.assertRaises(ValueError): surface_self_intersection(p*0., [[0, 1, 2]])
        with self.assertRaises(RuntimeError):
            surface_self_intersection(np.vstack((p, p)), [[0, 1, 2], [3, 4, 5]], pair_limit=1)

    def test_random_triangle_pairs_agree_with_independent_fcl(self):
        import fcl
        rng = np.random.default_rng(4207)
        a, b = rng.normal(size=(2, 600, 3, 3))
        actual = triangle_intersections(a, b)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        expected = []
        for x, y in zip(a, b):
            objects = []
            for vertices in (x, y):
                model = fcl.BVHModel()
                model.beginModel(3, 1); model.addSubModel(vertices, faces); model.endModel()
                objects.append(fcl.CollisionObject(model))
            expected.append(bool(fcl.collide(*objects, fcl.CollisionRequest(), fcl.CollisionResult())))
        np.testing.assert_array_equal(actual, expected)


class ContactClassification(unittest.TestCase):
    def box(self, center=(0., 0., 0.), half=.5):
        return np.array([[x, y, z] for x in (-half, half) for y in (-half, half) for z in (-half, half)])+center

    def test_convex_boundary_contact_and_small_true_overlap_are_different(self):
        from topogym.planning.knot_untying.contact_geometry import convex_relation
        a = ConvexCover(self.box())
        for x, expected in ((1.01, 'separated'), (1., 'contact'), (.999999, 'penetrating'), (0., 'penetrating')):
            self.assertEqual(convex_relation(a, ConvexCover(self.box((x, 0., 0.)))), expected)

    def test_filled_self_volume_contact_and_containment(self):
        from topogym.planning.knot_untying.contact_geometry import tet_relations, self_volume_contacts, classify_gap
        a = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        for b, expected in ((a+[1., 0., 0.], 'contact'), (a+[.9, 0., 0.], 'penetrating'),
                            (a*.1+.1, 'penetrating'), (a+[2., 0., 0.], 'separated')):
            self.assertEqual(classify_gap(tet_relations(a[None], b[None])[0]), expected)
            result = self_volume_contacts(np.vstack((a, b)), np.arange(8).reshape(2, 4))
            self.assertEqual(result['penetrating_cells'] is not None, expected == 'penetrating')

    def test_surface_contact_refinement_uses_the_adjacent_solids(self):
        from topogym.planning.knot_untying.contact_geometry import FACES, surface_cell_owners, surface_solid_contacts
        a = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
        elements = np.arange(8).reshape(2, 4)
        faces = np.vstack((FACES, FACES+4))
        owners = surface_cell_owners(elements, faces)
        np.testing.assert_array_equal(owners, [0]*4+[1]*4)
        for shift, penetration in (([1., 0., 0.], False), ([.9, 0., 0.], True), ([0., 0., 0.], True)):
            result = surface_solid_contacts(np.vstack((a, a+shift)), elements, faces, owners)
            self.assertEqual(result['penetrating_cells'] is not None, penetration)

    def test_concave_cover_overlap_is_refined_against_actual_closed_mesh(self):
        import trimesh
        from topogym.planning.knot_untying.contact_geometry import MeasuredCollider
        left = trimesh.creation.box(extents=[1., 1., 1.])
        left.apply_translation([-1., 0., 0.])
        right = left.copy()
        right.apply_translation([2., 0., 0.])
        mesh = trimesh.util.concatenate((left, right))
        collider = MeasuredCollider(dict(native_type='MESH', native_convex=False),
            mesh.vertices, mesh.faces, mesh.vertices)
        self.assertTrue(collider.closed)
        gap = ConvexCover(self.box(half=.1))
        self.assertTrue(collider.cover.overlap(gap))
        self.assertEqual(collider.against_convex(gap), 'separated')
        self.assertEqual(collider.against_convex(ConvexCover(self.box((-.4, 0., 0.), half=.1))), 'contact')
        self.assertEqual(collider.against_convex(ConvexCover(self.box((-1., 0., 0.), half=.1))), 'penetrating')
        self.assertEqual(collider.against_convex(ConvexCover(self.box((-.5, 0., 0.), half=.1))), 'penetrating')

    def test_sphere_uses_analytic_surface_and_open_mesh_stays_unresolved(self):
        from topogym.planning.knot_untying.contact_geometry import MeasuredCollider
        vertices = self.box(half=1.)
        sphere = MeasuredCollider(dict(native_type='SPHERE', native_data=[1.], primitive_position_in_link_m=[0., 0., 0.]),
                                  vertices, None, vertices)
        for x, expected in ((1.6, 'separated'), (1.5, 'contact'), (1.499999, 'penetrating')):
            self.assertEqual(sphere.against_convex(ConvexCover(self.box((x, 0., 0.)))), expected)
        open_mesh = MeasuredCollider(dict(native_type='MESH', native_convex=False), vertices,
                                    np.array([[0, 1, 2]]), vertices)
        self.assertEqual(open_mesh.against_convex(ConvexCover(self.box())), 'unresolved')


if __name__ == '__main__':
    unittest.main()
