"""wuji_gen.py - produce the Wuji Hand 2.2 trajectory for essential_cube_reorient (privileged mode).

Physics-shooting (CEM) controller: forecasts run on separate MjData copies of the task's own model; only legal Wuji
finger position targets (the six wrist targets stay at the locked pose) are executed in the task's Session, whose
checker decides the stages. No object state, force, weld or predicate is ever written.

The accepted trajectory was made in two phases (both deterministic: fixed NumPy seeds, deterministic MuJoCo):
  A. score version 1, seed 1, horizon 60 substeps, sigma 0.08, from reset, first 53 rows (stage 1 completes at row 53);
  B. score version 2, seed 12, horizon 150, sigma 0.12, 40 samples, error-free band 0.07, pad-force weight 0.1,
     displacement weight 0.5, resumed after those 53 rows, until the checker reports success (row 165).
Usage: python wuji_gen.py [--tools <task>/environment] [--out <file>]   (~3.5 min on one CPU core; rewrites
../solution/wuji/trajectory.npz byte for byte)
"""
import os, sys, json, math, time, argparse, shutil, tempfile
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1'); os.environ.setdefault('OMP_NUM_THREADS', '1')
_pre = argparse.ArgumentParser(add_help=False); _pre.add_argument('--tools', default=os.environ.get('RCB_TOOLS', '/opt/tools'))
_known, _ = _pre.parse_known_args()
sys.path.insert(0, _known.tools)
import numpy as np, mujoco
from scipy.spatial.transform import Rotation
from rcb_dexhand import Session
from essential_inhand import PALM_AXES


class harness:
    """Session factory (the Wuji hand) and short actuator names -> row index."""
    J = {}

    @staticmethod
    def make_session():
        s = Session("essential_cube_reorient", hand="wuji")
        for i, n in enumerate(s.actuator_names):
            harness.J[n.replace('r_wuji_r_', '')] = i
        return s


def angle(R):
    return math.acos(float(np.clip((np.trace(R) - 1) / 2, -1, 1)))

