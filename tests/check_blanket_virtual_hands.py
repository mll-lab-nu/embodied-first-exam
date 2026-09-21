"""External grip controls must remain bounded and cannot become extra hands."""
from types import SimpleNamespace
import unittest

import numpy as np

from topogym.tasks.blanket_flatten.virtual_hands import VirtualHands, bounded_grip_velocity, corner_patch, upright_grip_targets, corner_material_rotation, edge_following_lay_targets


class VirtualHandChecks(unittest.TestCase):
    def test_laying_tracks_sliding_free_edge_without_exceeding_material_span(self):
        offsets = [np.array([[0.,-.003,0.],[0.,.003,0.]])]*2
        pivot = np.array([.35, 0., .002])
        initial = edge_following_lay_targets(offsets, [-.23,.23], pivot, .58, .65, .015, 0.)
        self.assertTrue(all(np.allclose(p.mean(axis=0)[[0,2]], [.35,.65]) for p in initial))
        for t in [.5, .75, 1.]:
            a = edge_following_lay_targets(offsets, [-.23,.23], pivot, .58, .65, .015, t)
            b = edge_following_lay_targets(offsets, [-.23,.23], pivot+[.1,0,0], .58, .65, .015, t)
            for before, after in zip(a,b):
                self.assertTrue(np.allclose(after-before, [.1,0,0]))
                self.assertAlmostEqual(np.linalg.norm(before.mean(axis=0)[[0,2]]-pivot[[0,2]]), .58)
                self.assertAlmostEqual(np.linalg.norm(before[1]-before[0]), .006)

    def test_corner_alignment_corrects_reversed_material_direction_without_reflection(self):
        from scipy.spatial.transform import Rotation
        uv = np.array([[0.,0.],[.004,0.],[0.,.004],[.003,.003]])
        uv -= uv.mean(axis=0)
        upright = np.c_[np.zeros(len(uv)),uv[:,1],-uv[:,0]]
        folded = upright@Rotation.from_rotvec([.2,-.6,2.7]).as_matrix().T
        rotation, error = corner_material_rotation(folded, uv)
        self.assertLess(error, 1e-12)
        self.assertAlmostEqual(np.linalg.det(rotation), 1.)
        self.assertTrue(np.allclose(folded@rotation.T, upright))
        with self.assertRaises(ValueError):
            corner_material_rotation(folded, np.zeros_like(uv))

    def test_uprighting_preserves_patch_geometry_and_sets_supported_vertical_span(self):
        patch = np.array([[0.,-.03,0.],[.01,0.,.002],[0.,.03,0.]])
        groups = [patch+[-.27,0.,1.2],patch+[.27,0.,1.2]]
        initial = upright_grip_targets(groups, .57, 1.4, 0.)
        self.assertTrue(all(np.allclose(a,b) for a,b in zip(initial,groups)))
        final = upright_grip_targets(groups, .57, 1.4, 1.)
        centers = np.array([p.mean(axis=0) for p in final])
        self.assertAlmostEqual(centers[0,2]-centers[1,2], .57)
        self.assertAlmostEqual(centers[:,2].mean(), 1.4)
        self.assertAlmostEqual(centers[0,0], centers[1,0])
        for before, after in zip(groups, final):
            self.assertTrue(np.allclose(np.linalg.norm(before[:,None]-before,axis=2),
                                        np.linalg.norm(after[:,None]-after,axis=2)))

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
