"""Scripted privileged-state oracle for CastKeyhole (very_easy first).

Pipeline per control step (30 Hz): measured plate poses -> desired plate poses (phase plan, relative
disassembly route from the old oracle) -> gripper TCP targets through the grasp offsets measured right after
closing (+ a small integral correction on the object pose error) -> numpy damped-least-squares IK on the
unchanged YAM kinematics (tools/yam_kin.py, validated against Isaac to < 1 micron) -> 14-D joint targets.
Friction grasps only (+ YAMLab's grasp clamp); no welds, no state writes.

Saves: actions.npy (T x 14), states.npz (per-step plate/arm states + TCP targets + goal-check values),
metrics.json, phases.json.

usage: python oracle.py --tier very_easy --out runs/oracle_ve [--stop_after PHASE] [--variant naive_pull]
"""
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ck_env

p = ck_env.base_parser("CastKeyhole oracle")
p.add_argument("--stop_after", default=None, help="stop after this phase (debug)")
p.add_argument("--variant", default="oracle", choices=["oracle", "naive_pull", "nop"])
p.add_argument("--params", default=None, help="JSON file with parameter overrides")
p.add_argument("--settle_steps", type=int, default=90)
args, app = ck_env.launch(p)

import numpy as np
import torch
from scipy.spatial.transform import Rotation, Slerp

ck_env.tools_path()
import yam_kin as yk
import route as rt
import plan2 as pl
from layout import Scene, T_from, TABLE_Z

OPEN, CLOSED = -0.0475, 0.0
DT = 1.0 / 30.0

P = dict(gold_grasp="band", gold_fork_x=0.056, gold_fork_tip_y=-0.068, gold_y=-0.004, gold_x_tcp=0.061, gold_jaw=1.0, silver_y=-0.0024, silver_x_tcp=-0.051, silver_jaw=-1.0, fix_jaw=True,
         work_bar=[0.50, -0.07], h_bar=0.0405, h_setup=0.052, t_lower=2.0, psi=0.0, gamma=0.0, split=0.5, t_setup=9.0,
         t_hover=3.0, t_down=1.5, t_approach=1.5, t_close=1.2, t_lift=1.5, lift=0.02, t_stand=6.0, t_align=4.0, t_level=6.0,
         t_turn=8.0, chan_speed=0.010, chan_extra=0.04, k_corr={'gold': 0.0, 'silver': 0.1}, corr_max=[0.02, 0.2], gold_filter=0.15, corr_ik_gate=1.0, rel_fb=1.0, t_align_hold=3.0, max_dq=0.06, lost_mm=25.0, lost_deg=25.0,
         pre_back=0.06, hover_up=0.06, sep_up=0.06, gold_release_h=0.030, gold_dy=-0.02, t_gold_down=2.5,
         place_margin=0.012, silver_tip0_deg=30.0, silver_carry_h=0.02, silver_set_h=0.002, silver_tip_deg=65.0, t_tip=3.0, t_carry=5.0, t_wait=3.0)
if args.params:
    P.update(json.load(open(args.params)))

os.makedirs(args.out, exist_ok=True)
env, tid = ck_env.make_env(args.tier)
env.reset()


def plate_T(name):
    s = ck_env.snapshot(env)[name]
    return T_from(Rotation.from_quat(s[[4, 5, 6, 3]]), s[:3])


scene = Scene(args.tier)
REL = pl.Relative(scene.record, args.tier)
TPP = scene.T_part_plate


def plate_frame(name):          # measured plate (authored outline) frame in world
    return plate_T(f"keyhole_{name}") @ TPP[name]


