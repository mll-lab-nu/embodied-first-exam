"""Private single-episode Meta-World service: spec/observe/step/status only; no reset.

Runs in the sim sidecar as an unprivileged user. The accepted privileged runtime
(`mw_runtime.py`, byte-identical to the verifier copy) restores the frozen instance
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
from mw_runtime import Session, MAX_ACTIONS, integration, snapshot
from archive import digest

ROOT = Path('/recorded')
LIMIT = 3600.0
WIDTH = HEIGHT = 480
PROTOCOL = 'metaworldplus-limited-v1'
SCHEMA = 'rcb-metaworldplus-limited-controls-v1'
ROBOT_JOINTS = ('right_j0', 'right_j1', 'right_j2', 'right_j3', 'right_j4', 'right_j5', 'right_j6', 'r_close', 'l_close')


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    def plain(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=plain, allow_nan=False)


from episode_clock import AgentClock

class Service(AgentClock):
    def __init__(self, instance='/private/instance.npz'):
        ROOT.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.session = Session(instance, budget_path=None)
        env = self.session.env
        m = env.model
        if env.max_path_length != MAX_ACTIONS or env.frame_skip != 5 or abs(m.opt.timestep - 0.0025) > 1e-12:
            raise RuntimeError('Unexpected native horizon/control period; explicit adaptation required')
        self.cameras = [m.camera(i).name for i in range(m.ncam)]
        self.joint_ids = [m.joint(name).id for name in ROBOT_JOINTS]
        self.rgb = mujoco.Renderer(m, HEIGHT, WIDTH)
        self.depth = mujoco.Renderer(m, HEIGHT, WIDTH)
        self.depth.enable_depth_rendering()
        self.actions = []
        self.physical_steps = 0
        self.active = self.ended = self.sealed = False
        self.online_success = False
        self.first_success_index = None
        self.reason = None
        self.start = self.started_at = self.ended_at = self.end_elapsed = None
        self.events = self.rejected = self.observations = 0
        self.initial_state_sha = digest(snapshot(env))
        self.event('ready', instance_sha=self.session.instance_sha, initial_state_sha=self.initial_state_sha,
                   cameras=self.cameras)
        self.init_agent_clock()
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


    def persist(self):
        value = dict(protocol=PROTOCOL, started_at=self.started_at, ended_at=self.ended_at,
                     agent_seconds=self.end_elapsed if self.ended else self.elapsed(), limit_seconds=LIMIT,
                     ready=True, activated=self.active, active=self.active and not self.ended, ended=self.ended, sealed=self.sealed,
                     termination_reason=self.reason, online_success=self.online_success,
                     first_success_index=self.first_success_index, n_actions=len(self.actions),
                     completed_controls=len(self.session.actions), physics_steps=self.physical_steps,
                     control_dt=float(self.session.env.model.opt.timestep * self.session.env.frame_skip),
                     frame_skip=self.session.env.frame_skip, max_actions=MAX_ACTIONS, resets=0, initializations=1,
                     rejected_calls=self.rejected, observations=self.observations, events=self.events,
                     initial_state_sha=self.initial_state_sha, instance_sha=self.session.instance_sha)
        value.update(self.agent_clock_fields())
        temp = ROOT / 'episode.tmp'; temp.write_text(canonical(value) + '\n'); temp.replace(ROOT / 'episode.json')
        return value

    def robot(self):
        e = self.session.env; m, d = e.model, e.data
        qpos = [float(d.qpos[m.jnt_qposadr[j]]) for j in self.joint_ids]
        qvel = [float(d.qvel[m.jnt_dofadr[j]]) for j in self.joint_ids]
        right, left = d.body('rightclaw').xpos, d.body('leftclaw').xpos
        return dict(joint_names=list(ROBOT_JOINTS), joint_positions=qpos, joint_velocities=qvel,
                    hand_position=d.body('hand').xpos.tolist(), hand_quaternion_wxyz=d.body('hand').xquat.tolist(),
                    tcp_position=np.asarray(e.tcp_center).tolist(),
                    gripper_opening=float(np.clip(np.linalg.norm(right - left) / 0.1, 0.0, 1.0)),
                    mocap_target_position=d.mocap_pos[0].tolist())

    def calibration(self, camera):
        m, d = self.session.env.model, self.session.env.data
        c = m.camera(camera).id
        f = 0.5 * HEIGHT / np.tan(np.deg2rad(m.cam_fovy[c]) / 2)
        intrinsic = np.array([[f, 0, WIDTH / 2], [0, f, HEIGHT / 2], [0, 0, 1.0]])
        # MuJoCo camera frame looks along -Z with +Y up; report the OpenCV optical frame.
        rotation = d.cam_xmat[c].reshape(3, 3) @ np.diag([1.0, -1.0, -1.0])
        pose = np.eye(4); pose[:3, :3] = rotation; pose[:3, 3] = d.cam_xpos[c]
        return intrinsic, pose

    def status(self):
        return dict(active=self.active and not self.ended, ended=self.ended, actions=len(self.actions),
                    max_actions=MAX_ACTIONS, physics_steps=self.physical_steps,
                    remaining_seconds=max(0.0, LIMIT - self.elapsed()) if self.active else LIMIT)

    def spec(self):
        e = self.session.env
        return dict(protocol=PROTOCOL, action_shape=[4], action_lower=[-1.0] * 4, action_upper=[1.0] * 4,
                    action_semantics='[dx, dy, dz, grip]: mocap XYZ displacement = clip(a,-1,1)*0.01 m per control '
                                     '(world frame, target clipped to mocap bounds); grip +1 closes, -1 opens',
                    action_scale_m=float(e.action_scale), mocap_lower=e.mocap_low.tolist(), mocap_upper=e.mocap_high.tolist(),
                    control_hz=float(1 / (e.model.opt.timestep * e.frame_skip)), physics_timestep=float(e.model.opt.timestep),
                    physics_steps_per_control=e.frame_skip, max_actions=MAX_ACTIONS, agent_seconds=LIMIT,
                    cameras=self.cameras, width=WIDTH, height=HEIGHT, world_frame='MuJoCo world, metres, +Z up')

    def observe(self, camera):
        d = self.session.env.data
        self.rgb.update_scene(d, camera=camera); rgb = self.rgb.render().copy()
        self.depth.update_scene(d, camera=camera); depth = self.depth.render().astype(np.float32)
        intrinsic, pose = self.calibration(camera)
        buff = io.BytesIO()
        np.savez_compressed(buff, rgb=rgb, depth_m=depth, intrinsic=intrinsic, camera_to_world=pose)
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
                raw = body['action']
                if not isinstance(raw, list) or len(raw) != 4 or any(type(x) not in (int, float) for x in raw): raise ValueError()
                a = np.asarray(raw, dtype=np.float64)
                if not np.isfinite(a).all() or np.any(np.abs(a) > 1): raise ValueError()
                if len(self.actions) >= MAX_ACTIONS: raise ValueError()
                s = self.session; data = s.env.data
                # Journal the attempted control BEFORE physics, including one that fails.
                self.actions.append(a.copy())
                index = len(self.actions) - 1
                before = float(data.time)
                self.event('action_begin', index=index, action=a, physics_time=before)
                try:
                    _, _, info = s.step(a)
                    if bool(info['success']) and not self.online_success:
                        self.online_success = True; self.first_success_index = index
                    if self.elapsed() >= LIMIT: self.finish('timeout')
                    elif self.online_success: self.finish('native_success')
                    elif len(self.actions) >= MAX_ACTIONS: self.finish('native_horizon')
                except Exception as exc:
                    self.event('simulation_error', error_type=type(exc).__name__, error=str(exc))
                    traceback.print_exc()
                    self.finish('simulation_failure')
                finally:
                    advanced = int(round((float(data.time) - before) / s.env.model.opt.timestep))
                    self.physical_steps += advanced
                    self.event('action_end', index=index, physics_steps=advanced, physics_time=float(data.time),
                               completed_controls=len(s.actions))
                    self.persist()
                return self.status()
            raise ValueError()

    def admin(self, command):
        with self.lock:
            if command == 'start':
                if self.active or self.sealed: raise ValueError('episode already started')
                self.start = time.monotonic(); self.started_at = utc(); self.active = True
                self.event('agent_start'); self.persist()
                return {'started': True}
            if command == 'stop': return self.stop_agent()
            if command == 'seal':
                self.stop_agent()
                self.deadline()
                if not self.ended: self.finish('agent_stopped')
                if not self.sealed:
                    s = self.session
                    np.savez_compressed(ROOT / 'trajectory.npz', actions=np.asarray(self.actions, dtype=np.float64).reshape(-1, 4),
                                        instance_sha=np.array(s.instance_sha), schema=np.array(SCHEMA))
                    np.savez_compressed(ROOT / 'online.state.npz', integration=integration(s.env))
                    try: (ROOT / 'online.json').write_text(canonical(s.result()) + '\n')
                    except Exception as exc: self.event('online_result_error', error_type=type(exc).__name__)
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
