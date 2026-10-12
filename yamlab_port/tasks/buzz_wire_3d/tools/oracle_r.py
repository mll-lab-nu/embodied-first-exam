"""BuzzWire3D scripted oracle (Plan R, see plan_r.py) running in Isaac / YAMLab, plus nop and naive variants.

Privileged state (wand pose, joint positions, link poses) -> Cartesian wand waypoints -> numpy IK
(BatchIK continuation, verified against Isaac FK) -> 14-D joint targets at 30 Hz. Every stage is
re-planned from the measured state; grasp transforms are measured after each grasp closes.
Saves <name>_actions.npy (open-loop replayable), <name>_states.npz and <name>_metrics.json.

  BUZZ_NO_CAMERAS=1 PYTHONPATH=$RUN/yamlab python oracle_r.py --headless --tier very_easy --mode oracle --out DIR
  modes: oracle | nop | naive_skip_traverse
"""
import argparse
import json
import os
import sys
import time

from isaaclab.app import AppLauncher

ap = argparse.ArgumentParser()
ap.add_argument("--tier", default="very_easy")
ap.add_argument("--mode", default="oracle")
ap.add_argument("--out", default="results/oracle")
ap.add_argument("--name", default=None)
ap.add_argument("--nop_steps", type=int, default=600)
AppLauncher.add_app_launcher_args(ap)
args = ap.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yamlab
from bw_runner import Runner, make_env, OPEN, CLOSED
from bw_geom import Scene, Layout, TABLE_Z
from grasps import pen, ring, T_from
from plan_r import Planner, PlanError, frame_h_n, interp_T, n_steps, rrt_connect, densify

print("yamlab from", yamlab.__file__)
from yamlab.envs.tasks.buzz_wire_3d_manager_cfg import BUZZ_LAYOUTS

LAY = BUZZ_LAYOUTS[args.tier]
scene = Scene(args.tier, Layout(LAY["yaw_deg"], LAY["translation"]))
env = make_env(args.tier, cameras=False)
env.reset()
name = args.name or args.mode
R = Runner(env, args.out)
P = Planner(scene)
DT = env.cfg.sim.dt * env.cfg.decimation
p0, p1 = scene.rail[0, :2], scene.rail[-1, :2]
GUP, GDN, RG = pen("up", 0.033, -0.0275, 4.0), pen("down", 0.033, -0.0275, 4.0), ring()
FQ_PEN, FQ_RING, FQ_OPEN_PEN, FQ_OPEN_RING = -0.0056, -0.0023, -0.0089, -0.0053
back = lambda T, d: T @ T_from(np.eye(3), [0, 0, -d])
Rz = lambda d: Rotation.from_euler("z", d, degrees=True).as_matrix()
cmd_q = {"left": np.zeros(6), "right": np.zeros(6)}
cmd_g = {"left": OPEN, "right": OPEN}
notes = {}


# ----------------------------------------------------------------------------- execution
ARM_WIRE = {}  # phase -> {side: [min finger-wire gap, min any-link-wire gap]} (numpy model at measured joints)


def log_arm_wire():
    from bw_geom import seg_point_dist, WIRE_R
    for sd in ("left", "right"):
        qm, fq = R.arm_q(sd)
        pts = P.AP[sd].world(qm, fq)
        fing = np.concatenate([pts[l] for l in ("left_finger", "right_finger")])
        allp = np.concatenate(list(pts.values()))
        df = seg_point_dist(fing, scene.rail[:-1], scene.rail[1:]).min() - WIRE_R
        da = seg_point_dist(allp, scene.rail[:-1], scene.rail[1:]).min() - WIRE_R
        cur = ARM_WIRE.setdefault(R.phase, {}).setdefault(sd, [1.0, 1.0])
        cur[0], cur[1] = min(cur[0], float(df)), min(cur[1], float(da))


