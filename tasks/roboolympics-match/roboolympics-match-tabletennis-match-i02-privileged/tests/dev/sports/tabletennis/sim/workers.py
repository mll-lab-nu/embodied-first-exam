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
    """Prepare a contact configuration (the duel's high level, off the world lock): the base's goal (the act's `base`,
    else the stance rule) as far as the base can reach it by the contact, and the arm's IK there. The trajectory start
    is deliberately NOT baked in (workers.trajectory builds it at the effect boundary)."""
    import duel
    import rally
    import rcb_tt
    from rally import ARM_VEL
    dec = job['decision']
    pl.s.d.qpos[pl.s._qadr] = np.asarray(job['q'], float)
    pl.s._target = np.asarray(job['target'], float)
    prev = np.asarray(job.get('prev', job['target']), float)
    prev2 = np.asarray(job['prev2'], float) if job.get('prev2') is not None else 2 * prev - pl.s._target   # (a = 0)
    pl.s._actions = [prev2, prev, pl.s._target.copy()]
    pos, normal, vel = (np.asarray(dec[k], float) for k in ('pos', 'normal', 'vel'))
    normal = normal / np.linalg.norm(normal)
    role = 0 if pl.side == duel.FIRST_SERVER else 1
    rng = np.random.default_rng([duel.SEED, role, job['point'], job['ordinal']])
    if os.environ.get('DUEL_SCATTER', '1') == '1':   # the execution scatter, as match.PADDLE_SCATTER (1 cm, 1.5 deg, 5 %; revision 11)
        pos = pos + rng.normal(0, .01, 3)
        axis = np.cross(normal, rng.normal(size=3))
        axis /= max(np.linalg.norm(axis), 1e-12)
        angle = np.radians(rng.normal(0, 1.5))
        normal = normal*np.cos(angle) + np.cross(axis, normal)*np.sin(angle)
        normal /= np.linalg.norm(normal)
        vel = vel * (1 + rng.normal(0, .05))
    n = max(1, int(np.ceil(float(dec['t'])/rcb_tt.CONTROL_DT)))
    goal, short, _ = pl.base_plan(pos, dec.get('base'), n)
    if rally.PLANNER != 'hermite':
        last = getattr(pl, '_last_contact', None)   # a re-plan of the same ball: correct the last contact state
        prev = last[1] if (last is not None and last[0] == (job['point'], job.get('ball'))) else None
        q, qd, error = pl._contact_state(pos, normal, vel, goal, n, prev, pl._arm_inertia(pl.s._target[2:], goal),
                                         serve=bool(job.get('serving')))
        pl._last_contact = ((job['point'], job.get('ball')), (q.copy(), qd.copy()))
    else:
        q, error = pl._ik_best(pos, normal, None, goal)
        jac = pl.s.jacobian(np.r_[goal, q])[:3, 2:]
        weight = np.diag(ARM_VEL**2)
        qd = weight @ jac.T @ np.linalg.solve(jac @ weight @ jac.T + 1e-8*np.eye(3), vel)
    M_c = pl._arm_inertia(q, goal)
    scale = rally.contact_prescale(float(np.max(np.abs(qd)/ARM_VEL)))   # as match.plan_paddle (revision 14/11)
    import rally
    vias = []                                      # pre-contact poses for table avoidance (used if the path dips)
    for dz in rally.VIA_DZ:
        q_pre, r_pre = pl._ik(rally.via_pose(pos, vel, normal, dz), normal, q, goal)
        if r_pre <= 1e-3:
            vias.append((dz, q_pre))
    return dict(q=q, qd=qd/scale, ik_residual=float(error), speed_scale=scale, base_goal=goal.tolist(),
                base_short_m=round(short, 3), vias=vias, M=M_c)


_CHECK = []


def _check_session():
    """A single-robot simulator for the kinematic table check of the duel's swings (the seat's own frame)."""
    if not _CHECK:
        import rally
        import rcb_tt
        _CHECK.append(rcb_tt.Session(instance=str(rally.INSTANCE), scene=str(rally.SCENE)))
    return _CHECK[0]


