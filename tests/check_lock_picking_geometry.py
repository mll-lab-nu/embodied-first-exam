"""Geometry and variant-dependent decisions for the physical staged-lock task."""
import unittest
from dataclasses import replace
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from omegaconf import OmegaConf
import numpy as np
import trimesh
from topogym.tasks.lock_picking._staged_lock_geometry import LockGeometry,variant_geometry,VARIANTS,disc_assets,write_disc,write_key,key_rest_layout,write_key_cradle
from topogym.tasks.lock_picking.planner import next_entry_angle,insertion_window
from topogym.tasks.lock_picking.evaluator import StagedLockEvaluator


class StagedLockTaskTests(unittest.TestCase):
    def test_variants_reproducible_and_distinct(self):
        g=LockGeometry()
        for variant in VARIANTS:
            self.assertEqual(variant_geometry(g,variant,7),variant_geometry(g,variant,7))
        self.assertNotEqual(variant_geometry(g,'reindexed',7),variant_geometry(g,'reindexed',8))
        self.assertNotEqual(variant_geometry(g,'asymmetric',7).slots,g.slots)

    def test_oracle_adapts_to_each_variant(self):
        for variant in VARIANTS:
            for seed in range(20):
                g=variant_geometry(LockGeometry(),variant,seed)
                state=dict(depth=0.,key_deg=g.initial_key_deg,disc_deg=list(g.initial_disc_deg))
                for level in range(4):
                    target=next_entry_angle(g,state,level)
                    delta=target-state['key_deg']
                    for i in range(level): state['disc_deg'][i]+=delta
                    state['key_deg']=target
                    # Ideal zero-backlash coupling is only an offline oracle
                    # contract. Separate GPU tests exercise actual contact.
                    self.assertFalse(g.clearance(level+1,target,state['disc_deg']))
                    state['depth']=level+1

    def test_changed_hidden_disc_changes_legal_action(self):
        g=LockGeometry()
        self.assertFalse(g.clearance(3,0,[0,-30,0]))
        self.assertTrue(g.clearance(3,0,[0,-30,30]))

    def test_endpoint_direction_is_required(self):
        g=LockGeometry()
        self.assertFalse(g.clearance(4,0,[0,-30,0]))
        self.assertIn('tab0/endpoint',g.clearance(4,30,[30,0,30]))

    def test_withdrawal_changes_engagement_without_resetting_discs(self):
        g=LockGeometry()
        angles=[0,-30,30]
        self.assertTrue(g.clearance(3,0,angles))
        self.assertFalse(g.clearance(1,0,angles))

    def test_collision_pieces_do_not_fill_slots(self):
        g=LockGeometry()
        with tempfile.TemporaryDirectory() as temp:
            _,paths=disc_assets(g,g.slots[0],Path(temp))
            for path in paths:
                mesh=trimesh.load(path,process=False)
                self.assertTrue(mesh.is_convex)
                # Slot centre at 0 degrees must remain open up to tab radius.
                point=np.array([0,0,g.tab_radius])
                # Convex half-space test avoids an optional rtree dependency.
                inside=np.all(np.sum((point-mesh.triangles_center)*mesh.face_normals,axis=1)<=1e-8)
                self.assertFalse(inside)

    def test_invalid_geometry_rejected(self):
        for g in (replace(LockGeometry(),slot_radius=.1),replace(LockGeometry(),pitch=.01),
                  replace(LockGeometry(),slots=((0,5),(0,),(0,)))):
            with self.assertRaises(ValueError): g.validate()

    def test_key_embedded_pbr_preserves_physics(self):
        # Check the serialized renderer asset and the unchanged URDF physics.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);g=LockGeometry()
            finish=dict(color=[.32,.35,.38],metallic=1.,roughness=.28)
            old=write_key(g,root/'old',.1)
            new=write_key(g,root/'new',.1,visual_finish=finish)
            trees=[ET.parse(path).getroot() for path in (old,new)]
            for tree in trees:
                for link in tree.findall('link'):
                    for visual in link.findall('visual'): link.remove(visual)
                for mesh in tree.findall('.//mesh'):
                    mesh.set('filename',Path(mesh.get('filename')).name)
            self.assertEqual(ET.tostring(trees[0]),ET.tostring(trees[1]))
            for path in old.parent.glob('part*.obj'):
                self.assertEqual(path.read_bytes(),(new.parent/path.name).read_bytes())
            a=trimesh.load(old.parent/'visual.obj',process=False)
            b=trimesh.load(new.parent/'visual.glb',force='mesh',process=False)
            np.testing.assert_allclose(a.vertices,b.vertices,atol=1e-8)
            np.testing.assert_array_equal(a.faces,b.faces)
            np.testing.assert_array_equal(b.visual.material.baseColorFactor,[82,89,97,255])
            self.assertEqual(b.visual.material.metallicFactor,1.)
            self.assertAlmostEqual(b.visual.material.roughnessFactor,.28)
            self.assertIsNone(ET.parse(new).find('.//visual/material'))

    def test_endpoint_cannot_override_execution_violations(self):
        state=dict(depth=4.,key_deg=0.,disc_deg=[0.,-30.,0.],
                   linear_speed=0.,angular_speed=0.,axis_offset=0.,axis_tilt_deg=0.)
        task=SimpleNamespace(state=lambda:state,layout=LockGeometry(),
            force_limit_triggered=False,geometry_error_steps=0,max_contact_penetration=0.,
            cfg=SimpleNamespace(physics=SimpleNamespace(max_penetration=.002),
                success=SimpleNamespace(depth_tolerance=.025,max_linear_speed=.01,max_angular_speed=.1,
                                        max_axis_offset=.01,max_axis_tilt_deg=3.)))
        evaluator=StagedLockEvaluator()
        self.assertTrue(evaluator.evaluate(task)['success'])
        self.assertFalse(evaluator.evaluate(task,grasp_released=False)['success'])
        task.force_limit_triggered=True
        self.assertFalse(evaluator.evaluate(task)['success'])
        task.force_limit_triggered=False
        task.geometry_error_steps=1
        self.assertFalse(evaluator.evaluate(task)['success'])
        task.geometry_error_steps=0
        task.max_contact_penetration=.003
        self.assertFalse(evaluator.evaluate(task)['success'])
        task.max_contact_penetration=0.
        state['axis_offset']=.02
        self.assertFalse(evaluator.evaluate(task)['success'])
        state['axis_offset']=0.;state['axis_tilt_deg']=10.
        self.assertFalse(evaluator.evaluate(task)['success'])

    def test_free_key_has_mass_inside_physical_support_span(self):
        with tempfile.TemporaryDirectory() as temp:
            g=LockGeometry();rest=key_rest_layout(g)
            path=write_key(g,Path(temp)/'key',.12)
            tree=ET.parse(path)
            self.assertEqual(len(tree.findall('.//link')),1)
            self.assertEqual(tree.findall('.//joint'),[])
            mass=float(tree.find('.//inertial/mass').get('value'))
            com=np.fromstring(tree.find('.//inertial/origin').get('xyz'),sep=' ')
            self.assertAlmostEqual(mass,.12)
            self.assertLess(rest['cradle_x'][0],g.tip_x(0)+com[0])
            self.assertGreater(rest['cradle_x'][1],g.tip_x(0)+com[0])
            inertia=tree.find('.//inertia')
            matrix=np.array([[float(inertia.get('i'+a+b if a<=b else 'i'+b+a)) for b in 'xyz'] for a in 'xyz'])
            self.assertTrue(np.all(np.linalg.eigvalsh(matrix)>0))
            self.assertLess(rest['resting_axis_z'],g.axis_z-.05)
            self.assertGreater(rest['tray_start'],g.grip_pos(0)[0]+.035)
            for p in write_key_cradle(rest,Path(temp)/'rest'):
                mesh=trimesh.load(p,process=True)
                self.assertTrue(mesh.is_watertight and mesh.is_convex)
                self.assertAlmostEqual(mesh.bounds[0,2],0.)

    def test_visible_limits_keep_one_textured_visual_per_link(self):
        # Nyx addresses URDF visuals by link name. Separate visuals on one
        # link alias each other; retain one visual plus many convex colliders.
        with tempfile.TemporaryDirectory() as temp:
            g=LockGeometry()
            stop=OmegaConf.create(dict(bounds_deg=[-35,35],ear_phase_deg=-35))
            path=write_disc(g,g.slots[0],Path(temp)/'disc',.12,.03,(.76,.53,.23),stop=stop)
            tree=ET.parse(path)
            joint=tree.find('.//joint')
            self.assertEqual(joint.get('type'),'revolute')
            self.assertAlmostEqual(float(joint.find('limit').get('lower')),np.radians(-35))
            self.assertAlmostEqual(float(joint.find('limit').get('upper')),np.radians(35))
            frame=ET.parse(path.parent/'limits'/'stop_frame.urdf')
            for link in (tree.find("link[@name='disc']"),frame.find('link')):
                self.assertEqual(len(link.findall('visual')),1)
                self.assertGreater(len(link.findall('collision')),4)
                mesh=trimesh.load(link.find('visual/geometry/mesh').get('filename'),force='mesh',process=False)
                self.assertIsNotNone(mesh.visual.material.baseColorTexture)
                self.assertGreater(np.max(np.linalg.norm(mesh.vertices[:,1:],axis=1)),g.disc_radius)

    def test_single_ring_has_one_open_slot_and_solid_end_caps(self):
        from topogym.tasks.lock_picking._staged_lock_ring import slot_profile
        # The ring is fully closed except for its centre and ONE connected slot.
        angles=np.arange(0,360,.25)
        lower,upper=slot_profile(angles,-35,35,-35)
        opened=upper-lower>1e-8
        self.assertEqual(np.count_nonzero(opened!=np.roll(opened,1)),2)
        with tempfile.TemporaryDirectory() as temp:
            g=LockGeometry()
            stop=OmegaConf.create(dict(style='single_ring',bounds_deg=[-35,35],ear_phase_deg=-35))
            path=write_disc(g,g.slots[0],Path(temp)/'disc',.12,.03,(.76,.53,.23),stop=stop,mount_z=-.157)
            frame=ET.parse(path.parent/'limits'/'stop_frame.urdf')
            self.assertEqual(len(frame.findall('.//visual')),1)
            planes=[]
            for item in frame.findall('.//collision/geometry/mesh'):
                mesh=trimesh.load(item.get('filename'),process=False)
                planes.append((mesh.triangles_center,mesh.face_normals))
            def occupied(point):
                return any(np.all(np.sum((point-centres)*normals,axis=1)<1e-8)
                           for centres,normals in planes)
            # A point in the bore, several points down the slot, and solid
            # material just past either cap use the actual exported colliders.
            self.assertFalse(occupied(np.array([0,0,0])))
            for angle in (-65,-35,-5):
                a=np.radians(angle)
                self.assertFalse(occupied(np.array([0,.097*np.sin(a),.097*np.cos(a)])))
            for angle in (-80,10,100):
                a=np.radians(angle)
                self.assertTrue(occupied(np.array([0,.097*np.sin(a),.097*np.cos(a)])))


if __name__=='__main__': unittest.main()
