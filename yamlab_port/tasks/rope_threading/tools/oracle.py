"""Scripted oracle for RopeThreading-Easy (privileged rope state, numpy YAM IK, 14-D joint targets, 30 Hz).

The END tip (link_109, last CSV row) is fed, so the crossings appear along the material in the order R1, R2.
Layout (yaw +90 deg): R1 normal +y (R1- = tip travels -y), R2 normal -x (R2+ = tip travels -x).
Stages (privileged rope state; every arm motion is IK-planned with a capsule collision check vs rings/stands/table/
other arm; grasps are friction grasps, the gripper target -1.5 mm closes on the 8 mm rope at -4.9 mm):
  ready    unfold both arms (home is a singular pose).
  pick     ledge regrasp (left): fingertip-pinch drags move the end until ~0.24 m of rope overhangs the left table
           edge (collider edge y = 0.65), then a deep top-down grasp of the overhang `--grasp_from_tip` from the tip
           (fingers below the tabletop beyond the edge), lift; back over the table, roll about the rope axis to
           approach +x pitched `--pitch`, climb to ring height, 180 deg wrist roll about the approach (tip -> -y).
  feed1    left: align the measured tip with R1's aperture, push -y until the grip is `--feed_stop` before the plane.
  recv1    right: grasp ~7 cm past R1 (approach scanned around the local rope tangent); left lets go.
  pull1    right pulls toward `--pull1_xyz` (about 0.35 m of rope through R1).
  regrip   right lowers the end to `--drop_xyz`, releases (the rope hangs from R1's rim), re-grasps the hanging rope
           deep `--regrip_from_tip` from the tip (rope-axis sign chosen so the R2 feed is reachable), lifts.
  feed2    right: re-orient (approach +y sideways, rope along -x), align the tip with R2, push -x.
  recv2    left: grasp ~7 cm past R2; right lets go.
  pull2    left pulls the end through R2 along `--pull2_wps` and lays it on the table, releases; both arms ready.
  settle   wait until the goal latches (or `--settle_max_s`).
Variants: oracle | nop (hold the start pose) | naive (feed1 passes the tip BESIDE R1, 13 cm off-axis, instead of
through it -> no R1 crossing) | naive_noR2 (the oracle up to the R1 receive, then hold still: R2 never threaded).
Usage (vast): vrun.sh 3000 oracle.py --out runs/or1 [--stop_after pick]
"""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="RopeThreading-Easy-v0")
p.add_argument("--out", default="or")
p.add_argument("--variant", default="oracle", choices=["oracle", "nop", "naive", "naive_noR2"])
p.add_argument("--stop_after", default="")
p.add_argument("--env_mode", default="evaluation", choices=["evaluation", "replay"],
               help="evaluation (deliverable: terminations on, stops at the first success); replay = no terminations "
                    "(diagnostic: lets the release finish run to its end)")
p.add_argument("--finish", default="release", choices=["hold", "release"],
               help="hold: after feed2 the right keeps the rope still until the goal latches (holding allowed); "
                    "release: left receives past R2, lays the tail on the table, both release")
p.add_argument("--save_ckpt", action="store_true", help="development: save a sim snapshot at the regrip stage")
p.add_argument("--grasp_from_tip", type=float, default=0.20)
p.add_argument("--grip_close", type=float, default=-0.0015, help="finger target when holding (jaw = -2 q; rope 8 mm)")
p.add_argument("--pitch", type=float, default=30.0)
p.add_argument("--speed", type=float, default=0.05)
p.add_argument("--feed_stop", type=float, default=0.06, help="grip point distance before the ring plane at the end of a feed")
p.add_argument("--feed_stop2", type=float, default=0.09, help="as --feed_stop, for R2 (the right gripper clears R2 only from 9 cm)")
p.add_argument("--recv_off", type=float, default=0.07, help="receiver grip point distance past the ring plane")
p.add_argument("--recv_depth", type=float, default=0.012, help="rope depth inside the pads for in-air grasps (from the TCP toward the tips)")
p.add_argument("--pull1", type=float, default=0.33)
p.add_argument("--pull1_xyz", type=float, nargs=3, default=[0.62, -0.25, 1.00])
p.add_argument("--regrip_from_tip", type=float, nargs="+", default=[0.19, 0.17, 0.21, 0.15])
p.add_argument("--drop_xyz", type=float, nargs=3, default=[0.62, -0.20, 0.92])
p.add_argument("--drop_settle_s", type=float, default=1.5)
p.add_argument("--feed2_start", type=float, default=0.21)
p.add_argument("--pull2_wps", type=json.loads, default=[[0.36, -0.02, 0.98], [0.36, 0.08, 0.86], [0.38, 0.20, 0.79]])
p.add_argument("--feed2_stage_y", type=float, default=-0.12)
p.add_argument("--drag1_from_tip", type=float, default=0.15)
p.add_argument("--drag_x", type=float, default=0.48)
p.add_argument("--drag1_y", type=float, default=0.50)
p.add_argument("--overhang", type=float, default=0.27)
p.add_argument("--reorient_x", type=float, default=0.55)
p.add_argument("--reorient_y", type=float, default=0.45)
p.add_argument("--reorient_z", type=float, default=0.85)
p.add_argument("--flip_x", type=float, default=0.60)
p.add_argument("--flip_y", type=float, default=0.40)
p.add_argument("--flip_sense", type=float, default=1.0)
p.add_argument("--feed_start_y", type=float, default=0.30)
p.add_argument("--handover_xyz", type=float, nargs=3, default=[0.40, 0.25, 0.83])
p.add_argument("--support_from_tip", type=float, nargs="+", default=[0.03])
p.add_argument("--pitch2", type=float, default=0.0, help="pitch of the sideways approach for R2")
p.add_argument("--regrip_left_off", type=float, default=0.08)
p.add_argument("--settle_max_s", type=float, default=20.0)
p.add_argument("--nop_steps", type=int, default=300)
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
app = AppLauncher(args).app