class Arm:
    def __init__(self, name, side):
        self.name, self.side = name, side
        self.q = ck_env.arm_q(env, name)
        self.grip = OPEN
        self.G = None                       # grasp offset: plate frame -> commanded TCP
        self.corr = np.zeros(6)
        self.ik_err = 0.0

    def tcp_meas(self):
        return yk.base_to_world(yk.fk_tcp(ck_env.arm_q(env, self.name)), self.side)

    def tcp_cmd(self):
        return yk.base_to_world(yk.fk_tcp(self.q), self.side)

    def solve(self, Tw):
        qn, ok, ep, er = yk.ik(yk.world_to_base(Tw, self.side), self.q, iters=60, margin=0.0)
        dq = np.clip(qn - self.q, -P["max_dq"], P["max_dq"])
        self.q = self.q + dq
        self.ik_err = max(ep, er * 0.1)
        return ok


L, R = Arm("left_arm", "left"), Arm("right_arm", "right")
ARMS = {"gold": L, "silver": R}   # left arm holds gold (+x band), right arm holds silver (-x edge)
actions, log, phases = [], [], []
t_wall = time.time()


def step(extra=None):
    a = np.zeros(14, np.float32)
    a[0:6], a[6], a[7:13], a[13] = L.q, L.grip, R.q, R.grip
    actions.append(a.copy())
    obs, rew, term, trunc, info = env.step(torch.as_tensor(a)[None])
    s = ck_env.snapshot(env)
    s["left_arm_tcp"] = L.tcp_cmd()[:3, 3]
    s["right_arm_tcp"] = R.tcp_cmd()[:3, 3]
    ck = ck_env.ck_info_numpy(info["cast_keyhole"])
    for k, v in ck.items():
        s["ck_" + k] = np.array(float(v))
    s["ik_err"] = np.array([L.ik_err, R.ik_err])
    log.append(s)
    if ck.get("success"):
        # The env terminates on success and auto-resets inside this very step (Isaac Lab), so stop here.
        print(f"[oracle] success latched at step {len(actions) - 1}", flush=True)
        finish("success")
    for n, a in ARMS.items():
        if a.G is not None and a.grip == CLOSED and args.variant == "oracle":
            # in-hand slip: measured plate frame vs the one implied by the measured link_6 and the grasp offset
            exp = a.tcp_meas() @ np.linalg.inv(a.G)
            got = plate_frame(n)
            dp = np.linalg.norm(exp[:3, 3] - got[:3, 3])
            dr = Rotation.from_matrix(exp[:3, :3].T @ got[:3, :3]).magnitude()
            a.slip = (dp, dr)
            if dp > P["lost_mm"] / 1000 or dr > np.radians(P["lost_deg"]):
                print(f"[oracle] {a.name} lost its grasp (slip {dp*1000:.1f} mm, {np.degrees(dr):.1f} deg)", flush=True)
                finish("lost_grasp_" + a.name)
    return ck


def smooth(u):
    return u * u * (3 - 2 * u)


def phase(name):
    phases.append(dict(name=name, start_step=len(actions)))
    print(f"[oracle] phase {name} at step {len(actions)}", flush=True)
    if args.stop_after is not None and len(phases) > 1 and phases[-2]["name"] == args.stop_after:
        finish("stopped")


def interp_T(A, B, u):
    T = np.eye(4)
    T[:3, 3] = A[:3, 3] + u * (B[:3, 3] - A[:3, 3])
    T[:3, :3] = Slerp([0, 1], Rotation.from_matrix([A[:3, :3], B[:3, :3]]))(u).as_matrix()
    return T


def cart_move(targets, dur):
    """targets: {arm: T_world_goal}; straight line + slerp from the current command."""
    n = max(1, int(round(dur / DT)))
    start = {a: a.tcp_cmd() for a in targets}
    for k in range(1, n + 1):
        u = smooth(k / n)
        for a, T in targets.items():
            a.solve(interp_T(start[a], T, u))
        step()


def joint_move(targets, dur):
    n = max(1, int(round(dur / DT)))
    start = {a: a.q.copy() for a in targets}
    for k in range(1, n + 1):
        u = smooth(k / n)
        for a, q in targets.items():
            a.q = start[a] + u * (q - start[a])
        step()


