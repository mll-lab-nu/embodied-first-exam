"""Permanent attachment and rejection of reverse/bypass task shortcuts."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np

from topogym.tasks.fiber_bundling.geometry import FiberLayout
from topogym.tasks.fiber_bundling.anchored_geometry import AnchoredLayout, generate_anchored_assets
from topogym.tasks.fiber_bundling.anchored_verifier import AnchoredThreadingVerifier


class AnchoredChecks(unittest.TestCase):
    def test_spaced_support_and_historical_replay(self):
        from omegaconf import OmegaConf
        old = OmegaConf.create(dict(axis_height_m=.24, ring_distance_from_roots_m=.11))
        old_anchor = AnchoredLayout.from_task_config(old)
        self.assertEqual(old_anchor.cradle_x_m, .10)
        old.cradle_x_m = .02
        new_anchor = AnchoredLayout.from_task_config(old)
        self.assertEqual(new_anchor, AnchoredLayout())
        a, b = old_anchor.spacing(FiberLayout()), new_anchor.spacing(FiberLayout())
        self.assertAlmostEqual(b["cradle_center_to_ring_plane_m"], .33)
        self.assertAlmostEqual(b["cradle_upper_edge_to_ring_plane_m"]-a["cradle_upper_edge_to_ring_plane_m"], .08)

    def test_one_fixed_tree_and_no_free_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            _,r=generate_anchored_assets(folder)
            root=ET.parse(Path(folder)/"bundle.xml").getroot()
        terminal=root.find("worldbody/body")
        self.assertEqual(terminal.get("name"),"fixed_terminal")
        self.assertIsNone(terminal.find("joint"))
        self.assertFalse(root.findall(".//freejoint"))
        self.assertIsNotNone(terminal.find(".//body[@name='trunk_00']/joint"))
        self.assertEqual(len(terminal.findall(".//body[@name='fiber_00_00']")),1)
        self.assertTrue(all(n.startswith("trunk_") for n in r["graspable_links"]))
        self.assertGreater(r["coarse_min_initial_surface_clearance_m"],.005)
        self.assertGreater(r["lead_length_m"],.5)

    def setUp(self):
        self.layout=FiberLayout()
        self.anchor=np.array([-.4,0.,0.])
        self.initial=np.array([self.anchor,[-.25,0.,0.],[-.17,0.,0.],[-.09,0.,0.]])
        self.v=AnchoredThreadingVerifier(self.layout,np.zeros(3),self.anchor,self.anchor,[1.,0,0,0])
        self.update(self.initial)

    def update(self,coarse,terminal=None,fiber_offset=0.,forbidden_contact=None):
        roots=np.asarray(self.layout.fibers())[:,0]-[self.layout.trunk_length_m,0.,0.]+coarse[-1]
        fibers=roots[:,None,:]+np.linspace(0,.08,11)[None,:,None]*np.array([1.,0,0])
        fibers[:,:,1]+=fiber_offset
        return self.v.update(coarse=np.asarray(coarse),fibers=fibers,
            terminal_pos=self.anchor if terminal is None else terminal,terminal_quat=np.array([1.,0,0,0]),
            ring_pos=np.zeros(3),ring_quat=np.array([1.,0,0,0]),forbidden_contact=forbidden_contact)

    def test_fine_contact_fails_even_after_separation_and_valid_threading(self):
        event=dict(reason="gripper_fine_strand_contact",fine_link="fiber_00_04",
                   gripper_link="left_finger",substep=3,time_s=.0015,position_m=[0.,0.,0.])
        first=self.update(self.initial,forbidden_contact=event)
        self.assertTrue(first["failed"])
        self.assertTrue(first["terminated"])
        final=self.update(np.array([self.anchor,[-.25,0,0],[-.05,0,0],[.05,0,0]]))
        self.assertFalse(final["success"])
        self.assertTrue(final["failed"])
        self.assertFalse(final["checks"]["no_gripper_fine_contact"])
        self.assertEqual(final["first_forbidden_contact"],event)

    def test_head_first_attached_cable_can_succeed(self):
        result=self.update(np.array([self.anchor,[-.25,0,0],[-.05,0,0],[.05,0,0]]))
        self.assertTrue(result["success"])

    def test_tip_order_is_not_required_but_final_full_passage_is(self):
        coarse=np.array([self.anchor,[-.25,0,0],[-.05,0,0],[.005,0,0]])
        roots=np.asarray(self.layout.fibers())[:,0]-[self.layout.trunk_length_m,0.,0.]+coarse[-1]
        fibers=roots[:,None,:]+np.linspace(0,.08,11)[None,:,None]*np.array([1.,0,0])
        fibers[0,-1,0]=-.01  # One tip still trails when the distal jacket enters.
        first=self.v.update(coarse=coarse,fibers=fibers,terminal_pos=self.anchor,
            terminal_quat=np.array([1.,0,0,0]),ring_pos=np.zeros(3),ring_quat=np.array([1.,0,0,0]))
        self.assertFalse(first["failed"])
        self.assertFalse(first["success"])
        self.assertTrue(first["checks"]["head_first_entry"])
        self.assertFalse(first["checks"]["all_fine_strands_beyond"])
        final=self.update(np.array([self.anchor,[-.25,0,0],[-.05,0,0],[.05,0,0]]))
        self.assertTrue(final["success"])

    def test_mid_cable_loop_first_is_permanently_rejected(self):
        result=self.update(np.array([self.anchor,[.03,0,0],[-.05,0,0],[-.09,0,0]]))
        self.assertFalse(result["success"])
        self.assertIn("rear_or_loop_first_or_bypass_entry",result["invalid_reasons"])
        result=self.update(np.array([self.anchor,[-.25,0,0],[-.05,0,0],[.05,0,0]]))
        self.assertFalse(result["success"])

    def test_going_around_ring_cannot_count_as_threading(self):
        result=self.update(np.array([self.anchor,[-.25,.08,0],[-.05,.08,0],[.05,.08,0]]))
        self.assertFalse(result["success"])
        self.assertIn("coarse_cable_bypassed_aperture",result["invalid_reasons"])

    def test_moving_fixed_terminal_invalidates_otherwise_passing_pose(self):
        result=self.update(np.array([self.anchor,[-.25,0,0],[-.05,0,0],[.05,0,0]]),terminal=self.anchor+[.01,0,0])
        self.assertFalse(result["success"])
        self.assertIn("fixed_terminal_or_attachment_moved",result["invalid_reasons"])

    def test_fine_tips_only_do_not_complete_attached_task(self):
        result=self.update(np.array([self.anchor,[-.25,0,0],[-.08,0,0],[-.02,0,0]]))
        self.assertFalse(result["success"])
        self.assertFalse(result["checks"]["all_fine_strands_beyond"])


if __name__=="__main__":unittest.main()
