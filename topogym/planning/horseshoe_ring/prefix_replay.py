"""Replay recorded ordinary controls from home, then calibrate measured grasps.

This is an action cache, not a physics checkpoint. Every control advances the
new episode normally; the workflow checks every tick and the final state must
reproduce the recorded grasp before measured-state planning continues.
"""
import hashlib
import json

import numpy as np

from topogym.planning.rigid_reference.feedback import body_pose, relative_pose
from topogym.utils.io import to_jsonable, write_json_atomic
from .policy import HorseshoePolicy


def replay_config_hash(config):
    values=dict(to_jsonable(config))
    values.pop('work_dir',None)
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


def validate_replay(data, config, seed):
    if data.get('schema_version')!=1 or data.get('seed')!=seed:
        raise ValueError('Replay schema or seed mismatch')
    if data.get('source_config_sha256')!=replay_config_hash(config):
        raise ValueError('Replay requires the same simulator configuration except work_dir')
    if config.control_mode!='JOINT_ABS' or config.control_decimation!=1:
        raise ValueError('Prefix replay requires one ordinary joint action per World tick')
    records=data.get('controls',())
    if not isinstance(records,list) or not records or len(records)>config.max_physics_steps:
        raise ValueError('Invalid prefix control count')
    for tick,row in enumerate(records,1):
        if row.get('physics_step')!=tick or not isinstance(row.get('phase'),str):
            raise ValueError('Prefix controls must cover consecutive ticks from birth')
        action=row.get('action')
        if not isinstance(action,dict) or set(action)-{'left','right'}:
            raise ValueError('Replay contains a non-robot action')
        for values in action.values():
            if not isinstance(values,dict) or set(values)-{'joint_position_rad','gripper_position_m'}:
                raise ValueError('Replay accepts only ordinary joint and gripper targets')
            if 'joint_position_rad' in values:
                q=np.asarray(values['joint_position_rad'],dtype=float)
                if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('Invalid replay joints')
            if 'gripper_position_m' in values and not np.isfinite(float(values['gripper_position_m'])):
                raise ValueError('Invalid replay gripper target')
    if data['expected_end']['state']['physics_step']!=len(records):
        raise ValueError('Replay endpoint does not match its control count')


class ReplayPrefixPolicy(HorseshoePolicy):
    def __init__(self,*args,replay,**kwargs):
        super().__init__(*args,**kwargs)
        self.replay=replay

    def actions(self):
        if self.obs['state']['physics_step']!=0:raise ValueError('Replay must start at episode birth')
        for row in self.replay['controls']:
            self.phase='replay/'+row['phase']
            for side,values in row['action'].items():
                if 'gripper_position_m' in values:self.grip[side]=float(values['gripper_position_m'])
            yield row['action']
        self.held_entities={'left':'target_ring','right':'horseshoe_right'}
        expected=self.replay['expected_end'];world=self.obs['privileged']['world']
        errors={}
        for name,row in expected['bodies'].items():
            p,r=body_pose(world['bodies'][name]);ep,er=body_pose(row)
            errors[name]=dict(position_m=float(np.linalg.norm(p-ep)),rotation_rad=float((r*er.inv()).magnitude()))
        joint_errors={s:float(np.max(np.abs(np.asarray(self.obs['robot'][s]['joint_position_rad'])-q)))
                      for s,q in expected['joint_position_rad'].items()}
        bindings={s:bool(world['grasp']['hands'][s]['binding'] and
                         world['grasp']['hands'][s]['binding']['target'][0]==name)
                  for s,name in self.held_entities.items()}
        passed=(self.obs['state']['physics_step']==len(self.replay['controls']) and all(bindings.values())
                and all(e['position_m']<=1e-6 and e['rotation_rad']<=1e-5 for e in errors.values())
                and all(e<=1e-6 for e in joint_errors.values()))
        self.replay_result=dict(passed=passed,state=self.obs['state'],body_errors=errors,
            maximum_joint_errors_rad=joint_errors,expected_bindings=bindings,
            controls_replayed=len(self.replay['controls']),
            scope='new continuous physics from home through ordinary controls; no state restoration')
        write_json_atomic(self.planner.directory/'prefix_replay_result.json',self.replay_result)
        if not passed:raise RuntimeError('Replayed prefix did not reproduce the recorded grasp')
        bodies,tcp=self.bodies(),self.tcp()
        self.offsets={s:relative_pose(bodies[s],tcp[s]) for s in self.grasps}
        self.support_hold=None
        self.phase='replayed_ring_grasp_complete'
