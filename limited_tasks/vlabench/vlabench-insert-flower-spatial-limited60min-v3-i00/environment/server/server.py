"""Private, single-episode simulator. Only four public endpoints; no reset."""
import base64
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import socketserver
import threading
import time
import traceback

import numpy as np
from vlb_traj import Session, MAX_ACTIONS, SCHEMA, UPSTREAM, canonical, physics_state
from runtime import count_physics

ROOT=Path('/recorded')
LIMIT=3600.0


def utc(): return datetime.now(timezone.utc).isoformat()


from episode_clock import AgentClock

class Service(AgentClock):
    def __init__(self):
        ROOT.mkdir(exist_ok=True)
        self.lock=threading.RLock()
        self.session=Session('/private/instance.json',budget_path=None)
        self.physics_counter=count_physics(self.session)
        self.actions=[]
        self.physical_steps=0
        self.active=False
        self.ended=False
        self.sealed=False
        self.online_success=False
        self.reason=None
        self.start=None
        self.started_at=None
        self.ended_at=None
        self.end_elapsed=None
        self.events=0
        self.rejected=0
        self.observations=0
        self.max_actions=MAX_ACTIONS
        s=self.session
        if s.lower.shape!=(9,) or abs(s.dt-0.1)>1e-12:
            raise RuntimeError('Unsupported actuator shape/control period; requires explicit adaptation')
        self.cameras=list(range(min(4,s._env.physics.model.ncam)))
        if not self.cameras: raise RuntimeError('No usable RGB cameras')
        self.event('ready',initial_state_sha=s.initial_hash,model_sha=s.model_sha)
        self.init_agent_clock()
        self.persist()

    def event(self,kind,**data):
        self.events+=1
        row=dict(sequence=self.events,at=utc(),elapsed=self.elapsed(),kind=kind,**data)
        with (ROOT/'events.jsonl').open('a') as f:
            f.write(canonical(row)+'\n'); f.flush(); os.fsync(f.fileno())

    def elapsed(self): return time.monotonic()-self.start if self.start else 0.0

    def finish(self,reason):
        if not self.ended:
            self.ended=True; self.reason=reason; self.ended_at=utc(); self.end_elapsed=self.elapsed()
            self.event('episode_end',reason=reason,online_success=self.online_success)


    def persist(self):
        value=dict(protocol='vlabench-limited-v1',started_at=self.started_at,ended_at=self.ended_at,
                   agent_seconds=self.end_elapsed if self.ended else self.elapsed(),limit_seconds=LIMIT,
                   ready=True,active=self.active,ended=self.ended,sealed=self.sealed,termination_reason=self.reason,
                   online_success=self.online_success,n_actions=len(self.actions),
                   completed_controls=self.session.sim_steps,physics_steps=self.physical_steps,
                   control_dt=self.session.dt,n_substeps=self.session.substeps,resets=0,initializations=1,
                   rejected_calls=self.rejected,observations=self.observations,events=self.events,
                   initial_state_sha=self.session.initial_hash,instance_sha=self.session.instance_sha)
        value.update(self.agent_clock_fields())
        temp=ROOT/'episode.tmp'; temp.write_text(canonical(value)+'\n'); temp.replace(ROOT/'episode.json')
        return value

    def robot(self):
        e=self.session._env
        fingers=[e.robot.mjcf_model.find('joint',f'finger_joint{i}') for i in (1,2)]
        return dict(joint_positions=e.robot.get_qpos(e.physics).copy(),
                    joint_velocities=e.robot.get_qvel(e.physics).copy(),
                    gripper_positions=e.physics.bind(fingers).qpos.copy(),
                    tcp_position=e.get_ee_pos().copy(),tcp_quaternion_wxyz=e.get_ee_quat().copy())

    def status(self):
        return dict(active=self.active and not self.ended,ended=self.ended,
                    actions=len(self.actions),physics_steps=self.physical_steps,
                    remaining_seconds=max(0,LIMIT-self.elapsed()) if self.active else LIMIT)

    def dispatch(self,path,body):
        with self.lock:
            self.deadline()
            s=self.session
            if path=='/v1/spec' and body=={}:
                return dict(protocol='vlabench-limited-v1',action_shape=[9],action_lower=s.lower.tolist(),
                            action_upper=s.upper.tolist(),control_dt=s.dt,physics_substeps=s.substeps,
                            max_actions=self.max_actions,agent_seconds=LIMIT,cameras=self.cameras,
                            width=480,height=480,action_semantics='seven_absolute_arm_radians_two_finger_metres')
            if path=='/v1/status' and body=={}: return self.status()
            if path=='/v1/observe' and set(body)=={'camera'}:
                camera=body['camera']
                if type(camera) is not int or camera not in self.cameras: raise ValueError()
                obs=s.observe(camera=camera,width=480,height=480)
                buff=io.BytesIO()
                np.savez_compressed(buff,rgb=obs['rgb'],depth_m=obs['depth_m'],
                                    intrinsic=obs['intrinsic'],camera_to_world=obs['camera_to_world'])
                self.observations+=1
                self.event('observation',camera=camera)
                return dict(npz_base64=base64.b64encode(buff.getvalue()).decode(),robot=self.robot())
            if path=='/v1/step' and set(body)=={'action'}:
                if not self.active or self.ended or self.sealed: raise ValueError()
                raw=body['action']
                if not isinstance(raw,list) or len(raw)!=9 or any(type(x) not in (int,float) for x in raw): raise ValueError()
                a=np.asarray(raw,dtype=np.float64)
                if not np.isfinite(a).all() or (a<s.lower).any() or (a>s.upper).any(): raise ValueError()
                if len(self.actions)>=self.max_actions: raise ValueError()
                # Persist the attempted control BEFORE physics, including controls that fail.
                self.actions.append(a.copy())
                before=float(s._env.physics.data.time)
                before_steps=self.physics_counter['steps']
                self.event('action_begin',index=len(self.actions)-1,action=a,physics_time=before)
                try:
                    s._step(a)
                    self.online_success=bool(s.status()['success'])
                    if self.elapsed()>=LIMIT: self.finish('timeout')
                    elif self.online_success: self.finish('native_success')
                    elif s.done: self.finish('native_termination')
                    elif len(self.actions)>=self.max_actions: self.finish('physical_step_limit')
                except Exception as exc:
                    self.event('simulation_error',error_type=type(exc).__name__,error=str(exc))
                    traceback.print_exc()
                    self.finish('simulation_failure')
                finally:
                    after=float(s._env.physics.data.time)
                    advanced=self.physics_counter['steps']-before_steps
                    self.physical_steps+=advanced
                    self.event('action_end',index=len(self.actions)-1,physics_steps=advanced,
                               physics_time=after,completed_controls=s.sim_steps)
                    self.persist()
                return self.status()
            raise ValueError()

    def admin(self,command):
        with self.lock:
            if command=='start':
                if self.active or self.sealed: raise ValueError('episode already started')
                self.start=time.monotonic(); self.started_at=utc(); self.active=True
                self.event('agent_start'); self.persist()
                return {'started':True}
            if command=='stop': return self.stop_agent()
            if command=='seal':
                self.stop_agent()
                self.deadline()
                if not self.ended: self.finish('agent_stopped')
                if not self.sealed:
                    s=self.session
                    # Empty nop trajectory is valid evidence of an uncompleted episode.
                    metadata=dict(schema=SCHEMA,upstream_commit=UPSTREAM,instance_sha=s.instance_sha,
                                  native_task=s.spec['native_task'],control_dt=s.dt,
                                  action_semantics='absolute_actuator_position_targets',
                                  n_substeps=s.substeps,dtype='float64')
                    np.savez_compressed(ROOT/'trajectory.npz',actions=np.asarray(self.actions,dtype=np.float64).reshape(-1,9),
                                        times=np.arange(len(self.actions))*s.dt,metadata=canonical(metadata))
                    np.savez_compressed(ROOT/'online.state.npz',integration=physics_state(s._env))
                    try: (ROOT/'online.json').write_text(canonical(s.status())+'\n')
                    except Exception: pass
                    self.sealed=True; self.event('sealed'); self.persist()
                return {'sealed':True}
            raise ValueError('unsupported management command')