def run_joint_path(side, qs, w_max=0.5, lin=None, tcp=None):
    """Stream joint waypoints; each segment takes max(dq/w_max, dx/lin) seconds."""
    global cmd_q
    q_prev = cmd_q[side].copy()
    for i, q in enumerate(qs):
        k = int(np.ceil(np.abs(q - q_prev).max() / (w_max * DT)))
        if lin is not None and tcp is not None and i > 0:
            k = max(k, int(np.ceil(np.linalg.norm(tcp[i] - tcp[i - 1]) / (lin * DT))))
        k = max(k, 1)
        for u in np.linspace(0, 1, k + 1)[1:]:
            R.set_arm(side, (1 - u) * q_prev + u * q)
            R.step()
            if len(R.actions) % 6 == 0:
                log_arm_wire()
        q_prev = np.array(q)
    cmd_q[side] = q_prev.copy()


def grip(side, g, steps=15):
    g0 = cmd_g[side]
    for u in np.linspace(0, 1, steps + 1)[1:]:
        R.set_grip(side, (1 - u) * g0 + u * g)
        R.step()
    cmd_g[side] = g


def hold(n):
    R.step(n)


def q_now(side):
    return R.arm_q(side)[0]


def grasp_meas(side):
    """Link_6 pose in the wand frame, measured."""
    return np.linalg.inv(R.wand_T()) @ R.link_T(side)


def sync_cmd(side, tol=0.02):
    """If the arm sits away from its command (contact, wrist lag), re-seed from the measured joints."""
    qm = q_now(side)
    dev = np.abs(qm - cmd_q[side]).max()
    if dev > tol:
        print(f"   {side}: measured q deviates from command by {dev:.3f} rad -> re-seed", flush=True)
        notes.setdefault("reseed", []).append([R.phase, side, float(dev)])
    return qm


def cart_wand(side, Ws, G, fq, lin=0.02, w_max=0.5, **kw):
    """Move the wand through poses Ws with arm `side` holding it with grasp G."""
    qm = sync_cmd(side)
    T_now = P.ik[side].fk(qm[None])[0][0]
    Ts = [W @ G for W in Ws]
    Ts = interp_T(T_now, Ts[0], n_steps(T_now, Ts[0], lin=0.001)) + Ts[1:]
    qs, worst = P.track(side, Ts, qm, fq, **kw)
    run_joint_path(side, qs, w_max=w_max, lin=lin, tcp=[T[:3, 3] for T in Ts])
    return worst


def cart_tcp(side, T_to, fq, lin=0.02, **kw):
    T_from_ = P.ik[side].fk(cmd_q[side][None])[0][0]
    Ts = interp_T(T_from_, T_to, n_steps(T_from_, T_to))
    qs, worst = P.track(side, Ts, cmd_q[side], fq, **kw)
    run_joint_path(side, qs, lin=lin, tcp=[T[:3, 3] for T in Ts])
    return worst


def converge(side, tol=0.01, max_steps=45):
    for _ in range(max_steps):
        if np.abs(q_now(side) - cmd_q[side]).max() < tol:
            return
        R.step()
    dev = np.abs(q_now(side) - cmd_q[side]).max()
    print(f"   {side}: not converged after free move ({dev:.3f} rad)", flush=True)
    notes.setdefault("unconverged", []).append([R.phase, side, float(dev)])


def free_to(side, q_goal, fq, w_max=0.4):
    path = rrt_connect(P, side, cmd_q[side], q_goal, fq)
    run_joint_path(side, densify(path, 0.02), w_max=w_max)
    converge(side)