import numpy as np
import torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rt_common import Runner, make_env, frame, frame_az, OPEN, SL, GI
import yam_kin as K

env = make_env(args.task, mode=args.env_mode)
R = Runner(env, args.out)
scn = env.scn
ring = {r["name"]: r for r in scn["rings"]}
R1, R2 = ring["R1"], ring["R2"]
TABLE = 0.75
log = {}
EX, EY, EZ = np.eye(3)


def say(*a):
    print("[ORACLE]", *a); sys.stdout.flush()


def rope_pts():
    return R.centerline()


def station(from_tip):
    """Point and unit tangent (toward the end tip) at arc length `from_tip` from the end tip."""
    P = rope_pts()[::-1]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    i = int(np.searchsorted(s, from_tip)); i = min(max(i, 1), len(P) - 1)
    f = (from_tip - s[i - 1]) / (s[i] - s[i - 1])
    pt = P[i - 1] + f * (P[i] - P[i - 1])
    t = P[i - 1] - P[i]
    return pt, t / np.linalg.norm(t)


def held_offset(s, from_tip):
    """Rope station position in the TCP frame of arm s."""
    T = R.tcp(s)
    pt, t = station(from_tip)
    return T[:3, :3].T @ (pt - T[:3, 3]), T[:3, :3].T @ t


def rope_point_at_axial(c, axis, dist, max_from_tip=0.45):
    """Point on the rope polyline (searched from the end tip backwards, within `max_from_tip` of material and only
    while the rope is still on the travel side of the plane) where (p - c) . axis == dist."""
    P = rope_pts()[::-1]
    d = (P - c) @ axis
    n_max = int(max_from_tip / env.link_length)
    for i in range(min(len(P) - 1, n_max)):
        if d[i] < -0.02:
            break
        if (d[i] - dist) * (d[i + 1] - dist) <= 0 and d[i] != d[i + 1]:
            f = (dist - d[i]) / (d[i + 1] - d[i])
            s_from_tip = i * env.link_length + f * env.link_length
            return P[i] + f * (P[i + 1] - P[i]), s_from_tip
    return None, None


def tip():
    return rope_pts()[-1]


def finish(extra=None):
    m = R.save(dict(variant=args.variant, args=vars(args), stages=log, **(extra or {})))
    say("METRICS", json.dumps({k: m[k] for k in ("success", "first_success_step", "steps", "sim_time_s", "wall_time_s", "rope_state_sha16")}))
    say("FINAL", json.dumps(m["final"]))
    sys.stdout.flush(); os._exit(0)


def stage_done(name, **kw):
    if R.done and R.first_success is None:
        log["terminated_at"] = len(R.actions)
    g = R.rows[-1] if R.rows else {}
    log[name] = dict(step=len(R.actions), crossings=g.get("crossing_sequence"), **kw)
    say("STAGE", name, json.dumps(log[name], default=lambda x: np.round(np.asarray(x, float), 4).tolist()))
    if args.stop_after == name or R.done:
        finish()


def pitched(h, deg):
    pr = np.radians(deg)
    return np.cos(pr) * np.asarray(h, float) + np.array([0, 0, -np.sin(pr)])


def grip_T(s, approach, z_dir, gp, offset):
    """TCP frame with the given approach / rope axis such that the held rope point (offset in the TCP frame)
    lands on the world point gp."""
    T = frame_az(approach, z_dir)
    T[:3, 3] = gp - T[:3, :3] @ offset
    return T


def slip_report(s, from_tip, off0):
    off, _ = held_offset(s, from_tip)
    return float(np.linalg.norm(off - off0))



def cmd_T(s):
    return R.tcp(s, R.cur[0, SL[s]].numpy().astype(float)).copy()


def move_or_goto(s, T, speed):
    try:
        return R.move_route(s, T, speed=speed)
    except RuntimeError as e:
        say("line IK failed, joint-space move instead:", e)
        return R.goto(s, T, 60)


def grasp_from_behind(s, T, back=0.09):
    Tpre = T.copy(); Tpre[:3, 3] -= back * T[:3, 0]
    move_or_goto(s, Tpre, 0.12)
    R.move(s, T, speed=0.04)
    R.hold(5)
    R.set_grip(s, args.grip_close, 15)
    R.hold(15)
    check_closed(s, "grasp_" + s)


def release_and_leave(s, back=0.08, extra=None):
    R.set_grip(s, OPEN, 15)
    T = cmd_T(s); T[:3, 3] -= back * T[:3, 0]
    if extra is not None:
        T[:3, 3] += extra
    R.move(s, T, speed=0.08)
    try:
        R.move_route(s, R.tcp(s, R.q_ready[s]), speed=0.10)
    except RuntimeError as e:
        say("return to ready failed:", e)