def hold(dur):
    for _ in range(max(1, int(round(dur / DT)))):
        step()


SEED_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(args.out)), "seed_cache.json")
try:
    SEED_CACHE = json.load(open(SEED_CACHE_PATH))
except Exception:
    SEED_CACHE = {}


def seed_ik(Tw, side, tries=150, good=0.45):
    """Multi-start IK (deterministic RNG). Results are cached by (side, pose rounded to 1e-6) in
    runs/seed_cache.json; the cache only skips recomputing the same deterministic search."""
    key = side + ":" + ",".join(f"{v:.6f}" for v in np.asarray(Tw)[:3, :].ravel())
    if key in SEED_CACHE:
        v = SEED_CACHE[key]
        return None if v is None else (np.array(v[0]), v[1])
    out = _seed_ik(Tw, side, tries, good)
    SEED_CACHE[key] = None if out is None else [out[0].tolist(), out[1]]
    try:
        json.dump(SEED_CACHE, open(SEED_CACHE_PATH, "w"))
    except Exception:
        pass
    return out


def _seed_ik(Tw, side, tries=150, good=0.45):
    rng = np.random.default_rng(0)
    Tb = yk.world_to_base(Tw, side)
    best = None
    for _ in range(tries):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, ep, er = yk.ik(Tb, q0, iters=100)
        if ok:
            m = float(np.min(np.minimum(q - yk.LOWER, yk.UPPER - q)))
            if best is None or m > best[1]:
                best = (q, m)
            if m > good:
                break
    return best


ZMASK = [1, 1, 1, 1, 1, 1]
DES = {}          # last desired plate poses (phases start from these, not from the measured poses)
GF = {"T": None}  # low-pass filtered measured gold pose (relative feedback for the silver)
RFB = [0.0]       # ramp of the relative feedback weight (0 -> 1 during the align hold)


def gold_filtered():
    Tm = plate_frame("gold")
    if GF["T"] is None:
        GF["T"] = Tm
    else:
        GF["T"] = pl.interp_T(GF["T"], Tm, P["gold_filter"])
    return GF["T"]


def rel_target(Tg_des, rel):
    """Silver target: the relative configuration applied to the measured (filtered) gold, blended with the
    desired gold by rel_fb (1 = pure relative feedback)."""
    w = P["rel_fb"] * RFB[0]
    Tg = pl.interp_T(Tg_des, gold_filtered(), w) if w > 0 else Tg_des
    return Tg @ rel


def track_objects(fn, dur, gate=None):
    """fn(u) -> {name: T_plate_desired_world}. Each arm commands T_des @ G (+ correction)."""
    n = max(1, int(round(dur / DT)))
    for k in range(1, n + 1):
        u = smooth(k / n) if gate is None else k / n
        des = fn(u)
        DES.update(des)
        for name, Td in des.items():
            a = ARMS[name]
            kc = P["k_corr"][name] if isinstance(P["k_corr"], dict) else P["k_corr"]
            if kc > 0:
                Tm = plate_frame(name)
                e = np.r_[Td[:3, 3] - Tm[:3, 3], Rotation.from_matrix(Td[:3, :3] @ Tm[:3, :3].T).as_rotvec()]
                if a.ik_err < P["corr_ik_gate"]:          # anti-windup: no integration while IK saturates
                    a.corr = a.corr + kc * e * np.asarray(ZMASK)
                a.corr[:3] = np.clip(a.corr[:3], -P["corr_max"][0], P["corr_max"][0])
                a.corr[3:] = np.clip(a.corr[3:], -P["corr_max"][1], P["corr_max"][1])
            C = T_from(Rotation.from_rotvec(a.corr[3:]), a.corr[:3])
            Tt = Td @ a.G
            Tt = T_from(Rotation.from_matrix(C[:3, :3] @ Tt[:3, :3]), Tt[:3, 3] + C[:3, 3])
            a.solve(Tt)
        step()


