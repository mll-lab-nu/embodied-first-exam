"""Geometric negative controls and fail-closed contact qualification."""
from copy import deepcopy
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.tasks.cast_keyhole.collision import CompoundCollision, Motion, certify_motion
from topogym.tasks.cast_keyhole.physics_probe import specifications
from topogym.tasks.cast_keyhole.qualify import compare_reports
from topogym.tasks.cast_keyhole.route_probe import candidates


class CollisionChecks(unittest.TestCase):
    def test_full_containment_and_separation(self):
        col = CompoundCollision([trimesh.creation.box([2,2,2])], [trimesh.creation.box([.2,.2,.2])])
        self.assertLess(col.gap(np.eye(3), np.zeros(3)), 0)
        self.assertAlmostEqual(col.gap(np.eye(3), [2,0,0]), .9)

    def test_aperture_is_not_replaced_by_compound_hull(self):
        sides = []
        for x in (-2,2):
            mesh = trimesh.creation.box([1,4,1])
            mesh.apply_translation([x,0,0])
            sides.append(mesh)
        col = CompoundCollision(sides,[trimesh.creation.box([1,1,1])])
        self.assertGreater(col.gap(np.eye(3),[0,0,0]),0)
        self.assertLess(col.gap(Rotation.from_euler("z",.7).as_matrix(),[1.5,0,0]),0)

    def test_interval_certificate_rejects_collision_between_clear_endpoints(self):
        col = CompoundCollision([trimesh.creation.box([1,1,1])],[trimesh.creation.box([1,1,1])])
        bad = Motion("through", np.eye(3), np.array([-2.,0,0]), np.array([2.,0,0]))
        self.assertGreater(col.gap(*bad.pose(0)),0)
        self.assertGreater(col.gap(*bad.pose(1)),0)
        self.assertFalse(certify_motion(col,bad)["passed"])
        safe = Motion("around", np.eye(3), np.array([-2.,2,0]), np.array([2.,2,0]))
        result = certify_motion(col,safe)
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["continuous_gap_lower_bound_m"],.00005)

    def test_rotational_certificate_catches_sweep_collision(self):
        obstacle = trimesh.creation.box([.2,.2,.2])
        obstacle.apply_translation([0,2,0])
        moving = trimesh.creation.box([.2,.2,.2])
        col = CompoundCollision([obstacle],[moving])
        motion = Motion("sweep", np.eye(3), np.array([2.,0,0]),
                        axis=np.array([0.,0,1]),angle_rad=np.pi,pivot=np.zeros(3))
        self.assertGreater(col.gap(*motion.pose(0)),0)
        self.assertGreater(col.gap(*motion.pose(1)),0)
        self.assertFalse(certify_motion(col,motion)["passed"])


class QualificationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs = specifications()

    def reports(self):
        coarse = dict(config=dict(dt=.001),thresholds={},fingerprint={"test":"current"},
            source_changed_during_run=False,passed=True,pose_writes_after_reset=False,
            simulated_seconds=5.,sat_sample_interval_s=.005,genesis_version="test",
            cases=[dict(**s,passed=True,max_contact_penetration_m=0.,min_sampled_sat_gap_m=.001,
                tail_linear_speed_m_s=0.,tail_angular_speed_rad_s=0.,
                final_relative_translation_m=[0.,0,0],final_relative_quaternion_xyzw=[0,0,0,1]) for s in self.specs])
        fine = deepcopy(coarse)
        fine["config"]["dt"] = .0005
        return coarse,fine

    def evaluate(self,a,b):
        return compare_reports(a,b,{"test":"current"})

    def test_bench_pass_does_not_qualify_robot_or_official_route(self):
        a,b = self.reports()
        result = self.evaluate(a,b)
        self.assertTrue(result["contact_bench_qualified"])
        for key in ("official_route_verified","robot_grasp_verified","formal_demo_qualified"):
            self.assertFalse(result[key])

    def test_missing_duplicate_failed_stale_and_changed_sources_rejected(self):
        for change in (lambda b:b["cases"].pop(),lambda b:b["cases"].append(b["cases"][0]),
                       lambda b:b["cases"][0].update(passed=False),
                       lambda b:b.update(fingerprint={}),lambda b:b.update(source_changed_during_run=True)):
            a,b = self.reports()
            change(b)
            self.assertFalse(self.evaluate(a,b)["contact_bench_qualified"])

    def test_convergence_and_numeric_corruption_rejected(self):
        for value in ([.0011,0,0],[float("nan"),0,0],[0,0]):
            a,b = self.reports()
            b["cases"][0]["final_relative_translation_m"] = value
            self.assertFalse(self.evaluate(a,b)["contact_bench_qualified"])
        a,b = self.reports()
        b["cases"][0]["final_relative_quaternion_xyzw"] = Rotation.from_rotvec([0,0,.021]).as_quat().tolist()
        self.assertFalse(self.evaluate(a,b)["contact_bench_qualified"])

    def test_config_change_or_same_time_step_is_not_convergence_evidence(self):
        a,b = self.reports()
        b["config"]["friction"] = .7
        self.assertFalse(self.evaluate(a,b)["contact_bench_qualified"])
        a,b = self.reports()
        b["config"]["dt"] = a["config"]["dt"]
        self.assertFalse(self.evaluate(a,b)["contact_bench_qualified"])

    def test_pass_flag_cannot_override_contact_failure(self):
        a,b = self.reports()
        b["cases"][0]["min_sampled_sat_gap_m"] = -.001
        self.assertFalse(self.evaluate(a,b)["contact_bench_qualified"])


class PartialRouteChecks(unittest.TestCase):
    def test_partial_approach_certifies_but_direct_notch_transfer_collides(self):
        source,_,collision,motions,wrong = candidates()
        self.assertFalse(source["complete_route"])
        self.assertFalse(source["robot_execution"])
        for motion in motions:
            with self.subTest(segment=motion.name):
                result = certify_motion(collision,motion,margin_m=.00015)
                self.assertTrue(result["passed"],result)
        self.assertFalse(certify_motion(collision,wrong,margin_m=.00015)["passed"])


if __name__ == "__main__":
    unittest.main()
