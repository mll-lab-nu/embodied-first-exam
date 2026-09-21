"""Physical model contracts; long-duration qualification is a separate probe."""
from pathlib import Path
import tempfile
import unittest

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.slotted_post_ring.fixture import cord_disk_crossings
from topogym.tasks.slotted_post_ring.physics import build_model, node_positions


class SlottedPostPhysicsChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.directory.name)
        cls.model, _, cls.spec = build_model(cls.folder)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)

    def ray(self, origin, direction, groups):
        geom = np.array([-1], dtype=np.int32)
        return mujoco.mj_ray(self.model, self.data, np.asarray(origin, dtype=float),
                            np.asarray(direction, dtype=float),
                            np.asarray(groups, dtype=np.uint8), 1, -1, geom)

    def test_slot_collision_is_open_and_rails_are_solid(self):
        groups = [0, 0, 0, 1, 0, 0]
        self.assertLess(self.ray([0, -.1, .19], [0, 1, 0], groups), 0)
        self.assertAlmostEqual(self.ray([.025, -.1, .19], [0, 1, 0], groups), .086, places=6)

    def test_bead_collision_has_a_real_axial_bore(self):
        body = self.model.body('bead_left').id
        center = self.data.xpos[body]
        rotation = self.data.xmat[body].reshape(3, 3)
        groups = [1, 0, 0, 0, 0, 0]
        distance = self.ray(center+rotation@[0, 0, -.04], rotation[:, 2], groups)
        self.assertTrue(distance < 0 or distance > .07, distance)
        self.assertLess(self.ray(center+rotation@[.012, 0, -.04], rotation[:, 2], groups), .04)

    def test_binary_and_xml_reload_preserve_dynamics(self):
        xml_model = mujoco.MjModel.from_xml_path(str(self.folder/'scene.xml'))
        binary_model = mujoco.MjModel.from_binary_path(str(self.folder/'scene.mjb'))
        self.assertEqual(xml_model.nflex, 1)
        np.testing.assert_array_equal(xml_model.qpos0, binary_model.qpos0)
        np.testing.assert_array_equal(xml_model.eq_data, binary_model.eq_data)
        np.testing.assert_array_equal(xml_model.flexedge_length0, binary_model.flexedge_length0)
        self.assertEqual(xml_model.opt.ccd_tolerance, self.spec['settings']['ccd_tolerance_m'])

    def test_gravity_is_active_and_terminals_remain_attached(self):
        initial = node_positions(self.model, self.data)
        for _ in range(400):
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        nodes = node_positions(self.model, self.data)
        self.assertLess(np.min(nodes[:, 2]-initial[:, 2]), -.001)
        self.assertTrue(np.isfinite(self.data.qvel).all())
        for side, node in (('left', 0), ('right', -1)):
            site = self.model.site(f'disc_{side}_anchor').id
            self.assertLess(np.linalg.norm(self.data.site_xpos[site]-nodes[node]), .0005)

    def test_ring_distance_alone_does_not_prove_release(self):
        points = node_positions(self.model, self.data)
        center = .5*(points[5]+points[6])
        normal = points[6]-points[5]; normal /= np.linalg.norm(normal)
        x = np.cross([1., 0., 0.], normal); x /= np.linalg.norm(x)
        q = Rotation.from_matrix(np.column_stack([x, np.cross(normal, x), normal])).as_quat()
        address = self.model.joint('ring_free').qposadr[0]
        self.data.qpos[address:address+7] = np.r_[center, q[[3, 0, 1, 2]]]
        mujoco.mj_forward(self.model, self.data)
        self.assertGreater(cord_disk_crossings(self.model, self.data), 0)
        self.data.qpos[address:address+3] = [.5, .5, .2]
        mujoco.mj_forward(self.model, self.data)
        self.assertEqual(cord_disk_crossings(self.model, self.data), 0)


if __name__ == '__main__':
    unittest.main()
