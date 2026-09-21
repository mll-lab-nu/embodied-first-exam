"""Interactive ALOHA manipulation with physical joint control and audited grasps.

Commands pause simulated time between stages, retaining one MjData episode.
Weld/ball assistance is explicit; task-body poses are never prescribed during
execution. A candidate becomes a full demo only after its recorded checks pass.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation, Slerp

from topogym.tasks.cast_coil.robot_plan import Kinematics, PAD_CENTER
from .fixture import cord_disk_crossings
from .physics import contact_summary, wxyz
from .robot import execute as initial_pregrasp

# Guard against discontinuous IK branches on the 50 ms planning grid. This is
# a planning heuristic, not a claim about the hardware's joint-speed limits.
MAX_IK_SAMPLE_JUMP_RAD = .5


def static_collisions(model, initial_qpos, robot_qs):
    """Reject sampled robot/self/table/post collisions before any actuation.

    Moving task bodies and the cord still require the subsequent physical audit.
    """
    preview=mujoco.MjData(model);preview.qpos[:]=initial_qpos
    failures=[]
    for i,q in enumerate(robot_qs):
        preview.qpos[:16]=q;mujoco.mj_fwdPosition(model,preview)
        for c in preview.contact:
            if c.dist>=-.0001:continue
            names=[model.body(model.geom_bodyid[g]).name if g>=0 else 'cord' for g in c.geom]
            if not any('/' in n for n in names):continue
            if all(n.endswith('/base_link') or n=='world' for n in names):continue
            if all('/' in n for n in names) or any(n in ('world','post','base') for n in names):
                failures.append(dict(sample=i,bodies=names,depth_m=float(-c.dist)))
    return failures


class Episode:
    def __init__(self, source, output):
        self.output=Path(output)
        initial_pregrasp(source,self.output,plan_only=True)
        initial_check=json.loads((self.output/'initial_grasp_check.json').read_text())
        if not initial_check['passed']:
            raise RuntimeError('Initial pregrasp has forbidden contacts')
        root=ET.parse(self.output/'model/scene.xml').getroot()
        equality=root.find('equality')
        self.bindings={('left','target_ring'):'left_ring_grasp',('right','bead_right'):'right_bead_grasp'}
        for side in ('left','right'):
            for body in ('target_ring','disc_left','disc_right'):
                if (side,body) in self.bindings:continue
                name=f'{side}_{body}_assisted_grasp'
                ET.SubElement(equality,'weld',name=name,body1=f'{side}/gripper_link',body2=body,
                              active='false',torquescale='.1',solref='.002 1',solimp='.999 .9999 .001 .5 2')
                self.bindings[side,body]=name
        xml=ET.tostring(root,encoding='unicode')
        (self.output/'model/scene.xml').write_text(xml)
        self.m=mujoco.MjModel.from_xml_string(xml);self.d=mujoco.MjData(self.m)
        initial=np.load(self.output/'initial_state.npz')
        self.d.qpos[:]=initial['qpos'];self.d.qvel[:]=initial['qvel']
        mujoco.mj_forward(self.m,self.d)
        mujoco.mj_saveModel(self.m,str(self.output/'model/scene.mjb'))
        self.actuated=self.m.jnt_qposadr[self.m.actuator_trnid[:,0]]
        self.d.ctrl[:]=self.d.qpos[self.actuated]
        cfg=OmegaConf.load(Path(__file__).resolve().parents[3]/'configs/robot_control_configs/aloha_position_ik.yaml')
        self.k=Kinematics(cfg);self.k.q[:]=self.d.qpos[:16]
        self.targets={s:self.tcp(s) for s in ('left','right')}
        self.fingers={'left':.018,'right':.0277}
        self.held={'left':'target_ring','right':'bead_right'}
        self.relative={s:self.relative_grasp(s,b) for s,b in self.held.items()}
        spec=json.loads((self.output/'model/model_spec.json').read_text())
        self.lengths=np.asarray(spec['cord_segment_lengths'])
        self.cord_sites=[i for i in range(self.m.nsite) if self.m.site(i).name.startswith('cord_node_') or self.m.site(i).name=='cord_tip']
        self.rigids=[self.m.body(n).id for n in ('target_ring','disc_left','disc_right','bead_left','bead_right')]
        self.trace={k:[] for k in ('qpos','qvel','ctrl','eq_active','eq_data','eq_obj2id','time_s','phase','cord_nodes')}
        self.commands=[];self.depths={};self.violations=[];self.max_stretch=0.;self.max_attachment=0.
        self.max_force=np.zeros(16);self.max_raw_force=np.zeros(self.m.nu);self.tail=deque()
        self.max_grasp_error=0.
        self.max_joint_tracking=np.zeros(self.m.nu)
        self.steps=0;self.wall=time.monotonic()

    def body_pose(self, name):
        b=self.m.body(name).id
        return self.d.xpos[b].copy(),Rotation.from_matrix(self.d.xmat[b].reshape(3,3))

    def tcp(self, side):
        p,r=self.body_pose(f'{side}/gripper_link')
        return p+r.apply(PAD_CENTER),r

    def relative_grasp(self, side, body):
        p,r=self.body_pose(body);t,g=self.tcp(side)
        return r.inv().apply(t-p),r.inv()*g

    def contacts(self, allowed):
        contacts=[]
        for c in self.d.contact:
            if c.dist>=0:continue
            names=[self.m.body(self.m.geom_bodyid[g]).name if g>=0 else 'cord' for g in c.geom]
            if not any('/' in n for n in names):continue
            if all(n.endswith('/base_link') or n=='world' for n in names):continue
            intended=any(body in names and any(n.startswith(side+'/') and 'finger' in n for n in names)
                         for side,body in allowed.items() if body)
            contacts.append(dict(bodies=names,depth_m=float(-c.dist),intended=intended))
        return contacts

    def audit(self, phase, allowed):
        self.max_joint_tracking=np.maximum(self.max_joint_tracking,np.abs(self.d.ctrl-self.d.qpos[self.actuated]))
        for key,value in contact_summary(self.m,self.d).items():self.depths[key]=max(self.depths.get(key,0),value)
        bad=[c for c in self.contacts(allowed) if not c['intended'] and c['depth_m']>.0005]
        if bad and len(self.violations)<100:self.violations.append(dict(time_s=float(self.d.time),phase=phase,contacts=bad))
        points=self.d.site_xpos[self.cord_sites].copy()
        self.max_stretch=max(self.max_stretch,float(np.max(np.abs(np.linalg.norm(np.diff(points,axis=0),axis=1)/self.lengths-1))))
        for side,node in [('left',0),('right',-1)]:
            self.max_attachment=max(self.max_attachment,float(np.linalg.norm(self.d.site_xpos[self.m.site(f'disc_{side}_anchor').id]-points[node])))
        for side,body in self.held.items():
            if body:
                bp,br=self.body_pose(body);tp,_=self.tcp(side)
                expected=bp if body=='bead_right' else bp+br.apply(self.relative[side][0])
                self.max_grasp_error=max(self.max_grasp_error,float(np.linalg.norm(tp-expected)))
        speed=0.;velocity=np.zeros(6)
        for body in self.rigids:
            mujoco.mj_objectVelocity(self.m,self.d,mujoco.mjtObj.mjOBJ_BODY,body,velocity,0)
            speed=max(speed,float(np.linalg.norm(velocity[3:])))
        self.tail.append((float(self.d.time),speed,not any(self.held.values())))
        while self.tail and self.tail[0][0]<self.d.time-2:self.tail.popleft()
        if self.steps%round(.05/self.m.opt.timestep)==0:
            for key in ('qpos','qvel','ctrl','eq_active'):self.trace[key].append(getattr(self.d,key).copy())
            for key in ('eq_data','eq_obj2id'):self.trace[key].append(getattr(self.m,key).copy())
            self.trace['time_s'].append(float(self.d.time));self.trace['phase'].append(phase);self.trace['cord_nodes'].append(points)

    def move(self, command):
        seconds=float(command['seconds']);phase=command['phase']
        if seconds<=0:raise ValueError('Positive stage duration required')
        starts={s:self.tcp(s) for s in ('left','right')}
        goals=dict(self.targets)
        for side,value in command.get('tcp',{}).items():
            goals[side]=(np.asarray(value[0]),Rotation.from_quat(value[1]))
        for side,value in command.get('approach',{}).items():
            p,_=self.body_pose(value['body'])
            goals[side]=(p+np.asarray(value['world_offset']),Rotation.from_quat(value['rotation_xyzw']))
        for side,value in command.get('objects',{}).items():
            body=self.held[side]
            if body is None:raise ValueError(f'{side} is not holding an object')
            p=np.asarray(value[0])
            if body=='bead_right':goals[side]=(p,self.targets[side][1])
            else:
                r=Rotation.from_quat(value[1]);offset,relative=self.relative[side]
                goals[side]=(p+r.apply(offset),r*relative)
        # An empty hand may retreat through a continuous joint path to avoid
        # an IK branch switch near a wrist singularity.
        joint_goals={}
        measured_q=self.d.qpos[:16].copy()
        for side,value in command.get('joint_positions',{}).items():
            if self.held[side] or any(side in command.get(key,{}) for key in ('tcp','approach','objects')):
                raise ValueError('Joint retreat requires a released hand and no Cartesian command for that side')
            q=np.asarray(value,dtype=float)
            if q.shape!=(len(self.k.indices[side]),) or not np.isfinite(q).all():
                raise ValueError('Joint retreat requires six finite arm angles')
            if np.any(q<self.k.limits[:,0]) or np.any(q>self.k.limits[:,1]):
                raise ValueError('Joint retreat exceeds arm joint limits')
            joint_goals[side]=q
            self.k.q[:]=measured_q;self.k.q[self.k.indices[side]]=q
            goals[side]=self.k.pose(side)
        fingers=dict(self.fingers);fingers.update(command.get('fingers',{}))
        measured_fingers={side:float(self.d.qpos[self.m.joint(f'{side}/left_finger').qposadr[0]])
                          for side in starts}
        allowed=dict(self.held);allowed.update(command.get('allowed_contact',{}))
        rotations={s:Slerp([0,1],Rotation.from_matrix([starts[s][1].as_matrix(),goals[s][1].as_matrix()])) for s in starts}
        grid=np.linspace(0,seconds,max(2,round(seconds/.05)+1));qs=[];failures=[]
        self.k.q[:]=self.d.qpos[:16]
        for t in grid:
            u=t/seconds;b=u*u*u*(10-15*u+6*u*u)
            for side in starts:
                if side in joint_goals:
                    indices=self.k.indices[side]
                    self.k.q[indices]=measured_q[indices]*(1-b)+joint_goals[side]*b
                else:
                    p=starts[side][0]*(1-b)+goals[side][0]*b;r=rotations[side]([b])[0]
                    ep,ea=self.k.solve(side,p,r)
                    if ep>1e-5 or ea>1e-4:failures.append(dict(side=side,time=t,position_error=ep,angle_error=ea))
                for finger in ('left_finger','right_finger'):
                    address=self.k.model.joint(f'{side}/{finger}').qposadr[0]
                    self.k.q[address]=measured_fingers[side]*(1-b)+fingers[side]*b
            qs.append(self.k.q.copy())
        qs=np.asarray(qs)
        jumps=[dict(sample=int(i+1),joint=self.m.joint(int(self.m.dof_jntid[j])).name,delta_rad=float(qs[i+1,j]-qs[i,j]))
               for i,j in np.argwhere(np.abs(np.diff(qs,axis=0))>MAX_IK_SAMPLE_JUMP_RAD)]
        collisions=static_collisions(self.m,self.d.qpos,qs) if not failures and not jumps else []
        if failures or collisions or jumps:
            (self.output/'last_rejected_plan.json').write_text(json.dumps(dict(command=command,failures=failures,
                static_collisions=collisions,joint_sample_jumps=jumps),indent=2)+'\n')
            print(json.dumps(dict(rejected_phase=phase,ik_failures=failures[:3],static_collisions=collisions[:3],joint_sample_jumps=jumps[:3])),flush=True)
            return False
        dt=self.m.opt.timestep
        for tick in range(round(seconds/dt)):
            local=tick*dt;i=min(np.searchsorted(grid,local,side='right')-1,len(grid)-2)
            u=(local-grid[i])/(grid[i+1]-grid[i]);q=qs[i]*(1-u)+qs[i+1]*u
            self.d.ctrl[:]=q[self.actuated]
            mujoco.mj_step1(self.m,self.d);self.audit(phase,allowed);mujoco.mj_step2(self.m,self.d)
            self.max_force=np.maximum(self.max_force,np.abs(self.d.qfrc_actuator[:16]))
            self.max_raw_force=np.maximum(self.max_raw_force,np.abs(self.d.actuator_force));self.steps+=1
        mujoco.mj_forward(self.m,self.d)
        self.targets=goals;self.fingers=fingers;self.commands.append(command)
        folder=self.output/'checkpoints';folder.mkdir(exist_ok=True)
        np.savez_compressed(folder/f'{phase}.npz',qpos=self.d.qpos,qvel=self.d.qvel,time_s=self.d.time,
                            eq_active=self.d.eq_active,eq_data=self.m.eq_data,ctrl=self.d.ctrl)
        print(json.dumps(dict(phase=phase,time_s=float(self.d.time),wall_s=time.monotonic()-self.wall,
            depths=self.depths,max_relative_extension=self.max_stretch,forbidden_events=len(self.violations),
            object_positions={n:self.body_pose(n)[0].tolist() for n in ('target_ring','bead_right','disc_left','disc_right')})),flush=True)
        return True

    def grasp(self, side, body):
        if self.held[side]:raise ValueError('Release the current object before a new grasp')
        if (side,body) not in self.bindings:raise ValueError('Unsupported assisted grasp')
        current=self.contacts({side:body})
        touching=[c for c in current if c['intended']]
        if not touching or max(c['depth_m'] for c in touching)>.0005:
            raise ValueError('A grasp requires measured finger contact within the penetration limit')
        e=self.m.equality(self.bindings[side,body]).id
        if body=='bead_right':
            if np.linalg.norm(self.tcp(side)[0]-self.body_pose(body)[0])>.001:raise ValueError('Bead center is outside the ball-grasp tolerance')
        else:
            hp,hr=self.body_pose(f'{side}/gripper_link');bp,br=self.body_pose(body)
            self.m.eq_data[e,3:6]=hr.inv().apply(bp-hp)
            self.m.eq_data[e,6:10]=wxyz(hr.inv()*br)
        self.d.eq_active[e]=True;self.held[side]=body;self.relative[side]=self.relative_grasp(side,body)
        self.commands.append(dict(grasp=side,body=body,time_s=float(self.d.time)))
        print(json.dumps(dict(grasped=body,side=side,contacts=touching)),flush=True)

    def release(self, side):
        body=self.held[side]
        if body:self.d.eq_active[self.m.equality(self.bindings[side,body]).id]=False
        self.held[side]=None
        self.commands.append(dict(release=side,time_s=float(self.d.time)))

    def finish(self):
        ring=self.body_pose('target_ring')[0]
        warnings={mujoco.mjtWarning(i).name:int(w.number) for i,w in enumerate(self.d.warning) if w.number}
        checks=dict(no_forbidden_contacts=not self.violations,contact_depth=max(self.depths.values(),default=0)<.0005,
            terminal_attachment=self.max_attachment<.0005,limited_stretch=self.max_stretch<.005,
            finite_state=bool(np.all(np.isfinite(self.d.qpos)) and np.all(np.isfinite(self.d.qvel))),
            no_external_body_forces=not bool(np.any(self.d.xfrc_applied)),assisted_grasp_error=self.max_grasp_error<.001,
            joint_force_limits=bool(np.all(self.max_force<=self.m.jnt_actfrcrange[:16,1]+1e-8)),no_warnings=not warnings,
            ring_away_from_post=bool(np.linalg.norm(ring[:2])>.19),ring_on_table=bool(abs(ring[2]-.01)<.002),
            cord_clear_of_ring_disk=cord_disk_crossings(self.m,self.d)==0,
            all_assistance_released=not any(self.held.values()),
            last_two_seconds_released=bool(self.tail and self.tail[-1][0]-self.tail[0][0]>1.99 and all(x[2] for x in self.tail)),
            final_rigid_speed=bool(self.tail and max(x[1] for x in self.tail)<.002))
        passed=all(checks.values())
        report=dict(scope='continuous_robot_sequence_attempt',passed=passed,checks=checks,full_robot_demo=passed,
            robot_execution=True,pregrasp=True,assistance='measured-contact weld grasps; right bead ball connection',
            pose_writes_after_initialization=False,fps=20,simulated_seconds=float(self.d.time),
            audit_frequency='every integration step',max_contact_depth_m=self.depths,
            max_relative_segment_extension=self.max_stretch,max_endpoint_error_m=self.max_attachment,
            max_assisted_grasp_tcp_error_m=self.max_grasp_error,
            max_final_two_seconds_rigid_speed_m_s=max((row[1] for row in self.tail),default=None),
            maximum_actuated_joint_command_error=self.max_joint_tracking.tolist(),
            maximum_actual_generalized_joint_force=self.max_force.tolist(),maximum_unclamped_actuator_force=self.max_raw_force.tolist(),
            forbidden_contacts=self.violations,warnings=warnings)
        np.savez_compressed(self.output/'states.npz',**self.trace)
        np.savez_compressed(self.output/'final_state.npz',qpos=self.d.qpos,qvel=self.d.qvel,time_s=self.d.time,
                            eq_active=self.d.eq_active,eq_data=self.m.eq_data)
        (self.output/'commands.json').write_text(json.dumps(self.commands,indent=2)+'\n')
        (self.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();episode=Episode(args.source,args.output)
    for line in sys.stdin:
        try:
            command=json.loads(line)
            if command.get('finish'):break
            if 'grasp' in command:episode.grasp(command['grasp'],command['body'])
            elif 'release' in command:episode.release(command['release'])
            else:episode.move(command)
        except (ValueError,KeyError) as exc:print(json.dumps(dict(rejected_command=str(exc))),flush=True)
    episode.finish()


if __name__=='__main__':main()