def finish(status):
    wall = time.time() - t_wall
    np.save(os.path.join(args.out, "actions.npy"), np.array(actions))
    np.savez(os.path.join(args.out, "states.npz"), **{k: np.array([s[k] for s in log]) for k in log[0]})
    last = {k[3:]: float(v) for k, v in log[-1].items() if k.startswith("ck_")}
    succ_steps = [i for i, s in enumerate(log) if s["ck_success"] > 0.5]
    m = dict(task=tid, variant=args.variant, status=status, success=bool(succ_steps),
             first_success_step=succ_steps[0] if succ_steps else None, steps=len(actions),
             sim_time_s=len(actions) * DT, wall_time_s=wall, final_check=last,
             final_state_hash=ck_env.state_hash({k: v for k, v in ck_env.snapshot(env).items()}),
             params=P, phases=phases)
    json.dump(m, open(os.path.join(args.out, "metrics.json"), "w"), indent=1, default=float)
    print(json.dumps({k: m[k] for k in ("status", "success", "first_success_step", "steps", "sim_time_s",
                                        "wall_time_s", "final_check")}, indent=1, default=float), flush=True)
    env.close()
    app.close()
    sys.exit(0)


# ----------------------------------------------------------------------------- run
phase("settle")
hold(args.settle_steps * DT)
if args.variant == "nop":
    hold(20.0)
    finish("nop_done")

Tg0, Ts0 = plate_frame("gold"), plate_frame("silver")


def make_grasp(name, jaw):
    if name == "gold" and P.get("gold_grasp") == "fork":
        return pl.gold_fork_grasp(P["gold_fork_x"], P["gold_fork_tip_y"], jaw)
    if name == "gold":
        return pl.gold_grasp(P["gold_y"], P["gold_x_tcp"], jaw)
    return pl.silver_edge_grasp(P["silver_y"], P["silver_x_tcp"], jaw)


# choose the jaw sign (wrist roll branch / camera side) per arm by IK margin at hover and grasp
G0, grasp_T, pre_T, hover_T, qs = {}, {}, {}, {}, {}
phase("hover")
for n, a in ARMS.items():
    best = None
    for jaw in ((P[n + "_jaw"],) if P.get("fix_jaw") else (1.0, -1.0)):
        G = make_grasp(n, jaw)
        T = (Tg0 if n == "gold" else Ts0) @ G
        pre = T.copy(); pre[:3, 3] -= P["pre_back"] * T[:3, 0]
        hov = pre.copy(); hov[:3, 3] += np.r_[0, 0, P["hover_up"]]
        s_h = seed_ik(hov, a.side)
        s_g = seed_ik(T, a.side, tries=150)
        print(f"[oracle] {a.name} jaw {jaw:+.0f}: hover margin {None if s_h is None else round(s_h[1], 3)}, "
              f"grasp margin {None if s_g is None else round(s_g[1], 3)}", flush=True)
        if s_h is None or s_g is None:
            continue
        score = min(s_h[1], s_g[1])
        if best is None or score > best[0]:
            best = (score, jaw, G, T, pre, hov, s_h[0])
    if best is None:
        print(f"[oracle] no IK for {a.name} hover/grasp", flush=True); finish("no_ik_hover")
    _, jaw, G0[n], grasp_T[a], pre_T[a], hover_T[a], qs[a] = best
    P[n + "_jaw_used"] = jaw
joint_move(qs, P["t_hover"])
phase("down"); cart_move(pre_T, P["t_down"])
phase("approach"); cart_move(grasp_T, P["t_approach"])
phase("close")
L.grip = R.grip = CLOSED
hold(P["t_close"])
for n, a in ARMS.items():
    a.G = np.linalg.inv(plate_frame(n)) @ a.tcp_cmd()
    DES[n] = plate_frame(n)

def _tr(T, d):
    o = T.copy(); o[:3, 3] += d; return o