def run(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--samples', type=int, default=40); ap.add_argument('--gens', type=int, default=2)
    ap.add_argument('--horizon', type=int, default=60); ap.add_argument('--apply', type=int, default=2)
    ap.add_argument('--iters', type=int, default=600); ap.add_argument('--sigma', type=float, default=0.08)
    ap.add_argument('--maxdelta', type=float, default=0.15); ap.add_argument('--wtip', type=float, default=0.3)
    ap.add_argument('--wdist', type=float, default=4.0); ap.add_argument('--resume'); ap.add_argument('--resume-steps', type=int)
    ap.add_argument('--joints', default='all'); ap.add_argument('--wdisp', type=float, default=2.0)
    ap.add_argument('--hint', type=int, default=0); ap.add_argument('--v1', action='store_true')
    ap.add_argument('--errfree', type=float, default=0.0); ap.add_argument('--wforce', type=float, default=0.0)
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    s = harness.make_session(); m, d = s.model, s.data
    rng = np.random.default_rng(args.seed)
    lo, hi = m.actuator_ctrlrange.T
    if args.joints == 'all': active = np.arange(6, 26)
    else: active = np.array([harness.J[j] for j in args.joints.split(',')])
    obj = m.body('object').id; og = m.geom('task_object').id
    palm_id = m.body('right_hand_C_MC').id
    hand_geoms = set()
    for g in range(m.ngeom):
        b = int(m.geom_bodyid[g])
        while b and b != palm_id: b = int(m.body_parentid[b])
        if b == palm_id: hand_geoms.add(g)
    pads = {f: m.geom(f'right_{f}_fingertip_collision').id for f in ['thumb', 'index', 'middle', 'ring', 'pinky']}
    pad_set = set(pads.values())
    frame = d.body('right_hand_C_MC').xmat.reshape(3, 3) @ PALM_AXES
    initial = d.body('object').xmat.reshape(3, 3).copy(); center = d.body('object').xpos.copy()
    first = Rotation.from_rotvec([0, math.pi / 2, 0]).as_matrix(); second = Rotation.from_rotvec([math.pi / 2, 0, 0]).as_matrix() @ first
    goals = [frame @ r @ frame.T @ initial for r in [first, second, np.eye(3)]]
    rel0 = frame.T @ (center - d.body('right_hand_C_MC').xpos)
    forecast = mujoco.MjData(m); flags = mujoco.mjtState.mjSTATE_INTEGRATION; state = np.empty(mujoco.mj_stateSize(m, flags))
    wrench = np.zeros(6)
    actions = []
    if args.resume:
        prefix = np.load(args.resume)['actions']
        if args.resume_steps: prefix = prefix[:args.resume_steps]
        for r in prefix:
            s.step(r); actions.append(r.copy())
            if s.status()['done']: break
    last = s.hold_action() if not actions else actions[-1].copy()
    tdofs = s._task_dofs

    def tip_forces(D):
        F = {}
        for i in range(D.ncon):
            c = D.contact[i]; g1, g2 = int(c.geom1), int(c.geom2)
            if og not in (g1, g2): continue
            other = g2 if g1 == og else g1
            if other in pad_set:
                mujoco.mj_contactForce(m, D, i, wrench); F[other] = F.get(other, 0) + float(np.linalg.norm(wrench[:3]))
        return sorted(F.values(), reverse=True) + [0.0, 0.0]

    def contacts(D):
        hand = 0; tips = set(); support = 0
        for i in range(D.ncon):
            c = D.contact[i]; g1, g2 = int(c.geom1), int(c.geom2)
            if og not in (g1, g2): continue
            other = g2 if g1 == og else g1
            mujoco.mj_contactForce(m, D, i, wrench); fn = np.linalg.norm(wrench[:3])
            if int(m.geom_bodyid[other]) == 0 and fn > 0.01: support += 1
            if other in hand_geoms and fn > 0.005: hand += 1
            if other in pad_set and fn > 0.01: tips.add(other)
        return hand, len(tips), support

    def score_v1(action, goal, stage):
        # First version (used for the first 53 rows of the accepted trajectory, run m1): contacts every 5 substeps.
        mujoco.mj_setState(m, forecast, state, flags); forecast.ctrl[:] = action
        maxspeed = 0.0; mintips = 9
        for k in range(args.horizon):
            mujoco.mj_step(m, forecast)
            sp = float(np.max(np.abs(forecast.qvel[tdofs])))
            maxspeed = max(maxspeed, sp)
            if maxspeed > 11: return 1e3 + maxspeed
            if k % 5 == 4 or k == args.horizon - 1:
                mujoco.mj_forward(m, forecast)
                hand, tips, support = contacts(forecast)
                if hand == 0 or support: return 1e3
                mintips = min(mintips, tips)
        R = forecast.xmat[obj].reshape(3, 3)
        err = angle(goal @ R.T)
        pal = forecast.xpos[palm_id]; disp = float(np.linalg.norm(frame.T @ (forecast.xpos[obj] - pal) - rel0))
        if disp > 0.062: return 1e3 + disp
        dists = sorted(mujoco.mj_geomDistance(m, forecast, g, og, 0.1, None) for g in pads.values())
        endspeed = float(np.linalg.norm(forecast.qvel[tdofs]))
        c = err + args.wtip * max(0, 2 - tips) + args.wdist * (max(0, dists[0]) + max(0, dists[1])) + args.wdisp * disp
        c += 0.01 * maxspeed + (0.3 if stage >= 3 else 0.05) * endspeed + 0.1 * max(0, tips - 4)
        return c

    def score(action, goal, stage):
        if args.v1: return score_v1(action, goal, stage)
        mujoco.mj_setState(m, forecast, state, flags); forecast.ctrl[:] = action
        maxspeed = 0.0; mintips = 9
        for k in range(args.horizon):
            mujoco.mj_step(m, forecast)
            sp = float(np.max(np.abs(forecast.qvel[tdofs])))
            maxspeed = max(maxspeed, sp)
            if maxspeed > 11: return 1e3 + maxspeed
            # contact data left by mj_step = the previous substep's post-step state (checked at every substep)
            hand, tips, support = contacts(forecast)
            if hand == 0 or support: return 1e3 + (args.horizon - k)
            if k % 5 == 4: mintips = min(mintips, tips)
        mujoco.mj_forward(m, forecast)
        hand, tips, support = contacts(forecast)
        if hand == 0 or support: return 1e3
        R = forecast.xmat[obj].reshape(3, 3)
        err = angle(goal @ R.T)
        pal = forecast.xpos[palm_id]; disp = float(np.linalg.norm(frame.T @ (forecast.xpos[obj] - pal) - rel0))
        if disp > 0.062: return 1e3 + disp
        dists = sorted(mujoco.mj_geomDistance(m, forecast, g, og, 0.1, None) for g in pads.values())
        endspeed = float(np.linalg.norm(forecast.qvel[tdofs]))
        tf = tip_forces(forecast)
        c = max(0.0, err - args.errfree) + args.wtip * max(0, 2 - tips) + args.wdist * (max(0, dists[0] + 0.0005) + max(0, dists[1] + 0.0005)) + args.wdisp * disp
        c += args.wforce * (max(0, 0.03 - tf[0]) + max(0, 0.03 - tf[1])) / 0.03
        c += 0.01 * maxspeed + (0.3 if stage >= 3 else 0.05) * endspeed + 0.1 * max(0, tips - 4)
        return c

    finger_idx = {f: [harness.J[pre + 'J%d' % k] for k in range(4)] for f, pre in
                  [('thumb', 'TH'), ('index', 'FF'), ('middle', 'MF'), ('ring', 'RF'), ('pinky', 'LF')]}
    jacp = np.zeros((3, m.nv)); fromto = np.zeros(6)

    def hint(goal, angle_step, near=0.006):
        # Fingers near the sphere follow their contact points through a small rotation toward the goal.
        R = d.xmat[obj].reshape(3, 3); c = d.xpos[obj].copy()
        rv = Rotation.from_matrix(goal @ R.T).as_rotvec(); n = np.linalg.norm(rv)
        if n < 1e-6: return None
        dR = Rotation.from_rotvec(rv / n * min(angle_step, n)).as_matrix()
        dq = np.zeros(m.nu)
        for f, gid in pads.items():
            dist = mujoco.mj_geomDistance(m, d, gid, og, 0.05, fromto)
            if dist > near: continue
            p = fromto[3:]; target = c + dR @ (p - c); delta = target - p
            mujoco.mj_jacGeom(m, d, jacp, None, gid)
            idx = finger_idx[f]; cols = m.jnt_dofadr[s._act_jids[idx]]
            Jf = jacp[:, cols]
            dq[idx] = Jf.T @ np.linalg.solve(Jf @ Jf.T + 1e-4 * np.eye(3), delta)
        return dq[active]

    began = time.time(); best_delta = np.zeros(len(active))
    log = open(os.path.join(args.out, 'log.jsonl'), 'a')
    for it in range(args.iters):
        st = s.status()
        if st['done']: break
        stage = s.checker.stage_index; goal = goals[min(stage, 2)]
        active_check = s.checker.stages[stage] if stage < len(s.checker.stages) else s.checker.terminal
        f = s.features()
        hold_bounds = {k: v for k, v in active_check['bounds'].items() if k != 'speed'}
        hold = s.checker._matches(f, hold_bounds) and (stage < 3 or f['speed'] < 0.2)
        if hold:
            s.step(last); actions.append(last.copy())
            continue
        mujoco.mj_getState(m, d, state, flags)
        base = last.copy(); mean = best_delta * 0.6; sigma = np.full(len(active), args.sigma)
        best = base.copy(); best_score = score(best, goal, stage)
        for gen in range(args.gens):
            deltas = rng.normal(mean, sigma, size=(args.samples, len(active))); deltas[0] = 0; deltas[1] = mean
            if args.hint and gen == 0:
                for j, step in enumerate((0.05, 0.1, 0.2, 0.35)):
                    h = hint(goal, step)
                    if h is not None: deltas[2 + j] = h
            cands = []
            for delta in deltas:
                a = base.copy(); a[active] = np.clip(base[active] + np.clip(delta, -args.maxdelta, args.maxdelta), lo[active], hi[active])
                v = score(a, goal, stage); cands.append((v, a, delta))
                if v < best_score: best_score = v; best = a
            cands.sort(key=lambda x: x[0]); el = cands[:max(4, args.samples // 6)]
            mean = np.mean([e[2] for e in el], 0); sigma = np.maximum(np.std([e[2] for e in el], 0), 0.01)
        best_delta = best[active] - base[active]; last = best
        for _ in range(args.apply):
            s.step(best); actions.append(best.copy())
            if s.status()['done']: break
        if it % 10 == 0 or s.status()['done'] or s.checker.stage_index != stage:
            f = s.features(); st = s.status()
            rec = dict(it=it, steps=st['steps'], t=round(time.time() - began, 1), score=round(best_score, 3), stage=s.checker.stage_index,
                       e=[round(f['cube_error_%d' % k], 3) for k in (1, 2, 3)], tips=f['contacts'], hc=f['object_hand_contacts'],
                       sp=round(f['speed'], 3), disp=round(f['object_displacement'], 4), reason=st['reason'])
            print(json.dumps(rec), flush=True); log.write(json.dumps(rec) + '\n'); log.flush()
        if it % 20 == 0: s.save_trajectory(np.array(actions), os.path.join(args.out, 'traj.npz'))
    s.save_trajectory(np.array(actions), os.path.join(args.out, 'traj.npz'))
    st = s.status(); print('FINAL', json.dumps({k: st[k] for k in ('success', 'stage', 'steps', 'reason', 'state_sha')}), flush=True)
    json.dump({k: st[k] for k in ('success', 'stage', 'steps', 'reason', 'state_sha')}, open(os.path.join(args.out, 'final.json'), 'w'))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tools', default=_known.tools)
    ap.add_argument('--out', default='/app/output/trajectory.npz'); ap.add_argument('--workdir')
    a = ap.parse_args()
    work = a.workdir or tempfile.mkdtemp(prefix='cube_reorient_gen_')
    phase_a = os.path.join(work, 'A'); phase_b = os.path.join(work, 'B')
    run(['--v1', '--out', phase_a, '--seed', '1', '--horizon', '60', '--sigma', '0.08', '--iters', '30'])
    run(['--out', phase_b, '--resume', os.path.join(phase_a, 'traj.npz'), '--resume-steps', '53', '--seed', '12',
         '--horizon', '150', '--sigma', '0.12', '--samples', '40', '--errfree', '0.07', '--wforce', '0.1', '--wdisp', '0.5'])
    with np.load(os.path.join(phase_b, 'traj.npz'), allow_pickle=False) as z:
        rows = np.asarray(z['actions'], dtype=np.float64)
    s = harness.make_session(); status = s.replay(rows)
    print('replay', json.dumps({k: status[k] for k in ('success', 'stage', 'steps', 'reason', 'state_sha')}), flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    s.save_trajectory(rows, a.out)
    print('saved', len(rows), 'wuji rows to', a.out)


if __name__ == '__main__':
    main()
