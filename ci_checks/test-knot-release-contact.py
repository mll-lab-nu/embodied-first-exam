#!/usr/bin/env python3
"""Knot release contact policy: analytic CPU checks, not a physical success claim."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.evaluation.terminal import SettlingSpec, evaluate_settling
from topogym.evaluation.terminal.clearance import convex_cover_planes
from topogym.tasks.knot_untying.common import KnotUntyingTask
from topogym.world.physics.release_geometry import ReleaseGeometry

TET = np.array([[0., 0., 0.], [.01, 0., 0.], [0., .01, 0.], [0., 0., .01]])
SPEC = KnotUntyingTask().final_settling_spec()


def state(gap, *, fixed=False, mesh=None, convex=True):
    if mesh is None:
        mesh = trimesh.creation.box(extents=[.1, .1, .1])
        mesh.apply_translation([0., 0., -.05-gap])
    vertices = np.asarray(mesh.vertices)
    return dict(physics_step=1, assist_active=False,
        fem={'rope': dict(position_m=TET.copy(), velocity_m_s=np.zeros_like(TET))},
        release_geometry=dict(schema_version=3, physics_step=1, complete=True, robot_present=True,
            robot_bounds_m=np.array([[vertices.min(0), vertices.max(0)]]),
            robot_convex_planes_m=[convex_cover_planes(vertices)],
            fem_elements={'rope': np.array([[0, 1, 2, 3]])}, target_bounds_m={},
            robot_solids=[dict(link='base' if fixed else 'finger', geom_index=0,
                fixed_to_world=fixed, native_type='MESH', native_convex=convex, native_data=[],
                vertices_m=vertices, faces=np.asarray(mesh.faces))],
            robot_solid_poses=[dict(rotation=np.eye(3), position_m=np.zeros(3))]))


class KnotReleaseContact(unittest.TestCase):
    def test_fixed_contact_and_small_positive_active_gap(self):
        for gap, fixed, expected in ((0., True, True), (0., False, False), (.0009, False, False),
                                      (.001, False, True), (.0015, False, True), (.002, False, True)):
            with self.subTest(gap=gap, fixed=fixed):
                passed, metrics, _ = evaluate_settling(state(gap, fixed=fixed), SPEC)
                self.assertEqual(passed, expected, metrics)
                if fixed:
                    self.assertGreater(metrics['fixed_boundary_contacts'], 0)

    def test_all_parts_still_reject_micrometre_penetration_and_containment(self):
        for fixed in (False, True):
            for gap in (-1e-6, -.02):
                with self.subTest(fixed=fixed, gap=gap):
                    passed, metrics, _ = evaluate_settling(state(gap, fixed=fixed), SPEC)
                    self.assertFalse(passed)
                    self.assertFalse(metrics['robot_no_penetration'])
                    self.assertEqual(metrics['robot_contact_failures'][0]['relation'], 'penetrating')

    def test_concavity_refines_false_cover_overlap_and_measures_actual_gap(self):
        for gap, expected in ((.0015, True), (.0005, False)):
            left = trimesh.creation.box(extents=[.01, .04, .04])
            left.apply_translation([-.005-gap, 0., 0.])
            right = left.copy()
            right.apply_translation([.1, 0., 0.])
            mesh = trimesh.util.concatenate((left, right))
            measured = state(0., mesh=mesh, convex=False)
            self.assertFalse(evaluate_settling(measured, SettlingSpec(fem_targets=('rope',)))[0])
            passed, metrics, _ = evaluate_settling(measured, SPEC)
            self.assertEqual(passed, expected, metrics)
            self.assertGreater(metrics['exact_cell_queries'], 0)

    def test_unknown_geometry_and_stale_states_cannot_pass(self):
        s = state(0., fixed=True)
        s['release_geometry']['robot_solids'][0]['native_convex'] = False
        s['release_geometry']['robot_solids'][0]['faces'] = np.array([[0, 1, 2]])
        passed, metrics, _ = evaluate_settling(s, SPEC)
        self.assertFalse(passed)
        self.assertEqual(metrics['robot_contact_failures'][0]['relation'], 'unresolved')
        for key in ('robot_solids', 'robot_solid_poses'):
            s = state(.002)
            s['release_geometry'][key] = []
            with self.assertRaises(ValueError):
                evaluate_settling(s, SPEC)
        for version in (1, 2):
            s = state(.002)
            s['release_geometry']['schema_version'] = version
            passed, metrics, _ = evaluate_settling(s, SPEC)
            self.assertFalse(passed)
            self.assertEqual(metrics['evaluation_status'], 'unavailable')
        s = state(.002)
        s['release_geometry']['physics_step'] = 0
        with self.assertRaises(ValueError):
            evaluate_settling(s, SPEC)

    def test_old_default_and_other_completion_requirements_unchanged(self):
        old = SettlingSpec(fem_targets=('rope',))
        self.assertEqual(old.clearance_m, .005)
        self.assertFalse(evaluate_settling(state(.002), old)[0])
        for change in ('assist', 'speed', 'drift'):
            s = state(.002)
            reference = None
            if change == 'assist': s['assist_active'] = True
            if change == 'speed': s['fem']['rope']['velocity_m_s'][0, 0] = .0011
            if change == 'drift': reference = {'rope': TET+.0011}
            self.assertFalse(evaluate_settling(s, SPEC, reference)[0], change)
        task = KnotUntyingTask()
        with patch.object(task, 'evaluate_transition', return_value=(True, None, {}, {})):
            for tick in range(1, 204):
                s = state(.002)
                s['physics_step'] = s['release_geometry']['physics_step'] = tick
                if tick == 2: s['assist_active'] = True
                result = task.update(s, .0025)
                self.assertEqual(result.task_success, tick == 203, tick)

    def test_boundary_distance_matches_independent_fcl_for_disjoint_triangles(self):
        import fcl
        from topogym.utils.geometry.solid_contact import triangle_pair_distances
        rng = np.random.default_rng(1337)
        a = rng.uniform(-.05, .05, (120, 3, 3))
        b = rng.uniform(-.05, .05, (120, 3, 3))
        b[:, :, 2] += .102
        expected = []
        for x, y in zip(a, b, strict=True):
            objects = []
            for vertices in (x, y):
                model = fcl.BVHModel()
                model.beginModel(3, 1)
                model.addSubModel(vertices, np.array([[0, 1, 2]], dtype=np.int32))
                model.endModel()
                objects.append(fcl.CollisionObject(model))
            expected.append(fcl.distance(*objects, fcl.DistanceRequest(), fcl.DistanceResult()))
        np.testing.assert_allclose(triangle_pair_distances(a, b), expected, atol=1e-12, rtol=1e-10)

    def test_reader_uses_native_world_fixed_flag_not_link_name_or_fixed_joint(self):
        mesh = trimesh.creation.box()
        def geom(i):
            return SimpleNamespace(idx=i, type=SimpleNamespace(name='MESH'), data=[],
                init_verts=mesh.vertices, init_faces=mesh.faces, is_convex=True)
        # A fixed joint on a moving wrist is not fixed to world in Genesis.
        links = [SimpleNamespace(name='base', is_fixed=True, geoms=[geom(0)]),
                 SimpleNamespace(name='fixed_finger', is_fixed=False, geoms=[geom(1)])]
        solver = SimpleNamespace(get_geoms_pos=lambda *a, **k: np.zeros((2, 3)),
                                 get_geoms_quat=lambda *a, **k: np.tile([1., 0., 0., 0.], (2, 1)))
        world = SimpleNamespace(entities={'robot': SimpleNamespace(links=links)}, physics_step=4,
                                scene=SimpleNamespace(sim=SimpleNamespace(rigid_solver=solver)))
        native = ReleaseGeometry(world, (), exact_robot_contact=True).read()
        self.assertEqual(native['schema_version'], 3)
        self.assertEqual([r['fixed_to_world'] for r in native['robot_solids']], [True, False])
        old = ReleaseGeometry(world, ()).read()
        self.assertEqual(old['schema_version'], 2)
        self.assertNotIn('robot_solids', old)

    def test_rule_revision_does_not_relabel_saved_task_state(self):
        task = KnotUntyingTask()
        with patch.object(KnotUntyingTask, 'terminal_revision', 'terminal_v4_release_settling_default_success'):
            old = KnotUntyingTask().get_state()
        with self.assertRaises(ValueError): task.set_state(old)
        text = task.public_instruction()
        self.assertIn('at least 1 mm', text)
        self.assertIn('World-fixed bases may touch', text)
        self.assertNotIn('at least 5 mm', text)

    def test_oracle_does_not_search_for_extra_fixed_base_clearance(self):
        from topogym.planning.knot_untying.robot_oracle import Runner
        for gap, fixed, expected in ((0., True, []), (-1e-6, True, [0]),
                                     (.002, False, [0]), (0., False, [0])):
            s = state(gap, fixed=fixed)
            geometry = s['release_geometry']
            self.assertEqual(Runner.release_search_colliders(TET, geometry['fem_elements']['rope'],
                                                              geometry, .001), expected)


if __name__ == '__main__':
    unittest.main()