def approach_and_grip(side, T_grasp, fq_open, fq_close_target, dists=(0.04, 0.03, 0.05, 0.02), ignore=()):
    last = None
    for d in dists:
        try:
            qpre, _ = P.ik_best(side, back(T_grasp, d), fq_open, prefer=None, ignore=ignore)
            path = rrt_connect(P, side, cmd_q[side], qpre, OPEN)
            Ts = interp_T(back(T_grasp, d), T_grasp, n_steps(back(T_grasp, d), T_grasp, lin=0.001))
            qs, _ = P.track(side, Ts, qpre, fq_open, ignore=ignore)
            break
        except PlanError as e:
            last = e
            print("   approach", side, d, e)
    else:
        raise PlanError(f"approach {side}: {last}")
    run_joint_path(side, densify(path, 0.02), w_max=0.4)
    converge(side)
    grip(side, fq_open, 10)
    run_joint_path(side, qs, lin=0.015, tcp=[T[:3, 3] for T in Ts])
    hold(10)
    grip(side, fq_close_target, 20)
    hold(15)
    print(f"   {side} grasp done: |q_meas - q_cmd| = {np.abs(q_now(side) - cmd_q[side]).max():.4f} rad", flush=True)
    return d


def release_and_leave(side, G_meas, fq_open=OPEN, d=0.05, park=True):
    grip(side, fq_open, 15)
    hold(5)
    T = R.wand_T() @ G_meas
    cart_tcp(side, back(T, d), OPEN, lin=0.03, ignore=("stops",))
    if park:
        free_to(side, np.zeros(6), OPEN)


def phase(name):
    R.phase = name
    print(f"[{len(R.actions):5d}] phase {name}  wand={np.round(R.wand_T()[:3, 3], 4).tolist()}  "
          f"diag={ {k: R.diags[-1][k] for k in ('touched', 'min_gap_m', 'route_cursor_m', 'traversal_complete')} if R.diags else {} }",
          flush=True)


# ----------------------------------------------------------------------------- the oracle
class IsaacExecutor:
    def __init__(self):
        self.G = {}

    def q(self, side):
        return q_now(side)

    def finger(self, side):
        return R.arm_q(side)[1]

    def wand(self):
        return R.wand_T()

    def grasp(self, side):
        return self.G[side]

    def grasp_meas(self, side):
        return grasp_meas(side)

    def attach(self, side, G):
        self.G[side] = G

    def detach(self, side):
        pass

    def run(self, side, qs, w_max=0.5, lin=None, tcp=None):
        sync_cmd(side)
        run_joint_path(side, qs, w_max=w_max, lin=lin, tcp=tcp)

    def converge(self, side):
        converge(side)

    def grip(self, side, v, steps=15):
        grip(side, v, steps)

    def hold(self, n):
        hold(n)

    def phase(self, name):
        phase(name)


from stages_r import StagesR
from stages_a import StagesA


try:
    if args.mode in ("oracle", "naive_skip_traverse"):
        t0 = time.time()
        StagesA(P, IsaacExecutor(), notes, skip_traverse=(args.mode == "naive_skip_traverse")).run()
        notes["oracle_wall_s"] = time.time() - t0
    elif args.mode == "nop":
        R.phase = "nop"
        hold(args.nop_steps)
    else:
        raise SystemExit(f"unknown mode {args.mode}")
    status = "completed"
except PlanError as e:
    status = f"plan_error: {e}"
    print("PLAN_ERROR", e)
except Exception as e:  # keep the evidence of a crashed run
    import traceback
    traceback.print_exc()
    status = f"exception: {e!r}"
notes["arm_wire_gap_mm_by_phase"] = {ph: {sd: dict(fingers=round(v[0] * 1000, 1), any_link=round(v[1] * 1000, 1))
                                          for sd, v in d.items()} for ph, d in ARM_WIRE.items()}
m = R.save(name, extra=dict(mode=args.mode, tier=args.tier, status=status, notes=notes,
                            layout=dict(yaw_deg=LAY["yaw_deg"], translation=list(LAY["translation"]))))
print("RESULT", json.dumps({k: m[k] for k in ("success", "termination", "steps", "sim_time_s", "touched",
                                               "min_metal_wire_gap_mm", "traversal_complete", "status")}))
env.close()
app.close()
