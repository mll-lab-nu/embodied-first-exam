"""Geometry/terminal regressions; physical evidence is produced by the runner."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from topogym.planning.interlocked_claws.object_oracle import (
    plan_object_path, audit_object_path, frozen_problem, separation_route, world_pose,
)
from topogym.planning.rigid_reference.geometry import RigidPathChecker, pose_dict
from topogym.planning.rigid_reference.feedback import relative_pose
from topogym.tasks.interlocked_claws.terminal import separation_candidate


class ClawsOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.problems = {v: frozen_problem(cls.root/v, variation=v)
                        for v in ("easy", "medium", "hard")}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def state(self, poses):
        return dict(bodies={n: dict(**pose_dict(p), linear_velocity_m_s=[0., 0., 0.],
                                   angular_velocity_rad_s=[0., 0., 0.]) for n, p in poses.items()})

    def test_positive_surface_gap_is_not_unlocked(self):
        for task, meshes, poses, _, report in self.problems.values():
            target, other = report["target"], report["other"]
            checker = RigidPathChecker(meshes[target], meshes[other])
            self.assertGreater(checker.clearance(relative_pose(poses[target], poses[other])), 0.)
            self.assertFalse(separation_candidate(self.state(poses), task.placement_vertices)[0])

    def test_complete_route_requires_both_pieces_quiet(self):
        for variation, (task, _, poses, _, report) in self.problems.items():
            target, other = report["target"], report["other"]
            route, _ = separation_route(task, variation)
            state = self.state({target: poses[target], other: world_pose(poses[target], route[-1])})
            self.assertTrue(separation_candidate(state, task.placement_vertices)[0])
            for name in (target, other):
                moving = deepcopy(state)
                moving["bodies"][name]["linear_velocity_m_s"] = [.01, 0., 0.]
                self.assertFalse(separation_candidate(moving, task.placement_vertices)[0])

    def test_hard_thinning_keeps_two_comparable_connected_solids(self):
        task, _, _, _, report = self.problems["hard"]
        self.assertEqual(task.claw_surface_inset_m, .003)
        pieces = report["asset_report"]["pieces"]
        self.assertTrue(all(p["watertight"] and p["components"] == 1 for p in pieces))
        self.assertLess(abs(pieces[0]["mass_kg"]/pieces[1]["mass_kg"]-1.), .01)
        self.assertFalse(report["asset_report"]["original_collision_triangles_preserved"])

    def test_hard_six_axis_pulls_still_hit(self):
        _, meshes, poses, _, report = self.problems["hard"]
        target, other = report["target"], report["other"]
        checker = RigidPathChecker(meshes[target], meshes[other])
        p, r = relative_pose(poses[target], poses[other])
        for direction in np.vstack([np.eye(3), -np.eye(3)]):
            self.assertTrue(any(checker.clearance((p+d*direction, r)) < 0.
                                for d in np.linspace(.0025, .25, 100)))

    def test_hard_route_recertifies_and_rejects_stale_identity(self):
        witness = plan_object_path(self.root/"hard_witness", variation="hard", clearance_m=.004)
        self.assertEqual(witness["status"], "object_witness_verified")
        self.assertTrue(audit_object_path(witness, self.root/"audit")["passed"])
        witness["model_revision"] = "pregrasp_scaled_weld_v3"
        with self.assertRaisesRegex(ValueError, "identity"):
            audit_object_path(witness, self.root/"stale")


if __name__ == "__main__":
    unittest.main()
