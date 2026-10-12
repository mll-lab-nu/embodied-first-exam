"""Scripted oracle for KnotUntying (privileged rope state, offline USD-kinematics IK, 14-D joint targets).

Plan (node deletion by carrying the over strand's free end across the under strand):
  1. Crossing analysis on the rope centreline (top view, heights) -> for each crossing the over
     strand. Pick the free end whose strand is OVER at its first crossing and has the shortest
     tail to it (very_easy: the start end, over at its only crossing).
  2. Grasp that strand `grasp_from_end` from the end with the arm that reaches it, gripper down,
     jaws closing across the local tangent, fingertips 2 mm above the table; close to a jaw
     `squeeze_mm` narrower than the rope (self-limited squeeze, no clamp).
  3. Lift `lift` m, carry the end along an arc around the crossing to the far side of the under
     strand (target chosen so the carried strand lies on the other side of the under strand's
     tail), lower to 1 cm, open, lift away, go home.
  4. Wait until the goal check latches (or time out).
Every control step's action is recorded (actions.npy) and the per-step rope/EE state is logged
(states.npz) for the open-loop replay and for plots.

--variant naive: same grasp and lift, but the tail is pulled straight away from the crossing
(tightening the loop neck) instead of being carried across the under strand -> the crossing stays,
planar_clear fails. --variant nop: hold the start pose.
"""
import argparse, hashlib, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="KnotUntying-VeryEasy-v0")
p.add_argument("--out", default="oracle_run")
p.add_argument("--variant", default="oracle", choices=["oracle", "nop", "naive"])
p.add_argument("--max_steps", type=int, default=3000)
p.add_argument("--settle_max_s", type=float, default=20.0)
p.add_argument("--grasp_from_end", type=float, default=0.03)
p.add_argument("--lift", type=float, default=0.05)
p.add_argument("--squeeze_mm", type=float, default=2.0)
p.add_argument("--speed", type=float, default=0.06, help="TCP speed m/s for carrying")
p.add_argument("--target_xy", type=str, default="", help="override carry target 'x,y'")
p.add_argument("--arm", default="auto")
p.add_argument("--max_iters", type=int, default=4)
p.add_argument("--spread_iters", type=int, default=3)
p.add_argument("--spread_target", type=float, default=0.011, help="spread until the tightest non-local gap >= this (m)")
p.add_argument("--spread_dist", type=float, default=0.03)
p.add_argument("--held_target", type=float, default=0.016, help="two-arm spread while the tail is still held until the gap >= this (m); the gap shrinks a little once the tail is laid down")
p.add_argument("--past_deg", type=float, default=35.0, help="carry the tail this far past the under strand's tail direction")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yamlab.utils.task_creation import create_task_environment
from isaaclab.sim.utils import get_current_stage
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G
from oracle_lib import Arm, OPEN, YamKin

os.makedirs(args.out, exist_ok=True)
# The registered env's normal evaluation behaviour: task_success / time_out / rope_off_table
# terminations active (an episode ends - and auto-resets - at the first terminated step).
env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu",
                              strip_cameras=True, timeout_steps=args.max_steps)
env.reset()
stage = get_current_stage()
arms = {n: Arm(env, n) for n in ("left_arm", "right_arm")}
kin = {}
for n, a in arms.items():
    a.calibrate(pad_along=0.0)
    pb, Rb = a.body_pose(0)
    kin[n] = YamKin(stage, "/World/envs/env_0/" + ("LeftArm" if n == "left_arm" else "RightArm"), pb, Rb, a.tcp_l6)
SL = {"left_arm": slice(0, 6), "right_arm": slice(7, 13)}
GI = {"left_arm": 6, "right_arm": 13}
TABLE = 0.75
q_home = {n: a.q().copy() for n, a in arms.items()}

# ------------------------------------------------------------------ logging
actions, log_rows, rope_pos, rope_quat, tcp_log = [], [], [], [], []
cur = torch.zeros(1, 14)
cur[0, 6] = OPEN; cur[0, 13] = OPEN
for n in arms:
    cur[0, SL[n]] = torch.tensor(q_home[n], dtype=torch.float32)
t_wall = time.time()
done_flag = {"success": False, "step": None}