def slerp_ok(side, T_start, R_goal, off, lift=0.08, n=13):
    """In-place rotation (about the held rope point, after a `lift` up) from T_start's orientation to R_goal:
    IK-continuous and collision-free under the capsule model?"""
    from scipy.spatial.transform import Slerp
    import plan_np as PN_
    gp = T_start[:3, :3] @ off + T_start[:3, 3] + lift * EZ
    sl = Slerp([0, 1], Rot.from_matrix(np.stack([T_start[:3, :3], R_goal])))
    q = None
    other_s = "left" if side == "right" else "right"
    other_q = R.cur[0, SL[other_s]].numpy().astype(float)
    for f in np.linspace(0, 1, n):
        Rm = sl(f).as_matrix(); T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = gp - Rm @ off
        if q is None:
            q = PN_.solve(side, T, margin=0.03)
            if q is None:
                return False
        else:
            qn, o, ep, er = K.ik(K.world_to_base(T, side), q, iters=200, margin=0.02)
            if not (o or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.5:
                return False
            q = qn
        if min(PN_.arm_clearance(side, q, R.fix, other=(other_s, other_q, True), grip_open=False).values()) < 0.008:
            return False
    return True


def safe_shift(s, delta, speed=0.03):
    """Translate arm s by `delta` (or the largest of 100/75/50/25 % of it that is IK-feasible and collision-free)."""
    for f in (1.0, 0.75, 0.5, 0.25):
        T = cmd_T(s); T[:3, 3] += f * np.asarray(delta)
        try:
            R.move(s, T, speed=speed)
            if f < 1.0:
                say("safe_shift: applied", f, "of", np.round(delta, 3))
            return f
        except RuntimeError:
            continue
    say("safe_shift: no part of", np.round(delta, 3), "feasible")
    return 0.0


def finger_low_z(T):
    """Lowest z of the open fingers' pad corners (tips +-0.037 along approach, +-0.0475+0.02 along the jaw, +-0.035 along z)."""
    pts = [T[:3, 3] + T[:3, :3] @ np.array([x, y, z]) for x in (-0.037, 0.037) for y in (-0.07, 0.07) for z in (-0.035, 0.035)]
    return min(p[2] for p in pts)


_GB = np.array([[x, y, z] for x in np.linspace(-0.13, 0.04, 6) for y in np.linspace(-0.07, 0.07, 5)
                for z in np.linspace(-0.035, 0.10, 5)])   # gripper + wrist + camera envelope in the TCP frame


def gripper_clearance(Ta, Tb):
    pa = Ta[:3, 3] + _GB @ Ta[:3, :3].T
    pb = Tb[:3, 3] + _GB @ Tb[:3, :3].T
    return float(np.min(np.linalg.norm(pa[:, None] - pb[None], axis=2)))


def other(s):
    return "right" if s == "left" else "left"


def retreat(s, dists=(0.08, 0.05, 0.03)):
    """Leave the rope after opening: up, else up + toward the arm base, else back along the approach."""
    base = np.array([0.2525, 0.305 if s == "left" else -0.305, 0.76])
    for d in dists:
        T0 = cmd_T(s)
        to_base = base - T0[:3, 3]; to_base[2] = 0; to_base /= max(np.linalg.norm(to_base), 1e-9)
        for off in (d * EZ, d * EZ + 0.05 * to_base, -d * T0[:3, 0]):
            T = T0.copy(); T[:3, 3] += off
            try:
                R.move(s, T, speed=0.05)
                return True
            except RuntimeError:
                continue
    say("retreat failed for", s)
    return False


def deep_grasp_T(s, from_tip, approaches, min_clear=0.03):
    pt, t = station(from_tip)
    To = cmd_T(other(s))
    for a in approaches:
        a = np.asarray(a, float)
        if abs(a @ t) > 0.5:
            continue
        for zs in (1, -1):
            T = grip_T(s, a, zs * t, pt, np.array([args.recv_depth, 0, 0]))
            Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * T[:3, 0]
            if finger_low_z(T) < TABLE + 0.015:
                continue
            if min(gripper_clearance(T, To), gripper_clearance(Tpre, To)) < min_clear:
                continue
            if R.reachable(s, T) and R.reachable(s, Tpre):
                return T
    return None


def check_closed(s, name):
    f = R.finger(s)
    if f < -0.0065:     # jaw wider than ~13 mm: blocked by something other than the 8 mm rope
        stage_done(name + "_blocked", finger=f)
        finish()


def receiver_T(side, c, axis, dists=(0.07, 0.06, 0.05, 0.08), extra_check=None):
    """Grasp of the rope `dist` past the ring plane (centre c, travel `axis`): approach scanned in the plane
    perpendicular to the local rope tangent, both rope-axis signs, rope 12 mm inside the pads, pre-grasp 9 cm back.
    Returns (T, dist, from_tip) or None."""
    for dist in dists:
        rp, s_r = rope_point_at_axial(c, axis, dist)
        if rp is None:
            continue
        P = rope_pts()[::-1]
        i = min(int(s_r / env.link_length), len(P) - 2)
        t = P[i] - P[i + 1]; t /= np.linalg.norm(t)
        u = np.cross(t, EZ); u /= np.linalg.norm(u); v = np.cross(u, t)
        cands = []
        for phi in range(0, 360, 15):
            a = np.cos(np.radians(phi)) * u + np.sin(np.radians(phi)) * v
            for zs in (1, -1):
                T = grip_T(side, a, zs * t, rp, np.array([args.recv_depth, 0, 0]))
                Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * a
                if finger_low_z(T) < TABLE + 0.015:
                    continue
                if R.reachable(side, T, grip_open=False) and R.reachable(side, Tpre):
                    ok_x = extra_check(zs) if extra_check is not None else True
                    cands.append((ok_x, -a[2], T, zs))          # prefer extra_check, then approaches from above
        if cands:
            cands.sort(key=lambda c_: (not c_[0], -c_[1]))
            if extra_check is not None and not cands[0][0]:
                say("receiver: no candidate passes the extra check at", dist)
            receiver_T.last_zs = cands[0][3]
            return cands[0][2], dist, s_r
    return None


def point_before_plane(c, travel, dist):
    """Rope point `dist` before the plane (opposite to the travel direction), found along the material from the tip:
    first the crossing nearest to the tip, then backward. Returns (point, from_tip) or (None, None)."""
    P = rope_pts()[::-1]
    d = (P - c) @ travel                   # > 0 past the plane
    for i in range(len(P) - 1):
        if d[i] > 0 >= d[i + 1]:
            for j in range(i + 1, len(P) - 1):
                if (-d[j] - dist) * (-d[j + 1] - dist) <= 0:
                    f = (dist + d[j]) / (d[j] - d[j + 1])
                    return P[j] + f * (P[j + 1] - P[j]), (j + f) * env.link_length
            break
    return None, None


def _hook(t, v, tb):
    import traceback
    from rt_common import EpisodeDone
    if isinstance(v, EpisodeDone):
        log["episode_end"] = v.args[0]
        say("EPISODE END", v.args[0], "success", R.first_success is not None)
    else:
        traceback.print_exception(t, v, tb)
        log["exception"] = repr(v)
    finish()


sys.excepthook = _hook
R.hold(10)
if args.variant == "nop":
    R.hold(args.nop_steps)
    finish()

# ======================================================================== ready: unfold both arms (home is singular)
for side, y in (("right", -0.30), ("left", 0.30)):     # probes/ready_probe.py: reachable, path from home clear
    R.goto(side, frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, y, 0.95)), 45)
