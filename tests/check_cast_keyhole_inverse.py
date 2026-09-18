"""Inverse-design solids must preserve real apertures and canonical body poses."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.tasks.cast_keyhole.collision import CompoundCollision
from topogym.tasks.cast_keyhole.inverse_variants import geometry_from_record, proposal, VARIANTS
from topogym.tasks.cast_keyhole.solution import read_motion, canonical_geometry
from topogym.tasks.cast_keyhole.variant_runtime import set_objects, actual_objects


def rectangle(x, y):
    return [[-x, -y], [x, -y], [x, y], [-x, y]]


class InverseDesignChecks(unittest.TestCase):
    def test_layered_solid_has_real_depth_relief_and_matched_collision_volume(self):
        # A wide middle lip extends beyond both faces, as in the tilted gate.
        record = dict(thickness_mm=3, rings_mm=dict(gold=[rectangle(1, 2)], silver=[rectangle(.2, .2)]),
                      layers=dict(gold=[dict(z_min_mm=lo, z_max_mm=hi, rings_mm=[rectangle(x, 2)])
                          for lo, hi, x in ((-1.5, -.25, 1), (-.25, .25, 2), (.25, 1.5, 1))]))
        meshes, cells = geometry_from_record(record)
        gold = meshes[0]
        self.assertTrue(gold.is_watertight)
        self.assertEqual(len(gold.split()), 1)
        self.assertEqual(gold.euler_number, 2)
        self.assertAlmostEqual(gold.volume, (8*2.5+16*.5)*.003**3, places=12)
        self.assertAlmostEqual(gold.volume, sum(c.volume for c in cells[0]), places=12)
        probe = trimesh.creation.box([.0003]*3)
        collision = CompoundCollision(cells[0], [probe])
        self.assertLess(collision.gap(np.eye(3), [.0045, 0, 0]), 0)
        self.assertGreater(collision.gap(np.eye(3), [.0045, 0, .003]), 0)

    def test_closed_aperture_survives_mesh_and_convex_export(self):
        record = dict(thickness_mm=1, rings_mm=dict(gold=[rectangle(3, 3), rectangle(2, 2)], silver=[rectangle(.2, .2)]))
        meshes, cells = geometry_from_record(record)
        self.assertTrue(meshes[0].is_watertight)
        self.assertEqual(meshes[0].euler_number, 0)
        collision = CompoundCollision(*cells)
        self.assertGreater(collision.gap(np.eye(3), [0, 0, 0]), .001)
        self.assertLess(collision.gap(np.eye(3), [.0075, 0, 0]), 0)

    def test_variants_share_unsolved_initial_instance_and_reach_separation(self):
        proposals = [proposal(name) for name in VARIANTS]
        first = [read_motion(p["motions"][0], 3).pose(0) for p in proposals]
        _, _, cells = canonical_geometry(3.)
        col = CompoundCollision(*cells)
        for p, (r, t) in zip(proposals, first):
            np.testing.assert_allclose(r, first[0][0], atol=1e-12)
            np.testing.assert_allclose(t, first[0][1], atol=1e-12)
            self.assertGreater(col.gap(r, t), 0)
            final = read_motion(p["motions"][-1], 3).pose(1)
            self.assertGreater(col.gap(*final), .02)
        self.assertNotEqual(proposals[0]["motions"], proposals[1]["motions"])
        self.assertNotEqual(proposals[1]["motions"], proposals[2]["motions"])

    def test_canonical_pose_round_trip_with_rotated_offcenter_com(self):
        class Body:
            def set_pos(self, pos): self.pos = np.array(pos)
            def set_quat(self, quat): self.quat = np.array(quat)
            def get_pos(self): return self.pos
            def get_quat(self): return self.quat
        task = SimpleNamespace(mount=np.array([.4, -.1, .8]), bodies={"test": Body()},
                               records=[dict(name="test", origin_m=[.012, -.038, .002])])
        pose = dict(pos=[-.02, .04, .3], quat=Rotation.from_euler("xyz", [.7, -1.3, .4]).as_quat().tolist())
        frame = dict(bodies=dict(test=deepcopy(pose)))
        set_objects(task, frame)
        _, actual = actual_objects(task)
        np.testing.assert_allclose(actual["test"]["pos"], pose["pos"], atol=1e-14)
        np.testing.assert_allclose(Rotation.from_quat(actual["test"]["quat"]).as_matrix(),
                                   Rotation.from_quat(pose["quat"]).as_matrix(), atol=1e-14)
        self.assertGreater(np.linalg.norm(task.bodies["test"].get_pos()-task.mount-pose["pos"]), .03)


if __name__ == "__main__":
    unittest.main()