def trajectory(target, previous, prepared, T, low, high, serve=False, acc=None):
    """Cheap trajectory construction from the latest command at the effective boundary: the base's go-to trajectory
    to the prepared goal and the arm's cubic swing to the prepared contact configuration, as 9-joint rows."""
    import rcb_tt
    from rally import hermite, CONTROL_DT, VEL_LIMIT
    import rally
    start = np.asarray(target, float)
    speed = (start - np.asarray(previous, float))/CONTROL_DT
    acc0 = np.zeros(rcb_tt.NQ) if acc is None else np.asarray(acc, float)     # the targets' acceleration now
    goal, velocity = prepared['q'], prepared['qd']
    n = max(1, int(np.ceil(T/CONTROL_DT)))
    base_rows, _ = rcb_tt.base_plan(start[:2], speed[:2], prepared.get('base_goal', start[:2]), n + 25, a=acc0[:2])
    follow = hermite(goal, velocity, goal + velocity*.125, np.zeros(7), .25, 25)

    def build(via):
        nf = rally.VIA_STEPS
        if via is not None and n - nf >= 8:
            qd_pre = (goal - via) / (nf * CONTROL_DT)
            qd_pre = qd_pre / max(1.0, float(np.max(np.abs(qd_pre) / rally.ARM_VEL)) / 0.95)
            path = np.vstack([hermite(start[2:], speed[2:], via, qd_pre, (n - nf)*CONTROL_DT, n - nf),
                              hermite(via, qd_pre, goal, velocity, nf*CONTROL_DT, nf)])
        else:
            path = hermite(start[2:], speed[2:], goal, velocity, n*CONTROL_DT, n)
        out, prev, clipped = [], start, 0
        for i, qa in enumerate(np.concatenate((path, follow))):
            desired = np.clip(np.r_[base_rows[i], qa], low+1e-4, high-1e-4)
            q = prev + np.clip(desired-prev, -VEL_LIMIT*CONTROL_DT*.999, VEL_LIMIT*CONTROL_DT*.999)
            clipped += int(np.max(np.abs(q-desired)) > 1e-8)
            out.append(q); prev = q
        return out, clipped
    if rally.PLANNER != "hermite":                 # the limits-aware planner (rally.stroke_rows)
        acc = acc0
        def build(via):
            cs = _check_session()
            Ms = [prepared['M']] if prepared.get('M') is not None else []
            Ms += [rally.arm_inertia(cs, start), rally.arm_inertia(cs, np.r_[start[:2], 0.5 * (start[2:] + goal)])]
            rows, si = rally.stroke_rows(start, speed, acc, goal, velocity, n, base_rows, low + 1e-4, high - 1e-4,
                                         via=via, n_follow=25, M=Ms, serve=serve)
            build.info = si
            return rows, 0
    out, clipped = build(None)
    approach = "direct"
    if prepared.get('vias') and rally.touches_table(_check_session(), out[:n]):
        approach = "direct (touches the table)"
        for dz, q_pre in prepared['vias']:
            cand, cl = build(np.asarray(q_pre, float))
            if not rally.touches_table(_check_session(), cand[:n]):
                out, clipped, approach = cand, cl, f"from above (+{dz:.2f} m) to clear the table"
                break
    extra = dict(getattr(build, 'info', None) or {})
    return out, dict(contact_steps=n, joint_limited_steps=clipped, approach=approach, **extra,
                     contact_joint_error=float(np.max(np.abs(out[n-1][2:]-goal))),
                     base_goal=[round(float(x), 4) for x in prepared.get('base_goal', start[:2])])


VEL_WEIGHT = float(os.environ.get('RCB_TT_KEEP_VW', '0.3'))   # s: 1 m/s of paddle velocity error ~ 30 cm of position


def keep_better(new_rows, info, old_rows, dec):
    """The limits-aware planner's re-plan rule: a late re-plan the arm cannot follow can be worse than the trajectory
    in force. Both are scored at the new contact step by the paddle's predicted miss (forward kinematics of the rows:
    position error + VEL_WEIGHT x velocity error against the act) and the better one is kept (info["kept"])."""
    import rally
    if rally.PLANNER == 'hermite' or not old_rows:
        return new_rows, info
    n = int(info['contact_steps'])
    if len(old_rows) < n + 1:
        return new_rows, info
    s = _check_session()
    pos, vel = np.asarray(dec['pos'], float), np.asarray(dec['vel'], float)

    def score(rows):
        q1, q0 = np.asarray(rows[n - 1], float), np.asarray(rows[n - 2], float)
        p1, _ = s.fk(q1)
        p0, _ = s.fk(q0)
        v = (p1 - p0) / rally.CONTROL_DT
        return float(np.linalg.norm(p1 - pos) + VEL_WEIGHT * np.linalg.norm(v - vel))
    s_new, s_old = score(new_rows), score(old_rows)
    info = dict(info, score_new=round(s_new, 4), score_old=round(s_old, 4))
    if s_old + 0.002 < s_new:
        return [np.asarray(q, float) for q in old_rows], dict(info, kept="the trajectory in force (a better contact)")
    return new_rows, info


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
