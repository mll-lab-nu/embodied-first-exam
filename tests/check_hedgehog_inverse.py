"""Solid containment and geometric frame checks for inverse cage design."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh

from topogym.tasks.hedgehog_in_cage.inverse_window import SolidOracle, Kinematics, SEED
from topogym.tasks.hedgehog_in_cage.inverse_runtime import admitted
from topogym.tasks.hedgehog_in_cage.plan_escape import interpolate


class InverseCageTests(unittest.TestCase):
    def test_convex_query_detects_full_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            trimesh.creation.box([.02]*3).export(p/'cage_collision_000.obj')
            trimesh.creation.box([.002]*3).export(p/'hedgehog_collision_000.obj')
            oracle=SolidOracle(p)
            self.assertLessEqual(oracle.distance([0,0,0,0,0,0,1]),0)
            self.assertAlmostEqual(oracle.distance([.03,0,0,0,0,0,1]),.019,places=8)

    def test_pose_sampling_bounds_motion_of_spike_tip(self):
        a=np.array([0,0,0,0,0,0,1.])
        b=np.r_[[.01,.02,-.03],Rotation.from_euler('xyz',[.4,-1.,.5]).as_quat()]
        samples=list(interpolate(a,b,.0001));points=np.array([[.092,0,0],[0,-.092,0],[0,0,.092]])
        previous=None
        for q in samples:
            current=Rotation.from_quat(q[3:]).apply(points)+q[:3]
            if previous is not None:self.assertLessEqual(np.linalg.norm(current-previous,axis=1).max(),.000100001)
            previous=current

    @unittest.skipUnless((SEED/'robot_escape_plan.npz').exists(),'Seed demo archive is an external generated artifact')
    def test_seed_fk_matches_saved_object_pose(self):
        kin=Kinematics();seed=np.load(SEED/'robot_escape_plan.npz')
        for i in (0,50,100,150,219):
            kin.q[:7]=seed['arm_qpos'][i];actual=kin.ball_pose();expected=seed['ball_poses'][i]
            # The seed's 1e-4 rad hand tolerance is amplified by the 175 mm
            # hand-to-ball lever arm, in addition to its 1e-5 m tolerance.
            self.assertLess(np.linalg.norm(actual[:3]-expected[:3]),.00005)
            self.assertLess((Rotation.from_quat(actual[3:])*Rotation.from_quat(expected[3:]).inv()).magnitude(),.0001)

    def test_pass_flag_without_positive_margin_cannot_admit_physics(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'certificate.json').write_text(json.dumps(dict(passed=True,continuous_clearance_lower_bound_m=0)))
            with self.assertRaisesRegex(ValueError,'certificate'):admitted(p)


if __name__=='__main__':unittest.main()
