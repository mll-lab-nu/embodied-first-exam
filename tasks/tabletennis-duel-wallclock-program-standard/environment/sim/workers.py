"""Bounded, per-seat planning/render processes. No worker owns the shared world."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
from ipc import _Conn

HERE = Path(__file__).resolve().parent


def affinity(name, all_threads=False):
    value = os.environ.get(name, "")
    if value:
        cpus = set()
        for part in value.split(','):
            ends = part.split('-')
            cpus.update(range(int(ends[0]), int(ends[-1]) + 1))
        if all_threads:
            # Mesa can override the inherited mask when it creates native threads.
            for path in Path('/proc/self/task').iterdir():
                try: os.sched_setaffinity(int(path.name), cpus)
                except ProcessLookupError: pass
        else:
            os.sched_setaffinity(0, cpus)


class ProcessWorker:
    def __init__(self, kind, side, timeout=30):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), kind, side],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=HERE)
        self.conn = _Conn(self.proc.stdout, self.proc.stdin)
        try:
            if self.conn.recv(time.monotonic() + timeout) != 'ready':
                raise RuntimeError('worker startup failed')
        except Exception:
            self.close()
            raise

    def call(self, payload):
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('one request per seat and worker may be in flight')
        try:
            deadline = time.monotonic() + self.timeout
            self.conn.send(payload, deadline)
            ok, value = self.conn.recv(deadline)
            if not ok:
                raise RuntimeError(value)
            return value
        except Exception:
            self.close()
            raise
        finally:
            self.lock.release()

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=1)
        self.proc.stdin.close(); self.proc.stdout.close()


def prepare(pl, job):
    """Prepare a contact configuration. The trajectory start is deliberately NOT baked in."""
    import duel
    from rally import VEL_LIMIT
    dec = job['decision']
    pl.s.d.qpos[pl.s._qadr] = np.asarray(job['q'], float)
    pl.s._target = np.asarray(job['target'], float)
    pos, normal, vel = (np.asarray(dec[k], float) for k in ('pos', 'normal', 'vel'))
    normal = normal / np.linalg.norm(normal)
    role = 0 if pl.side == duel.FIRST_RECEIVER else 1
    rng = np.random.default_rng([duel.SEED, role, job['point'], job['ordinal']])
    if os.environ.get('DUEL_SCATTER', '1') == '1':
        pos = pos + rng.normal(0, .004, 3)
        axis = np.cross(normal, rng.normal(size=3))
        axis /= max(np.linalg.norm(axis), 1e-12)
        angle = np.radians(rng.normal(0, .6))
        normal = normal*np.cos(angle) + np.cross(axis, normal)*np.sin(angle)
        normal /= np.linalg.norm(normal)
        vel = vel * (1 + rng.normal(0, .02))
    q, error = pl._ik_best(pos, normal)
    jac = pl.s.jacobian(q)[:3]
    weight = np.diag(VEL_LIMIT**2)
    qd = weight @ jac.T @ np.linalg.solve(jac @ weight @ jac.T + 1e-8*np.eye(3), vel)
    scale = max(1., float(np.max(np.abs(qd)/VEL_LIMIT))/.9)
    return dict(q=q, qd=qd/scale, ik_residual=float(error), speed_scale=scale)


def trajectory(target, previous, prepared, T, low, high):
    """Cheap trajectory construction from the latest command at the effective boundary."""
    from rally import hermite, CONTROL_DT, VEL_LIMIT
    start = np.asarray(target, float)
    speed = (start - np.asarray(previous, float))/CONTROL_DT
    goal, velocity = prepared['q'], prepared['qd']
    n = max(1, int(np.ceil(T/CONTROL_DT)))
    path = hermite(start, speed, goal, velocity, n*CONTROL_DT, n)
    follow = hermite(goal, velocity, goal + velocity*.125, np.zeros(7), .25, 25)
    out, prev, clipped = [], start, 0
    for q in np.concatenate((path, follow)):
        desired = np.clip(q, low+1e-4, high-1e-4)
        q = prev + np.clip(desired-prev, -VEL_LIMIT*CONTROL_DT*.999, VEL_LIMIT*CONTROL_DT*.999)
        clipped += int(np.max(np.abs(q-desired)) > 1e-8)
        out.append(q); prev = q
    return out, dict(contact_steps=n, joint_limited_steps=clipped,
                     contact_joint_error=float(np.max(np.abs(out[n-1]-goal))))


def main(kind, side):
    affinity(f'DUEL_{kind.upper()}_{side}_CPUS')
    import duel
    if kind == 'plan':
        obj = duel.Planner(side)
    elif kind == 'render':
        obj = duel.Duel()
        obj.render_views(side)  # create Mesa/LLVM threads before the ready handshake
    else:
        raise ValueError(kind)
    affinity(f'DUEL_{kind.upper()}_{side}_CPUS', all_threads=True)
    proto = os.fdopen(os.dup(1), 'wb')
    os.dup2(2, 1); sys.stdout = sys.stderr
    conn = _Conn(sys.stdin.buffer, proto)
    conn.send('ready')
    while True:
        try: job = conn.recv()
        except EOFError: return
        try:
            t0 = time.monotonic()
            affinity(f'DUEL_{kind.upper()}_{side}_CPUS', all_threads=True)
            if kind == 'plan':
                out = prepare(obj, job)
            else:
                obj.hist.clear(); obj.hist.extend(job['snapshots'])
                obj.rs.update(job['rs'])
                out = dict(png=obj.render_views(side))
            out['worker_s'] = time.monotonic()-t0
            conn.send((True, out))
        except Exception as exc:
            conn.send((False, repr(exc)))


if __name__ == '__main__':
    main(*sys.argv[1:])