# --- stand: the silver pivots about its lower (+x) edge, which stays on the table, until it is perpendicular to
#     the gold (nominal relative configuration); the gold follows the relative align path. The table carries the
#     silver, so its edge clamp sees no pry moment.
phase("stand")
Tg1, Ts1 = DES["gold"], DES["silver"]
r_m, c_m = REL.measured(Tg1, Ts1)
R_target_s = Tg1[:3, :3] @ REL.r0.as_matrix()                 # silver orientation if the gold stays put
R_piv = R_target_s @ Ts1[:3, :3].T
edge = [Ts1 @ np.r_[0.039, yy, zz, 1.0] for yy in (-0.06, 0.06) for zz in (-0.0045, 0.0045)]
pivot = min(edge, key=lambda q: q[2])[:3]
rv = Rotation.from_matrix(R_piv).as_rotvec()
align1 = REL.align(Tg1, Ts1)
print(f"[oracle] stand: silver pivots {np.degrees(np.linalg.norm(rv)):.1f} deg about {rv.round(3)}", flush=True)
def f_stand(u):
    Ts = pl.rot_about(Ts1, Rotation.from_rotvec(rv * u).as_matrix(), pivot)
    if P.get("stand_gold_follow"):
        # compliant gold: the left hand follows the measured gold (blended with the plan) instead of forcing it
        Tg = pl.interp_T(Ts @ np.linalg.inv(align1(u)), plate_frame("gold"), P["stand_gold_follow"])
        return {"silver": Ts, "gold": Tg}
    return {"silver": Ts, "gold": Ts @ np.linalg.inv(align1(u))}
track_objects(f_stand, P["t_stand"])
hold(0.5)

# --- optional regrasp of the gold (easier): while the assembly rests on the table after the stand, the left
#     hand lets go of the gold and re-grasps it at regrasp_gold_y (closer to the fork end)
if P.get("regrasp_gold_y") is not None:
    phase("regrasp")
    L.G = None                    # no slip guard while re-grasping
    L.grip = OPEN
    hold(0.6)
    T = L.tcp_cmd(); Tb = T.copy(); Tb[:3, 3] -= 0.05 * T[:3, 0]; Tb[2, 3] += 0.02
    cart_move({L: Tb}, 1.0)
    Tg_rest = plate_frame("gold")
    G_new = pl.gold_grasp(P["regrasp_gold_y"], P["gold_x_tcp"], P["gold_jaw_used"])
    T_new = Tg_rest @ G_new
    s_ = None
    for up in (0.03, 0.015, 0.0):
        T_pre = T_new.copy(); T_pre[:3, 3] -= 0.05 * T_new[:3, 0]; T_pre[2, 3] += up
        s_ = seed_ik(T_pre, "left")
        print(f"[oracle] regrasp pregrasp (up {up}) IK margin {None if s_ is None else round(s_[1], 3)}", flush=True)
        if s_ is not None:
            break
    if s_ is None:
        finish("no_ik_regrasp")
    joint_move({L: s_[0]}, 2.5)
    T_pre2 = T_new.copy(); T_pre2[:3, 3] -= 0.05 * T_new[:3, 0]
    cart_move({L: T_pre2}, 0.8)
    cart_move({L: T_new}, 1.2)
    L.grip = CLOSED
    hold(1.0)
    L.G = np.linalg.inv(plate_frame("gold")) @ L.tcp_cmd()
    L.corr = np.zeros(6)
    DES["gold"] = plate_frame("gold")