R.hold(5)
R.q_ready = {sd: R.cur[0, SL[sd]].numpy().astype(float).copy() for sd in ("left", "right")}

# ======================================================================== pick (left): ledge regrasp
# A rope lying on the table can only be pinched in the last ~2 mm of the YAM pads; that pinch survives translations
# but the rope pivots / pops out under re-orientation and lifting (runs t5, t18, t22). So: pinch-drag the end until
# its last `--overhang` m stick out past the left table edge (y = 0.55), release, then grasp the overhang deep
# (fingers below the tabletop level, beyond the edge), lift.
TABLE_EDGE_Y = 0.65                     # workstation.usd table_surface collider edge (nominal yam.yaml: 0.55)
a_down = -EZ
DEPTH_TABLE = 0.035                    # rope centre 2 mm above the fingertips (tips at +0.037 along approach)
a1 = pitched(EX, args.pitch)
from scipy.spatial.transform import Rotation as Rot


def rotate_about_grip(s, Rw, off, speed=0.04, ang_speed=0.4):
    T0 = cmd_T(s)
    gp = T0[:3, :3] @ off + T0[:3, 3]
    T1 = np.eye(4); T1[:3, :3] = Rw @ T0[:3, :3]
    T1[:3, 3] = gp - T1[:3, :3] @ off
    try:
        R.move(s, T1, speed=speed, ang_speed=ang_speed)
    except RuntimeError as e:
        say("rotate line failed, routed:", str(e)[:120])
        R.move_route(s, T1, speed=speed, ang_speed=ang_speed)
    R.hold(15)


def pinch(from_tip, shift=None, fail=True):
    """Top-down fingertip pinch; `shift` (world vector) = the planned drag, whose end pose must be reachable too."""
    pt, t = station(from_tip)
    t_h = t - EZ * (t @ EZ); t_h /= np.linalg.norm(t_h)
    for zs in (-1, 1):
        Tg = frame_az(a_down, zs * t_h); Tg[:3, 3] = pt - DEPTH_TABLE * a_down
        Tpre = Tg.copy(); Tpre[:3, 3] += 0.08 * EZ
        ok = R.reachable("left", Tg) and R.reachable("left", Tpre)
        if ok and shift is not None:
            for f in (0.5, 1.0):
                Tm = Tg.copy(); Tm[:3, 3] += f * np.asarray(shift) + 0.03 * EZ
                ok &= R.reachable("left", Tm, grip_open=False)
        if ok:
            break
    else:
        if not fail:
            return None
        stage_done("pick_failed", reason=f"pinch at {from_tip} unreachable", pt=pt); finish()
    move_or_goto("left", Tpre, 0.15)
    R.move("left", Tg, speed=0.04)
    R.hold(5)
    R.set_grip("left", args.grip_close, 15)
    R.hold(15)
    off, _ = held_offset("left", from_tip)
    T = cmd_T("left"); T[:3, 3] += 0.03 * EZ
    R.move("left", T, speed=0.03)
    R.hold(10)
    return off


