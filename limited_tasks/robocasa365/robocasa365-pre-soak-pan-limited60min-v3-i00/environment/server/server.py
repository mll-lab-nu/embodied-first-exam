"""Private single-episode RoboCasa service: spec/observe/step/status only; no reset.

Runs in the sim sidecar with all Linux capabilities dropped. The accepted privileged runtime
(the native RoboCasa runtime, byte-identical to the verifier copy) restores the frozen instance
once; every attempted control is journaled before physics and the complete episode
is sealed by the trusted control plane (Unix socket, sim-only).
"""
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

import mujoco
import numpy as np
from backend import Backend

ROOT = Path('/recorded')
LIMIT = 3600.0
WIDTH = HEIGHT = 480
PROTOCOL = 'robocasa-limited-v2'
SCHEMA = 'rcb-casa-limited-actuators-v2'
ROBOT_JOINTS = ('right_j0', 'right_j1', 'right_j2', 'right_j3', 'right_j4', 'right_j5', 'right_j6', 'r_close', 'l_close')


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    def plain(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=plain, allow_nan=False)


class Service:
    def __init__(self, instance='/private/instance.npz'):
        ROOT.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.backend = Backend(Path(instance).parent)
        self.session = self.backend.session
        m = self.backend.model
        self.cameras = self.backend.cameras
        if not self.cameras: raise RuntimeError('No native RGB camera available')
        self.rgb = mujoco.Renderer(m, HEIGHT, WIDTH)
        self.traces = []; self.completed = []
        self.actions = []
        self.physical_steps = 0
        self.active = self.ended = self.sealed = False
        self.agent_stopped = self.agent_timeout = False
        self.agent_stop_elapsed = self.agent_stopped_at = None
        self.online_success = False
        self.first_success_index = None
        self.reason = None
        self.start = self.started_at = self.ended_at = self.end_elapsed = None
        self.events = self.rejected = self.observations = 0
        self.initial_state_sha = self.backend.initial_sha
        self.event('ready', instance_sha=self.backend.instance_sha, initial_state_sha=self.initial_state_sha,
                   cameras=self.cameras)
        self.persist()

    def event(self, kind, **data):
        self.events += 1
        row = dict(sequence=self.events, at=utc(), elapsed=self.elapsed(), kind=kind, **data)
        with (ROOT / 'events.jsonl').open('a') as f:
            f.write(canonical(row) + '\n'); f.flush(); os.fsync(f.fileno())

    def elapsed(self):
        return time.monotonic() - self.start if self.start else 0.0

    def finish(self, reason):
        if not self.ended:
            self.ended = True; self.reason = reason; self.ended_at = utc(); self.end_elapsed = self.elapsed()
            self.event('episode_end', reason=reason, online_success=self.online_success)

    def deadline(self):
        if self.active and not self.agent_stopped and not self.agent_timeout and self.elapsed() >= LIMIT:
            self.agent_timeout = True
            if not self.ended: self.finish('timeout')
            else: self.event('agent_timeout')
            self.persist()

    def persist(self):
        value = dict(protocol=PROTOCOL, started_at=self.started_at, ended_at=self.ended_at,
                     agent_seconds=self.agent_stop_elapsed if self.agent_stopped else self.elapsed(), limit_seconds=LIMIT,
                     episode_seconds=self.end_elapsed if self.ended else self.elapsed(),
                     agent_stopped=self.agent_stopped,agent_stopped_at=self.agent_stopped_at,agent_timeout=self.agent_timeout,
                     ready=True, activated=self.active, active=self.active and not self.ended, ended=self.ended, sealed=self.sealed,
                     termination_reason='timeout' if self.agent_timeout else self.reason,
                     episode_termination_reason=self.reason, online_success=self.online_success,
                     first_success_index=self.first_success_index, n_actions=len(self.actions),
                     completed_controls=self.backend.completed, physics_steps=self.physical_steps,
                     control_dt=float(1/self.backend.env.control_freq),
                     frame_skip=self.backend.nsub, max_actions=self.backend.cap, resets=0, initializations=1,
                     rejected_calls=self.rejected, observations=self.observations, events=self.events,
                     initial_state_sha=self.initial_state_sha, instance_sha=self.backend.instance_sha)
        temp = ROOT / 'episode.tmp'; temp.write_text(canonical(value) + '\n'); temp.replace(ROOT / 'episode.json')
        return value

    def robot(self):
        return self.backend.robot()

    def calibration(self, camera):
        m, d = self.backend.model, self.backend.data
        c = m.camera(camera).id
        f = 0.5 * HEIGHT / np.tan(np.deg2rad(m.cam_fovy[c]) / 2)
        intrinsic = np.array([[f, 0, WIDTH / 2], [0, f, HEIGHT / 2], [0, 0, 1.0]])
        # MuJoCo camera frame looks along -Z with +Y up; report the OpenCV optical frame.
        rotation = d.cam_xmat[c].reshape(3, 3) @ np.diag([1.0, -1.0, -1.0])
        pose = np.eye(4); pose[:3, :3] = rotation; pose[:3, 3] = d.cam_xpos[c]
        return intrinsic, pose

    def status(self):
        return dict(active=self.active and not self.ended, ended=self.ended, actions=len(self.actions),
                    max_actions=self.backend.cap, physics_steps=self.physical_steps,
                    remaining_seconds=max(0.0, LIMIT - (self.agent_stop_elapsed if self.agent_stopped else self.elapsed())) if self.active else LIMIT)

    def spec(self):
        return dict(self.backend.spec, instruction=self.backend.language, protocol=PROTOCOL, cameras=self.cameras, width=WIDTH,height=HEIGHT,
                    physics_timestep=float(self.backend.model.opt.timestep),physics_steps_per_control=self.backend.nsub,
                    max_actions=self.backend.cap,agent_seconds=LIMIT)

    def observe(self, camera):
        d = self.backend.data
        self.rgb.update_scene(d, camera=camera); rgb = self.rgb.render().copy()
        intrinsic, pose = self.calibration(camera)
        buff = io.BytesIO()
        np.savez_compressed(buff, rgb=rgb, intrinsic=intrinsic, camera_to_world=pose)
        return dict(npz_base64=base64.b64encode(buff.getvalue()).decode(), robot=self.robot(), camera=camera)

    def dispatch(self, path, body):
        with self.lock:
            self.deadline()
            if path == '/v1/spec' and body == {}:
                return self.spec()
            if path == '/v1/status' and body == {}:
                return self.status()
            if path == '/v1/observe' and set(body) == {'camera'}:
                camera = body['camera']
                if type(camera) is not str or camera not in self.cameras: raise ValueError()
                value = self.observe(camera)
                self.observations += 1
                self.event('observation', camera=camera, physics_steps=0)
                return value
            if path == '/v1/step' and set(body) == {'action'}:
                if not self.active or self.ended or self.sealed: raise ValueError()
                a = self.backend.validate(body['action'])
                if len(self.actions) >= self.backend.cap: raise ValueError()
                s = self.backend; data = s.data
                # Journal the attempted control BEFORE physics, including one that fails.
                self.actions.append(a.copy())
                index = len(self.actions) - 1
                before = float(data.time)
                self.event('action_begin', index=index, action=a, physics_time=before)
                try:
                    info = s.step(a)
                    if bool(info['success']) and not self.online_success:
                        self.online_success = True; self.first_success_index = index
                    if self.elapsed() >= LIMIT: self.finish('timeout')
                    elif self.online_success: self.finish('native_success')
                    elif info['done'] or len(self.actions) >= self.backend.cap: self.finish('episode_horizon')
                except Exception as exc:
                    self.event('simulation_error', error_type=type(exc).__name__, error=str(exc))
                    traceback.print_exc()
                    self.finish('simulation_failure')
                finally:
                    # Count actual native physics calls, even if a numerical
                    # failure made MuJoCo's clock jump back to zero.
                    advanced = len(s.frame)
                    self.physical_steps += advanced
                    self.traces.append(np.asarray(s.frame,dtype=np.float64).reshape(-1,s.model.nu))
                    self.completed.append(s.completed > sum(self.completed))
                    self.event('action_end', index=index, physics_steps=advanced, physics_time=float(data.time),
                               completed_controls=s.completed)
                    self.persist()
                return self.status()
            raise ValueError()

    def admin(self, command):
        with self.lock:
            if command == 'start':
                if self.active or self.sealed or self.agent_stopped: raise ValueError('episode already started')
                self.start = time.monotonic(); self.started_at = utc(); self.active = True
                self.event('agent_start'); self.persist()
                return {'started': True}
            if command == 'stop':
                self.deadline()
                if not self.agent_stopped:
                    self.agent_stop_elapsed = self.elapsed(); self.agent_stopped_at = utc(); self.agent_stopped = True
                    self.agent_timeout |= self.active and self.agent_stop_elapsed >= LIMIT
                    if not self.ended: self.finish('agent_stopped')
                    self.event('agent_stop'); self.persist()
                return {'stopped': True}
            if command == 'seal':
                self.admin('stop')
                if not self.sealed:
                    s = self.backend
                    lengths=[len(t) for t in self.traces]
                    np.savez_compressed(ROOT/'trajectory.npz',actions=np.asarray(self.actions,dtype=np.float64).reshape(-1,s.dim),
                        actuator_controls=np.concatenate(self.traces) if self.traces else np.empty((0,s.model.nu)),
                        offsets=np.r_[0,np.cumsum(lengths,dtype=np.int64)],completed=np.asarray(self.completed,dtype=bool),
                        instance_sha=np.array(s.instance_sha),schema=np.array(SCHEMA))
                    np.savez_compressed(ROOT/'online.state.npz',integration=s.state())
                    (ROOT/'online.json').write_text(canonical(s.result())+'\n')
                    self.sealed = True; self.event('sealed', n_actions=len(self.actions)); self.persist()
                return {'sealed': True}
            raise ValueError('unsupported management command')