# --- move: rigid motion of the aligned assembly: up by `lift`, gold normal straight down, bar to the work point
#     (h_setup above the table), assembly yawed by psi; then lowered so the silver stands on the table again
phase("move")
Tg2, Ts2 = DES["gold"], DES["silver"]
Trel2 = np.linalg.inv(Tg2) @ Ts2
R_lv = Rotation.align_vectors([[0, 0, -1.0]], [Tg2[:3, 2]])[0].as_matrix()
R_lv = Rotation.from_euler("z", P["psi"], degrees=True).as_matrix() @ R_lv
bar2 = Tg2[:3, :3] @ REL.c0 + Tg2[:3, 3]
Tg_goal = pl.rot_about(Tg2, R_lv, bar2)
Tg_goal[:3, 3] += np.r_[P["work_bar"][0], P["work_bar"][1], TABLE_Z + P["h_setup"]] - bar2
Tg_up = _tr(Tg2, [0, 0, P["lift"]])
def f_move(u):
    if u < 0.2:
        Tg = pl.interp_T(Tg2, Tg_up, u / 0.2)
    else:
        Tg = pl.interp_T(Tg_up, Tg_goal, (u - 0.2) / 0.8)
    return {"gold": Tg, "silver": Tg @ Trel2}
track_objects(f_move, P["t_setup"])
hold(0.5)
# --- lower until the silver stands on its +x edge on the table (no vertical integral correction from here)
phase("lower")
ZMASK[:] = [1, 1, 0, 1, 1, 1]
Tg2b = DES["gold"]
Tg2b_goal = _tr(Tg2b, [0, 0, P["h_bar"] - P["h_setup"]])
rel_nom = REL.nominal()
Trel_lo = np.linalg.inv(DES["gold"]) @ DES["silver"]       # continue from the current desired relative pose
track_objects(lambda u: (lambda Tg: {"gold": Tg, "silver": Tg @ pl.interp_T(Trel_lo, rel_nom, u)})(pl.interp_T(Tg2b, Tg2b_goal, u)),
              P["t_lower"])
# optional regrasp of the gold in the work pose (easier): the left hand opens, the gold drops onto the standing
# silver's hole edge and the table, the hand re-grasps it at regrasp2_gold_y and lifts it back to its pose
if P.get("regrasp2_gold_y") is not None:
    phase("regrasp_work")
    Tg_keep = DES["gold"]
    L.G = None
    L.grip = OPEN
    hold(1.2)
    T = L.tcp_cmd(); Tb = T.copy(); Tb[:3, 3] -= 0.05 * T[:3, 0]; Tb[2, 3] += 0.02
    cart_move({L: Tb}, 1.0)
    Tg_rest = plate_frame("gold")
    G_new = pl.gold_grasp(P["regrasp2_gold_y"], P["gold_x_tcp"], P["gold_jaw_used"])
    T_new = Tg_rest @ G_new
    s_ = None
    for up in (0.03, 0.015, 0.0):
        T_pre = T_new.copy(); T_pre[:3, 3] -= 0.05 * T_new[:3, 0]; T_pre[2, 3] += up
        s_ = seed_ik(T_pre, "left")
        print(f"[oracle] work regrasp pregrasp (up {up}) IK margin {None if s_ is None else round(s_[1], 3)}", flush=True)
        if s_ is not None:
            break
    if s_ is None:
        finish("no_ik_regrasp")
    joint_move({L: s_[0]}, 2.5)
    T_pre2 = T_new.copy(); T_pre2[:3, 3] -= 0.05 * T_new[:3, 0]
    cart_move({L: T_pre2}, 0.8)
    cart_move({L: T_new}, 1.2)
    L.grip = CLOSED
    hold(1.0)
    L.G = np.linalg.inv(plate_frame("gold")) @ L.tcp_cmd()
    L.corr = np.zeros(6)
    phase("regrasp_lift")
    Tg_m = plate_frame("gold")
    track_objects(lambda u: {"gold": pl.interp_T(Tg_m, Tg_keep, u)}, 2.5)
    hold(0.5)

# hold with relative feedback (silver follows the filtered measured gold) so the relative pose converges
GF["T"] = None
for k_ in range(int(P["t_align_hold"] / DT)):
    RFB[0] = min(1.0, (k_ + 1) / (0.75 * P["t_align_hold"] / DT))
    track_objects(lambda u: {"gold": Tg2b_goal, "silver": rel_target(Tg2b_goal, rel_nom)}, DT)
