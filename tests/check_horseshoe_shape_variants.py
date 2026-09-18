"""Shape changes must preserve attachment geometry and use the actual ellipse bore."""
from copy import deepcopy
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks.horseshoe_ring.geometry import HorseshoeAssembly, band_centerline, horseshoe_band
from topogym.tasks.horseshoe_ring.shape_variants import seed, make_template, retarget_frames
from topogym.tasks.horseshoe_ring.independent_motion import IndependentWitness


class ShapeChecks(unittest.TestCase):
    def test_outline_deformation_preserves_terminal_anchors(self):
        base=seed()['template']['horseshoe']
        angles=np.array([np.radians(base['mouth_half_angle_deg']),2*np.pi-np.radians(base['mouth_half_angle_deg'])])
        expected=band_centerline(base,1.,angles)
        for shape in (-1.,1.):
            h=make_template(shape,1.15,18.)['horseshoe']
            np.testing.assert_allclose(band_centerline(h,1.,angles),expected,atol=1e-12)
            self.assertGreater(np.linalg.norm(band_centerline(h,1.,np.array([2.2]))-band_centerline(base,1.,np.array([2.2]))),1.)
            mesh,pieces=horseshoe_band(h,.002)
            self.assertTrue(mesh.is_watertight)
            self.assertTrue(all(p.is_convex for p in pieces))

    def test_waist_is_continuous_at_the_back_of_the_shoe(self):
        h=make_template(-1.,1.1,18.)['horseshoe']
        points=band_centerline(h,1.,np.array([np.pi-1e-6,np.pi,np.pi+1e-6]))
        self.assertAlmostEqual(points[1,1],0.,places=10)
        self.assertLess(np.linalg.norm(points[0]-points[2]),.001)

    def test_ellipse_phase_changes_axes_without_changing_plane(self):
        t=make_template(0.,1.3,18.)
        a=HorseshoeAssembly(t).loops['target_ring']
        t=deepcopy(t);t['target_ring']['initial_phase_deg']=90.
        b=HorseshoeAssembly(t).loops['target_ring']
        np.testing.assert_allclose(a.rotation.apply([0,0,1]),b.rotation.apply([0,0,1]),atol=1e-12)
        self.assertGreater(np.ptp(b.points()[:,1]),np.ptp(a.points()[:,1])+.01)

    def test_long_axis_cannot_hide_an_invalid_minor_bore(self):
        t=deepcopy(seed()['template'])
        t['target_ring']['centerline_radii']=[45.,8.]
        topology=HorseshoeAssembly(t).topology_report()
        self.assertFalse(topology['target_encloses_both_chain_spans'])

    def test_com_retarget_preserves_eye_material_motion(self):
        base=HorseshoeAssembly(seed()['template'],seed()['scale'])
        model=IndependentWitness(make_template(.5,1.1,18.),seed()['scale'])
        indices=[0,800,2000]
        frames=retarget_frames(model,indices)
        for index,frame in zip(indices,frames):
            for k in (0,1):
                old=base.bodies[k];new=model.assembly.bodies[k]
                a=seed()['frames'][index][old.name];b=frame[new.name]
                world_old=Rotation.from_quat(a['quat']).apply(old.loops[0].points()-seed()['centers'][k])+a['pos']
                world_new=Rotation.from_quat(b['quat']).apply(new.loops[0].points()-model.centers[k])+b['pos']
                np.testing.assert_allclose(world_new,world_old,atol=1e-12)

    def test_invalid_ellipse_and_outline_parameters_are_rejected(self):
        for key,value in [('centerline_radii',[20.,1.]),('initial_phase_deg',float('nan'))]:
            t=deepcopy(seed()['template']);t['target_ring'][key]=value
            with self.assertRaises(ValueError):HorseshoeAssembly(t)
        t=deepcopy(seed()['template']);t['horseshoe']['outline_power']=0.
        with self.assertRaises(ValueError):HorseshoeAssembly(t)


if __name__=='__main__':
    unittest.main()
