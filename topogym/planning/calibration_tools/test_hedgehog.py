"""Detached asset integrity checks; these do not qualify a robot solution."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from .adapters.hedgehog_in_cage import BASE_SHA256, declaration, deform_vertices, parameters_checked, preview


class HedgehogReliefTests(unittest.TestCase):
    def task(self):
        from topogym.tasks.hedgehog_in_cage.hedgehog_in_cage_hard import HedgehogInCageHardTask
        # The earlier bar-relief study is tied to the original frozen cage.
        # It must not silently deform or qualify the later S5-post model.
        class OriginalHard(HedgehogInCageHardTask):
            model_revision = 'fixed_v2'
            asset_resource = 'variations/hedgehog_in_cage/gen_keyhole/assets.zip'
            prototype_resource = 'variations/hedgehog_in_cage/gen_keyhole/prototype.json'
            initial_ball_pose = {
                'position_m': [0.034, -4.059817334521296e-9, -0.013093779603251927],
                'quaternion_wxyz': [-0.08985502802683738, -0.38231459195763656,
                                   0.8996677947434726, 0.19068163471078864],
            }
        return OriginalHard(seed=0)

    def test_parameter_bounds_and_fixed_collar(self):
        for patch in ({'radial_offset_m': float('nan')}, {'radial_offset_m': -.001},
                      {'end_z_m': .12}, {'bar_phases_deg': [241]}, {'unknown': 1},
                      {'plateau_start_z_m': .036}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parameters_checked(patch)
        z = np.array([-.102, .036, .06816667, .106, .120])
        angle = np.deg2rad(240+4.659091+159.09090742*z)
        v = np.column_stack([.063*np.cos(angle), .063*np.sin(angle), z])
        moved = deform_vertices(v, {})
        np.testing.assert_array_equal(moved[[0,1,3,4]], v[[0,1,3,4]])
        self.assertAlmostEqual(np.linalg.norm(moved[2]-v[2]), .004, places=12)
        np.testing.assert_array_equal(deform_vertices(v, {'radial_offset_m': 0}), v)

    def test_render_collision_mass_and_resource_integrity(self):
        from topogym.assets.library import resource_path
        task = self.task()
        source = resource_path(task.asset_resource)
        with tempfile.TemporaryDirectory(prefix='hedgehog_relief_assets_') as tmp:
            folder = Path(tmp)/'candidate'
            record = preview(task, {}, folder)
            self.assertEqual(len(record['changed_collision_cells']), 9)
            self.assertFalse(record['formal_qualification'])
            with zipfile.ZipFile(source) as z:
                original = trimesh.load(io.BytesIO(z.read('cage.obj')), file_type='obj', process=False)
                candidate = trimesh.load(folder/'cage.obj', force='mesh', process=False)
                expected = deform_vertices(original.vertices, {})
                np.testing.assert_allclose(candidate.vertices, expected, atol=1e-8, rtol=0)
                original_glb = trimesh.load(io.BytesIO(z.read('cage.glb')), file_type='glb', process=False)
                actual_glb = trimesh.load(folder/'cage.glb', process=False)
                for name, geometry in original_glb.geometry.items():
                    actual = actual_glb.geometry[name]
                    np.testing.assert_allclose(actual.vertices, deform_vertices(geometry.vertices, {}), atol=1e-8, rtol=0)
                    np.testing.assert_array_equal(actual.visual.uv, geometry.visual.uv)
                    self.assertEqual(actual.visual.material.name, geometry.visual.material.name)
                visual_points = np.vstack([m.vertices for m in actual_glb.geometry.values()])
                self.assertLess(cKDTree(candidate.vertices).query(visual_points)[0].max(), 3e-8)
                for name in z.namelist():
                    if name.startswith(('hedgehog', 'counterfactual_closed_stem')):
                        self.assertEqual((folder/name).read_bytes(), z.read(name))
            for path in folder.glob('cage_collision_*.obj'):
                mesh = trimesh.load(path, force='mesh', process=False)
                self.assertTrue(mesh.is_watertight and mesh.is_convex and mesh.volume > 0)
            inertial = ET.parse(folder/'cage.urdf').getroot().find('link/inertial')
            inertia = inertial.find('inertia').attrib
            mat = np.array([[float(inertia['i'+a+b if a<=b else 'i'+b+a]) for b in 'xyz'] for a in 'xyz'])
            self.assertTrue((np.linalg.eigvalsh(mat)>0).all())
            report = json.loads((folder/'asset_report.json').read_text())
            self.assertIsNone(report['shape']['side_exit_blocked_by_core'])
            self.assertTrue(report['shape']['side_exit_guard_requires_revalidation'])
            self.assertAlmostEqual(float(inertial.find('mass').get('value')), report['bodies']['cage']['mass_kg'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), BASE_SHA256)

    def test_disposable_identity_and_live_task_rejection(self):
        task = self.task()
        identity, revision = task.instance_id, task.model_revision
        with declaration(task, {}):
            self.assertNotEqual(task.instance_id, identity)
            first = task.instance_id
            self.assertNotEqual(task.model_revision, revision)
        self.assertEqual((task.instance_id, task.model_revision), (identity, revision))
        with declaration(task, {'radial_offset_m': .006}):
            self.assertNotEqual(task.instance_id, first)
        task.entities = {'hedgehog_ball': object()}
        with self.assertRaises(ValueError), declaration(task, {}):
            pass


if __name__ == '__main__':
    unittest.main()