hold(0.5)

# --- key turn: gold held still, silver follows the measured gold through the route's turn stage
phase("turn")
Tg3 = DES["gold"]
f_turn, _ = REL.sampler(REL.stage("turn"))
if args.variant == "naive_pull":          # negative check: no key turn
    hold(P["t_turn"])
else:
    bw = Tg3[:3, :3] @ REL.c0 + Tg3[:3, 3]
    def f_turn_both(u):
        Tg = pl.rot_about(Tg3, Rotation.from_euler("z", P["gamma"] * u, degrees=True).as_matrix(), bw)
        return {"gold": Tg, "silver": rel_target(Tg, f_turn(u))}
    track_objects(f_turn_both, P["t_turn"])
hold(0.5)

# --- channel: relative bar point along the channel guides (+ extra past the route end);
#     the gold moves split * the world displacement the other way, the silver follows the measured gold
phase("channel")
Tg4 = DES["gold"]
f_ch, length = REL.sampler(REL.stage("channel"), extra=np.array([0.0, -P["chan_extra"], 0.0]))
if args.variant == "naive_pull":          # negative check: pull straight along the gold's -y from the start pose
    f_ch, length = REL.sampler([(REL.r0, REL.c0)], extra=np.array([0.0, -0.20, 0.0]))
rel0 = f_ch(0.0)
def f_channel(u):
    rel = f_ch(u)
    d = Tg4[:3, :3] @ (rel[:3, 3] - rel0[:3, 3])      # silver displacement relative to gold, world
    Tg = _tr(Tg4, -P["split"] * d)
    return {"gold": Tg, "silver": rel_target(Tg, rel)}
track_objects(f_channel, max(2.0, length / P["chan_speed"]), gate=True)
if args.stop_after == "channel":
    finish("stopped")

# --- separate: silver straight up
phase("silver_up")
Ts5 = DES["silver"]
track_objects(lambda u: {"silver": _tr(Ts5, np.r_[0, 0, P["sep_up"]] * u)}, 1.5)

# --- gold back down onto the table (flat), on the system side; release; left arm retreats home
phase("gold_down")
Tg6 = DES["gold"]
tgt = Tg6.copy()
tgt[2, 3] = TABLE_Z + P["gold_release_h"]
tgt[1, 3] += P["gold_dy"]
track_objects(lambda u: {"gold": pl.interp_T(Tg6, tgt, u)}, P["t_gold_down"])
phase("gold_release")
L.grip = OPEN
hold(1.0)
phase("left_retreat")
T = L.tcp_cmd(); T2 = T.copy(); T2[:3, 3] -= 0.08 * T[:3, 0]; T2[2, 3] += 0.10
cart_move({L: T2}, 1.5)
joint_move({L: np.zeros(6)}, 2.5)