def do_step(a=None):
    global cur
    if done_flag.get("ended"):
        return True          # the episode has terminated: no more steps
    if a is not None:
        cur = a.clone()
    obs, r, term, trunc, info = env.step(cur)
    actions.append(cur[0].numpy().copy())
    pos, quat, lv, av = env.rope_state(0)
    rope_pos.append(pos.astype(np.float32)); rope_quat.append(quat.astype(np.float32))
    tcp_log.append(np.r_[arms["left_arm"].tcp()[0], arms["right_arm"].tcp()[0]].astype(np.float32))
    g = info["goal"][0]
    log_rows.append(dict(step=len(actions), success=bool(info["success"][0]), goal_now=bool(info["goal_now"][0]),
                         hold=int(info["goal_hold_steps"][0]), **{k: g[k] for k in ("planar_clear", "on_table", "quiet", "intact",
                         "n_crossings", "minimum_nonlocal_distance_m", "maximum_speed_m_s", "z_min_surface_above_table_m",
                         "z_max_surface_above_table_m")}))
    if bool(info["success"][0]) and not done_flag["success"]:
        done_flag.update(success=True, step=len(actions), latch_goal=dict(g))
    if bool(term[0] or trunc[0]):
        # the env auto-reset inside this step: the logged rope state of this last step is the reset state,
        # info["goal"] (and log_rows[-1]) is the evaluation before the reset
        done_flag.update(ended=True, end_reason="terminated" if bool(term[0]) else "time_out")
    return bool(term[0] or trunc[0])


# ------------------------------------------------------------------ privileged plan + execution
z_tip_table = TABLE + 0.002        # fingertip height when touching the rope / placing
rope_d = 2 * env.rope_radius
q_grip_closed = -(rope_d - args.squeeze_mm / 1000) / 2   # jaw = -2 q
arm_name = "left_arm"


def move_joints(q_to, n_steps, grip=None):
    q_from = cur[0, SL[arm_name]].numpy().astype(float)
    g_from = float(cur[0, GI[arm_name]])
    for i in range(1, n_steps + 1):
        a = cur.clone()
        f = i / n_steps
        f = 0.5 - 0.5 * np.cos(np.pi * f)
        a[0, SL[arm_name]] = torch.tensor(q_from + f * (q_to - q_from), dtype=torch.float32)
        if grip is not None:
            a[0, GI[arm_name]] = g_from + f * (grip - g_from)
        if do_step(a):
            return True
    return False


def hold(n):
    for _ in range(n):
        if do_step():
            return True
    return False


def solve_path(g_pt, close_yaw, arc, yaws, only_arm=None):
    """Arm with the best worst-case IK error along pre-grasp, grasp and the carry path."""
    best = None
    for n in ("left_arm", "right_arm"):
        if (args.arm != "auto" and n != args.arm) or (only_arm is not None and n != only_arm):
            continue
        k, a = kin[n], arms[n]
        qs, worst, q = [], 0.0, q_home[n].copy()
        seeds = [np.array([0, 1.6, 1.4, -0.6, 0, 0.0]), np.array([0, 2.2, 1.9, -1.0, 0, 0.0]), np.array([0, 1.0, 0.8, -0.3, 0, 0])]
        b = k.base[:3, 3]
        for sd in seeds:
            sd[0] = np.arctan2(g_pt[1] - b[1], g_pt[0] - b[0])
        pts = [np.r_[g_pt[:2], z_tip_table + 0.08], np.r_[g_pt[:2], z_tip_table]] + arc
        ys = [close_yaw, close_yaw] + yaws
        for i, (pp, yy) in enumerate(zip(pts, ys)):
            sol = None
            for yv in (yy, yy + np.pi):   # parallel jaw: yaw and yaw + pi are the same grasp
                qq, ep, er = k.ik(pp, a.down_rotation(yv), q, extra_seeds=seeds if i == 0 else ())
                if sol is None or (ep + 0.05 * er, np.linalg.norm(qq - q)) < (sol[1] + 0.05 * sol[2], np.linalg.norm(sol[0] - q)):
                    sol = (qq, ep, er, yv)
            q = sol[0]; qs.append(q.copy()); worst = max(worst, sol[1])
            ys[i] = sol[3]
        if best is None or worst < best[1]:
            best = (n, worst, qs, list(ys))
    return best


