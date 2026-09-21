"""Geometric and replay-integrity regressions for authored Claw families."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import mujoco

from topogym.tasks.interlocked_claws.family_models import FamilyModel,geometry_audit
from topogym.tasks.interlocked_claws.family_robot import execute,robot_support_contacts


class AuthoredClawChecks(unittest.TestCase):
    def test_closed_solids_and_real_grasp_locations(self):
        for name in ("helical_crown","orthogonal_gate","orthogonal_gate_balanced_v2"):
            model=FamilyModel(name)
            for part in model.parts:
                self.assertTrue(part.mesh.is_watertight)
                self.assertEqual(len(part.mesh.split()),1)
                self.assertTrue((np.linalg.eigvalsh(part.mesh.moment_inertia)>0).all())
                self.assertTrue(part.mesh.contains([part.grasp[:3,3]])[0],(name,part.name))

    def test_swept_paths_and_wrong_motion_witnesses(self):
        for name in ("helical_crown","orthogonal_gate","orthogonal_gate_balanced_v2"):
            audit=geometry_audit(FamilyModel(name))
            self.assertTrue(audit["continuous_pair_path_certified"])
            self.assertGreater(audit["minimum_sampled_gap_m"],.005)
            self.assertTrue(all(x["blocked"] for x in audit["negative_controls"]))

    def test_balanced_windows_have_equal_geometry_and_baseline_scale(self):
        model=FamilyModel("orthogonal_gate_balanced_v2")
        self.assertLessEqual(float(model.parts[0].mesh.extents.max()),.264)
        # Reflection exchanges the complete windows, including their shared
        # corner. A large frame paired with a small one cannot pass this check.
        original=[];reflected=[]
        for item in model.parts[0].boxes:
            p=np.asarray(item["pose"])[:3,3];s=np.asarray(item["size"])
            original.append(tuple(np.round(np.r_[p,s],9)))
            reflected.append(tuple(np.round(np.r_[[p[1]-.12,p[0]+.12,p[2]],s[[1,0,2]]],9)))
        self.assertEqual(sorted(original),sorted(reflected))

    def test_balanced_helical_claws_are_congruent_and_need_coupled_motion(self):
        model=FamilyModel("helical_claws_balanced_v2")
        a,b=model.parts
        self.assertEqual(a.boxes,b.boxes)
        np.testing.assert_allclose(a.mesh.extents,b.mesh.extents,atol=1e-12)
        self.assertAlmostEqual(a.mesh.mass,b.mesh.mass,places=12)
        self.assertLess(a.mesh.extents.max(),.264)
        for part in model.parts:
            self.assertTrue(part.mesh.contains([part.grasp[:3,3]])[0])
        audit=geometry_audit(model)
        self.assertTrue(audit["passed"])
        self.assertGreater(audit["minimum_sampled_gap_m"],.003)
        self.assertEqual(len(audit["negative_controls"]),7)
        self.assertGreater(sum(s.rotation_angle for s in model.segments),np.pi)

    def test_counter_rotation_is_continuous_past_half_turn(self):
        from topogym.tasks.interlocked_claws.family_robot import assembly_poses
        from scipy.spatial.transform import Rotation
        model=FamilyModel("helical_claws_balanced_v2")
        settings=dict(yaw=0,counter_rotate=-.5,center=[0,-.18,.3],fraction=.5,
                      axis_rotation_xyz_deg=[0,90,0])
        poses=[assembly_poses(model,t,settings)[0] for t in np.linspace(0,model.duration,281)]
        for before,after in zip(poses,poses[1:]):
            for a,b in zip(before,after):
                self.assertLess(Rotation.from_matrix(b[:3,:3]@a[:3,:3].T).magnitude(),.02)

    def test_changed_geometry_cannot_reuse_old_ik_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);model=FamilyModel("helical_crown")
            snapshot=model.save(root/"assets")
            snapshot["parts"][0]["boxes"][0]["size"][0]*=1.01
            (root/"assets/model.json").write_text(json.dumps(snapshot))
            (root/"plan.json").write_text(json.dumps(dict(family=model.family,report=dict(passed=True))))
            with self.assertRaisesRegex(ValueError,"Model changed after planning"):
                execute(root/"plan.json",root/"execution")

    def test_released_object_still_supported_by_robot_is_detected(self):
        # No weld exists: a free block resting on an open hand is still not
        # independent table rest. Moving the support away makes it fall.
        for support_x,expected in ((0,True),(1,False)):
            xml=f'''<mujoco><option timestep=".001"/><worldbody>
              <geom type="plane" size="2 2 .1"/>
              <body name="left/left_finger_link" pos="{support_x} 0 .1">
                <geom type="box" size=".04 .04 .01"/></body>
              <body name="piece_1" pos="0 0 .131"><freejoint/>
                <geom type="box" size=".02 .02 .02" mass=".1"/></body>
              </worldbody></mujoco>'''
            model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
            for _ in range(1000):mujoco.mj_step(model,data)
            mujoco.mj_forward(model,data)
            self.assertEqual(bool(robot_support_contacts(model,data)),expected)


if __name__=="__main__":unittest.main()
