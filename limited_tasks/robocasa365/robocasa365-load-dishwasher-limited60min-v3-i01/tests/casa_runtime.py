"""Fixed RoboCasa / GR1 instances and native actuator traces.

Client: native robot controllers. Replay: recorded actuator controls, while the
native environment still advances its task logic at each control boundary.
No IK, policy or motion planner executes in replay.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,random,time,types
from pathlib import Path
import mujoco,numpy as np
import robosuite,robocasa
from archive import load_npz,digest

SPEC=mujoco.mjtState.mjSTATE_INTEGRATION
MODEL_FIELDS=('body_pos','body_quat','site_pos','site_quat','geom_pos','geom_quat','geom_size','eq_data','geom_rgba','site_rgba')
MAX_CONTROLS=3000

class InvalidTrajectory(ValueError):
 pass

def encode(x):
 if isinstance(x,np.ndarray):
  if x.dtype.hasobject:raise TypeError()
  return {'__array__':x.tolist(),'dtype':x.dtype.str}
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,tuple):return {'__tuple__':[encode(v) for v in x]}
 if isinstance(x,list):return [encode(v) for v in x]
 if isinstance(x,dict):
  if any(not isinstance(k,str) for k in x):raise TypeError()
  return {k:encode(v) for k,v in x.items()}
 if x is None or isinstance(x,(int,float,str,bool)):return x
 raise TypeError()

def decode(x):
 if isinstance(x,dict):
  if '__array__' in x:return np.asarray(x['__array__'],dtype=x['dtype'])
  if '__tuple__' in x:return tuple(decode(v) for v in x['__tuple__'])
  return {k:decode(v) for k,v in x.items()}
 if isinstance(x,list):return [decode(v) for v in x]
 return x

def caches(obj):
 out={}
 for k,v in vars(obj).items():
  try:
   value=encode(v);json.dumps(value,allow_nan=False);out[k]=value
  except (TypeError,ValueError):pass
 return out

def graph(env):
 # Explicit object graph; no pickle, arbitrary deserialization or dotted eval.
 out={'env':env}
 for k,v in env.fixtures.items():out['fixture:'+k]=v
 for i,r in enumerate(env.robots):
  out['robot:'+str(i)]=r
  out['composite:'+str(i)]=r.composite_controller
  for k,v in r.part_controllers.items():out[f'controller:{i}:{k}']=v
  for k,v in r.gripper.items():out[f'gripper:{i}:{k}']=v
  for k,v in vars(r).items():
   if type(v).__module__=='robosuite.utils.buffers':out[f'buffer:{i}:{k}']=v
 for k,v in env._observables.items():out['observable:'+k]=v
 return out

def raw(env):return env.sim.model._model,env.sim.data._data

def physical(env):
 m,d=raw(env);state=np.empty(mujoco.mj_stateSize(m,SPEC));mujoco.mj_getState(m,d,state,SPEC)
 result={'integration':state}
 result.update({'model_'+k:getattr(m,k).copy() for k in MODEL_FIELDS})
 return result

def snapshot(env):
 result=physical(env)
 result['caches']=np.array(json.dumps({k:caches(v) for k,v in graph(env).items()},sort_keys=True,allow_nan=False))
 result['rng']=np.array(json.dumps(encode(env.rng.bit_generator.state),sort_keys=True))
 result['global_rng']=np.array(json.dumps(encode(np.random.get_state()),sort_keys=True))
 result['python_rng']=np.array(json.dumps(encode(random.getstate())))
 return result

def restore(env,frozen):
 m,d=raw(env)
 for k in MODEL_FIELDS:getattr(m,k)[:]=frozen['model_'+k]
 for name,values in decode(json.loads(str(frozen['caches']))).items():
  obj=graph(env)[name]
  for k,v in values.items():setattr(obj,k,v)
 env.rng.bit_generator.state=decode(json.loads(str(frozen['rng'])))
 np.random.set_state(decode(json.loads(str(frozen['global_rng']))));random.setstate(decode(json.loads(str(frozen['python_rng']))))
 mujoco.mj_setState(m,d,frozen['integration'],SPEC);mujoco.mj_forward(m,d)
 # forward changes warmstart / derived accelerations, restore integration again.
 mujoco.mj_setState(m,d,frozen['integration'],SPEC)

def make_env(config,meta=None,xml=None,render=False):
 random.seed(0);np.random.seed(0);kw=copy.deepcopy(config)
 kw.update(has_renderer=False,has_offscreen_renderer=render,use_camera_obs=False,seed=0)
 env=robosuite.make(**kw)
 if meta is not None:env.set_ep_meta(copy.deepcopy(meta))
 env.reset()
 if xml is not None:
  env.reset_from_xml_string(env.edit_model_xml(xml));env.sim.reset()
 return env

def freeze(env,config,path):
 # Capture after all initialization and native update_state calls.
 data=snapshot(env);meta=env.get_ep_meta()
 data.update(config=np.array(json.dumps(config)),ep_meta=np.array(json.dumps(meta,default=lambda x:x.item() if isinstance(x,np.generic) else list(x))),xml=np.array(env.sim.model.get_xml()),schema=np.array('rcb-casa-instance-v1'))
 data['instance_sha']=np.array(digest(data));Path(path).parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(path,**data)
 return str(data['instance_sha'])

def load_instance(path):
 # Trusted, authored input; never supplied by agent to verifier.
 with np.load(path,allow_pickle=False) as z:data={k:z[k].copy() for k in z.files}
 sha=str(data.pop('instance_sha'))
 if str(data['schema'])!='rcb-casa-instance-v1' or digest(data)!=sha:raise ValueError('instance digest mismatch')
 return data,sha

def task_state(env):
 # Native task and fixture logic, excluding observation/controller caches that
 # do not run on the actuator replay path. Physics includes all integration fields.
 skip={'_obs_cache','_ep_meta','_cam_configs','object_cfgs','fixture_cfgs','_curr_gen_fixtures'}
 simple={k:v for k,v in caches(env).items() if k not in skip and not isinstance(v,(dict,list,str))}
 # Include array and tuple task caches (e.g. previous vegetable positions).
 for k,v in caches(env).items():
  if k not in skip and isinstance(v,dict) and ('__array__' in v or '__tuple__' in v):simple[k]=v
 fixture={name:{k:v for k,v in caches(obj).items() if k.startswith('_') and isinstance(v,(int,float,bool))} for name,obj in env.fixtures.items()}
 return dict(env=simple,fixtures=fixture)

def state_hash(env):
 data=physical(env);data['task_state']=np.array(json.dumps(task_state(env),sort_keys=True));return digest(data)

class Session:
 def __init__(self,instance='/app/instance.npz',render=False,budget_path='/app/output/budget.json',replaying=False):
  self.instance=Path(instance);self.render_enabled=render;self.budget_path=budget_path;self.env=None;self.calls=0;self.total_steps=0;self.total_physics=0;self.resets=0;self.started=time.monotonic();self.replaying=replaying;self.reset()
 def budget(self):return dict(wall_seconds=time.monotonic()-self.started,tool_calls=self.calls,resets=self.resets,sim_steps=self.total_steps,physics_steps=self.total_physics,simulation_seconds=self.total_steps/self.env.control_freq)
 def _budget(self):
  if self.budget_path:
   p=Path(self.budget_path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(self.budget())+'\n')
 def reset(self):
  if self.resets>=40:raise RuntimeError('reset budget exhausted')
  if self.env is not None:self.env.close()
  data,self.instance_sha=load_instance(self.instance)
  self.env=make_env(json.loads(str(data['config'])),json.loads(str(data['ep_meta'])),str(data['xml']),self.render_enabled)
  restore(self.env,data);self.actions=[];self.controls=[];self.resets+=1;self.calls+=1;self.initial_success=bool(self.env._check_success());self.ever_success=self.initial_success
  method='step2' if self.env.lite_physics else 'step'
  self._native_sim_step=getattr(self.env.sim,method)
  setattr(self.env.sim,method,self._physics_step)
  if self.replaying:
   # Task bookkeeping stays native; robot controllers (including IK) are bypassed.
   for robot in self.env.robots:robot.control=lambda *args,**kwargs:None
  self._pending=None;self._frame_controls=[];self._cursor=0;self._budget()
  return self.observe()
 def _physics_step(self):
  if self._pending is not None:
   if self._cursor>=len(self._pending):raise ValueError('too few actuator controls')
   self.env.sim.data.ctrl[:]=self._pending[self._cursor];self._cursor+=1
  self._frame_controls.append(self.env.sim.data.ctrl.copy());self._native_sim_step()
 def observe(self):
  self.calls+=1;self._budget();e=self.env
  return dict(instruction=e.get_ep_meta().get('lang',''),qpos=e.sim.data.qpos.copy(),qvel=e.sim.data.qvel.copy(),body_positions={name:e.sim.data.get_body_xpos(name).copy() for name in e.sim.model.body_names if name},body_quaternions_wxyz={name:e.sim.data.get_body_xquat(name).copy() for name in e.sim.model.body_names if name},objects=e.get_ep_meta().get('object_cfgs',[]),joint_names=list(e.sim.model.joint_names),joint_limits=e.sim.model.jnt_range.copy(),actuator_names=list(e.sim.model.actuator_names),action_dim=e.action_dim,action_limits=e.action_spec,control_hz=e.control_freq,action_parts=dict(getattr(e.robots[0].composite_controller,'_whole_body_controller_action_split_indexes',{}) or e.robots[0]._action_split_indexes))
 def solve_ik(self,position,quaternion_wxyz=None,iterations=100):
  """Robot-model DLS IK on scratch data; no object selection/collision planning."""
  from scipy.spatial.transform import Rotation
  self.calls+=1;self._budget();e=self.env;r=e.robots[0];c=r.part_controllers['right'];m,_=raw(e)
  if type(c).__name__!='JointPositionController' or len(c.qpos_index)!=7:raise ValueError('IK helper requires the 13-D Panda joint-position configuration')
  target=np.asarray(position,dtype=float)
  if target.shape!=(3,) or not np.isfinite(target).all():raise ValueError('expected finite world XYZ metres')
  target_R=None
  if quaternion_wxyz is not None:
   quat=np.asarray(quaternion_wxyz,dtype=float)
   if quat.shape!=(4,) or not np.isfinite(quat).all() or np.linalg.norm(quat)<1e-8:raise ValueError('invalid WXYZ quaternion')
   target_R=Rotation.from_quat(quat[[1,2,3,0]]).as_matrix()
  d=mujoco.MjData(m);d.qpos[:]=e.sim.data.qpos;site=r.eef_site_id['right'];jp=np.zeros((3,m.nv));jr=np.zeros((3,m.nv));error=np.zeros(3)
  limits=m.jnt_range[c.joint_index];angular_error=0.
  for _ in range(min(int(iterations),200)):
   mujoco.mj_kinematics(m,d);mujoco.mj_comPos(m,d);mujoco.mj_jacSite(m,d,jp,jr,site)
   error=target-d.site_xpos[site];J=jp[:,c.qvel_index];residual=error
   if target_R is not None:
    ori=Rotation.from_matrix(target_R@d.site_xmat[site].reshape(3,3).T).as_rotvec();angular_error=float(np.linalg.norm(ori));J=np.vstack([J,jr[:,c.qvel_index]]);residual=np.r_[error,ori]
   if np.linalg.norm(residual)<1e-4:break
   dq=J.T@np.linalg.solve(J@J.T+1e-4*np.eye(len(residual)),residual)
   d.qpos[c.qpos_index]=np.clip(d.qpos[c.qpos_index]+np.clip(dq,-.1,.1),limits[:,0],limits[:,1])
  mujoco.mj_kinematics(m,d);position_error=float(np.linalg.norm(target-d.site_xpos[site]))
  if target_R is not None:angular_error=float(np.linalg.norm(Rotation.from_matrix(target_R@d.site_xmat[site].reshape(3,3).T).as_rotvec()))
  return dict(joints=d.qpos[c.qpos_index].copy(),position_error_m=position_error,orientation_error_rad=angular_error,converged=position_error<.002 and angular_error<.02)
 def move(self,position,quaternion_wxyz=None,gripper=-1,steps=20):
  """Track an agent-supplied Cartesian target using generic robot-only IK."""
  solution=self.solve_ik(position,quaternion_wxyz)
  if not solution['converged']:return solution
  action=np.zeros(self.env.action_dim);parts=self.env.robots[0]._action_split_indexes
  lo,hi=parts['right'];action[lo:hi]=solution['joints'];lo,hi=parts['right_gripper'];action[lo:hi]=gripper;action[-1]=-1
  for _ in range(min(int(steps),200)):self.step(action)
  return solution
 def step(self,action,actuator_controls=None):
  a=np.array(action,dtype=np.float64,copy=True)
  if a.shape!=(self.env.action_dim,) or not np.isfinite(a).all():raise InvalidTrajectory('wrong native action shape / nonfinite action')
  # IK absolute poses are not normalized; native action limits can be infinite.
  lo,hi=(x.copy() for x in self.env.action_spec)
  if self.env.robots[0].robot_model.__class__.__name__=='GR1ArmsAndWaistFourierHands':
   # The official unscaled Fourier-hand demos use [-3,3], despite advertised [-1,1].
   lo[:12]=-10;hi[:12]=10;lo[12:]=-3;hi[12:]=3
  if np.any(a<lo) or np.any(a>hi):raise InvalidTrajectory('native action outside limits')
  if len(self.actions)>=MAX_CONTROLS or self.total_steps>=16000:raise RuntimeError('control budget exhausted')
  if actuator_controls is not None and not self.replaying:raise InvalidTrajectory('actuator input is verifier-only')
  self._pending=actuator_controls;self._cursor=0;self._frame_controls=[]
  submitted_action=a.copy()
  _,reward,done,info=self.env.step(a)
  if self._pending is not None and self._cursor!=len(self._pending):raise InvalidTrajectory('too many actuator controls')
  self._pending=None;self.actions.append(submitted_action);self.controls.append(np.asarray(self._frame_controls));self.calls+=1;self.total_steps+=1;self.total_physics+=len(self._frame_controls);self.ever_success|=bool(self.env._check_success());self.last_reward=float(reward);self._budget()
  return dict(native_success=bool(self.env._check_success()),native_reward=float(reward),done=bool(done),control_steps=len(self.actions))
 def render(self,camera=None,width=512,height=384):
  self.calls+=1;self._budget();camera=camera or ('egoview' if 'egoview' in self.env.sim.model.camera_names else 'robot0_agentview_center')
  return self.env.sim.render(height=height,width=width,camera_name=camera)[::-1]
 def result(self):return dict(success=int(self.ever_success if robocasa.__version__.startswith('1.') else self.env._check_success()),final_success=int(self.env._check_success()),ever_success=int(self.ever_success),initial_success=int(self.initial_success),n_actions=len(self.actions),sim_steps=len(self.actions),physics_steps=sum(map(len,self.controls)),state_sha=state_hash(self.env),final_reward=float(getattr(self,'last_reward',0)),budget=self.budget())
 def save(self,path='/app/output/trajectory.npz'):
  p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
  np.savez_compressed(p,actions=np.asarray(self.actions,dtype=np.float64),actuator_controls=np.asarray(self.controls,dtype=np.float64),schema=np.array('rcb-casa-actuator-trace-v1'),instance_sha=np.array(self.instance_sha));self._budget()
 def close(self):
  if self.env is not None:self.env.close()

def load_trajectory(path,s):
 try:d=load_npz(path,max_bytes=16_000_000)
 except (ValueError,KeyError,TypeError) as exc:raise InvalidTrajectory(str(exc)) from exc
 if set(d)!={'actions','actuator_controls','schema','instance_sha'} or str(d['schema'])!='rcb-casa-actuator-trace-v1' or str(d['instance_sha'])!=s.instance_sha:raise InvalidTrajectory('wrong schema or instance')
 a=d['actions'];c=d['actuator_controls'];m,_=raw(s.env)
 nsub=int(s.env.control_timestep/s.env.model_timestep)
 if a.dtype!=np.float64 or a.ndim!=2 or a.shape[1]!=s.env.action_dim or not 1<=len(a)<=MAX_CONTROLS or not np.isfinite(a).all():raise InvalidTrajectory('invalid native controls')
 if c.dtype!=np.float64 or c.shape!=(len(a),nsub,m.nu) or not np.isfinite(c).all():raise InvalidTrajectory('invalid actuator trace')
 limited=m.actuator_ctrllimited.astype(bool)
 if np.any(c[:,:,limited]<m.actuator_ctrlrange[limited,0]) or np.any(c[:,:,limited]>m.actuator_ctrlrange[limited,1]):raise InvalidTrajectory('actuator range violation')
 return a,c

def replay(instance,trajectory,output,video=None):
 s=Session(instance,render=video is not None,budget_path=None,replaying=True);actions,controls=load_trajectory(trajectory,s);writer=None
 if video:
  import imageio.v2 as iio
  writer=iio.get_writer(video,fps=s.env.control_freq/2,codec='libx264');writer.append_data(s.render())
 try:
  for i,(a,c) in enumerate(zip(actions,controls)):
   s.step(a,c)
   if writer and i%2==0:writer.append_data(s.render())
  result=s.result();Path(output).write_text(json.dumps(result,indent=2)+'\n');np.savez_compressed(str(output)+'.state.npz',**physical(s.env));print(json.dumps(result),flush=True)
 finally:
  if writer:writer.close()
  s.close()
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--instance',required=True);p.add_argument('--trajectory',required=True);p.add_argument('--output',required=True);p.add_argument('--video');a=p.parse_args();replay(a.instance,a.trajectory,a.output,a.video)