def make_plan():
    pos, quat, lv, av = env.rope_state(0)
    d = env.link_length
    joints, _ = G.chain_points_from_links(pos, quat, d)
    s_j = np.arange(len(joints)) * d
    L = s_j[-1]
    cr = G.crossings_fast(joints)
    plan = dict(step=len(actions), crossings=len(cr), over_under=G.over_under_sequence(cr))
    if not cr:
        return plan, None
    passes = []
    for c in cr:
        passes.append((c["si"], c["first_over"], c))
        passes.append((c["sj"], not c["first_over"], c))
    passes.sort(key=lambda x: x[0])
    cands = []
    s0, over0, c0 = passes[0]
    if over0:
        cands.append(("start", s0, c0))
    s1, over1, c1 = passes[-1]
    if over1:
        cands.append(("end", L - s1, c1))
    cands.sort(key=lambda x: x[1])
    plan["candidates"] = [(c[0], c[1]) for c in cands]
    if not cands:
        plan["error"] = "no free end is over at its first crossing"
        return plan, None
    point_at = lambda s: np.array([np.interp(s, s_j, joints[:, k]) for k in range(3)])

    def tangent_at(s):
        t = point_at(min(s + 0.01, L)) - point_at(max(s - 0.01, 0))
        return t / np.linalg.norm(t)
    end_name, tail, c0 = cands[0]
    s_g = args.grasp_from_end if end_name == "start" else L - args.grasp_from_end
    g_pt = point_at(s_g)
    tan = tangent_at(s_g)
    close_yaw = np.arctan2(tan[1], tan[0]) + np.pi / 2
    over_is_i = (c0["first_over"])
    s_over = c0["si"] if over_is_i else c0["sj"]
    s_under = c0["sj"] if over_is_i else c0["si"]
    X = np.r_[c0["xy"], 0]
    under_dir_s = 1.0 if (L - s_under) < s_under else -1.0
    u_tail = point_at(np.clip(s_under + under_dir_s * 0.12, 0, L)) - X
    u_tail[2] = 0; u_tail /= np.linalg.norm(u_tail)
    o_tail = g_pt - X; o_tail[2] = 0; o_tail /= np.linalg.norm(o_tail)
    ang_o = np.arctan2(o_tail[1], o_tail[0]); ang_u = np.arctan2(u_tail[1], u_tail[0])
    dang = (ang_u - ang_o + np.pi) % (2 * np.pi) - np.pi
    ang_t = ang_o + dang + np.sign(dang) * np.radians(args.past_deg)
    if args.variant == "naive":
        ang_t = ang_o          # naive: lift and pull the tail straight away from the crossing (no carry across)
    tail_len = s_over if end_name == "start" else L - s_over
    R_t = 0.85 * (tail_len - args.grasp_from_end)
    if args.variant == "naive":
        R_t = tail_len + 0.03
    r0 = np.linalg.norm((g_pt - X)[:2])
    n_arc = 40
    angs = np.linspace(ang_o, ang_t, n_arc)
    rads = np.linspace(r0, R_t, n_arc)
    arc = [X + np.array([r * np.cos(a), r * np.sin(a), 0]) for a, r in zip(angs, rads)]
    for p_ in arc:
        p_[2] = z_tip_table + args.lift
    if args.target_xy:
        arc[-1][:2] = [float(v) for v in args.target_xy.split(",")]
    yaws = [close_yaw + (a - ang_o) for a in angs]
    plan.update(end=end_name, s_grasp=s_g, grasp_point=g_pt.tolist(), crossing_xy=X[:2].tolist(), target=arc[-1][:2].tolist(),
                over_tail_angle_deg=float(np.degrees(ang_o)), under_tail_angle_deg=float(np.degrees(ang_u)),
                target_angle_deg=float(np.degrees(ang_t)), tail_len=tail_len)
    best = solve_path(g_pt, close_yaw, arc, yaws)
    plan.update(arm=best[0], worst_ik_err_mm=best[1] * 1000)
    return plan, dict(arm=best[0], q_way=best[2], yaws=best[3], arc=arc, s_grasp=s_g, kind="carry")


def tightest_pair():
    pos, quat, lv, av = env.rope_state(0)
    d = env.link_length
    pts, st = G.stations_points(pos, quat, d)
    n = len(pts) - 1
    I, J = np.triu_indices(n, k=2)
    D = G._pair_segment_distance_2d(pts[I, :2], pts[I + 1, :2], pts[J, :2], pts[J + 1, :2])
    D = np.where(st[J] - st[I + 1] < 2 * rope_d, np.inf, D)
    k = int(np.argmin(D))
    return float(D[k]), st[I[k]], st[J[k]], pts[I[k]], pts[J[k]]