def overhang_len():
    """Rope arc length beyond the left table edge (from the end tip back to the first point inside)."""
    P = rope_pts()[::-1]
    inside = np.flatnonzero(P[:, 1] <= TABLE_EDGE_Y)
    if not len(inside):
        return np.inf
    k = inside[0]
    return float(np.linalg.norm(np.diff(P[:k + 1], axis=0), axis=1).sum())


def put_down_release():
    T = cmd_T("left"); T[:3, 3] -= 0.03 * EZ
    try:
        R.move("left", T, speed=0.03)
    except RuntimeError as e:
        say("put down: cannot lower, releasing from 3 cm:", str(e)[:80])
    R.hold(5)
    R.set_grip("left", OPEN, 12)
    retreat("left")
    R.hold(10)


# drag 1: pinch near the end, yaw so the tip points +y, carry toward the edge
off = pinch(args.drag1_from_tip)
T0 = cmd_T("left")
tipdir = station(args.drag1_from_tip)[1]
ang = np.arctan2(np.cross(tipdir * [1, 1, 0], EY) @ EZ, (tipdir * [1, 1, 0]) @ EY)
rotate_about_grip("left", Rot.from_rotvec(EZ * ang).as_matrix(), off)
off, _ = held_offset("left", args.drag1_from_tip)
T = cmd_T("left"); gp = T[:3, :3] @ off + T[:3, 3]
cands = sorted(((y, x) for y in np.arange(args.drag1_y, 0.34, -0.02) for x in (args.drag_x, 0.52, 0.56, 0.60, 0.64)),
               key=lambda c: (-c[0], abs(c[1] - args.drag_x)))
for y, x in cands:
    Tc = T.copy(); Tc[:3, 3] += np.array([x, y, gp[2]]) - gp
    if R.reachable("left", Tc, grip_open=False):
        try:
            R.move_route("left", Tc, speed=0.04)
        except RuntimeError as e:
            say("drag1 candidate", (round(x, 2), round(y, 2)), "failed:", str(e)[:80])
            continue
        say("drag1 to", (round(x, 2), round(y, 2)))
        break
R.hold(10)
put_down_release()
say("after drag1: tip", np.round(tip(), 3))
# drag 2..: pinch 6 cm inside the edge, carry the end toward (drag_x, edge + overhang) by the largest reachable step
for it in range(6):
    tp = tip()
    over_now = overhang_len()
    want = np.array([args.drag_x - tp[0], args.overhang - over_now, 0.0])
    if over_now >= args.overhang - 0.01 and abs(want[0]) < 0.04:
        break
    ft2 = max(0.12, over_now + 0.07)
    off = None
    for step in (0.12, 0.08, 0.05, 0.03):
        sh = want * min(1.0, step / max(np.linalg.norm(want), 1e-9))
        for sh_try in (sh, np.array([sh[0], 0, 0]), np.array([0, sh[1], 0])):
            if np.linalg.norm(sh_try) < 0.01:
                continue
            off = pinch(ft2, shift=sh_try, fail=False)
            if off is not None:
                sh = sh_try
                break
        if off is not None:
            break
    if off is None:
        stage_done("pick_failed", reason="no reachable drag step", tip=tip()); finish()
    T = cmd_T("left"); T[:3, 3] += sh
    R.move("left", T, speed=0.03)
    R.hold(10)
    put_down_release()
    say("after drag2.%d (shift %s): tip" % (it, np.round(sh, 3)), np.round(tip(), 3), "overhang arc", round(overhang_len(), 3))
# deep grasp of the overhang, top-down, rope 12 mm inside the pads, z_tcp = tip direction (+y)
GF = args.grasp_from_tip
pt, t = station(GF)
zs1 = 1
Tg = frame_az(a_down, t); Tg[:3, 3] = pt - args.recv_depth * a_down
Tpre = Tg.copy(); Tpre[:3, 3] += 0.07 * EZ
move_or_goto("left", Tpre, 0.12)
R.move("left", Tg, speed=0.03)
R.hold(5)
R.set_grip("left", args.grip_close, 15)
R.hold(15)
check_closed("left", "deep_grasp")
off_pick, _ = held_offset("left", GF)
T = cmd_T("left"); T[:3, 3] += 0.06 * EZ
R.move("left", T, speed=0.03)
R.hold(15)
slip_lift = slip_report("left", GF, off_pick)
stage_done("ledge_grasp", held_offset=off_pick, slip_after_lift_m=slip_lift, tip=tip())
# re-orient for feeding: back over the table, roll about the rope axis to the feed approach a1 (tip still +y),
# climb, then a 180 deg wrist roll about the approach (tip -> -y; the trailing rope then runs +y to the dragged end)
off_now, _ = held_offset("left", GF)
T = cmd_T("left"); gp = T[:3, :3] @ off_now + T[:3, 3]
T[:3, 3] += np.array([args.reorient_x, args.reorient_y, args.reorient_z]) - gp
R.move_route("left", T, speed=0.03)
R.hold(10)
T0 = cmd_T("left")
ax = T0[:3, 2]
a_t = a1 - ax * (ax @ a1); a_t /= np.linalg.norm(a_t)
ang = np.arctan2(np.cross(T0[:3, 0], a_t) @ ax, T0[:3, 0] @ a_t)
off_now, _ = held_offset("left", GF)
rotate_about_grip("left", Rot.from_rotvec(ax * ang).as_matrix(), off_now)
off_now, _ = held_offset("left", GF)
T = cmd_T("left"); gp = T[:3, :3] @ off_now + T[:3, 3]
T[:3, 3] += np.array([args.flip_x, args.flip_y, R1["center"][2] - 0.01]) - gp
R.move_route("left", T, speed=0.03)
R.hold(10)
say("before flip: held offset", np.round(held_offset("left", GF)[0], 4), "tip", np.round(tip(), 3))
for k in range(18):
    off_now, _ = held_offset("left", GF)
    a_now = cmd_T("left")[:3, 0]
    rotate_about_grip("left", Rot.from_rotvec(a_now * np.radians(10.0 * args.flip_sense)).as_matrix(), off_now,
                      speed=0.03, ang_speed=0.5)
