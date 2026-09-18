"""Inverse-scene consistency and the limits of inherited geometric evidence."""
from copy import deepcopy
from pathlib import Path
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.horseshoe_ring.geometry import load_template
from topogym.tasks.horseshoe_ring.independent_motion import IndependentWitness
from topogym.tasks.horseshoe_ring.ik_trace import command_hash
from topogym.tasks.horseshoe_ring.trace_scene_variants import (
    common_pose, infer_body_from_grasp, inverse_initial_similarity, placement_weight, relative_pose,
)


class TraceVariantChecks(unittest.TestCase):
    def setUp(self):
        self.before = {
            "left": (np.array([-.15, -.03, .2]), Rotation.from_euler("xyz", [15, 30, 20], degrees=True)),
            "right": (np.array([.15, .03, .2]), Rotation.from_euler("xyz", [-10, 25, -30], degrees=True)),
        }
        self.r = Rotation.from_euler("xyz", [5, 2, -3], degrees=True)
        self.s = .96
        self.t = np.array([.02, -.01, .008])
        self.after = {k: (self.s*self.r.apply(p)+self.t, self.r*r) for k, (p, r) in self.before.items()}

    def test_scene_recovered_from_two_full_grasp_poses(self):
        scale, rotation, shift, residual = inverse_initial_similarity(self.before, self.after)
        self.assertAlmostEqual(scale, self.s)
        np.testing.assert_allclose(rotation.as_matrix(), self.r.as_matrix(), atol=1e-12)
        np.testing.assert_allclose(shift, self.t, atol=1e-12)
        self.assertLess(residual["position_residual_m"], 1e-12)

    def test_arbitrary_joint_effects_cannot_be_called_a_scene(self):
        after = deepcopy(self.after)
        after["right"][0][2] += .015
        with self.assertRaisesRegex(ValueError, "compatible initial scene"):
            inverse_initial_similarity(self.before, after)
        after = deepcopy(self.after)
        after["right"] = (after["right"][0], Rotation.from_euler("x", 3, degrees=True)*after["right"][1])
        with self.assertRaisesRegex(ValueError, "compatible initial scene"):
            inverse_initial_similarity(self.before, after)

    def test_scaled_grasp_round_trip_retains_contact_transform(self):
        body = dict(pos=[.2, .1, .3], quat=Rotation.from_euler("x", .7).as_quat().tolist())
        grasp = relative_pose(body, self.before["left"])
        recovered = infer_body_from_grasp(self.after["left"], grasp, self.s)
        expected_p = self.s*self.r.apply(body["pos"])+self.t
        expected_r = self.r*Rotation.from_quat(body["quat"])
        np.testing.assert_allclose(recovered["pos"], expected_p, atol=1e-12)
        self.assertLess((Rotation.from_quat(recovered["quat"]).inv()*expected_r).magnitude(), 1e-12)

    def test_trace_hash_covers_fingers_and_time(self):
        motion = dict(fps=12, frames=[dict(qpos=[0.]*16)])
        original = command_hash(motion)
        changed = deepcopy(motion); changed["frames"][0]["qpos"][14] = .01
        self.assertNotEqual(command_hash(changed), original)
        changed = deepcopy(motion); changed["fps"] = 24
        self.assertNotEqual(command_hash(changed), original)

    def test_positive_similarity_preserves_actual_collision_distances(self):
        path = Path(__file__).resolve().parents[1]/"assets/tasks/horseshoe_ring/tutorial_solvable_v3/template.json"
        a = IndependentWitness(load_template(path), 2.)
        b = IndependentWitness(load_template(path), 2.*self.s)
        old = {n: dict(pos=p.tolist(), quat=[0, 0, 0, 1]) for n, p in zip(a.names, a.centers)}
        new = {n: dict(pos=(self.s*self.r.apply(p)+self.t).tolist(), quat=self.r.as_quat().tolist())
               for n, p in zip(a.names, a.centers)}
        np.testing.assert_allclose(b.distances(new), self.s*a.distances(old), atol=1e-10, rtol=1e-8)

    def test_workspace_return_is_monotonic_with_zero_endpoint_slope(self):
        values = [placement_weight(t, 10, 20) for t in np.linspace(0, 30, 301)]
        self.assertEqual(values[0], 1)
        self.assertEqual(values[-1], 0)
        self.assertTrue(np.all(np.diff(values) <= 1e-15))
        self.assertLess(abs(placement_weight(10.0001, 10, 20)-1), 1e-9)
        self.assertLess(abs(placement_weight(19.9999, 10, 20)), 1e-9)

    def test_terminal_anchor_avoids_moving_the_extracting_wrist(self):
        origin = np.array([0., .05, .2])
        center, rotation = common_pose(829, self.before["left"], self.after["left"], origin,
            origin+self.t, self.r, self.s, {"fold_roll_deg": 2}, 252, 625, 805, 12)
        tcp = center+rotation.apply(self.s*(self.after["left"][0]-origin))
        np.testing.assert_allclose(tcp, self.before["left"][0], atol=1e-12)
        self.assertLess(((rotation*self.after["left"][1]).inv()*self.before["left"][1]).magnitude(), 1e-12)


if __name__ == "__main__":
    unittest.main()