def make_spread(only_arm=None, avoid_xy=None, avoid_s=None, target=None):
    """Final spread: if the tightest non-local top-view gap < --spread_target, grasp a free tail at a
    station with >= 20 mm top-view clearance (narrow jaw), lift 2 cm and shift it --spread_dist away
    from the tight pair, lay it down."""
    gap, sa, sb, pa, pb = tightest_pair()
    plan = dict(step=len(actions), kind="spread", gap_mm=gap * 1000, s_pair=[float(sa), float(sb)])
    if gap >= (args.spread_target if target is None else target):
        return plan, None
    pos, quat, lv, av = env.rope_state(0)
    joints, _ = G.chain_points_from_links(pos, quat, env.link_length)
    s_j = np.arange(len(joints)) * env.link_length
    L = s_j[-1]
    point_at = lambda s: np.array([np.interp(s, s_j, joints[:, k]) for k in range(3)])
    cands = []
    if only_arm is None:     # post-release fallback: free-tail stations
        stations = [s for off in np.arange(0.02, 0.081, 0.01) for s in (off, L - off)]
    else:                    # second-arm spread: stations 3-10 cm (arc) from the tight pair on either strand
        stations = [s for c in (sa, sb) for dd in np.arange(0.03, 0.101, 0.01) for s in (c - dd, c + dd) if 0.01 < s < L - 0.01]
    for s_g in stations:
            g = point_at(s_g)
            if avoid_s is not None and abs(s_g - avoid_s) < 0.05:
                continue
            if avoid_xy is not None and np.linalg.norm(g[:2] - avoid_xy[:2]) < 0.09:
                continue
            far = np.abs(s_j - s_g) > 0.03
            clr = float(np.min(np.linalg.norm(joints[far, :2] - g[:2], axis=1)))
            if clr >= 0.020:
                cands.append((round(min(abs(s_g - sa), abs(s_g - sb)), 3), -clr, s_g, g))
    if not cands:
        plan["error"] = "no free-tail station with 20 mm clearance"
        return plan, None
    cands.sort(key=lambda c: (c[0], c[1]))
    _, nclr, s_g, g = cands[0]
    u = (pa - pb) if abs(s_g - sa) < abs(s_g - sb) else (pb - pa)
    u = u[:2] / np.linalg.norm(u[:2])
    t = point_at(min(s_g + 0.01, L)) - point_at(max(s_g - 0.01, 0))
    close_yaw = np.arctan2(t[1], t[0]) + np.pi / 2
    tgt = g.copy(); tgt[:2] += args.spread_dist * u
    arc = [np.r_[(g + f * (tgt - g))[:2], z_tip_table + 0.02] for f in np.linspace(0, 1, 8)]
    yaws = [close_yaw] * len(arc)
    best = solve_path(g, close_yaw, arc, yaws, only_arm=only_arm)
    if best is None or best[1] > 0.003:
        plan["error"] = "spread station not reachable"
        return plan, None
    plan.update(s_grasp=float(s_g), clearance_mm=-nclr * 1000, grasp_point=g.tolist(), target=tgt[:2].tolist(),
                arm=best[0], worst_ik_err_mm=best[1] * 1000)
    return plan, dict(arm=best[0], q_way=best[2], yaws=best[3], arc=arc, open_q=-0.009, lift=0.02, s_grasp=s_g, kind="spread")


