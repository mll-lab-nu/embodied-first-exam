"""External grip controls must remain bounded and cannot become extra hands."""
from types import SimpleNamespace
import unittest

import numpy as np

from topogym.tasks.blanket_flatten.virtual_hands import VirtualHands, bounded_grip_velocity, corner_patch


class VirtualHandChecks(unittest.TestCase):
    def test_velocity_limit_preserves_joint_motion_direction(self):
        p = np.array([[0., 0., 0.], [.02, 0., 0.]])
        target = p+np.array([[1., 2., 3.], [-2., 1., 0.]])
        velocity = bounded_grip_velocity(p, target, .005, .2)
        self.assertAlmostEqual(np.linalg.norm(velocity, axis=1).max(), .2)
        self.assertTrue(np.allclose(velocity, (target-p)*velocity[0, 0]))
        self.assertTrue(np.array_equal(p, [[0., 0., 0.], [.02, 0., 0.]]))
        self.assertTrue(np.array_equal(bounded_grip_velocity(p, p, .005, .2), np.zeros_like(p)))

    def test_material_patch_excludes_spatially_overlapping_other_layers(self):
        uv = np.array([[-.3,-.24],[-.296,-.24],[-.3,-.236],[.3,-.24],[-.3,.24]])
        self.assertEqual(corner_patch(uv, [-.3,-.24], .01).tolist(), [0, 1, 2])
        with self.assertRaises(ValueError):
            corner_patch(uv, [-.3,-.24], .001)

    def test_rejects_more_than_two_overlapping_or_unreleased_grips_before_backend_calls(self):
        e = VirtualHands.__new__(VirtualHands)
        e.grips = []
        for groups in ([np.array([0])]*3, [np.array([0,1]), np.array([1,2])], []):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                e.grasp(groups, 'test')
        e.grips = [object()]
        with self.assertRaises(ValueError):
            e.grasp([np.array([0,1,2])], 'test')

    def test_release_zeroes_and_frees_only_the_held_particles(self):
        calls = []
        cloth = SimpleNamespace(set_particles_vel=lambda v, i: calls.append(('velocity', v, i.tolist())),
                                release_particle=lambda i: calls.append(('release', i.tolist())))
        e = VirtualHands.__new__(VirtualHands)
        e.task = SimpleNamespace(cloth=cloth)
        e.grips = [dict(indices=np.array([2,3])), dict(indices=np.array([8,9]))]
        e.releases = 0
        e.label = lambda *args: None
        e.release()
        self.assertEqual(calls, [('velocity',0.,[2,3]),('release',[2,3]),('velocity',0.,[8,9]),('release',[8,9])])
        self.assertEqual(e.grips, [])
        self.assertEqual(e.releases, 1)

    def test_releasing_one_end_preserves_the_other_grip(self):
        calls = []
        cloth = SimpleNamespace(set_particles_vel=lambda v, i: calls.append(('velocity', i.tolist())),
                                release_particle=lambda i: calls.append(('release', i.tolist())))
        e = VirtualHands.__new__(VirtualHands)
        e.task = SimpleNamespace(cloth=cloth)
        e.grips = [dict(indices=np.array([2,3])), dict(indices=np.array([8,9]))]
        e.releases = 0
        e.label = lambda *args, **kwargs: None
        e.release_one(1)
        self.assertEqual(calls, [('velocity',[8,9]),('release',[8,9])])
        self.assertEqual(len(e.grips), 1)
        self.assertEqual(e.grips[0]['indices'].tolist(), [2,3])


if __name__ == '__main__':
    unittest.main()
