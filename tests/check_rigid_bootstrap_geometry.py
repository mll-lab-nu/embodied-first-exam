"""Geometry checks that prevent invalid chain probe initializations."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.tasks._rigid_geometry import RingGeometry, write_ring
from topogym.tasks.horseshoe_ring.chain_probe import ChainProbeLayout
from topogym.tasks.buzz_wire_3d.probe import BuzzProbeLayout


class RigidProbeGeometryChecks(unittest.TestCase):
    def test_chain_is_linked_and_invalid_spacing_is_rejected(self):
        layout = ChainProbeLayout()
        layout.validate()
        self.assertEqual([abs(v) for v in layout.linking(layout.poses())], [1,1])
        for spacing in (.001, .1):
            with self.assertRaises(ValueError): replace(layout,spacing_m=spacing).validate()
        separated = replace(layout,spacing_m=.12)
        self.assertEqual(separated.linking(separated.poses()), [0,0])

    def test_compound_ring_is_one_rigid_body_without_joints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"ring.urdf"
            geometry = RingGeometry()
            report = write_ring(path,geometry)
            root = ET.parse(path).getroot()
            self.assertEqual(len(root.findall("link")),1)
            self.assertEqual(root.findall("joint"),[])
            self.assertEqual(len(root.findall(".//collision")),96)
            self.assertGreater(report["mass_kg"],0.)
            self.assertAlmostEqual(report["mass_kg"],geometry.mass_kg)

    def test_buzz_aperture_and_bend_clearance_are_required(self):
        layout=BuzzProbeLayout()
        layout.validate()
        for invalid in (replace(layout,wire_radius_m=.03),replace(layout,curve_radius_m=.03)):
            with self.assertRaises(ValueError): invalid.validate()

    def test_buzz_reference_ring_plane_follows_wire_tangent(self):
        layout=BuzzProbeLayout()
        for u in (.2,.5,.8,1.):
            _,q=layout.pose(u)
            p0,_=layout.pose(u-1e-5);p1,_=layout.pose(u+1e-5)
            tangent=(p1-p0)/np.linalg.norm(p1-p0)
            normal=Rotation.from_quat(q[[1,2,3,0]]).apply([0,0,1])
            np.testing.assert_allclose(tangent,normal,atol=1e-7)


if __name__ == "__main__": unittest.main()
