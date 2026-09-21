"""Physics monitors must reject real intersections, tunnelling and inversion."""
import unittest
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np

from topogym.tasks.knot_untying.diagnostics import FemDiagnostics, SurfaceCCD, signed_tet_volumes
from topogym.tasks.knot_untying.physics_probe import SolverLog
from topogym.tasks.knot_untying.physics_review import compare_centerlines, evidence_satisfies_case, write_review
from topogym.tasks.knot_untying.rigid_diagnostics import swept_aabbs_overlap


class KnotPhysicsChecks(unittest.TestCase):
    def test_settle_gate_report_is_not_changed_by_later_loaded_motion(self):
        monitor = FemDiagnostics.__new__(FemDiagnostics)
        monitor.window = []
        monitor.initial = np.zeros((2, 3))
        monitor.loaded = False
        monitor.min_J = 1.
        monitor.count = 0
        monitor.dt = .00125
        monitor.elapsed_diagnostics_s = 0.
        monitor.failures = []
        monitor.ccd = SimpleNamespace(initial_intersections=False, checks=0, failures=0)
        monitor.maxima = dict(max_table_penetration_m=0., max_total_length_relative_change=.003,
                              max_local_axial_strain=.01)
        gate = monitor.report()
        monitor.maxima['max_total_length_relative_change'] = .04
        monitor.failures.append(dict(time_s=30., reason='inverted_tetrahedron'))
        later = monitor.report()
        self.assertEqual(gate['extrema']['max_total_length_relative_change'], .003)
        self.assertEqual(gate['failures'], [])
        self.assertTrue(gate['checks']['total_length'])
        self.assertFalse(later['checks']['total_length'])
        self.assertFalse(later['checks']['finite_no_inversion'])

    def test_grasp_distance_detects_edge_contact_without_nearby_vertices(self):
        vertices = np.array([[-1., 0, 0], [1., 0, 0], [1., .01, 0],
                             [0., -1, .0005], [0., 1., .0005], [.01, 1., .0005]])
        checker = SurfaceCCD(vertices, np.arange(6).reshape(2, 3),
                             primary_vertices=np.arange(6) < 3, cross_only=True)
        try:
            self.assertAlmostEqual(checker.minimum_distance(vertices, .0008), .0005, places=10)
            self.assertIsNone(checker.minimum_distance(vertices, .0004))
            self.assertEqual(checker.checks, 0)
        finally:
            checker.close()

    def test_newton_iteration_limit_is_preserved_in_diagnostics(self):
        log = SolverLog('/tmp')
        log.reader = StringIO('Newton Iteration Exits with Max Iteration: 100 (Frame=2990)\n<<< End Frame: 2990\n')
        log.update()
        self.assertEqual(log.max_iterations, 100)
        self.assertEqual(log.frames, 1)
        self.assertEqual(len(log.warnings), 1)
        self.assertFalse(log.report(1)['convergence_verified'])

    def test_solver_log_message_split_across_reads(self):
        log = SolverLog('/tmp')
        log.reader = StringIO('Newton Iteration Converged with Iteration Co')
        log.update()
        self.assertEqual(log.converged, 0)
        log.reader = StringIO('unt: 7\n<<< End Frame: 1\n')
        log.update()
        self.assertTrue(log.report(1)['convergence_verified'])

    def test_swept_collision_when_both_endpoints_are_intersection_free(self):
        triangle = np.array([[-1., -1, 0], [1., -1, 0], [0, 1., 0]])
        vertices = np.vstack((triangle, triangle+[0, 0, 1]))
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        checker = SurfaceCCD(vertices, faces)
        try:
            self.assertFalse(checker.initial_intersections)
            self.assertTrue(checker.step(vertices))
            moved = vertices.copy()
            moved[3:, 2] = -1.
            self.assertFalse(checker.step(moved))
        finally:
            checker.close()

    def test_initial_intersection_rejected(self):
        vertices = np.array([[-1., -1, 0], [1., -1, 0], [0, 1., 0],
                             [0, -.5, -1], [0, -.5, 1], [0, .5, 0]])
        checker = SurfaceCCD(vertices, np.array([[0, 1, 2], [3, 4, 5]]))
        try:
            self.assertTrue(checker.initial_intersections)
        finally:
            checker.close()

    def test_volume_inversion(self):
        vertices = np.array([[0., 0, 0], [1., 0, 0], [0, 1., 0], [0, 0, 1.]])
        elements = np.array([[0, 1, 2, 3]])
        initial = signed_tet_volumes(vertices, elements)
        vertices[3, 2] = -1.
        self.assertLess(float((signed_tet_volumes(vertices, elements)/initial)[0]), 0.)

    def test_rigid_pair_filter_still_checks_fem_rigid_sweeps(self):
        triangle = np.array([[-1., -1, 0], [1., -1, 0], [0, 1., 0]])
        vertices = np.vstack((triangle+[4, 0, 1], triangle,
                              [[0, -.5, -1], [0, -.5, 1], [0, .5, 0]]))
        checker = SurfaceCCD(vertices, np.arange(9).reshape(3, 3),
                             primary_vertices=np.arange(9) < 3)
        try:
            self.assertFalse(checker.initial_intersections)
            moved = vertices.copy()
            moved[:3] = triangle+[0, 0, -1]
            self.assertFalse(checker.step(moved))
        finally:
            checker.close()

    def test_swept_body_bounds_do_not_skip_midstep_crossing(self):
        face = np.array([[-1., -1, 0], [1., -1, 0], [0, 1., 0]])
        self.assertTrue(swept_aabbs_overlap(face+[0, 0, 1], face-[0, 0, 1], face, face))
        self.assertFalse(swept_aabbs_overlap(face+[0, 0, 2], face+[0, 0, 1], face, face))

    def test_explicit_ccd_interval_uses_its_actual_previous_state(self):
        face = np.array([[-1., -1, 0], [1., -1, 0], [0, 1., 0]])
        vertices = np.vstack((face+[0, 0, 1], face))
        checker = SurfaceCCD(vertices, np.arange(6).reshape(2, 3), primary_vertices=np.arange(6) < 3,
                             cross_only=True)
        try:
            previous, current = vertices.copy(), vertices.copy()
            previous[:3, 2], current[:3, 2] = -2., -3.
            self.assertTrue(checker.step_between(previous, current))
            current[:3, 2] = 1.
            self.assertFalse(checker.step_between(previous, current))
        finally:
            checker.close()

    def test_missing_convergence_logs_cannot_pass(self):
        log = SolverLog('/tmp')
        log.frames = 4
        log.converged = 3
        self.assertFalse(log.report(4)['convergence_verified'])
        log.converged = 4
        self.assertTrue(log.report(4)['convergence_verified'])
        log.warnings = ['linear solver failed']
        self.assertFalse(log.report(4)['convergence_verified'])

    def test_matching_final_shape_cannot_hide_divergent_feed_cycle(self):
        with TemporaryDirectory() as tmp:
            first, second = Path(tmp)/'first', Path(tmp)/'second'
            first.mkdir()
            second.mkdir()
            times = np.array([5., 7., 9., 11., 13., 15., 20.])
            points = np.array([[0., 0., 0.], [.5, 0., 0.], [1., 0., 0.]])
            baseline = np.repeat(points[None], len(times), axis=0)
            changed = baseline.copy()
            changed[0, :, 1] += .01
            for folder, trajectory in ((first, baseline), (second, changed)):
                np.savez(folder/'trajectory.npz', times=times, centerlines=trajectory, initial_centerline=points)
                (folder/'validation_spec.json').write_text(json.dumps(dict(experiment='feed_release')))
            result = compare_centerlines(first, second)
            self.assertEqual(result['final']['max_m'], 0.)
            self.assertFalse(result['passed'])

    def test_empty_evidence_cannot_qualify_physics(self):
        with TemporaryDirectory() as tmp:
            result = write_review(Path(tmp))
            self.assertFalse(result['complete_physics_suite_passed'])
            self.assertFalse(result['full_untying_demo_qualified'])
            self.assertTrue(all(case['status'] == 'not_run' for case in result['experiments'].values()))

    def test_short_probe_and_fixture_cannot_certify_later_gates(self):
        self.assertFalse(evidence_satisfies_case('free_settle_0', dict(passed=True, simulated_seconds=3.)))
        self.assertFalse(evidence_satisfies_case('robot_grasp', dict(passed=True, simulated_seconds=20.,
                                                                  robot_grasp_qualified=False)))


if __name__ == '__main__':
    unittest.main()
