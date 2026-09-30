"""Private simulator adapter. Never installed in main or returned by the public API."""
import hashlib
import json
from pathlib import Path
import mujoco
import numpy as np

class Backend:
    def __init__(self,root='/private',replaying=False):
        root=Path(root);self.config=json.loads((root/'backend.json').read_text());self.kind=self.config['kind']
        if self.kind=='navigation':
            from casa_traj import Session,state_sha,snapshot
            class CaptureInitialObservation(Session):
                def observe(self):
                    value=super().observe();self.last_observation=value
                    return value
            self.session=CaptureInitialObservation(root/'instance.npz')
            self.instance_sha=hashlib.sha256((root/'instance.npz').read_bytes()).hexdigest()
            self.hash=lambda:state_sha(self.env)
            self.state=lambda:np.concatenate([np.asarray(v).ravel() for v in snapshot(self.env).values()])
        else:
            from casa_runtime import Session,state_hash,physical
            self.session=Session(root/'instance.npz',budget_path=None,replaying=replaying)
            self.instance_sha=self.session.instance_sha
            self.hash=lambda:state_hash(self.env)
            self.state=lambda:physical(self.env)['integration']
        self.env=self.session.env;self.language=self.env.get_ep_meta().get('lang','');self.model=self.env.sim.model._model;self.data=self.env.sim.data._data
        self.spec=json.loads((root/'public_spec.json').read_text())
        self.dim=self.spec['action_shape'][0];self.cap=self.config['max_actions']
        self.nsub=int(round(self.env.control_timestep/self.env.model_timestep))
        self.pending=None;self.cursor=0;self.frame=[];self.completed=0;self.ever=False
        self.bad_warning_ids=[int(getattr(mujoco.mjtWarning,name)) for name in ('mjWARN_BADQPOS','mjWARN_BADQVEL','mjWARN_BADQACC','mjWARN_BADCTRL')]
        if replaying:
            for r in self.env.robots:r.control=lambda *a,**kw:None
        method='step2' if self.env.lite_physics else 'step'
        native=getattr(self.env.sim,method)
        def physics():
            if self.pending is not None:
                if self.cursor>=len(self.pending):raise RuntimeError('partial_control_boundary')
                self.data.ctrl[:]=self.pending[self.cursor];self.cursor+=1
            control=self.data.ctrl.copy();before=float(self.data.time);returned=False
            warnings=self.data.warning.number[self.bad_warning_ids].copy()
            try:
                value=native();returned=True
                if not np.array_equal(warnings,self.data.warning.number[self.bad_warning_ids]):
                    raise RuntimeError('native numerical instability; implicit restart rejected')
                # MuJoCo may automatically reset after numerical instability.
                # That must end a limited episode as a simulation failure.
                if not np.isclose(float(self.data.time),before+self.model.opt.timestep,rtol=0,atol=1e-9):
                    raise RuntimeError('native simulation clock discontinuity; implicit restart rejected')
                return value
            finally:
                if returned or float(self.data.time)>before:self.frame.append(control)
        setattr(self.env.sim,method,physics)
        # Some native predicates increment timers. Reuse the source Session's
        # check instead of invoking it again at ready, seal, or result export.
        self.initial_success=bool(self.session.initial_success) if self.kind!='navigation' else bool(self.session.last_observation['success'])
        self.last_success=self.initial_success
        self.initial_sha=self.hash()
        self.joints=[]
        for r in self.env.robots:
            names=list(r.robot_model.joints)
            base=getattr(r.robot_model,'base',None)
            if base is not None:names+=list(base.joints)
            for gripper in r.gripper.values():names+=list(gripper.joints)
            for name in names:
                if name not in self.joints:self.joints.append(name)
        self.cameras=[self.model.camera(i).name for i in range(self.model.ncam)]
        # Panda's first native camera (robotview) can sit inside an opaque body.
        # Prefer the native task-facing agent camera for client defaults/video;
        # retain every native camera as an explicitly selectable observation.
        preferred=('robot0_agentview_center','agentview','robot0_frontview')
        self.cameras.sort(key=lambda name: preferred.index(name) if name in preferred else len(preferred))
    def validate(self,action):
        if not isinstance(action,list) or len(action)!=self.dim or any(type(x) not in (int,float) for x in action):raise ValueError('action')
        a=np.asarray(action,dtype=np.float64)
        if not np.isfinite(a).all() or np.any(a<self.spec['action_lower']) or np.any(a>self.spec['action_upper']):raise ValueError('bounds')
        return a
    def step(self,a,controls=None):
        self.pending=controls;self.cursor=0;self.frame=[]
        value=self.session.step(a)
        if controls is not None and self.cursor!=len(controls):raise ValueError('unused actuator controls')
        self.completed+=1
        native=bool(value['success'] if self.kind=='navigation' else value['native_success'])
        if self.config['ever_success']:native=bool(self.session.ever_success)
        self.last_success=native;self.ever|=native
        return dict(success=native,done=bool(value.get('done',False)))
    def result(self):
        return dict(success=bool(self.ever if self.config['ever_success'] else self.last_success),
                    initial_success=self.initial_success,state_sha=self.hash(),completed_controls=self.completed)
    def robot(self):
        m,d=self.model,self.data;positions=[];velocities=[];types=[]
        for name in self.joints:
            j=m.joint(name).id;qa=m.jnt_qposadr[j];va=m.jnt_dofadr[j]
            nq=7 if m.jnt_type[j]==0 else 4 if m.jnt_type[j]==1 else 1
            nv=6 if m.jnt_type[j]==0 else 3 if m.jnt_type[j]==1 else 1
            positions.append(d.qpos[qa:qa+nq].tolist());velocities.append(d.qvel[va:va+nv].tolist());types.append(int(m.jnt_type[j]))
        tips={}
        for ri,r in enumerate(self.env.robots):
            for arm,site in r.eef_site_id.items():
                quat=np.empty(4);mujoco.mju_mat2Quat(quat,d.site_xmat[site])
                tips[f'{ri}:{arm}']=dict(position=d.site_xpos[site].tolist(),quaternion_wxyz=quat.tolist())
        return dict(joint_names=self.joints,joint_positions=positions,joint_velocities=velocities,joint_types=types,end_effectors=tips)
    def close(self):self.session.close()