class Handler(BaseHTTPRequestHandler):
    server_version='LimitedAPI'; sys_version=''
    def log_message(self,*args): pass
    def do_POST(self):
        self.connection.settimeout(10)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096 or self.headers.get('Transfer-Encoding'): raise ValueError()
            body=json.loads(self.rfile.read(size),parse_constant=lambda x: (_ for _ in ()).throw(ValueError()))
            if not isinstance(body,dict): raise ValueError()
            value=self.server.service.dispatch(self.path,body); code=200
        except Exception:
            with self.server.service.lock:
                self.server.service.rejected+=1
                self.server.service.event('request_rejected')
            value={'error':'request_rejected'}; code=400
        raw=canonical(value).encode()
        self.send_response(code); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw))); self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError): pass
    def do_GET(self):
        self.send_response(405); self.send_header('Content-Length','0'); self.end_headers()


class Admin(socketserver.StreamRequestHandler):
    def handle(self):
        try: value=self.server.service.admin(self.rfile.readline(100).decode().strip())
        except Exception: value={'error':'rejected'}
        self.wfile.write((canonical(value)+'\n').encode())


if __name__=='__main__':
    service=Service()
    socket_path='/run/limited/control.sock'
    admin=socketserver.UnixStreamServer(socket_path,Admin); admin.service=service
    threading.Thread(target=admin.serve_forever,daemon=True).start()
    def timer():
        while True:
            time.sleep(0.1)
            with service.lock: service.deadline()
    threading.Thread(target=timer,daemon=True).start()
    http=HTTPServer(('0.0.0.0',8000),Handler); http.service=service
    http.serve_forever()