def execute(ex):
    global arm_name
    arm_name = ex["arm"]; A, K = arms[arm_name], kin[arm_name]
    q_way, arc, yaws = ex["q_way"], ex["arc"], ex["yaws"]
    open_q = ex.get("open_q", OPEN)
    lift = ex.get("lift", args.lift)
    move_joints(q_way[0], 75, grip=open_q)          # 2.5 s to pre-grasp (8 cm above)
    move_joints(q_way[1], 45)                       # 1.5 s descend
    hold(10)
    move_joints(q_way[1], 30, grip=q_grip_closed)   # 1 s close (self-limited squeeze)
    hold(15)
    path_q = q_way[2:]
    seg = [np.linalg.norm(arc[i + 1] - arc[i]) for i in range(len(arc) - 1)]
    move_joints(path_q[0], max(15, int(np.ceil(lift / args.speed * 30))))
    for i in range(1, len(path_q)):
        move_joints(path_q[i], max(2, int(np.ceil(seg[i - 1] / args.speed * 30))))
    q_end = path_q[-1]
    p_end = arc[-1].copy(); p_end[2] = z_tip_table + 0.006
    q_place, ep, er = K.ik(p_end, A.down_rotation(yaws[-1]), q_end)
    move_joints(q_place, 45)
    # Held spread (two arms): if this carry removed the last crossing but left a tight non-local gap,
    # this arm keeps holding the tail raised (rope not on the table -> the goal cannot latch) while the
    # other arm grasps a strand 3-10 cm from the tight pair (>= 20 mm clearance, narrow jaw), shifts it
    # 3 cm away from the pair and releases it. Then this arm lays its tail down and releases.
    if args.variant == "oracle" and ex.get("kind") == "carry":
        holder = arm_name
        for k_sp in range(args.spread_iters):
            if n_crossings_now() != 0 or done_flag.get("ended"):
                break
            other = "right_arm" if holder == "left_arm" else "left_arm"
            sp_plan, sp_ex = make_spread(only_arm=other, avoid_xy=arms[holder].tcp()[0], avoid_s=ex["s_grasp"], target=args.held_target)
            sp_plan["held_by"] = holder
            held_spreads.append(sp_plan)
            print("HELD_SPREAD", json.dumps(sp_plan))
            if sp_ex is None:
                break
            execute(sp_ex)
            arm_name = holder
    hold(15)
    move_joints(q_place, 30, grip=open_q)
    hold(10)
    p_up = p_end.copy(); p_up[2] += 0.08
    q_up, _, _ = K.ik(p_up, A.down_rotation(yaws[-1]), q_place)
    move_joints(q_up, 45)
    move_joints(q_home[arm_name], 75, grip=OPEN)
    hold(15)


def n_crossings_now():
    pos, quat, lv, av = env.rope_state(0)
    return len(G.crossings_fast(G.chain_points_from_links(pos, quat, env.link_length)[0]))


plans, held_spreads = [], []
if args.variant == "nop":
    hold(args.max_steps)
else:
    for it in range(1 if args.variant == "naive" else args.max_iters):
        if done_flag.get("ended"):
            break
        plan, ex = make_plan()
        plans.append(plan)
        print("PLAN", it, json.dumps(plan))
        if ex is None or done_flag.get("ended"):
            break
        execute(ex)
    if args.variant == "oracle" and not done_flag.get("ended") and n_crossings_now() == 0:
        for it in range(args.spread_iters):
            plan, ex = make_spread()
            plans.append(plan)
            print("SPREAD", it, json.dumps(plan))
            if ex is None or done_flag.get("ended"):
                break
            execute(ex)
    # finish when the goal holds again for the full 0.5 s (or at max_steps)
    while not done_flag.get("ended") and len(actions) < args.max_steps:
        if hold(1):
            break
lg = done_flag.get("latch_goal") or {}
gap_final = lg.get("minimum_nonlocal_distance_m")
print("LATCH_GAP_MM", None if gap_final is None else round(gap_final * 1000, 2), "end", done_flag.get("end_reason"))
plan = dict(iterations=plans, held_spreads=held_spreads)

wall = time.time() - t_wall
last = log_rows[-1]
h = hashlib.sha256(np.stack(rope_pos).tobytes()).hexdigest()[:16]
metrics = dict(task=args.task, variant=args.variant, success=done_flag["success"], success_step=done_flag["step"],
               steps=len(actions), sim_time_s=len(actions) / 30.0, wall_time_s=wall, plan=plan, final=last,
               min_nonlocal_final_m=last["minimum_nonlocal_distance_m"], latch_min_nonlocal_m=gap_final,
               latch_goal=lg, end_reason=done_flag.get("end_reason"), rope_state_sha16=h,
               action_sha16=hashlib.sha256(np.stack(actions).tobytes()).hexdigest()[:16])
np.save(os.path.join(args.out, "actions.npy"), np.stack(actions))
np.savez_compressed(os.path.join(args.out, "states.npz"), rope_pos=np.stack(rope_pos), rope_quat=np.stack(rope_quat),
                    tcp=np.stack(tcp_log), actions=np.stack(actions))
json.dump(log_rows, open(os.path.join(args.out, "goal_log.json"), "w"))
json.dump(metrics, open(os.path.join(args.out, "metrics.json"), "w"), indent=1)
print("METRICS", json.dumps({k: metrics[k] for k in ("variant", "success", "success_step", "steps", "sim_time_s", "wall_time_s", "rope_state_sha16")}),
      json.dumps(last))
sys.stdout.flush(); os._exit(0)
