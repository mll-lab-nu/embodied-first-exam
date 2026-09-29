"""FEM agent boundaries, contact-selected assistance and released goal tests."""
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import numpy as np

from topogym.agent_bridge.fem_robot_adapter import RopeGraspBank, FEMRobotAdapter
from topogym.tasks.knot_untying.agent_adapter import configuration, KnotAdapter, planar_clear
from topogym.tasks.knot_untying.agent_spec import describe_task
from topogym.tasks.knot_untying.geometry import KnotLayout
from topogym.world import genesis_ipc_vertex_constraints as ipc


class KnotAgentChecks(unittest.TestCase):
    def test_public_contract_has_four_views_without_private_layout(self):
        cfg=configuration(); before=describe_task(cfg)
        cfg.task.geometry.cut_angle_rad=.4
        cfg.task.origin_xy_m=[.1,.2]
        self.assertEqual(before,describe_task(cfg))
        self.assertEqual(len(before['cameras']),4)
        self.assertEqual(cfg.robot_control.home.left[-1],.037)
        for secret in ('cut_angle_rad','centerline','ring_indices','overhand_trefoil','remote_adaptive'):
            self.assertNotIn(secret,json.dumps(before))
        with self.assertRaisesRegex(ValueError,'CUDA'):
            configuration(backend='cpu')
        self.assertIs(KnotAdapter.step,FEMRobotAdapter.step)
        tree=ast.parse(Path('topogym/agent_bridge/fem_robot_adapter.py').read_text())
        self.assertFalse(any(isinstance(n,ast.ImportFrom) and n.module and 'topogym.tasks' in n.module for n in ast.walk(tree)))

    def test_projection_rejects_initial_knot_overlap_and_vertical_degeneracy(self):
        self.assertFalse(planar_clear(KnotLayout().centerline(),.004))
        line=np.c_[np.linspace(0,.5,80),np.zeros((80,2))]
        self.assertTrue(planar_clear(line,.004))
        self.assertFalse(planar_clear(np.array([[0.,0,0],[.2,0,0],[.1,0,.01],[.3,0,.01]]),.004))
        self.assertFalse(planar_clear(np.array([[0.,0,0],[0.,0,.01],[.2,0,.01]]),.004))

    def test_inactive_overlapping_capacity_cannot_erase_an_active_band(self):
        flags=np.zeros(4,dtype=int); targets=np.zeros((4,3))
        geom=NS(vertices=lambda:NS(find=lambda key:NS(data=flags if key=='flag' else targets)))
        info=NS(geo_slots=lambda:[NS(geometry=lambda:geom)])
        spec=ipc._EntitySpec(follow_verts=[np.array([0,1,2]),np.array([1,2,3])],
            engaged=[True,False],targets=[np.ones((3,3)),None])
        fake=NS(view=lambda x:x.data,builtin=NS(is_constrained='flag',aim_position='aim'))
        with patch.dict(ipc._SPECS,{'test':spec}),patch.dict(sys.modules,{'uipc':fake}):
            ipc._animate_fem_follow(lambda:True,'test',0,info)
            np.testing.assert_array_equal(flags,[1,1,1,0])
            spec.engaged=[False,True];spec.targets[1]=np.full((3,3),2.)
            ipc._animate_fem_follow(lambda:True,'test',0,info)
            np.testing.assert_array_equal(flags,[0,1,1,1])
            spec.engaged=[False,False]
            ipc._animate_fem_follow(lambda:True,'test',0,info)
            self.assertFalse(flags.any())

    def bank(self,right_gap):
        class Checker:
            initial_intersections=False
            def __init__(self,points,*args,**kwargs):self.right=points[-1,0]>0
            def minimum_distance(self,*args):return right_gap if self.right else .0001
            def close(self):pass
        bank=RopeGraspBank(Checker)
        bank.bands=[NS(indices=np.array([0,1,2]),_handle=Mock(),active=False,release=Mock()) for _ in range(2)]
        positions=np.array([[0.,0,0],[.001,0,0],[0,.001,0]])
        parts=[dict(name=f'{s}/{f}_finger_link',previous=np.array([[float(f=='right'),0.,0.]]),faces=np.array([[0,0,0]]))
               for s in ('left','right') for f in ('left','right')]
        monitor=NS(last_positions=positions,faces=np.array([[0,1,2]]),ccd=NS(parts=parts))
        arm=NS(grasp_center_pos=lambda:np.zeros(3),hand_pos=lambda:np.zeros(3),hand_quat=lambda:np.array([1.,0,0,0]),
               gripper_qpos=lambda:np.array([.015,.015]),set_gripper=Mock())
        return bank,NS(arms={'left':arm,'right':arm}),monitor

    def test_both_fingers_required_and_overlapping_bimanual_grasp_rejected(self):
        bank,ctrl,monitor=self.bank(None)
        self.assertFalse(bank.try_attach('left',ctrl,monitor,.0008))
        self.assertFalse(bank.owners)
        bank,ctrl,monitor=self.bank(.0002)
        self.assertTrue(bank.try_attach('left',ctrl,monitor,.0008))
        self.assertFalse(bank.try_attach('right',ctrl,monitor,.0008))
        bank.drive(ctrl)
        bank.bands[0]._handle.update_targets.assert_called_once()
        bank.release('left')
        self.assertFalse(bank.owners)
        self.assertTrue(bank.try_attach('right',ctrl,monitor,.0008))
        bank.close()

    def adapter(self):
        a=KnotAdapter.__new__(KnotAdapter)
        a.cfg=configuration(); a.rest_origin=None
        floor=float(a.cfg.env.frames.table_surface.origin[2])
        p=np.c_[np.linspace(-.3,.3,80),np.zeros(80),np.full(80,floor+.004)]
        a.monitor=NS(agent_failure=None,min_J=1.,maxima={'max_total_length_relative_change':0.,'max_local_axial_strain':0.},
            last_positions=p,last_centers=p.copy(),last_velocity=np.zeros_like(p),floor=floor,ccd=NS(parts=[]))
        a.scene=NS(sim=NS(rigid_solver=NS(collider=NS(get_contacts=lambda:dict(penetration=np.array([]))))))
        a.ctrl=NS(arms={})
        a.bank=NS(owners={})
        a.task=NS(layout=NS(rope_radius_m=.004))
        return a

    def test_repeated_closure_preserves_captured_gap_until_opening(self):
        a=FEMRobotAdapter.__new__(FEMRobotAdapter)
        arm=NS(current_gripper_qpos=.015)
        arm.set_gripper=Mock(side_effect=lambda q:setattr(arm,'current_gripper_qpos',q))
        a.ctrl=NS(arms={'left':arm})
        a.bank=NS(owners={0:'left'},release=Mock())
        a.bank.release.side_effect=lambda side:a.bank.owners.clear()
        a.armed={'left':True}
        for _ in range(3):
            a._apply({'left':{'gripper':0.}})
        arm.set_gripper.assert_not_called()
        self.assertEqual(arm.current_gripper_qpos,.015)
        a._apply({'left':{'gripper':.037}})
        a.bank.release.assert_called_once_with('left')
        self.assertFalse(a.armed['left'])
        self.assertEqual(arm.current_gripper_qpos,.037)
        a._apply({'left':{'gripper':0.}})
        self.assertTrue(a.armed['left'])
        self.assertEqual(arm.current_gripper_qpos,0.)

    def test_goal_rejects_motion_height_drift_and_nearby_fingers(self):
        a=self.adapter()
        self.assertEqual(a._failure_and_goal(),(None,True))
        a.monitor.last_positions[:,0]+=.003
        self.assertEqual(a._failure_and_goal(),(None,False))
        a.monitor.last_velocity[:,0]=.01
        self.assertEqual(a._failure_and_goal(),(None,False))
        a.monitor.last_velocity[:]=0
        a.monitor.last_positions[:,2]+=.02
        self.assertEqual(a._failure_and_goal(),(None,False))
        a.monitor.last_positions[:,2]-=.02
        a.monitor.ccd.parts=[dict(name='left_finger_link',previous=a.monitor.last_positions.copy())]
        self.assertEqual(a._failure_and_goal(),(None,False))

    def test_failures_are_independent_of_uncrossed_shape(self):
        a=self.adapter();a.monitor.agent_failure='swept surface intersection'
        self.assertIn('intersection',a._failure_and_goal()[0])
        a.monitor.agent_failure=None;a.monitor.min_J=.1
        self.assertIn('volume',a._failure_and_goal()[0])
        a.monitor.min_J=1.;a.monitor.maxima['max_total_length_relative_change']=.06
        self.assertIn('length',a._failure_and_goal()[0])
        a.monitor.maxima['max_total_length_relative_change']=0.;a.monitor.maxima['max_local_axial_strain']=.21
        self.assertIn('strain',a._failure_and_goal()[0])


if __name__=='__main__':
    unittest.main()