zs1 = 1 if (cmd_T("left")[:3, 2] @ -EY) > 0 else -1
# settle onto the exact feed frame: approach a1, rope axis along the tip direction -y
off_now, _ = held_offset("left", GF)
T0 = cmd_T("left")
Tf = frame_az(a1, zs1 * -EY)
rotate_about_grip("left", Tf[:3, :3] @ T0[:3, :3].T, off_now, speed=0.03, ang_speed=0.4)
off_rot, _ = held_offset("left", GF)
stage_done("pick", zsign=zs1, finger=R.finger("left"), held_offset_deep=off_pick, held_offset_after_reorient=off_rot,
           approach=cmd_T("left")[:3, 0], rope_axis=cmd_T("left")[:3, 2], tip=tip())
# traverse to the feed start (tip on the +y side of R1)
off, _ = held_offset("left", GF)
T = cmd_T("left"); gp = T[:3, :3] @ off + T[:3, 3]
T[:3, 3] += np.array([R1["center"][0], args.feed_start_y, R1["center"][2] - 0.01]) - gp
move_or_goto("left", T, 0.03)
R.hold(10)
say("at feed start: held offset", np.round(held_offset("left", GF)[0], 4), "tip", np.round(tip(), 3))

# ======================================================================== feed1 (left)
off, _ = held_offset("left", GF)
tpm = tip(); Tm = R.tcp("left")
say("feed1 mid: tip", np.round(tpm, 4), "TCP", np.round(Tm[:3, 3], 4), "tip in TCP frame", np.round(Tm[:3, :3].T @ (tpm - Tm[:3, 3]), 4),
    "held offset", np.round(held_offset("left", GF)[0], 4))
# align the measured tip with the aperture centre (tip droops below the grip point)
over = args.variant == "naive"
for it in range(2):
    tp = tip()
    # naive: the tip passes beside R1 (13 cm off-axis in x: outside the ring and its stand) instead of through it
    target_tip = R1["center"] + (np.array([0.13, 0.0, -0.01]) if over else np.array([0.0, 0.0, -0.01]))
    corr = target_tip - tp
    corr[1] = 0.0
    safe_shift("left", corr, args.speed)
    R.hold(15)
off, _ = held_offset("left", GF)
gp_now = R.tcp("left")[:3, :3] @ off + R.tcp("left")[:3, 3]
stroke = (gp_now[1] - (R1["center"][1] + args.feed_stop))
T_end = R.tcp("left", R.cur[0, SL["left"]].numpy().astype(float)).copy(); T_end[:3, 3] += -stroke * EY
R.move("left", T_end, speed=args.speed)
R.hold(20)
tp = tip()
stage_done("feed1", tip_past_R1_m=float(-(tp - R1["center"]) @ EY), tip_radial_m=float(np.hypot(tp[0] - R1["center"][0], tp[2] - R1["center"][2])),
           slip_m=slip_report("left", GF, off))

# ======================================================================== recv1 (right)
res = receiver_T("right", R1["center"], -EY)
if res is None:
    stage_done("recv1_failed", reason="no reachable receiver grasp past R1", tip=tip())
    finish()
T_r, dist_r, s_r = res
say("recv1: grasp", round(dist_r, 3), "past R1, approach", np.round(T_r[:3, 0], 3))
T_rpre = T_r.copy(); T_rpre[:3, 3] -= 0.09 * T_r[:3, 0]
move_or_goto("right", T_rpre, 0.12)
R.move("right", T_r, speed=0.03)
R.hold(5)
R.set_grip("right", args.grip_close, 15)
R.hold(15)
check_closed("right", "recv1")
R.set_grip("left", OPEN, 15)
T_lb = cmd_T("left"); T_lb[:3, 3] += -0.08 * T_lb[:3, 0] + 0.03 * EY
try:
    R.move("left", T_lb, speed=0.06)
except RuntimeError:
    retreat("left")
move_or_goto("left", R.tcp("left", R.q_ready["left"]), 0.10)
R.hold(10)
s_hold_r = s_r
off_r1, _ = held_offset("right", s_hold_r)
stage_done("recv1", s_from_tip=s_hold_r, held_offset=off_r1)
if args.variant == "naive_noR2":
    # naive: the oracle with the R2 feed removed -> the rope stays threaded through R1 only, held still
    R.hold(int(args.settle_max_s * 30))
    stage_done("naive_hold", success=R.first_success is not None)
    finish()

# ======================================================================== pull1 (right)
# pull the tip through R1 toward a comfortable spot of the right arm; the orientation may change on the way
T0 = cmd_T("right")
zs_r = 1.0 if T0[:3, 2] @ -EY > 0 else -1.0
pull_target = np.array(args.pull1_xyz)
off_r, _ = held_offset("right", s_hold_r)
T_p = None
for p_ in (45, 30, 60, 0):
    T = frame_az(pitched(EX, p_), zs_r * -EY); T[:3, 3] = pull_target - T[:3, :3] @ off_r
    if R.reachable("right", T, grip_open=False):
        T_p = T; break
