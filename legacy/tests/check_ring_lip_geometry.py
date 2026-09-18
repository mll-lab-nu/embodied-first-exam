"""Geometry gates for an open, one-sided lip; no simulation success inference."""
import unittest
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from topogym.tasks_legacy.deformation._ring_lip_geometry import (
    validate_geometry, sector_mesh, lip_bounds, clearance_radius, seat_report,
)


class RingLipGeometryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = OmegaConf.load(Path(__file__).resolve().parents[1]/'configs/ring_lip_install.yaml').install

    def test_count_does_not_change_opening_or_individual_lip(self):
        for count in (1,2,3):
            self.cfg.lip_count=count
            report=validate_geometry(self.cfg)
            self.assertEqual(report['local_opening_mm'],12.)
            self.assertEqual(report['arc_per_lip_deg'],20.)
            self.assertFalse(report['fixed_bridge'])

    def test_swept_solids_are_closed_and_have_expected_volume(self):
        for angle in (20.,360.):
            mesh=sector_mesh(.1,.12,.02,.025,0.,angle,segments=128)
            exact=np.pi*(.12**2-.1**2)*.005*angle/360
            self.assertTrue(mesh.is_watertight)
            self.assertAlmostEqual(mesh.volume/exact,1.,delta=.001)

    def test_both_opening_directions_admit_undeformed_cross_section(self):
        g=self.cfg
        g.lip_sides=['outer','inner','outer']
        for i in range(3):
            r=clearance_radius(g,i)
            lo,hi=lip_bounds(g,i)
            self.assertGreater(r-g.tube_radius,g.groove_inner)
            self.assertLess(r+g.tube_radius,g.groove_outer)
            self.assertTrue(r+g.tube_radius<lo or r-g.tube_radius>hi)

    def test_reject_bridge_full_circle_and_overlapping_lips(self):
        for field,value in [('lip_opening',0.),('lip_arc_deg',360.),('lip_angles_deg',[-90.,-85.,150.])]:
            with self.subTest(field=field):
                cfg=OmegaConf.create(OmegaConf.to_container(self.cfg))
                cfg[field]=value
                with self.assertRaises(ValueError): validate_geometry(cfg)

    def test_success_requires_whole_ring_and_material_under_each_lip(self):
        g=self.cfg
        angles=np.linspace(0,2*np.pi,360,endpoint=False)
        points=np.column_stack((g.center[0]+g.radius*np.cos(angles),
                                g.center[1]+g.radius*np.sin(angles),np.full(360,g.floor_z+g.tube_radius)))
        self.assertTrue(seat_report(points,g)['success'])
        points[0,2]=g.lip_top_z+.01
        self.assertFalse(seat_report(points,g)['success'])


if __name__=='__main__': unittest.main()
