"""Numerical contracts only; real physics evidence is recorded separately."""
import sys
from pathlib import Path
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.planning.calibration_tools.ipc_diagnostics import transform_error, limit_error
from topogym.planning.calibration_tools.material_trials import candidate_spec, ipc_pair_friction
from topogym.tasks.base import EntitySpec, TaskSpec


class DiagnosticTests(unittest.TestCase):
    def test_rotation_error_is_detected_with_identical_origins(self):
        native = np.eye(4)
        native[:3, :3] = Rotation.from_euler('z', 1, degrees=True).as_matrix()
        result = transform_error(native, np.eye(4), [[.1, 0, 0]])
        self.assertEqual(result['position_error_m'], 0.)
        self.assertAlmostEqual(result['orientation_error_rad'], np.pi/180)
        self.assertGreater(result['collision_vertex_error_m'], .0017)

    def test_affine_strain_is_separate_from_rotation(self):
        native = np.diag([1.01, 1., 1., 1.])
        result = transform_error(native, np.eye(4), [[.1, 0, 0]])
        self.assertEqual(result['orientation_error_rad'], 0.)
        self.assertAlmostEqual(result['affine_stretch_error'], .01)
        self.assertAlmostEqual(result['collision_vertex_error_m'], .001)

    def test_control_upper_is_not_physical_upper(self):
        self.assertEqual(limit_error(.039, 0., .041)['violation'], 0.)
        self.assertAlmostEqual(limit_error(.050, 0., .041)['violation'], .009)
        self.assertAlmostEqual(limit_error(-.002, 0., .041)['violation'], .002)
        with self.assertRaises(ValueError): limit_error(float('nan'), 0., .041)

    def test_material_candidate_preserves_original_and_mass(self):
        original = TaskSpec((EntitySpec('load', 'box', None,
            morph_options=dict(size=(.01, .02, .03)), material=dict(coup_type='ipc_only')),))
        result, changes = candidate_spec(original, materials={'load': {'coup_friction': 1.}},
                                         primitive_masses_kg={'load': .068})
        self.assertEqual(dict(original.entities[0].material), {'coup_type': 'ipc_only'})
        self.assertAlmostEqual(result.entities[0].material['rho']*.01*.02*.03, .068)
        self.assertFalse(result.metadata['formal_qualification'])
        self.assertEqual(len(changes), 1)

    def test_ambiguous_mass_and_invalid_overrides_are_rejected(self):
        spec = TaskSpec((EntitySpec('part', 'urdf', '/unused/model.urdf'),))
        with self.assertRaises(ValueError): candidate_spec(spec, primitive_masses_kg={'part': .068})
        with self.assertRaises(ValueError): candidate_spec(spec, materials={'part': {'coup_friction': -1.}})
        with self.assertRaises(ValueError): candidate_spec(spec, materials={'missing': {'rho': 10.}})
        with self.assertRaises(ValueError): candidate_spec(spec, materials={'part': {'mass': .068}})

    def test_effective_ipc_friction(self):
        self.assertAlmostEqual(ipc_pair_friction(.1, .3), .17320508075688773)
        self.assertAlmostEqual(ipc_pair_friction(1., .3), .5477225575051661)
        self.assertEqual(ipc_pair_friction(0., 1.), 0.)
        with self.assertRaises(ValueError): ipc_pair_friction(float('nan'), 1.)


if __name__ == '__main__': unittest.main()
