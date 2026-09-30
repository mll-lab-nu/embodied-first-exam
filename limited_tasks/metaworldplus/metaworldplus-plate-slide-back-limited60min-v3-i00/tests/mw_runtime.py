"""Meta-World v3 fixed-instance controls; no expert policy in the public API."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import mujoco
import numpy as np
from metaworld.env_dict import ENV_CLS_MAP
from archive import load_npz, digest

SPEC = mujoco.mjtState.mjSTATE_INTEGRATION
MODEL_FIELDS = ('body_pos','body_quat','site_pos','site_quat','geom_pos','geom_quat','geom_size','eq_data')
MAX_ACTIONS = 500


def encode(x):
    if isinstance(x, np.ndarray):
        if x.dtype.hasobject: raise TypeError()
        return {'__array__':x.tolist(), 'dtype':x.dtype.str}
    if isinstance(x, np.generic): return x.item()
    if isinstance(x, tuple): return {'__tuple__':[encode(v) for v in x]}
    if isinstance(x, list): return [encode(v) for v in x]
    if isinstance(x, dict):
        if any(not isinstance(k,str) for k in x): raise TypeError()
        return {k:encode(v) for k,v in x.items()}
    if x is None or isinstance(x,(int,float,str,bool)): return x
    raise TypeError()


def decode(x):
    if isinstance(x,dict):
        if '__array__' in x: return np.asarray(x['__array__'],dtype=x['dtype'])
        if '__tuple__' in x: return tuple(decode(v) for v in x['__tuple__'])
        return {k:decode(v) for k,v in x.items()}
    if isinstance(x,list): return [decode(v) for v in x]
    return x


def caches(env):
    out={}
    for key,value in vars(env).items():
        try:
            encoded=encode(value)
            json.dumps(encoded,allow_nan=False)
            out[key]=encoded
        except (TypeError,ValueError): pass
    return out


def integration(env):
    a=np.empty(mujoco.mj_stateSize(env.model,SPEC))
    mujoco.mj_getState(env.model,env.data,a,SPEC)
    return a


def snapshot(env):
    result={'integration':integration(env)}
    result.update({'model_'+k:getattr(env.model,k).copy() for k in MODEL_FIELDS})
    result['caches']=np.array(json.dumps(caches(env),sort_keys=True,allow_nan=False))
    result['rng']=np.array(json.dumps(encode(env.np_random.bit_generator.state),sort_keys=True))
    result['global_rng']=np.array(json.dumps(encode(np.random.get_state()),sort_keys=True))
    return result


def make_env(env_id, seed, rand_vec=None):
    np.random.seed(seed)
    env=ENV_CLS_MAP[env_id](render_mode='rgb_array',camera_name='corner',width=480,height=480,
                           reward_function_version='v2')
    env._set_task_called=True
    env._partially_observable=False
    # Native goal-observable factories invalidate this cached property too.
    # Otherwise step() clips the goal to the hidden-mode zero bounds.
    env.__dict__.pop('sawyer_observation_space', None)
    env.seed(seed)
    env.seeded_rand_vec=True
    env._freeze_rand_vec=rand_vec is not None
    if rand_vec is not None: env._last_rand_vec=np.asarray(rand_vec)
    env.reset()
    return env


def create_instance(env_id, seed, output):
    env=make_env(env_id,seed)
    try:
        data=snapshot(env)
        data.update(env_id=np.array(env_id),seed=np.array(seed),observation=env._get_obs().copy(),
                    rand_vec=env._last_rand_vec.copy(),schema=np.array('rcb-metaworldplus-v1'))
        # _get_obs updates the previous-observation cache; capture the matching cache.
        data.update(snapshot(env))
        data['instance_sha']=np.array(digest(data))
        Path(output).parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(output,**data)
    finally: env.close()


def load_instance(path):
    d=load_npz(path);sha=str(d.pop('instance_sha'))
    if digest(d)!=sha or str(d['schema'])!='rcb-metaworldplus-v1':raise ValueError('invalid instance')
    return d,sha


def load_trajectory(path,sha):
    d=load_npz(path)
    if set(d)!= {'actions','instance_sha','schema'} or str(d['instance_sha'])!=sha or str(d['schema'])!='rcb-metaworldplus-controls-v1':raise ValueError('wrong trajectory schema or instance')
    a=d['actions']
    if a.dtype!=np.float64 or a.ndim!=2 or a.shape[1]!=4 or not 1<=len(a)<=MAX_ACTIONS or not np.isfinite(a).all() or np.any(abs(a)>1):raise ValueError('invalid actions')
    return a


class Session:
    def __init__(self,instance='/app/instance.npz',budget_path='/app/output/budget.json'):
        self.instance=Path(instance);self.env=None;self.budget_path=budget_path
        self.started=time.monotonic();self.calls=0;self.resets=0;self.total_steps=0
        self.reset()

    def budget(self):
        return dict(wall_seconds=time.monotonic()-self.started,tool_calls=self.calls,resets=self.resets,
                    sim_steps=self.total_steps,physics_steps=self.total_steps*self.env.frame_skip)

    def _budget(self):
        if self.budget_path:
            p=Path(self.budget_path);p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(self.budget())+'\n')

    def reset(self):
        self.calls+=1
        if self.resets>=40:raise RuntimeError('reset budget exhausted')
        if self.env is not None:self.env.close()
        frozen,self.instance_sha=load_instance(self.instance)
        self.env=env=make_env(str(frozen['env_id']),int(frozen['seed']),frozen['rand_vec'])
        for k in MODEL_FIELDS:getattr(env.model,k)[:]=frozen['model_'+k]
        for k,v in decode(json.loads(str(frozen['caches']))).items():setattr(env,k,v)
        env.np_random.bit_generator.state=decode(json.loads(str(frozen['rng'])))
        np.random.set_state(decode(json.loads(str(frozen['global_rng']))))
        mujoco.mj_setState(env.model,env.data,frozen['integration'],SPEC)
        mujoco.mj_forward(env.model,env.data)
        mujoco.mj_setState(env.model,env.data,frozen['integration'],SPEC)
        self.obs=frozen['observation'].copy();self.actions=[];self.resets+=1
        self.last_reward,self.info=env.evaluate_state(self.obs,np.zeros(4))
        self.ever_success=bool(self.info['success']);self.initial_success=self.ever_success
        self._budget()
        return self.observe()

    def observe(self):
        self.calls+=1;self._budget()
        return dict(observation=self.obs.copy(),tcp=self.env.tcp_center.copy(),goal=self.env._target_pos.copy(),
                    joint_positions=self.env.data.qpos.copy(),joint_velocities=self.env.data.qvel.copy(),
                    bodies={self.env.model.body(i).name:{'position':self.env.data.xpos[i].copy(),
                      'quaternion_wxyz':self.env.data.xquat[i].copy()} for i in range(self.env.model.nbody)},
                    gripper=self.obs[3].item())

    def render(self):
        self.calls+=1;self._budget()
        return self.env.render()[::-1].copy()

    def step(self,action):
        self.calls+=1
        a=np.asarray(action,dtype=np.float64)
        if a.shape!=(4,) or not np.isfinite(a).all() or np.any(abs(a)>1):raise ValueError('four finite values in [-1,1] required')
        if len(self.actions)>=MAX_ACTIONS or self.total_steps>=16000:raise RuntimeError('control budget exhausted')
        self.obs,reward,terminated,truncated,info=self.env.step(a.copy())
        self.actions.append(a.copy());self.total_steps+=1;self.last_reward=float(reward);self.info=info
        self.ever_success|=bool(info['success']);self._budget()
        if self.env._did_see_sim_exception:raise RuntimeError('native simulation exception')
        return self.obs.copy(),self.last_reward,dict(info)

    def move(self,position,gripper=-1,steps=30,tolerance=.008):
        """Proportional native XYZ control, fixed wrist; no collision planning."""
        for _ in range(steps):
            error=np.asarray(position)-self.env.tcp_center
            if np.linalg.norm(error)<tolerance:break
            self.step(np.r_[np.clip(error*10,-1,1),gripper])
        return self.observe()

    def result(self):
        state=snapshot(self.env)
        return dict(success=int(self.ever_success),final_success=int(self.info['success']),initial_success=int(self.initial_success),
                    n_actions=len(self.actions),sim_steps=len(self.actions),physics_steps=len(self.actions)*self.env.frame_skip,
                    control_hz=1/(self.env.model.opt.timestep*self.env.frame_skip),final_reward=float(self.last_reward),
                    state_sha=digest(state),integration_sha=digest({'integration':integration(self.env)}),
                    budget=self.budget(),info={k:float(v) for k,v in self.info.items() if np.isscalar(v)})

    def save(self,path='/app/output/trajectory.npz'):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(path,actions=np.asarray(self.actions,dtype=np.float64).reshape(-1,4),
                            instance_sha=np.array(self.instance_sha),schema=np.array('rcb-metaworldplus-controls-v1'))
        self._budget()

    def close(self):
        if self.env is not None:self.env.close();self.env=None


def replay(instance,trajectory,output,video=None):
    _,sha=load_instance(instance);actions=load_trajectory(trajectory,sha)
    s=Session(instance,budget_path=None);writer=None
    try:
        if video:
            import imageio.v2 as imageio
            writer=imageio.get_writer(video,fps=1/(s.env.model.opt.timestep*s.env.frame_skip))
        for a in actions:
            s.step(a)
            if writer is not None:writer.append_data(s.render())
        r=s.result();Path(output).write_text(json.dumps(r,indent=2)+'\n')
        np.savez_compressed(str(output)+'.state.npz',integration=integration(s.env))
        return r
    finally:
        if writer is not None:writer.close()
        s.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--instance',required=True);p.add_argument('--trajectory',required=True);p.add_argument('--output',required=True);p.add_argument('--video')
    a=p.parse_args();print(json.dumps(replay(a.instance,a.trajectory,a.output,a.video)))