if T_p is None:
    stage_done("pull1_failed", reason="pull target unreachable"); finish()
R.move_route("right", T_p, speed=args.speed)
R.hold(20)
stage_done("pull1", slip_m=slip_report("right", s_hold_r, off_r1), tip=tip(), past_R1=float(-(tip() - R1["center"]) @ EY))
if args.stop_after == "pull1":
    finish()

# ======================================================================== regrip by the right alone (drop and re-grasp the hanging rope)
a3 = pitched(EY, args.pitch2)
gp_mid2 = R2["center"] + np.array([args.feed2_start, 0.0, 0.0])
gp_end2 = R2["center"] + np.array([args.feed_stop2, 0.0, -0.01])
off_r, _ = held_offset("right", s_hold_r)
T = cmd_T("right"); gp = T[:3, :3] @ off_r + T[:3, 3]
T[:3, 3] += np.array(args.drop_xyz) - gp
R.move_route("right", T, speed=args.speed)
R.hold(10)
R.set_grip("right", OPEN, 15)
retreat("right", dists=(0.06, 0.04))
R.hold(int(30 * args.drop_settle_s))
stage_done("drop", tip=tip(), past_R1=float(-(tip() - R1["center"]) @ EY))


def feed2_ok(zs):
    off_ = np.array([args.recv_depth, 0, 0])
    for p_ in (30, 0, 45, 60, 15):
        a_c = pitched(EY, p_)
        if all(R.reachable("right", grip_T("right", a_c, zs * -EX, g_, off_), grip_open=False) for g_ in (gp_mid2, gp_end2)):
            return True
    return False


say("feed2 frames reachable: z_tcp toward the tip", feed2_ok(1), "| away from the tip", feed2_ok(-1))


GF2 = None
for ft in args.regrip_from_tip:
    pt2, t2 = station(ft)
    u = np.cross(t2, EZ); u /= np.linalg.norm(u) if np.linalg.norm(u) > 1e-6 else 1.0
    if np.linalg.norm(u) < 0.5:
        u = np.cross(t2, EX); u /= np.linalg.norm(u)
    v = np.cross(u, t2)
    cands = []
    for phi in range(0, 360, 15):
        a = np.cos(np.radians(phi)) * u + np.sin(np.radians(phi)) * v
        for zs in (1, -1):
            T = grip_T("right", a, zs * t2, pt2, np.array([args.recv_depth, 0, 0]))
            Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * a
            if finger_low_z(T) < TABLE + 0.012:
                continue
            if R.reachable("right", T, grip_open=False) and R.reachable("right", Tpre):
                f2 = feed2_ok(zs)
                ro = f2 and any(slerp_ok("right", T, frame_az(pitched(EY, p_), zs * -EX)[:3, :3], np.array([args.recv_depth, 0, 0]))
                                for p_ in (0, 30, 15))
                cands.append((f2 and ro, f2, -a[2], zs, T))
    if cands:
        cands.sort(key=lambda c_: (not c_[0], not c_[1], -c_[2]))
        say("regrip candidates at", ft, ":", len(cands), "reorient-feasible:", sum(c_[0] for c_ in cands))
        if not cands[0][0]:
            continue
        _, ok2, _, zs2, T_rg = cands[0]
        GF2 = ft
        say("regrip at", ft, "from the tip: point", np.round(pt2, 3), "tangent", np.round(t2, 2), "approach", np.round(T_rg[:3, 0], 2),
            "feed2 reachable", ok2)
        break
if GF2 is None:
    stage_done("regrip_failed", reason="right cannot re-grasp the hanging rope", tip=tip()); finish()
grasp_from_behind("right", T_rg)
T = cmd_T("right"); T[:3, 3] += 0.08 * EZ
move_or_goto("right", T, 0.03)
R.hold(10)
off_rg, _ = held_offset("right", GF2)
stage_done("regrip", from_tip=GF2, held_offset=off_rg, tip=tip())
if args.save_ckpt:
    R.snapshot(os.path.join(args.out, "ckpt_regrip.pt"), dict(GF2=GF2, GF=GF, zs1=zs1, s_hold_r=s_hold_r))
# @@RESUME regrip
if args.stop_after == "regrip":
    finish()

# ======================================================================== feed2 (right)
def reorient(s, R_goal, from_tip, step_deg=10.0):
    """Rotate the held rope about the grip point onto the orientation R_goal in small slerp steps."""
    from scipy.spatial.transform import Slerp
    T0 = cmd_T(s)
    rv = Rot.from_matrix(R_goal @ T0[:3, :3].T).as_rotvec()
    n = max(1, int(np.ceil(np.degrees(np.linalg.norm(rv)) / step_deg)))
    for k in range(n):
        off_now, _ = held_offset(s, from_tip)
        try:
            rotate_about_grip(s, Rot.from_rotvec(rv / n).as_matrix(), off_now, speed=0.03, ang_speed=0.5)
        except RuntimeError as e:
            T0 = cmd_T(s); gp = T0[:3, :3] @ off_now + T0[:3, 3]
            T1 = np.eye(4); T1[:3, :3] = Rot.from_rotvec(rv / n).as_matrix() @ T0[:3, :3]; T1[:3, 3] = gp - T1[:3, :3] @ off_now
            say("reorient step", k, "line failed, joint-space step:", str(e)[:60])
            R.goto(s, T1, 12)


