"""FEM constitutive, mesh and reload checks, independent of long settling runs."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.slotted_post_ring.fem import FEMSettings, build_model, signed_volumes


class VolumetricCordChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory()
        cls.folder=Path(cls.directory.name)
        cls.model,cls.data,cls.spec=build_model(cls.folder)
        cls.mesh=np.load(cls.folder/'fem_mesh.npz')
        cls.settings=FEMSettings()

    @classmethod
    def tearDownClass(cls):
        cls.mesh.close();cls.directory.cleanup()

    def test_conforming_positive_volume_mesh(self):
        rest=self.mesh['rest'];tets=self.mesh['elements']
        self.assertGreater(signed_volumes(rest,tets).min(),0)
        faces=Counter(tuple(sorted(face)) for tet in tets for face in
                      (tet[[0,1,2]],tet[[0,1,3]],tet[[0,2,3]],tet[[1,2,3]]))
        self.assertTrue(all(n in (1,2) for n in faces.values()))
        boundary=[face for face,n in faces.items() if n==1]
        edges=Counter(tuple(sorted(e)) for f in boundary for e in
                      ((f[0],f[1]),(f[0],f[2]),(f[1],f[2])))
        self.assertTrue(all(n==2 for n in edges.values()))
        self.assertEqual(len(set(v for f in boundary for v in f))-len(edges)+len(boundary),2)
        side=self.settings.radial_segments;r=self.spec['layout']['rope_radius_m']
        area=.5*side*r*r*np.sin(2*np.pi/side)
        self.assertAlmostEqual(signed_volumes(rest,tets).sum(),area*np.ptp(rest[:,0]),places=12)

    def test_fem_and_assembled_keyframe_survive_xml_and_binary_reload(self):
        xml=mujoco.MjModel.from_xml_path(str(self.folder/'scene.xml'))
        binary=mujoco.MjModel.from_binary_path(str(self.folder/'scene.mjb'))
        for model in (xml,binary):
            self.assertEqual(model.flex_dim.tolist(),[3])
            self.assertEqual(model.neq,2)  # Two end pivots, no cord length equalities.
            self.assertTrue(np.any(model.flex_stiffness))
            self.assertEqual(model.flex_edgeequality.tolist(),[0])
            data=mujoco.MjData(model)
            mujoco.mj_resetDataKeyframe(model,data,model.key('assembled').id)
            mujoco.mj_forward(model,data)
            np.testing.assert_allclose(data.flexvert_xpos,self.mesh['spawn'],atol=2e-11)
            for side,node in (('left',0),('right',-1)):
                tip=data.flexvert_xpos[self.mesh['center_indices'][node]]
                np.testing.assert_allclose(data.site_xpos[model.site(f'disc_{side}_anchor').id],tip,atol=2e-11)
        np.testing.assert_array_equal(xml.flex_stiffness,binary.flex_stiffness)
        np.testing.assert_array_equal(xml.key_qpos,binary.key_qpos)

    def isolated_material(self,positions,velocity=None):
        model=mujoco.MjModel.from_binary_path(str(self.folder/'scene.mjb'))
        model.opt.gravity[:]=0
        model.opt.disableflags|=int(mujoco.mjtDisableBit.mjDSBL_CONTACT)|int(mujoco.mjtDisableBit.mjDSBL_EQUALITY)
        data=mujoco.MjData(model)
        indices=[]
        for i,delta in enumerate(positions-self.mesh['rest']):
            qs=[model.joint(f'fem_{i}_{a}').qposadr[0] for a in range(3)]
            data.qpos[qs]=delta
            indices.append([model.joint(f'fem_{i}_{a}').dofadr[0] for a in range(3)])
        if velocity is not None:
            data.qvel[np.asarray(indices)]=velocity
        mujoco.mj_forward(model,data)
        return data.qfrc_passive[np.asarray(indices)]

    def test_rigid_rotation_has_no_elastic_restoring_force(self):
        rest=self.mesh['rest']
        rotated=Rotation.from_euler('xyz',[.4,-.8,1.2]).apply(rest)+[.2,-.3,.5]
        self.assertLess(np.linalg.norm(self.isolated_material(rotated)),1e-7)

    def test_tensile_force_matches_continuum_constitutive_law(self):
        rest=self.mesh['rest'];stretched=rest.copy();stretch=1.01
        stretched[:,0]*=stretch
        forces=self.isolated_material(stretched)
        # Homogeneous axial stretch with zero lateral strain. The exact
        # first Piola stress is (lambda+2*mu)/2*(stretch^2-1)*stretch.
        E=self.settings.young_pa;nu=self.settings.poisson
        lame=E*nu/((1+nu)*(1-2*nu));mu=E/(2*(1+nu))
        sides=self.settings.radial_segments;r=self.spec['layout']['rope_radius_m']
        area=.5*sides*r*r*np.sin(2*np.pi/sides)
        expected=area*(lame+2*mu)/2*(stretch**2-1)*stretch
        left=forces[np.isclose(rest[:,0],rest[:,0].min()),0].sum()
        right=forces[np.isclose(rest[:,0],rest[:,0].max()),0].sum()
        self.assertAlmostEqual(left,expected,places=8)
        self.assertAlmostEqual(right,-expected,places=8)
        np.testing.assert_allclose(forces.sum(axis=0),0,atol=1e-9)

    def test_mass_proportional_damping_dissipates_rigid_translation(self):
        velocity=np.array([.03,.01,-.02])
        force=self.isolated_material(self.mesh['rest'],velocity)
        mass=self.mesh['nodal_volumes']*self.settings.density_kg_m3
        expected=-self.settings.mass_damping_rate_s_inv*mass[:,None]*velocity
        np.testing.assert_allclose(force,expected,atol=1e-9)
        self.assertLess(float(np.sum(force*velocity)),0)


if __name__=='__main__':unittest.main()