class Handler(BaseHTTPRequestHandler):
    server_version = 'LimitedAPI'; sys_version = ''
    def log_message(self, *args): pass
    def do_POST(self):
        self.connection.settimeout(10)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'): raise ValueError()
            body = json.loads(self.rfile.read(size), parse_constant=lambda x: (_ for _ in ()).throw(ValueError()))
            if not isinstance(body, dict): raise ValueError()
            value = self.server.service.dispatch(self.path, body); code = 200
        except Exception:
            with self.server.service.lock:
                self.server.service.rejected += 1
                self.server.service.event('request_rejected', physics_steps=0)
                self.server.service.persist()
            value = {'error': 'request_rejected'}; code = 400
        raw = canonical(value).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw))); self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_GET(self):
        self.send_response(405); self.send_header('Content-Length', '0'); self.end_headers()


class Admin(socketserver.StreamRequestHandler):
    def handle(self):
        try: value = self.server.service.admin(self.rfile.readline(100).decode().strip())
        except Exception: value = {'error': 'rejected'}
        self.wfile.write((canonical(value) + '\n').encode())


if __name__ == '__main__':
    service = Service()
    admin = socketserver.UnixStreamServer('/run/limited/control.sock', Admin); admin.service = service
    threading.Thread(target=admin.serve_forever, daemon=True).start()
    def timer():
        while True:
            time.sleep(0.1)
            with service.lock: service.deadline()
    threading.Thread(target=timer, daemon=True).start()
    http = HTTPServer(('0.0.0.0', 8000), Handler); http.service = service
    http.serve_forever()
