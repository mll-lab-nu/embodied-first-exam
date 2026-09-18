"""Route admission and analytic rigid-body feed-forward checks."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.cast_keyhole.collision import Motion
from topogym.tasks.cast_keyhole.route_probe import PoseSegment
from topogym.tasks.cast_keyhole.solution import unpack_pose, read_motion
from topogym.tasks.cast_keyhole.trajectory_probe import target, run
from topogym.tasks.cast_keyhole.instance_solution import initial_relative_pose, require_current_instance_certificate
from topogym.tasks.cast_keyhole.geometry import ASSET_ROOT
from topogym.tasks.cast_keyhole.solution import load_solution


class SolutionChecks(unittest.TestCase):
    def test_current_instance_path_starts_at_actual_mesh_assembly(self):
        data,_,_,motions=load_solution(ASSET_ROOT/"baseline_solution.json")
        actual_r,actual_t=initial_relative_pose(data["scale"])
        r,t=motions[0].pose(0)
        np.testing.assert_allclose(r,actual_r,atol=1e-12)
        np.testing.assert_allclose(t,actual_t,atol=1e-12)
        # The historical top-bore candidate is a different instance.
        other=json.loads((ASSET_ROOT/"route_candidates.json").read_text())
        self.assertGreater(np.linalg.norm(actual_t-np.array(other["initial_silver_translation_mm"])*.003),.005)

    def test_current_instance_pass_flag_cannot_bypass_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert=Path(tmp)/"certificate.json"
            cert.write_text(json.dumps(dict(certificate_type="current_instance_path_v1",
                full_geometric_path_verified=True,errors=[],initial_pose_verified_against_scene=True)))
            with self.assertRaisesRegex(ValueError,"Incomplete, failing, or stale"):
                require_current_instance_certificate(ASSET_ROOT/"baseline_solution.json",cert)
            with self.assertRaisesRegex(ValueError,"Incomplete, failing, or stale"):
                run(ASSET_ROOT/"baseline_solution.json",cert,Path(tmp)/"output")
            self.assertFalse((Path(tmp)/"output").exists())

    def test_invalid_pose_or_axis_cannot_be_normalized_silently(self):
        for q in ([0, 0, 0, 2], [0, 0, float("nan"), 1]):
            with self.assertRaises(ValueError):
                unpack_pose(dict(translation_mm=[0, 0, 0], quaternion_xyzw=q), 3)
        with self.assertRaises(ValueError):
            read_motion(dict(type="pivot", name="bad", start=dict(
                translation_mm=[0, 0, 0], quaternion_xyzw=[0, 0, 0, 1]),
                axis=[0, 2, 0], pivot_mm=[0, 0, 0], angle_rad=1), 3)

    def test_incomplete_route_rejected_before_simulator_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert = Path(tmp)/"certificate.json"
            cert.write_text(json.dumps(dict(full_geometric_path_verified=False)))
            with self.assertRaisesRegex(ValueError, "Full route geometry must pass"):
                run(Path(tmp)/"missing_solution.json", cert, Path(tmp)/"output")
            self.assertFalse((Path(tmp)/"output").exists())

    def test_pass_flag_without_interval_evidence_cannot_start_physics(self):
        with tempfile.TemporaryDirectory() as tmp:
            solution, cert = Path(tmp)/"solution.json", Path(tmp)/"certificate.json"
            solution.write_text(json.dumps(dict(motions=[], scale=3)))
            cert.write_text(json.dumps(dict(full_geometric_path_verified=True, errors=[], fingerprint={})))
            with self.assertRaisesRegex(ValueError, "Incomplete or stale"):
                run(solution, cert, Path(tmp)/"output")
            self.assertFalse((Path(tmp)/"output").exists())

    def test_com_velocity_acceleration_match_finite_differences(self):
        motions = [
            PoseSegment("combined", np.eye(3), Rotation.from_euler("xyz", [.5, -.6, .7]).as_matrix(),
                        np.array([.02, .03, .04]), np.array([.08, -.02, .01])),
            Motion("pivot", np.eye(3), np.array([.03, -.02, .07]),
                   axis=np.array([0., 1., 0.]), angle_rad=np.pi, pivot=np.array([.01, .02, -.03])),
        ]
        center = np.array([.006, .015, -.002])
        # Nonzero u'' exercises tangential as well as centripetal acceleration.
        def phase(t):
            return .3 + .2*t + .15*t*t, .2 + .3*t, .3
        for motion in motions:
            with self.subTest(motion=motion.name):
                t, h = .2, 1e-4
                actual = target(motion, *phase(t), center)
                before = target(motion, *phase(t-h), center)
                after = target(motion, *phase(t+h), center)
                np.testing.assert_allclose(actual[2], (after[0]-before[0])/(2*h), atol=1e-8)
                np.testing.assert_allclose(actual[4], (after[0]-2*actual[0]+before[0])/h**2, atol=1e-7)
                w = Rotation.from_matrix(after[1]@before[1].T).as_rotvec()/(2*h)
                np.testing.assert_allclose(actual[3], w, atol=1e-8)
                np.testing.assert_allclose(actual[5], (after[3]-before[3])/(2*h), atol=1e-8)


if __name__ == "__main__":
    unittest.main()
