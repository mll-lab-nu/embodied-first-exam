#!/usr/bin/env python3
"""Replay admission and endpoint contracts; synthetic states, no physics proof."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from topogym.simulator import SimulatorConfig
from topogym.planning.horseshoe_ring.prefix_replay import (
    ReplayPrefixPolicy,replay_config_hash,validate_replay)


class PrefixReplayTests(unittest.TestCase):
    def setUp(self):
        self.config=SimulatorConfig(task_id='horseshoe_ring',robot_id='aloha',
            compute_backend='cpu',enable_rgb=False,control_mode='JOINT_ABS',control_decimation=1)
        self.data=dict(schema_version=1,seed=0,source_config_sha256=replay_config_hash(self.config),
            controls=[dict(physics_step=1,phase='hold',action={}),
                      dict(physics_step=2,phase='grasp',action={'left':{'gripper_position_m':.002}})],
            expected_end=dict(state={'physics_step':2},
                bodies={n:dict(position_m=[0.,0.,1.],quaternion_wxyz=[1.,0.,0.,0.])
                        for n in ('target_ring','horseshoe_right')},
                joint_position_rad={s:[0.]*6 for s in ('left','right')}))

    def test_only_output_directory_may_change(self):
        validate_replay(self.data,replace(self.config,work_dir='/tmp/replay-output'),0)
        with self.assertRaisesRegex(ValueError,'configuration'):
            validate_replay(self.data,replace(self.config,physics_dt_s=.01),0)

    def test_gaps_and_non_robot_commands_are_rejected(self):
        for change in ('gap','state_write','nonfinite','end'):
            data=deepcopy(self.data)
            if change=='gap':data['controls'][1]['physics_step']=3
            if change=='state_write':data['controls'][1]['action']={'set_body_pose':{}}
            if change=='nonfinite':data['controls'][1]['action']={'left':{'joint_position_rad':[float('nan')]*6}}
            if change=='end':data['expected_end']['state']['physics_step']=1
            with self.subTest(change=change),self.assertRaises(ValueError):validate_replay(data,self.config,0)

    def observation(self,tick,shift=0.):
        bodies=deepcopy(self.data['expected_end']['bodies']);bodies['target_ring']['position_m'][0]+=shift
        return dict(state=dict(physics_step=tick,sim_time_s=tick*.025),
            robot={s:dict(joint_position_rad=[0.]*6,tcp_position_world_m=[0.,0.,1.],
                          tcp_orientation_wxyz=[1.,0.,0.,0.]) for s in ('left','right')},
            privileged=dict(world=dict(bodies=bodies,grasp=dict(hands={
                s:dict(binding=dict(target=[name,name])) for s,name in
                (('left','target_ring'),('right','horseshoe_right'))}))))

    def test_controls_are_emitted_and_the_actual_endpoint_is_required(self):
        for shift in (0.,.001):
            with self.subTest(shift=shift),tempfile.TemporaryDirectory() as folder:
                policy=ReplayPrefixPolicy({'left':{},'right':{}},replay=deepcopy(self.data),
                    planner=SimpleNamespace(directory=Path(folder)))
                policy.initialize(dict(action_spec=dict(robot_id='aloha',mode='EE_ABS'),
                    mode='unlimited',timing_spec=dict(control_dt_s=.025)))
                for tick,row in enumerate(self.data['controls']):
                    observation=self.observation(tick);before=deepcopy(observation)
                    self.assertEqual(policy.act(observation),row['action'])
                    self.assertEqual(observation,before)
                if shift:
                    with self.assertRaisesRegex(RuntimeError,'did not reproduce'):
                        policy.act(self.observation(2,shift))
                else:
                    self.assertIsNone(policy.act(self.observation(2)))
                    self.assertTrue(policy.replay_result['passed'])


if __name__=='__main__':unittest.main()