# --- silver: carry upright (top-down grasp) over the goal with its long axis along world X, set it down on its
#     +x edge, then tip it over about that edge onto its face (toward +Y) and let go
phase("silver_carry")
Ts7 = DES["silver"]
g = scene.goal
lo, hi = np.array(g["xy_min"]) + 0.004, np.array(g["xy_max"]) - 0.004
xs = np.array([0, 0, -1.0])
print("[oracle] silver grasp offset G (plate->TCP):", np.round(R.G, 4).tolist(), flush=True)
np.save(os.path.join(args.out, "G_silver.npy"), R.G); np.save(os.path.join(args.out, "Ts7.npy"), DES["silver"])
cands = []
y_now = np.arctan2(Ts7[1, 1], Ts7[0, 1])
for dyaw, nsign, fxs in itertools.product(np.radians(np.arange(-90, 91, 15)), (1.0, -1.0), (0.0, 0.5, 1.0)):
    yaw = y_now + dyaw
    ys = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    n = nsign * np.cross([0, 0, 1.0], ys)              # tip direction (horizontal, perpendicular to the long axis)
    Rf = np.c_[xs, ys, np.cross(xs, ys)]
    hx = abs(ys[0]) * 0.1035 + abs(n[0]) * 0.039      # final flat footprint half extents
    hy = abs(ys[1]) * 0.1035 + abs(n[1]) * 0.039
    if np.any(hi - lo < 2 * np.r_[hx, hy] + 2 * P["place_margin"]):
        continue
    fc = np.r_[lo[0] + hx + P["place_margin"] + fxs * (hi[0] - lo[0] - 2 * hx - 2 * P["place_margin"]),
               lo[1] + hy + P["place_margin"]]
    rc = fc - n[:2] * 0.0435                            # upright release centre
    def upright(height, Rf=Rf, rc=rc):
        T = np.eye(4); T[:3, :3] = Rf
        com = Rf @ np.r_[-0.0003, -0.0024, 0.0]
        T[:3, 3] = np.r_[rc[0] - com[0], rc[1] - com[1], TABLE_Z + 0.039 + height]
        return T
    Tu = upright(P["silver_set_h"])
    edges = [Tu @ np.r_[0.039, 0.0, zz, 1.0] for zz in (-0.0045, 0.0045)]
    piv = max(edges, key=lambda q: q[:2] @ n[:2])[:3]; piv[2] = TABLE_Z
    axis = np.cross([0, 0, 1.0], n)                    # rotating about Z x n tips the top toward +n
    def tipped(deg, Tu=Tu, piv=piv, axis=axis):
        return pl.rot_about(Tu, Rotation.from_rotvec(axis * np.radians(deg)).as_matrix(), piv)
    Tl = tipped(P["silver_tip0_deg"])                  # set down already leaning toward +n
    Ta = Tl.copy(); Ta[2, 3] += P["silver_carry_h"]
    Tt = tipped(P["silver_tip_deg"])
    ms = []
    for T in (Ta, Tl, Tt):
        s_ = seed_ik(T @ R.G, "right", tries=30)
        ms.append(None if s_ is None else s_[1])
        if s_ is None:
            break
    print(f"[oracle]   place cand dyaw {np.degrees(dyaw):+.0f} n {nsign:+.0f} fx {fxs:.1f}: {ms}", flush=True)
    if len(ms) == 3 and all(m is not None for m in ms):
        cands.append((min(ms), abs(dyaw), Ta, Tl, piv, axis, np.degrees(dyaw), fc))
cands.sort(key=lambda c: -c[0])
if not cands:
    finish("no_ik_silver_place")
mrg, _, T_above, T_low, piv, axis, dyaw_deg, fc = cands[0]
print(f"[oracle] silver place: yaw change {dyaw_deg:.0f} deg, final centre {fc.round(3)}, IK margin {mrg:.3f}", flush=True)
track_objects(lambda u: {"silver": pl.interp_T(Ts7, T_above, u)}, P["t_carry"])
phase("silver_lower")
track_objects(lambda u: {"silver": pl.interp_T(T_above, T_low, u)}, 1.5)
hold(0.3)
phase("silver_tip")
tip = np.radians(P["silver_tip_deg"])
tip0 = np.radians(P["silver_tip0_deg"])
track_objects(lambda u: {"silver": pl.rot_about(T_low, Rotation.from_rotvec(axis * (tip - tip0) * u).as_matrix(), piv)},
              P["t_tip"])
phase("silver_release")
R.grip = OPEN
hold(1.0)
phase("right_retreat")
T = R.tcp_cmd(); T2 = T.copy(); T2[:3, 3] -= 0.06 * T[:3, 0]; T2[2, 3] += 0.08
cart_move({R: T2}, 1.5)
phase("wait")
for _ in range(int(P["t_wait"] / DT)):
    ck = step()
finish("done")