# physical rope-axis sign: z_tcp = zs2 * (tip direction); the feed frame needs the tip toward -x
off_rg, _ = held_offset("right", GF2)
Tn = cmd_T("right"); gpn = Tn[:3, :3] @ off_rg + Tn[:3, 3]
zs2 = 1.0 if Tn[:3, 2] @ (tip() - gpn) > 0 else -1.0
a3 = None
for p_ in (0, 30, 15, 45, 60):
    a_c = pitched(EY, p_)
    if all(R.reachable("right", grip_T("right", a_c, zs2 * -EX, g_, off_rg), grip_open=False) for g_ in (gp_mid2, gp_end2)) \
            and slerp_ok("right", cmd_T("right"), frame_az(a_c, zs2 * -EX)[:3, :3], off_rg, lift=0.0):
        a3 = a_c; break
if a3 is None:
    stage_done("feed2_failed", reason="no feed approach reachable for the held rope-axis sign", zsign=zs2); finish()
say("feed2: approach", np.round(a3, 3), "zsign", zs2)
reorient("right", frame_az(a3, zs2 * -EX)[:3, :3], GF2)
off_rg, _ = held_offset("right", GF2)
T = cmd_T("right"); gp = T[:3, :3] @ off_rg + T[:3, 3]
T[:3, 3] += gp_mid2 - gp
R.move_route("right", T, speed=args.speed)
R.hold(15)
for it in range(2):
    tp = tip()
    corr = R2["center"] + np.array([0.0, 0.0, -0.01]) - tp
    corr[0] = 0.0
    safe_shift("right", corr, args.speed)
    R.hold(15)
off2, _ = held_offset("right", GF2)
gp_now = R.tcp("right")[:3, :3] @ off2 + R.tcp("right")[:3, 3]
T = cmd_T("right"); T[:3, 3] += -(gp_now[0] - (R2["center"][0] + args.feed_stop2)) * EX
R.move("right", T, speed=args.speed)
R.hold(20)
tp = tip()
stage_done("feed2", tip_past_R2_m=float(-(tp - R2["center"]) @ EX), tip_radial_m=float(np.hypot(tp[1] - R2["center"][1], tp[2] - R2["center"][2])),
           slip_m=slip_report("right", GF2, off2))

if args.finish == "hold":
    # holding is allowed by the old task: keep the right still and wait for the goal to latch
    R.hold(int(args.settle_max_s * 30))
    stage_done("settle_hold", success=R.first_success is not None)
    finish()

# ======================================================================== recv2 (left)
res = receiver_T("left", R2["center"], -EX)
if res is None:
    stage_done("recv2_failed", reason="no reachable receiver grasp past R2", tip=tip()); finish()
T_l2, dist_l2, s_r2 = res
say("recv2: grasp", round(dist_l2, 3), "past R2, approach", np.round(T_l2[:3, 0], 3))
grasp_from_behind("left", T_l2)
R.set_grip("right", OPEN, 15)
retreat("right")
move_or_goto("right", R.tcp("right", R.q_ready["right"]), 0.10)
R.hold(10)
stage_done("recv2", s_from_tip=s_r2, held_offset=held_offset("left", s_r2)[0])
if args.stop_after == "recv2":
    finish()

# ======================================================================== pull2 + lay (left)
# pull the end through R2 and lay it on the table in front of R2 (toward +y), so the tail rests on the table
off_l2, _ = held_offset("left", s_r2)
for wp in args.pull2_wps:
    wp = np.asarray(wp, float)
    T0 = cmd_T("left")
    done = False
    for p_ in (None, 45, 60, 30, 75):
        if p_ is None:
            T = T0.copy()
        else:
            zl = 1.0 if T0[:3, 2] @ -EX > 0 else -1.0
            T = frame_az(pitched(-EY, p_), zl * -EX)
        T[:3, 3] = wp - T[:3, :3] @ off_l2
        if not R.reachable("left", T, grip_open=False):
            continue
        try:
            R.move_route("left", T, speed=args.speed)
            done = True
            break
        except RuntimeError as e:
            say("pull2 waypoint", np.round(wp, 3), "pitch", p_, "failed:", str(e)[:80])
    say("pull2 waypoint", np.round(wp, 3), "reached" if done else "SKIPPED", "tip", np.round(tip(), 3))
    R.hold(10)
stage_done("pull2", tip=tip())
# lower the grip point to the table and release
T = cmd_T("left"); gp = T[:3, :3] @ off_l2 + T[:3, 3]
T[:3, 3] += (TABLE + 0.006 - gp[2]) * EZ
try:
    R.move("left", T, speed=0.03)
except RuntimeError as e:
    say("cannot lower to the table:", str(e)[:80])
R.hold(10)
R.set_grip("left", OPEN, 20)
retreat("left")
move_or_goto("left", R.tcp("left", R.q_ready["left"]), 0.10)
stage_done("release")
# ======================================================================== settle
n_max = int(args.settle_max_s * 30)
for k in range(n_max):
    if R.step() or R.first_success is not None:
        break
R.hold(15)
stage_done("settle", success=R.first_success is not None)
finish()
