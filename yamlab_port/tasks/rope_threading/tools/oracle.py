"""Scripted oracle for RopeThreading Easy / Medium (privileged rope state, numpy YAM IK, 14-D joint targets, 30 Hz).

The END tip (link_109, last CSV row) is fed, so the crossings appear along the material in the scene's ring order
(easy R1-, R2+; medium R1-, R2+, R3+). Ring k's travel direction d_k = sign_k * normal_k comes from the scene.
Every arm motion is IK-planned with a capsule collision check vs rings/stands/table/other arm; grasps are friction
grasps (the gripper target -1.5 mm closes on the 8 mm rope at -4.9 mm). `--chain` gives each ring's feeding and
receiving arm (easy LR,R: the left picks and feeds R1, the right receives, re-grasps and feeds R2).
--feed_tip start feeds the START tip instead: rings in reverse order, each travel reversed, the right arm picks (the
crossings along the material are the same). Stage k counts the rings in feeding order.
  ready    unfold both arms (home is a singular pose).
  pick     ledge regrasp (left): fingertip-pinch drags move the end until ~0.24 m of rope overhangs the left table
           edge (collider edge y = 0.65), then a deep top-down grasp of the overhang `--grasp_from_tip` from the tip
           (fingers below the tabletop beyond the edge), lift. easy: back over the table, roll about the rope axis to
           approach +x pitched `--pitch`, climb to ring height, 180 deg wrist roll about the approach (tip -> -y).
  per ring k (feeder s):
  orient   bring the held rope onto ring k's feed frame (rope axis along d_k, approach perpendicular to it, the
           whole stroke reachable): keep the orientation if it already is one, else rotate about the grip point at
           the first of `--orient_vias` (ring 1) / the current position where that rotation is feasible; go to
           the grip point `--feed_start` before the plane.
  feed     align the measured tip with the aperture centre, push along d_k until the grip is `--feed_stop` before
           the plane. The last ring ends here.
  recv     other arm: grasp ~7 cm past the plane (approach scanned around the local rope tangent); s lets go.
  repush   (chain entry like LL: the feeder also receives) the other arm clamps the rope behind the ring, the feeder
           re-grasps `--repush_from` before the plane and pushes again (`--repush` times); then it lets go under
           the clamp and receives past the ring itself (the clamp lets go).
  pull     the receiver pulls the end toward `--pull_xyz[k]`.
  regrip   the receiver lowers the end to `--drop_xyz[k]`, releases (the rope hangs from ring k's rim), and ring k+1's
           feeder re-grasps the hanging rope deep `--regrip_from_tip` from the tip (rope-axis sign chosen so the next
           feed is reachable), lifts. With `--handover` 1 (different arms) there is no drop: the feeder grasps while the
           receiver still holds the tip, then the receiver lets go.
  lay      (--lay, instead of pull + drop + regrip when the receiver feeds the next ring) the receiver drags the end on the
           table under ring k+1's feed line, lets go, pinches it `f` from the tip and lifts; orient then also requires the
           whole push to be feasible (medium D12, R1).
  finish   hold: the feeder keeps the rope still until the goal latches. release (easy): the other arm receives past
           the last ring, pulls the end along `--finish_wps`, lays it on the table, both release; settle.
Variants: oracle | nop (hold the start pose) | naive (the first feed passes the tip BESIDE ring 1, 13 cm off-axis,
instead of through it -> no ring-1 crossing) | naive_nolast (the oracle up to the receive at the second-to-last
ring, then hold still: the last ring is never threaded).
Development: --save_ckpt saves a snapshot after the pick, after every receive and after every regrip; --resume <ckpt> continues from it
(never a deliverable).
Usage: run.sh 3600 oracle.py --out runs/or1 [--task RopeThreading-Medium-v0] [--stop_after pick]
"""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("--task", default="RopeThreading-Easy-v0")
p.add_argument("--out", default="or")
p.add_argument("--variant", default="oracle", choices=["oracle", "nop", "naive", "naive_nolast"])
p.add_argument("--stop_after", default="")
p.add_argument("--env_mode", default="evaluation", choices=["evaluation", "replay"],
               help="evaluation (deliverable: terminations on, stops at the first success); replay = no terminations "
                    "(diagnostic: lets the release finish run to its end)")
p.add_argument("--finish", default=None, choices=["hold", "release"],
               help="hold: after the last feed the feeder keeps the rope still until the goal latches (holding allowed); "
                    "release: the other arm receives past the last ring, lays the tail on the table, both release")
p.add_argument("--save_ckpt", action="store_true", help="development: save a sim snapshot after the pick, every receive and every regrip")
p.add_argument("--resume", default="", help="development: continue from a --save_ckpt snapshot")
p.add_argument("--grasp_from_tip", type=float, default=0.20)
p.add_argument("--grip_close", type=float, default=-0.0015, help="finger target when holding (jaw = -2 q; rope 8 mm)")
p.add_argument("--pitch", type=float, default=30.0)
p.add_argument("--speed", type=float, default=0.05)
# per ring k (tier defaults in TIER_DEFAULTS); pull / drop: every ring but the last
p.add_argument("--feed_start", type=float, nargs="+", default=None, help="grip point distance before the plane at the feed start")
p.add_argument("--feed_stop", type=float, nargs="+", default=None, help="grip point distance before the plane at the end of a feed")
p.add_argument("--pull_xyz", type=json.loads, default=None, help="grip point targets of the pulls (JSON list of xyz)")
p.add_argument("--drop_xyz", type=json.loads, default=None, help="grip point where the receiver lets the end go (JSON list of xyz)")
p.add_argument("--orient_vias", type=json.loads, default=None, help="grip points tried for the rotation onto the ring-1 feed frame")
p.add_argument("--chain", type=lambda v: v.split(","), default=None,
               help="per ring in feeding order: feeding arm + receiving arm (L/R), the last ring feeding arm only, e.g. LR,R")
p.add_argument("--flip", type=int, default=None, help="1: easy's roll + 180 deg wrist roll onto the ring-1 feed frame after the pick")
p.add_argument("--ledge_align", type=int, default=None, help="1: close the deep ledge grasp along the rope's actual tangent")
p.add_argument("--reseat", type=int, default=None, help="1: after the ledge grasp, press the free end flat on the table")
p.add_argument("--reseat_at", type=json.loads, default=None, help="reseat grip point x, y and the tip's yaw (deg); default: "
               "0.25 m inside PK's edge, yaw kept")
p.add_argument("--reseat_roll", type=float, default=None, help="after the reseat, roll this much (deg) about the rope axis "
               "(jaw axis -> vertical: gravity no longer turns the rope in the fingertip pinch)")
p.add_argument("--feed_cone", type=float, default=None, help="a feed direction may deviate up to this much (deg) from d_k")
p.add_argument("--repush", type=int, nargs="+", default=None, help="per ring but the last, for a feeder that also "
               "receives (chain entry like LL): extra pushes before receiving (the other arm clamps meanwhile)")
p.add_argument("--repush_from", type=float, default=0.18, help="re-grasp this far before the plane for a re-push")
p.add_argument("--repush_to", type=float, default=0.04, help="a re-push ends with the grip this far before the plane")
p.add_argument("--feed_tip", default=None, choices=["end", "start"], help="end: the end tip, rings in order, left picks; "
               "start: the start tip, rings reversed, right picks (same crossings along the material)")
p.add_argument("--feed_slant", type=float, nargs="+", default=None, help="per ring: tilt the feed direction this many deg "
               "(horizontally, toward +x, away from the robot) before the --feed_cone offsets")
p.add_argument("--recv_skew", type=float, default=0.0, help="a receiver grasp may hold the rope up to this many deg off the "
               "gripper's rope axis")
p.add_argument("--recv_margin", type=float, default=0.05, help="joint-limit margin of the receiver grasp IK")
p.add_argument("--recv_clear", type=float, default=0.01, help="clearance above the planner's minimum for the receiver grasp")
p.add_argument("--recv_env_clear", type=float, default=None, help="receiver grasp + pre-grasp: the gripper/wrist/camera envelope "
               "keeps this much (m) from every ring tube and from the other gripper (the capsule model is thinner; X2a's receiver "
               "stalled on R3's ring and the feeder's gripper)")
p.add_argument("--pick_arm", default=None, choices=["left", "right"], help="the arm that picks the fed tip (default: right "
               "for --feed_tip start, else left; D11 mirrored rope start: left)")
p.add_argument("--turn_open", type=int, default=0, help="1: D11 opening (user's method): the picker pinches the rope near the "
               "fed tip on the table, drags it toward ring 1's feed start and turns the tip toward ring 1's horizontal feed "
               "direction (several drag + turn steps), re-grasps it `--turn_regrip` from the tip and lifts (instead of the ledge regrasp)")
p.add_argument("--hold_before", type=float, default=0.04, help="turn_open 2: the carried tip stops this far before ring 1's plane, "
               "left of it, pointing along the ring's horizontal feed direction")
p.add_argument("--hold_past", type=float, default=0.13, help="turn_open 2: the tip is pushed this far past ring 1's plane")
p.add_argument("--hold_aim", type=int, default=0, help="turn_open 2: after the lift, rotate about the grip point onto ring 1's "
               "feed direction (oracle.aim: the lifted rope pivots ~40-50 deg in the jaws) and push with oracle.feed")
p.add_argument("--hold_regrip", type=float, default=0.0, help="turn_open 2: put the carried rope down (briefly) and re-grasp it this far "
               "from the tip (a longer overhang balances the rope body's torque, which tips the tip up when lifted); 0 = keep holding")
p.add_argument("--hold_tipz", type=float, default=0.0, help="turn_open 2: the tip's height before the push is the aperture "
               "centre's plus this (an upward-pointing rope crosses the plane lower than its tip)")
p.add_argument("--pinch_tilt", type=float, default=0.0, help="the table pinch's approach leans this many deg from vertical toward the "
               "tip direction (the wrist sits behind the grip, away from the ring)")
p.add_argument("--hold_cross", type=float, default=0.0, help="turn_open 2: expected tip travel past the ring plane (m); the tip's height "
               "before the push is lowered by this x tan(measured chord pitch) so the sloping rope crosses the plane at the aperture centre")
p.add_argument("--hold_yaw", type=int, default=0, help="turn_open 2: after the lift, turn the held rope about the vertical through the "
               "grip point until its chord points along ring 1's horizontal feed direction (a put-down re-grasp loses the turn)")
p.add_argument("--hold_droop", type=float, default=0.12, help="turn_open 2: first lift puts the grip this far above the ring "
               "centre's height (the rope droops), then the measured tip height is corrected")
p.add_argument("--turn_hold", type=int, default=0, help="turn_open: one pinch turns and drags the whole way and keeps holding "
               "(no put-down, no re-grasp): the rope's rest shape springs a put-down turn back")
p.add_argument("--turn_pinch", type=float, default=0.12, help="turn_open: pinch this far from the tip while dragging / turning")
p.add_argument("--turn_regrip", type=float, default=0.14, help="turn_open: re-grasp this far from the tip")
p.add_argument("--turn_step", type=float, default=45.0, help="turn_open: largest turn per step (deg)")
p.add_argument("--turn_drag", type=float, default=0.06, help="turn_open: largest drag per step (m)")
p.add_argument("--min_clear", type=float, default=None, help="planner capsule clearance (m) for every move (default 0.004)")
p.add_argument("--recv_off", type=float, default=0.07, help="receiver grip point distance past the ring plane (tried first)")
p.add_argument("--recv_depth", type=float, default=0.012, help="rope depth inside the pads for in-air grasps (from the TCP toward the tips)")
p.add_argument("--recv_min_from_tip", type=float, default=None, help="receiver grasp at least this far from the tip")
p.add_argument("--feed_extra", type=float, default=None, help="after a feed, push up to this much further if collision-free")
p.add_argument("--handover", type=int, nargs="+", default=None, help="per ring but the last: 1 = the next feeder grasps "
               "while the receiver still holds (no drop; only when they are different arms)")
p.add_argument("--lay", type=json.loads, default=None, help="per ring but the last, null or [gx, gy, psi_deg, f]: instead of drop + "
               "regrip, the receiver (= the next feeder) lays the end on the table along ring k+1's horizontal feed direction "
               "yawed by psi and drags it until the rope point f from the tip lies at (gx, gy), lets go, "
               "pinches it there (z_tcp toward the tip) and lifts --lay_lift (lay_regrip)")
p.add_argument("--lay_lift", type=float, default=0.12)
p.add_argument("--lay_drag", type=float, default=0.20, help="lay_regrip: drag length along u")
p.add_argument("--lay_tilt", type=float, default=0.0, help="lay_regrip: the drag's approach leans this many deg from vertical "
               "against the lay direction")
p.add_argument("--pull1", type=float, default=0.33)
p.add_argument("--regrip_from_tip", type=float, nargs="+", default=None)
p.add_argument("--drop_settle_s", type=float, default=1.5)
p.add_argument("--finish_wps", type=json.loads, default=[[0.36, -0.02, 0.98], [0.36, 0.08, 0.86], [0.38, 0.20, 0.79]],
               help="release finish (easy): grip point waypoints of the last pull")
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
p.add_argument("--handover_xyz", type=float, nargs=3, default=[0.40, 0.25, 0.83])
p.add_argument("--support_from_tip", type=float, nargs="+", default=[0.03])
p.add_argument("--regrip_left_off", type=float, default=0.08)
p.add_argument("--settle_max_s", type=float, default=20.0)
p.add_argument("--nop_steps", type=int, default=300)
AppLauncher.add_app_launcher_args(p)
args = p.parse_args()
args.headless = True
TIER_DEFAULTS = {
    "RopeThreading-Easy-v0": dict(feed_start=[0.225, 0.21], feed_stop=[0.06, 0.09], pull_xyz=[[0.62, -0.25, 1.00]],
                                  drop_xyz=[[0.62, -0.20, 0.92]], orient_vias=[], finish="release", feed_tip="end", chain=["LR", "R"],
                                  flip=1, regrip_from_tip=[0.19, 0.17, 0.21, 0.15], recv_min_from_tip=0.0, ledge_align=0,
                                  feed_extra=0.0, reseat=0, handover=[0], reseat_roll=0.0, feed_cone=0.0, repush=[0]),
    # medium (yaw 195 layout, fixed by the user): the start tip is fed, R3 -> R2 -> R1; the right picks it at the right
    # edge, re-seats it on the table, flips, feeds R3; the left receives, pulls, lays the end low, re-grasps it itself and
    # feeds R2 (16 deg off its normal); past R2 neither arm reaches near R1, so the left pushes once more while the right
    # clamps behind, then receives past R2 itself under the clamp, pulls, lays it down, re-grasps and feeds R1.
    "RopeThreading-Medium-v0": dict(feed_start=[0.24, 0.20, 0.24], feed_stop=[0.07, 0.07, 0.07],
                                    pull_xyz=[[0.58, -0.10, 1.00], [0.55, 0.32, 1.00]],
                                    drop_xyz=[[0.66, -0.10, 0.80], [0.60, 0.30, 0.92]], regrip_from_tip=[0.19, 0.17, 0.15],
                                    orient_vias=[], finish="hold", feed_tip="start", chain=["RL", "LL", "L"], flip=1,
                                    recv_min_from_tip=0.055, ledge_align=1, feed_extra=0.025, reseat=1, handover=[0, 0],
                                    reseat_roll=0.0, feed_cone=25.0, repush=[0, 1]),
}
for k_, v_ in TIER_DEFAULTS[args.task].items():
    if getattr(args, k_) is None:
        setattr(args, k_, v_)
app = AppLauncher(args).app

import numpy as np
import torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rt_common import Runner, make_env, frame, frame_az, OPEN, SL, GI
import yam_kin as K

env = make_env(args.task, mode=args.env_mode)
R = Runner(env, args.out)
if args.min_clear is not None:
    R.min_clear = args.min_clear
scn = env.scn
ring = {r["name"]: r for r in scn["rings"]}
RINGS = [dict(ring[n], travel=sg * np.asarray(ring[n]["normal"], float)) for n, sg in scn["order"]]
if args.feed_tip == "start":     # the start tip goes through the rings in reverse order, against each crossing direction
    RINGS = [dict(r, travel=-r["travel"]) for r in RINGS[::-1]]
R1 = RINGS[0]
TABLE = 0.75
log = {}
EX, EY, EZ = np.eye(3)


def say(*a):
    print("[ORACLE]", *a); sys.stdout.flush()


def rope_pts():
    """Centreline ordered so that the fed tip is the last point (--feed_tip start reverses the material order)."""
    c = R.centerline()
    return c[::-1] if args.feed_tip == "start" else c


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


def backed(T, back):
    """T moved `back` against its approach (the pre-grasp pose)."""
    Tb = T.copy(); Tb[:3, 3] -= back * T[:3, 0]
    return Tb


def grasp_ok(s, from_tip, tol=0.012):
    """The rope point `from_tip` lies between the closed jaws (`--recv_depth` in front of the TCP; privileged check)."""
    off, _ = held_offset(s, from_tip)
    return R.finger(s) < -0.0035 and float(np.linalg.norm(off[:2] - (args.recv_depth, 0.0))) < tol


def grasp_from_behind(s, T, back=0.09, from_tip=None):
    """Pre-grasp `back` behind T, approach, close. With `from_tip`: re-aim at that rope point from the pre-grasp (the
    rope moves while the arm travels) and return whether it ended up between the jaws."""
    Tpre = T.copy(); Tpre[:3, 3] -= back * T[:3, 0]
    move_or_goto(s, Tpre, 0.12)
    if from_tip is None:
        R.move(s, T, speed=0.04)
    else:       # re-aimed grasp, else the planned one; neither collision-free -> report a miss (nothing closed)
        T_aim = T.copy(); T_aim[:3, 3] = station(from_tip)[0] - T[:3, :3] @ np.array([args.recv_depth, 0, 0])
        for T_try in (T_aim, T):
            try:
                R.move(s, T_try, speed=0.04)
                break
            except RuntimeError as e:
                say("grasp approach failed:", str(e)[:100])
        else:
            return False
    R.hold(5)
    R.set_grip(s, args.grip_close, 15)
    R.hold(15)
    check_closed(s, "grasp_" + s, empty_ok=from_tip is not None)
    return True if from_tip is None else grasp_ok(s, from_tip)


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


def ring_envelope_clearance(T):
    """Smallest distance of the gripper envelope (_GB at pose T) to any ring tube (torus)."""
    pts = T[:3, 3] + _GB @ T[:3, :3].T
    out = np.inf
    for rg in RINGS:
        n = np.asarray(rg["normal"], float); n = n / np.linalg.norm(n)
        v = pts - rg["center"]; h = v @ n
        rr = np.linalg.norm(v - np.outer(h, n), axis=1)
        out = min(out, float((np.sqrt((rr - rg["radius"]) ** 2 + h ** 2) - rg["tube"]).min()))
    return out


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


def check_closed(s, name, empty_ok=False):
    f = R.finger(s)
    if f < -0.0065:     # jaw wider than ~13 mm: blocked by something other than the 8 mm rope
        stage_done(name + "_blocked", finger=f)
        finish()
    if f > -0.0035 and not empty_ok:    # closed tighter than the 8 mm rope (-4.9 mm): nothing between the jaws
        stage_done(name + "_empty", finger=f)
        finish()


def approach_clear(s, Ta, Tb, n=4):
    """The straight approach Ta -> Tb (orientation fixed, gripper open) keeps the move's own clearance at n inner points."""
    for f in np.linspace(0, 1, n + 2)[1:-1]:
        T = Ta.copy(); T[:3, 3] = Ta[:3, 3] + f * (Tb[:3, 3] - Ta[:3, 3])
        if not R.reachable(s, T, clear=0.0):
            return False
    return True


def receiver_T(side, c, axis, dists=None, extra_check=None):
    """Grasp of the rope `dist` past the ring plane (centre c, travel `axis`; `--recv_off` first): approach scanned in the
    plane perpendicular to the local rope tangent, both rope-axis signs, rope 12 mm inside the pads, pre-grasp 9 cm back.
    Returns (T, dist, from_tip) or None."""
    if dists is None:
        dists = (args.recv_off,) + tuple(d for d in (0.07, 0.06, 0.05, 0.08, 0.10, 0.04, 0.03) if d != args.recv_off)
    for dist in dists:
        rp, s_r = rope_point_at_axial(c, axis, dist)
        if rp is None or s_r < args.recv_min_from_tip:     # pads (+-35 mm along the rope) closing on the tip knock it away
            continue
        P = rope_pts()[::-1]
        i = min(int(s_r / env.link_length), len(P) - 2)
        t = P[i] - P[i + 1]; t /= np.linalg.norm(t)
        u = np.cross(t, EZ); u /= np.linalg.norm(u); v = np.cross(u, t)
        cands = []
        sk = np.radians(args.recv_skew)       # rope axis tilted up to --recv_skew deg off the gripper's z axis
        for phi in range(0, 360, 15):
            a = np.cos(np.radians(phi)) * u + np.sin(np.radians(phi)) * v
            for zs in (1, -1):
                for az in ([None] if sk == 0 else [None, 0, 90, 180, 270]):
                    zt = zs * t if az is None else zs * (np.cos(sk) * t + np.sin(sk) * (np.cos(np.radians(az)) * u + np.sin(np.radians(az)) * v))
                    T = grip_T(side, a, zt, rp, np.array([args.recv_depth, 0, 0]))
                    Tpre = T.copy(); Tpre[:3, 3] -= 0.09 * a
                    if finger_low_z(T) < TABLE + 0.015:
                        continue
                    if args.recv_env_clear is not None and min(
                            ring_envelope_clearance(T), ring_envelope_clearance(Tpre),
                            gripper_clearance(T, cmd_T(other(side))), gripper_clearance(Tpre, cmd_T(other(side)))) < args.recv_env_clear:
                        continue
                    if (R.reachable(side, T, margin=args.recv_margin, grip_open=False, clear=args.recv_clear)
                            and R.reachable(side, Tpre, margin=args.recv_margin, clear=args.recv_clear)
                            and approach_clear(side, Tpre, T)):
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


# ======================================================================== ready: unfold both arms (home is singular)
def ready():
    """First collision-free pose of (0.40, 0.30, 0.95) (easy: probes/ready_probe.py), then farther out to the side."""
    for side, sy in (("right", -1), ("left", 1)):
        for x, y, z in ((0.40, 0.30, 0.95), (0.36, 0.42, 0.92), (0.34, 0.50, 0.90)):
            try:
                R.goto(side, frame((0.7071, 0, -0.7071), (0, 1, 0), (x, sy * y, z)), 45)
                break
            except RuntimeError as e:
                say("ready candidate", (x, sy * y, z), "failed:", str(e)[:100])
    R.hold(5)
    R.q_ready = {sd: R.cur[0, SL[sd]].numpy().astype(float).copy() for sd in ("left", "right")}


# ======================================================================== pick (PK, the fed tip's side): ledge regrasp
# A rope lying on the table can only be pinched in the last ~2 mm of the YAM pads; that pinch survives translations
# but the rope pivots / pops out under re-orientation and lifting (runs t5, t18, t22). So: pinch-drag the end until
# its last `--overhang` m stick out past the table edge on PK's side (|y| = 0.65), release, then grasp the overhang deep
# (fingers below the tabletop level, beyond the edge), lift.
TABLE_EDGE_Y = 0.65                     # workstation.usd table_surface collider edge (nominal yam.yaml: 0.55)
PK = args.pick_arm or ("right" if args.feed_tip == "start" else "left")     # the arm that picks the fed tip (the start tip lies on -y)
SG = 1.0 if PK == "left" else -1.0
ARM = {"L": "left", "R": "right"}
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


def pinch(from_tip, shift=None, fail=True, s=None, zss=(-1, 1)):
    """Top-down fingertip pinch by arm s (default PK), z_tcp = zs * the horizontal tangent toward the tip for the first
    reachable zs in `zss`; `shift` (world vector) = the planned drag, whose end pose must be reachable too."""
    s = s or PK
    pt, t = station(from_tip)
    t_h = t - EZ * (t @ EZ); t_h /= np.linalg.norm(t_h)
    tl = np.radians(args.pinch_tilt)
    a_p = np.cos(tl) * a_down + np.sin(tl) * t_h
    for zs in zss:
        Tg = frame_az(a_p, zs * t_h); Tg[:3, 3] = pt - DEPTH_TABLE * a_p
        Tpre = Tg.copy(); Tpre[:3, 3] += 0.08 * EZ
        ok = R.reachable(s, Tg) and R.reachable(s, Tpre)
        if ok and shift is not None:
            for f in (0.5, 1.0):
                Tm = Tg.copy(); Tm[:3, 3] += f * np.asarray(shift) + 0.03 * EZ
                ok &= R.reachable(s, Tm, grip_open=False)
        if ok:
            break
    else:
        if not fail:
            return None
        stage_done("pick_failed", reason=f"pinch at {from_tip} unreachable", pt=pt); finish()
    move_or_goto(s, Tpre, 0.15)
    R.move(s, Tg, speed=0.04)
    R.hold(5)
    R.set_grip(s, args.grip_close, 15)
    R.hold(15)
    off, _ = held_offset(s, from_tip)
    T = cmd_T(s); T[:3, 3] += 0.03 * EZ
    R.move(s, T, speed=0.03)
    R.hold(10)
    return off


def overhang_len():
    """Rope arc length beyond PK's table edge (from the fed tip back to the first point inside)."""
    P = rope_pts()[::-1]
    inside = np.flatnonzero(SG * P[:, 1] <= TABLE_EDGE_Y)
    if not len(inside):
        return np.inf
    k = inside[0]
    return float(np.linalg.norm(np.diff(P[:k + 1], axis=0), axis=1).sum())


def put_down_release():
    T = cmd_T(PK); T[:3, 3] -= 0.03 * EZ
    try:
        R.move(PK, T, speed=0.03)
    except RuntimeError as e:
        say("put down: cannot lower, releasing from 3 cm:", str(e)[:80])
    R.hold(5)
    R.set_grip(PK, OPEN, 12)
    retreat(PK)
    R.hold(10)


def chord_deg(s, GF):
    """Angle between the held rope's chord (grip point -> tip) and z_tcp: how far the rope sits pivoted in the jaws."""
    off, _ = held_offset(s, GF)
    T = R.tcp(s); c = T[:3, :3].T @ (tip() - (T[:3, :3] @ off + T[:3, 3]))
    return float(np.degrees(np.arccos(abs(c[2]) / np.linalg.norm(c))))


def reseat(GF):
    """Press the held rope's free end flat on the table. The YAM pads pinch only near the fingertips, so the rope keeps
    the angle it was grasped at beyond the ledge (~45-57 deg down in medium); pushed up by the table it re-seats along
    z_tcp, and friction then keeps that through the flip. Top-down, grip point at |y| 0.40 (0.25 m inside the edge; the free
    end, 0.2 m outward, over the table), fingertips 5 mm above the table, a 3 cm slide toward the tip, lift.
    --reseat_at moves the press to (x, y) with the tip yawed to psi; --reseat_roll then rolls about the rope axis."""
    before = chord_deg(PK, GF)
    off, _ = held_offset(PK, GF)
    T = cmd_T(PK); gp = T[:3, :3] @ off + T[:3, 3]
    if args.reseat_at is None:
        T[:3, 3] += np.array([gp[0], SG * (TABLE_EDGE_Y - 0.25), TABLE + 0.10]) - gp
    else:      # yaw about the vertical so that the tip points along psi
        x, y, psi = args.reseat_at
        zt = T[:3, 2] * (1.0 if T[:3, 2] @ (tip() - gp) > 0 else -1.0)
        T[:3, :3] = Rot.from_rotvec(EZ * (np.radians(psi) - np.arctan2(zt[1], zt[0]))).as_matrix() @ T[:3, :3]
        T[:3, 3] = np.array([x, y, TABLE + 0.10]) - T[:3, :3] @ off
    move_or_goto(PK, T, 0.04)
    R.hold(10)
    safe_shift(PK, (TABLE + 0.005 - finger_low_z(cmd_T(PK))) * EZ, 0.02)
    R.hold(20)
    safe_shift(PK, 0.03 * SG * EY, 0.02)
    R.hold(20)
    after = chord_deg(PK, GF)
    safe_shift(PK, (TABLE + 0.10 - finger_low_z(cmd_T(PK))) * EZ, 0.03)
    R.hold(10)
    if args.reseat_roll:
        off, _ = held_offset(PK, GF)
        rotate_about_grip(PK, Rot.from_rotvec(cmd_T(PK)[:3, 2] * np.radians(args.reseat_roll)).as_matrix(), off,
                          speed=0.03, ang_speed=0.4)
        R.hold(10)
    stage_done("reseat", chord_deg_before=before, chord_deg_pressed=after, chord_deg_lifted=chord_deg(PK, GF), tip=tip())


def pick():
    """Ledge regrasp by PK; easy also rolls onto the R1 feed frame. Returns the grip distance from the tip."""
    # drag 1: pinch near the tip, yaw so the tip points toward PK's edge (+-y), carry toward the edge
    off = pinch(args.drag1_from_tip)
    T0 = cmd_T(PK)
    tipdir = station(args.drag1_from_tip)[1]
    ang = np.arctan2(np.cross(tipdir * [1, 1, 0], SG * EY) @ EZ, (tipdir * [1, 1, 0]) @ (SG * EY))
    rotate_about_grip(PK, Rot.from_rotvec(EZ * ang).as_matrix(), off)
    off, _ = held_offset(PK, args.drag1_from_tip)
    T = cmd_T(PK); gp = T[:3, :3] @ off + T[:3, 3]
    cands = sorted(((y, x) for y in np.arange(args.drag1_y, 0.34, -0.02) for x in (args.drag_x, 0.52, 0.56, 0.60, 0.64)),
                   key=lambda c: (-c[0], abs(c[1] - args.drag_x)))
    for y, x in cands:
        Tc = T.copy(); Tc[:3, 3] += np.array([x, SG * y, gp[2]]) - gp
        if R.reachable(PK, Tc, grip_open=False):
            try:
                R.move_route(PK, Tc, speed=0.04)
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
        want = np.array([args.drag_x - tp[0], SG * (args.overhang - over_now), 0.0])
        if over_now >= args.overhang - 0.01 and abs(want[0]) < 0.04:
            break
        off = None
        for ft2 in (max(0.12, over_now + 0.07), over_now + 0.10, max(0.12, over_now + 0.04)):   # pinch 7 / 10 / 4 cm inside
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
            if off is not None:
                break
        if off is None:
            if overhang_len() >= args.grasp_from_tip + 0.03:     # enough overhang for the deep grasp beyond the edge
                say("no reachable drag step; overhang", round(overhang_len(), 3), "suffices for the deep grasp")
                break
            stage_done("pick_failed", reason="no reachable drag step", tip=tip()); finish()
        T = cmd_T(PK); T[:3, 3] += sh
        R.move(PK, T, speed=0.03)
        R.hold(10)
        put_down_release()
        say("after drag2.%d (shift %s): tip" % (it, np.round(sh, 3)), np.round(tip(), 3), "overhang arc", round(overhang_len(), 3))
    # deep grasp of the overhang, rope 12 mm inside the pads, z_tcp = tip direction. The overhang already bends down
    # at the grasp point (~57 deg in medium), and the fingertip-only pinch keeps whatever angle it closes on, so with
    # --ledge_align the jaws close along the actual tangent (approach: the most downward direction perpendicular to it).
    GF = min(args.grasp_from_tip, round(overhang_len() - 0.07, 3))   # the fingers need ~7 cm beyond the table edge
    pt, t = station(GF)
    zs1 = 1
    Tg = frame_az(a_down, t); Tg[:3, 3] = pt - args.recv_depth * a_down
    Tpre = Tg.copy(); Tpre[:3, 3] += 0.07 * EZ
    if args.ledge_align:
        a_t = -EZ - t * (t @ -EZ); a_t /= np.linalg.norm(a_t)
        Ta = frame_az(a_t, t); Ta[:3, 3] = pt - args.recv_depth * a_t
        if R.reachable(PK, Ta, grip_open=False) and R.reachable(PK, backed(Ta, 0.07)):
            Tg, Tpre = Ta, backed(Ta, 0.07)
        say("ledge grasp: tangent", np.round(t, 2), "aligned" if Tg is Ta else "not reachable aligned: top-down")
    move_or_goto(PK, Tpre, 0.12)
    R.move(PK, Tg, speed=0.03)
    R.hold(5)
    R.set_grip(PK, args.grip_close, 15)
    R.hold(15)
    check_closed(PK, "deep_grasp")
    off_pick, _ = held_offset(PK, GF)
    T = cmd_T(PK); T[:3, 3] += max(0.06, TABLE + 0.02 - finger_low_z(T)) * EZ      # fingertips 2 cm above the tabletop
    R.move(PK, T, speed=0.03)
    R.hold(15)
    slip_lift = slip_report(PK, GF, off_pick)
    stage_done("ledge_grasp", from_tip=GF, held_offset=off_pick, slip_after_lift_m=slip_lift, tip=tip())
    if args.reseat:
        reseat(GF)
    if not args.flip:
        stage_done("pick", finger=R.finger(PK), held_offset=off_pick, tip=tip())
        return GF
    # re-orient for feeding: back over the table, roll about the rope axis to the feed approach a1 (tip still +y),
    # climb, then a 180 deg wrist roll about the approach (tip -> -y; the trailing rope then runs +y to the dragged end)
    off_now, _ = held_offset(PK, GF)
    T = cmd_T(PK); gp = T[:3, :3] @ off_now + T[:3, 3]
    T[:3, 3] += np.array([args.reorient_x, SG * args.reorient_y, args.reorient_z]) - gp
    R.move_route(PK, T, speed=0.03)
    R.hold(10)
    T0 = cmd_T(PK)
    ax = T0[:3, 2]
    a_t = a1 - ax * (ax @ a1); a_t /= np.linalg.norm(a_t)
    ang = np.arctan2(np.cross(T0[:3, 0], a_t) @ ax, T0[:3, 0] @ a_t)
    off_now, _ = held_offset(PK, GF)
    rotate_about_grip(PK, Rot.from_rotvec(ax * ang).as_matrix(), off_now)
    off_now, _ = held_offset(PK, GF)
    T = cmd_T(PK); gp = T[:3, :3] @ off_now + T[:3, 3]
    T[:3, 3] += np.array([args.flip_x, SG * args.flip_y, R1["center"][2] - 0.01]) - gp
    R.move_route(PK, T, speed=0.03)
    R.hold(10)
    say("before flip: held offset", np.round(held_offset(PK, GF)[0], 4), "tip", np.round(tip(), 3))
    for k in range(18):
        off_now, _ = held_offset(PK, GF)
        a_now = cmd_T(PK)[:3, 0]
        rotate_about_grip(PK, Rot.from_rotvec(a_now * np.radians(10.0 * SG * args.flip_sense)).as_matrix(), off_now,
                          speed=0.03, ang_speed=0.5)
    zs1 = 1 if (cmd_T(PK)[:3, 2] @ R1["travel"]) > 0 else -1
    # settle onto the exact feed frame: approach a1, rope axis along ring 1's travel (the tip direction)
    off_now, _ = held_offset(PK, GF)
    T0 = cmd_T(PK)
    Tf = frame_az(a1, zs1 * R1["travel"])
    rotate_about_grip(PK, Tf[:3, :3] @ T0[:3, :3].T, off_now, speed=0.03, ang_speed=0.4)
    off_rot, _ = held_offset(PK, GF)
    stage_done("pick", zsign=zs1, finger=R.finger(PK), held_offset_deep=off_pick, held_offset_after_reorient=off_rot,
               approach=cmd_T(PK)[:3, 0], rope_axis=cmd_T(PK)[:3, 2], tip=tip())
    return GF


def pick_turn():
    """D11 opening (user's method): pinch near the fed tip on the table, drag it toward ring 1's feed start and turn the
    tip toward ring 1's horizontal feed direction (up to `--turn_step` deg and `--turn_drag` m per step, put down between
    steps), then re-grasp `--turn_regrip` from the tip. Returns that distance (the grip point's place on the feed start is
    reached by to_feed_frame)."""
    h = R1["travel"].copy(); h[2] = 0.0; h /= np.linalg.norm(h)                  # ring 1's horizontal feed direction
    g = args.turn_regrip
    tip_goal = feed_gps(0)[0][:2] + g * h[:2]                                    # tip xy: the regrip point lies under the feed start
    for it in range(8):
        tp = tip(); th = station(args.turn_pinch)[1][:2]; th /= np.linalg.norm(th)
        ang = float(np.arctan2(th[0] * h[1] - th[1] * h[0], th @ h[:2]))
        err = tip_goal - tp[:2]
        say(f"turn step {it}: tip", np.round(tp, 3), "to goal", np.round(tip_goal, 3), "turn left (deg)", round(np.degrees(ang), 1))
        if abs(ang) < np.radians(10) and np.linalg.norm(err) < 0.03:
            break
        step = ang if args.turn_hold else float(np.clip(ang, -np.radians(args.turn_step), np.radians(args.turn_step)))
        sh = np.r_[err, 0.0]
        if np.linalg.norm(sh) > args.turn_drag and not args.turn_hold:
            sh *= args.turn_drag / np.linalg.norm(sh)
        off = pinch(args.turn_pinch, shift=sh)
        rotate_about_grip(PK, Rot.from_rotvec(EZ * step).as_matrix(), off)
        T = cmd_T(PK); T[:3, 3] += sh
        try:
            R.move_route(PK, T, speed=0.04)
        except RuntimeError as e:
            say("turn drag failed:", str(e)[:80])
        R.hold(10)
        if args.turn_hold:
            stage_done("pick", from_tip=args.turn_pinch, tip=tip(), held_offset=held_offset(PK, args.turn_pinch)[0])
            return args.turn_pinch
        put_down_release()
    pinch(g)
    stage_done("pick", from_tip=g, tip=tip(), held_offset=held_offset(PK, g)[0])
    return g


def pick_hold():
    """turn_open 2 (D11, the user's method): one pinch near the fed tip turns it toward ring 1's horizontal feed direction
    and carries it to `--hold_before` m before ring 1's plane, left of it. No put-down (the rope springs back to its rest
    shape) and no later change of the grip's orientation (feed_hold only translates). Returns the pinch's distance."""
    h = R1["travel"].copy(); h[2] = 0.0; h /= np.linalg.norm(h)
    off = pinch(args.turn_pinch)
    th = station(args.turn_pinch)[1][:2]; th /= np.linalg.norm(th)
    ang = float(np.arctan2(th[0] * h[1] - th[1] * h[0], th @ h[:2]))
    say("hold: turn the tip by", round(np.degrees(ang), 1), "deg")
    rotate_about_grip(PK, Rot.from_rotvec(EZ * ang).as_matrix(), off)
    goal = R1["center"][:2] - args.hold_before * h[:2]
    T = cmd_T(PK); T[:3, 3] += np.r_[goal - tip()[:2], 0.0]
    try:
        R.move_route(PK, T, speed=0.04)
    except RuntimeError as e:
        say("hold: carry failed:", str(e)[:100])
    R.hold(10)
    GF = args.turn_pinch
    if args.hold_regrip > 0:
        tip_held = tip().copy()
        put_down_release()
        say("hold: put down, the tip sprang back by", round(float(np.linalg.norm(tip() - tip_held)), 3), "m to", np.round(tip(), 3))
        pinch(args.hold_regrip)
        GF = args.hold_regrip
    stage_done("pick", from_tip=GF, tip=tip(), held_offset=held_offset(PK, GF)[0])
    if args.save_ckpt:
        R.snapshot(os.path.join(args.out, "ckpt_pick.pt"), dict(k=0, s=PK, GF=GF))
    return GF


def feed_hold(s, k, GF):
    """Feed ring k by translation only (pick_hold's grip orientation is kept): lift until the measured tip is at the
    aperture's height (first `--hold_droop` above it), align the tip with the aperture on the horizontal line through it,
    push `--hold_before` + `--hold_past` m along the horizontal feed direction."""
    rg = RINGS[k]; c = rg["center"]
    h = rg["travel"].copy(); h[2] = 0.0; h /= np.linalg.norm(h)
    zt = c[2] - 0.01 + args.hold_tipz
    off, _ = held_offset(s, GF)
    gp = R.tcp(s)[:3, :3] @ off + R.tcp(s)[:3, 3]
    safe_shift(s, (zt + args.hold_droop - gp[2]) * EZ, 0.03)
    R.hold(20)
    for it in range(3):
        safe_shift(s, (zt - tip()[2]) * EZ, 0.03)
        R.hold(15)
    gp = R.tcp(s)[:3, :3] @ off + R.tcp(s)[:3, 3]
    ch = tip() - gp
    pitch = float(np.degrees(np.arctan2(ch[2], np.linalg.norm(ch[:2]))))
    stage_done("lift", pitch_deg=pitch, grip=gp, tip=tip(), chord_m=float(np.linalg.norm(ch)))
    if args.hold_cross > 0:
        zt += args.hold_cross * np.tan(np.radians(pitch))
        say("hold: tip height target", round(float(zt), 3), "for pitch", round(pitch, 1))
        for it in range(2):
            safe_shift(s, (zt - tip()[2]) * EZ, 0.03)
            R.hold(15)
    if args.hold_aim:
        feed(s, k, GF)
        return
    if args.hold_yaw:
        ch = tip() - gp; chh = ch[:2] / np.linalg.norm(ch[:2])
        ang = float(np.arctan2(chh[0] * h[1] - chh[1] * h[0], chh @ h[:2]))
        say("hold: yaw the held rope by", round(np.degrees(ang), 1), "deg")
        rotate_about_grip(s, Rot.from_rotvec(EZ * ang).as_matrix(), off)
        for it in range(2):
            safe_shift(s, (zt - tip()[2]) * EZ, 0.03)
            R.hold(15)
    for it in range(2):
        corr = np.r_[(c[:2] - args.hold_before * h[:2]) - tip()[:2], 0.0]
        safe_shift(s, corr, 0.03)
        R.hold(15)
    push = 0.0                       # 1 cm steps as far as the planner allows (the gripper cannot pass the ring itself)
    for i in range(int(round((args.hold_before + args.hold_past) / 0.01))):
        T = cmd_T(s); T[:3, 3] += 0.01 * np.r_[h[:2], 0.0]
        try:
            R.move(s, T, speed=args.speed)
        except RuntimeError as e:
            say(f"feed_hold: push stops after {i} cm:", str(e)[:140])
            break
        push += 0.01
    R.hold(20)
    rel = tip() - c
    d = rg["travel"]
    stage_done(f"feed{k + 1}", ring=rg["name"], push_fraction=push, tip_past_m=float(rel @ d),
               tip_radial_m=float(np.linalg.norm(rel - d * (rel @ d))), slip_m=slip_report(s, GF, off))


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


# ======================================================================== ring stages (generic over RINGS)
def perp_approaches(d, s, target):
    """Approaches perpendicular to the rope axis d: the horizontal pointing away from arm s's base first, pitched
    down 0, 30, 15, 45, 60 deg (within the plane perpendicular to d), then the opposite horizontal."""
    h = np.cross(EZ, d); h /= np.linalg.norm(h)
    up = np.cross(d, h)
    hs = sorted((h, -h), key=lambda hh: -(hh @ (np.asarray(target) - K.BASES[s])))
    return [np.cos(np.radians(p_)) * hh - np.sin(np.radians(p_)) * up for hh in hs for p_ in (0, 30, 15, 45, 60)]


def feed_dir(k):
    """Ring k's feed direction: d_k, or the off-axis direction to_feed_frame chose (within --feed_cone)."""
    return RINGS[k].get("feed_dir", RINGS[k]["travel"])


def feed_dirs(k):
    """d_k (tilted --feed_slant[k] deg toward +x) first, then directions 10 / 18 / 25 deg off it (up to --feed_cone),
    every 45 deg around."""
    d = RINGS[k]["travel"]
    sl = np.radians(args.feed_slant[k]) if args.feed_slant else 0.0
    if sl:
        Rz = lambda a: np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        d = max((Rz(sl) @ d, Rz(-sl) @ d), key=lambda v_: v_[0])
    h = np.cross(EZ, d); h /= np.linalg.norm(h); v = np.cross(d, h)
    return [d] + [np.cos(np.radians(dv)) * d + np.sin(np.radians(dv)) * (np.cos(np.radians(az)) * h + np.sin(np.radians(az)) * v)
                  for dv in (10, 18, 25) if dv <= args.feed_cone for az in range(0, 360, 45)]


def feed_gps(k, d=None):
    rg = RINGS[k]; d = feed_dir(k) if d is None else d
    return [rg["center"] - args.feed_start[k] * d - 0.01 * EZ, rg["center"] - args.feed_stop[k] * d - 0.01 * EZ]


def at_grip(Rm, g, off):
    """TCP pose with orientation Rm whose held rope point (offset `off` in the TCP frame) lies on g."""
    T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = g - Rm @ off
    return T


def rot_between(u, v):
    """Smallest rotation taking unit vector u onto unit vector v."""
    ax = np.cross(u, v); n = np.linalg.norm(ax)
    return np.eye(3) if n < 1e-9 else Rot.from_rotvec(ax / n * np.arctan2(n, u @ v)).as_matrix()


def feed_ok(s, Rm, k, off, d=None):
    """Start and end grip poses of ring k's feed (direction d) reachable with TCP orientation Rm. The end is close to
    the ring by design (easy R1: 4.0 mm in the capsule model, at the move's own limit), so it only needs 2 mm there."""
    g0, g1 = feed_gps(k, d)
    return (R.reachable(s, at_grip(Rm, g0, off), grip_open=False)
            and R.reachable(s, at_grip(Rm, g1, off), grip_open=False, clear=-0.002))


def stroke_ok(s, Rm, k, off, d):
    """The whole feed stroke (start -> end grip pose, orientation Rm) is a feasible straight move (Runner.plan_line, the push's
    own check) from one of the start pose's IK solutions. feed_ok checks only the two ends; L2r's push (frame 10 deg off d_k)
    stopped halfway: IK left the workspace mid-stroke (ep 2.1 mm)."""
    g0, g1 = feed_gps(k, d)
    n = max(8, int(np.ceil(30 * np.linalg.norm(g1 - g0) / args.speed)))
    for q in R._ik_all(s, at_grip(Rm, g0, off))[:3]:
        try:
            R.plan_line(s, at_grip(Rm, g1, off), n, q_start=q)
            return True
        except RuntimeError:
            continue
    return False


def feed_frames(s, k, zs, off, Q=np.eye(3), d=None):
    """Orientations of ring k's feed frame whose start and end grip poses arm s can reach: approach perpendicular to
    the feed direction d (default d_k), rope axis zs * d; Q (TCP frame) maps the held rope's measured chord onto that axis."""
    d = RINGS[k]["travel"] if d is None else d
    Rs = [frame_az(a, zs * d)[:3, :3] @ Q for a in perp_approaches(d, s, RINGS[k]["center"])]
    return [Rm for Rm in Rs if feed_ok(s, Rm, k, off, d)]


def joint_route(s, Tv, Tf):
    """Runner.goto's checks for a joint-space route through the via pose Tv to Tf: (q_via, q_goal) or None."""
    q0 = R.cur[0, SL[s]].numpy().astype(float)
    for qv in R._ik_all(s, Tv)[:3]:
        if R._path_ok(s, q0, qv)[0]:
            qg = next((q for q in R._ik_all(s, Tf)[:4] if R._path_ok(s, qv, q)[0]), None)
            if qg is not None:
                return qv, qg
    return None


def to_feed_frame(s, k, GF, vias=()):
    """Bring the rope held `GF` from the tip onto ring k's feed frame and to the feed start. Feed directions: d_k, then
    up to --feed_cone off it. Per direction and chord-correction fraction: rotate in place at a via / here,
    else (vias only) a joint-space route through the via, already in the feed orientation. After a --lay the whole stroke
    must also be feasible (stroke_ok)."""
    rg = RINGS[k]; d = rg["travel"]
    after_lay = bool(k > 0 and args.lay and args.lay[k - 1] is not None)
    off, _ = held_offset(s, GF)
    T0 = cmd_T(s); gp0 = T0[:3, :3] @ off + T0[:3, 3]
    c_t = T0[:3, :3].T @ (tip() - gp0); c_t /= np.linalg.norm(c_t)      # the held rope's chord in the TCP frame
    zs = 1.0 if c_t[2] > 0 else -1.0
    Q = rot_between(c_t, zs * EZ)                                       # the jaws pivot the rope; the free end curls
    keep = (T0[:3, :3] @ c_t) @ d > np.cos(np.radians(15)) and feed_ok(s, T0[:3, :3], k, off) and not after_lay
    if not keep:
        plan = None
        q_rv = Rot.from_matrix(Q).as_rotvec()
        for dd, frac in ((dd, frac) for dd in feed_dirs(k) for frac in (1.0, 2 / 3, 1 / 3, 0.0)):
            cands = feed_frames(s, k, zs, off, Rot.from_rotvec(frac * q_rv).as_matrix(), dd)
            for via in list(vias) + [None]:
                Tv = T0.copy()
                if via is not None:
                    Tv[:3, 3] += np.asarray(via, float) - gp0
                    if not R.reachable(s, Tv, grip_open=False):
                        continue
                Rm = next((Rm for Rm in cands if slerp_ok(s, Tv, Rm, off, lift=0.0)
                           and (not after_lay or stroke_ok(s, Rm, k, off, dd))), None)
                if Rm is not None:
                    plan = (via, Tv, Rm, frac, dd, None)
                    break
            for via in ([] if plan else vias):
                for Rm in cands:
                    route = joint_route(s, at_grip(Rm, np.asarray(via, float), off), at_grip(Rm, feed_gps(k, dd)[0], off))
                    if route is not None:
                        plan = (via, None, Rm, frac, dd, route)
                        break
                if plan:
                    break
            if plan is not None:
                break
        if plan is None:
            stage_done(f"orient{k + 1}_failed", reason="no feasible rotation onto the feed frame", zsign=zs,
                       chord_in_tcp=c_t); finish()
        via, Tv, Rm, frac, dd, route = plan
        rg["feed_dir"] = dd
        say(f"orient{k + 1}: via", via, "joint route" if route else "rotate in place", "approach", np.round(Rm[:, 0], 3),
            "zsign", zs, "chord correction (deg)", round(float(np.degrees(np.linalg.norm(q_rv))), 1), "applied fraction",
            round(frac, 2), "feed direction off d_k (deg)", round(float(np.degrees(np.arccos(np.clip(dd @ d, -1, 1)))), 1))
        if route is not None:
            for q_ in route:
                R.move_joints(s, q_, 60)
                R.hold(10)
        else:
            if via is not None:
                R.move_route(s, Tv, speed=0.04)
                R.hold(10)
            reorient(s, Rm, GF)
    off, _ = held_offset(s, GF)
    T = cmd_T(s); gp = T[:3, :3] @ off + T[:3, 3]
    T[:3, 3] += feed_gps(k)[0] - gp
    move_or_goto(s, T, 0.03)
    R.hold(15)
    stage_done(f"orient{k + 1}", approach=cmd_T(s)[:3, 0], zsign=zs, chord_in_tcp=c_t, held_offset=held_offset(s, GF)[0], tip=tip())


def aim(s, k, GF):
    """Rotate about the grip point until the held rope's chord (grip point -> tip) points along the feed direction (within 3 deg; at
    most 3 steps). The rope pivots in the jaws (~30 deg after the medium flip) and the free end curls along its rest
    shape, so z_tcp alone misaims the tip. Returns the remaining angle (deg)."""
    d = feed_dir(k)
    for it in range(4):
        off, _ = held_offset(s, GF)
        T = R.tcp(s); gp = T[:3, :3] @ off + T[:3, 3]
        ch = tip() - gp; ch /= np.linalg.norm(ch)
        ax = np.cross(ch, d); ang = float(np.arctan2(np.linalg.norm(ax), ch @ d))
        if ang < np.radians(3) or it == 3:
            break
        for f in (1.0, 0.5, 0.25):
            try:
                rotate_about_grip(s, Rot.from_rotvec(ax / np.linalg.norm(ax) * f * ang).as_matrix(), off, speed=0.03,
                                  ang_speed=0.4)
                break
            except RuntimeError as e:
                say(f"aim{k + 1}: rotation by {np.degrees(f * ang):.0f} deg failed:", str(e)[:80])
        else:
            break
    return float(np.degrees(ang))


def feed(s, k, GF, name="feed", stop=None, extra=None):
    """Aim the held rope's chord along d_k, align the measured tip with ring k's aperture centre (it droops below
    the grip), push along d_k (or the largest feasible part of the stroke). `stop` / `extra`: grip distance before the
    plane at the end / the extra push (default --feed_stop, --feed_extra)."""
    rg = RINGS[k]; c, d = rg["center"], feed_dir(k)
    stop = args.feed_stop[k] if stop is None else stop
    extra_max = args.feed_extra if extra is None else extra
    aim_deg = aim(s, k, GF)
    off, _ = held_offset(s, GF)
    for it in range(2):
        target = c - 0.01 * EZ
        if args.variant == "naive" and k == 0:      # the tip passes beside ring 1, 13 cm off-axis (outside ring and stand)
            h = np.cross(EZ, d); target = target + 0.13 * h / np.linalg.norm(h)
        corr = target - tip(); corr -= d * (corr @ d)
        safe_shift(s, corr, args.speed)
        R.hold(15)
    off, _ = held_offset(s, GF)
    T = R.tcp(s); gp = T[:3, :3] @ off + T[:3, 3]
    push = safe_shift(s, (-(gp - c) @ d - stop) * d, args.speed)
    extra = 0.0
    if extra_max > 0:      # a little further where the gripper still clears the ring: more rope for the receiver
        extra = safe_shift(s, extra_max * d, args.speed) * extra_max
    R.hold(20)
    rel = tip() - c
    stage_done(f"{name}{k + 1}" if name == "feed" else name, ring=rg["name"], aim_residual_deg=aim_deg, push_fraction=push, push_extra_m=extra, tip_past_m=float(rel @ d), tip_radial_m=float(np.linalg.norm(rel - d * (rel @ d))),
               slip_m=slip_report(s, GF, off))


def receive(s, k):
    """Arm s grasps the rope just past ring k; the feeder lets go and returns to ready. Returns the grip distance from the tip."""
    rg = RINGS[k]
    for attempt in range(2):        # the feeder keeps holding until the receiver's grasp is verified
        res = receiver_T(s, rg["center"], rg["travel"])
        if res is None:
            stage_done(f"recv{k + 1}_failed", reason="no reachable receiver grasp", tip=tip()); finish()
        T_r, dist_r, s_r = res
        say(f"recv{k + 1}: grasp", round(dist_r, 3), "past the plane,", round(s_r, 3), "from the tip, approach",
            np.round(T_r[:3, 0], 3))
        if grasp_from_behind(s, T_r, from_tip=s_r):
            break
        say(f"recv{k + 1}: missed the rope (attempt {attempt + 1}), held offset", np.round(held_offset(s, s_r)[0], 3))
        R.set_grip(s, OPEN, 10)
        retreat(s)
    else:
        stage_done(f"recv{k + 1}_failed", reason="receiver grasp missed twice", tip=tip()); finish()
    f = other(s)
    R.set_grip(f, OPEN, 15)
    T = cmd_T(f); T[:3, 3] += -0.08 * T[:3, 0] - 0.03 * rg["travel"]
    try:
        R.move(f, T, speed=0.06)
    except RuntimeError:
        back_out(f, k)
        retreat(f)
    move_or_goto(f, R.tcp(f, R.q_ready[f]), 0.10)
    R.hold(10)
    stage_done(f"recv{k + 1}", s_from_tip=s_r, held_offset=held_offset(s, s_r)[0])
    return s_r


def back_out(f, k, dist=0.06):
    """Feeder f (just opened) backs out against ring k's feed direction. Its push may end within ~2 mm of the ring in the
    capsule model (feed_ok allows -2 mm), where every other first move reads as a collision; this straight reverse of the
    push runs with the planner's clearance relaxed to -3 mm."""
    mc = R.min_clear
    R.min_clear = min(mc, -0.003)
    try:
        T = cmd_T(f); T[:3, 3] -= dist * feed_dir(k)
        R.move(f, T, speed=0.04)
    except RuntimeError as e:
        say("back out failed:", str(e)[:100])
    finally:
        R.min_clear = mc


def tail_grasp(s, k, dist, check=None):
    """Arm s grasps the rope `dist` before ring k's plane on its tail side: approach every 15 deg around the local
    tangent (from above first), both rope-axis signs, grasp + 9 cm pre-grasp reachable, `check(T)` if given. Returns the
    grip distance from the tip, or None."""
    rg = RINGS[k]
    pt, ft = point_before_plane(rg["center"], rg["travel"], dist)
    if pt is None:
        return None
    t = station(ft)[1]
    u = np.cross(t, EZ); u /= np.linalg.norm(u); v = np.cross(u, t)
    cands = []
    for phi in range(0, 360, 15):
        a = np.cos(np.radians(phi)) * u + np.sin(np.radians(phi)) * v
        for zs in (1, -1):
            T = grip_T(s, a, zs * t, pt, np.array([args.recv_depth, 0, 0]))
            if finger_low_z(T) >= TABLE + 0.015:
                cands.append((a[2], T))
    cands.sort(key=lambda c_: c_[0])
    T = next((T for _, T in cands if R.reachable(s, T, grip_open=False) and R.reachable(s, backed(T, 0.09))
              and approach_clear(s, backed(T, 0.09), T) and (check is None or check(T))), None)
    if T is None:
        return None
    if grasp_from_behind(s, T, from_tip=ft):
        return ft
    R.set_grip(s, OPEN, 10)
    retreat(s)
    return None


def clamp(c, k):
    """Arm c holds the rope behind ring k (0.04 / 0.07 m before the previous ring, else 0.20 / 0.16 m before ring k) so
    it cannot slide back while the feeder lets go."""
    for kk, dist in ((k - 1, 0.04), (k - 1, 0.07), (k, 0.20), (k, 0.16)):
        if kk >= 0 and tail_grasp(c, kk, dist) is not None:
            stage_done(f"clamp{k + 1}", ring=RINGS[kk]["name"], before_m=dist, tip=tip())
            return
    stage_done(f"clamp{k + 1}_failed", reason="no clamp grasp behind the ring", tip=tip()); finish()


def repush(s, k, clamped=False):
    """Push ring k's rope further: the other arm clamps it (and keeps holding), s lets go, re-grasps `--repush_from`
    before the plane and feeds again (aim, tip alignment) until the grip is `--repush_to` before the plane."""
    c = other(s)
    if not clamped:
        clamp(c, k)
        if args.save_ckpt:
            R.snapshot(os.path.join(args.out, f"ckpt_clamp{k + 1}.pt"), dict(k=k, s=s, GF=None, clamped=True))
    release_and_leave(s)
    shift = (args.repush_from - args.repush_to) * feed_dir(k)

    def end_ok(T):
        Te = T.copy(); Te[:3, 3] += shift
        return R.reachable(s, Te, grip_open=False, clear=-0.002)
    ft = tail_grasp(s, k, args.repush_from, check=end_ok)
    if ft is None:
        stage_done(f"repush{k + 1}_failed", reason="no re-grasp behind the ring", tip=tip()); finish()
    feed(s, k, ft, name=f"repush{k + 1}", stop=args.repush_to, extra=0.0)


def pull(s, k, s_hold, target=None):
    """Pull the end through ring k: grip point to `target` (default `--pull_xyz[k]`), keeping the grasp orientation
    if reachable."""
    d = RINGS[k]["travel"]
    off, _ = held_offset(s, s_hold)
    T0 = cmd_T(s)
    zs = 1.0 if T0[:3, 2] @ d > 0 else -1.0
    target = np.asarray(args.pull_xyz[k] if target is None else target, float)
    for Rm in [T0[:3, :3]] + [frame_az(a, zs * d)[:3, :3] for a in perp_approaches(d, s, target)]:
        T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = target - Rm @ off
        if R.reachable(s, T, grip_open=False):
            break
    else:
        stage_done(f"pull{k + 1}_failed", reason="pull target unreachable"); finish()
    R.move_route(s, T, speed=args.speed)
    R.hold(20)
    stage_done(f"pull{k + 1}", slip_m=slip_report(s, s_hold, off), tip=tip(), past_m=float((tip() - RINGS[k]["center"]) @ d))


def drop(r, k, s_hold):
    """The receiver lowers the end to `--drop_xyz[k]` and lets go: the rope hangs from ring k's rim."""
    off, _ = held_offset(r, s_hold)
    T = cmd_T(r); gp = T[:3, :3] @ off + T[:3, 3]
    T[:3, 3] += np.asarray(args.drop_xyz[k], float) - gp
    R.move_route(r, T, speed=args.speed)
    R.hold(10)
    R.set_grip(r, OPEN, 15)
    retreat(r, dists=(0.06, 0.04))
    R.hold(int(30 * args.drop_settle_s))
    stage_done(f"drop{k + 1}", tip=tip(), past_m=float((tip() - RINGS[k]["center"]) @ RINGS[k]["travel"]))


def regrip(s, k, holder=None):
    """Feeder s of ring k+1 re-grasps the rope deep `--regrip_from_tip` from the tip with a rope-axis sign from which
    ring k+1's feed frame is reachable by an in-place rotation; lift. The rope hangs from ring k's rim (after drop), or
    `holder` still holds it near the tip (in-air handover: the holder lets go once the grasp is verified). Returns the
    grip distance from the tip."""
    c_next = RINGS[k + 1]["center"]
    off_g = np.array([args.recv_depth, 0, 0])

    frames = {}         # zs -> feed frames of ring k+1 with a reachable stroke (independent of the grasp: computed once)

    def feed_reachable_from(T, zs):
        """Some feed frame of ring k+1 (direction within --feed_cone) reachable over its stroke and by an in-place
        rotation from grasp T (lifted)."""
        if zs not in frames:
            cands = [(dd, frame_az(a_, zs * dd)[:3, :3]) for dd in feed_dirs(k + 1) for a_ in perp_approaches(dd, s, c_next)]
            frames[zs] = [Rm for dd, Rm in cands if feed_ok(s, Rm, k + 1, off_g, dd)]
            say(f"regrip{k + 1}: {len(frames[zs])} reachable feed frames for zsign {zs}")
        return any(slerp_ok(s, T, Rm, off_g) for Rm in frames[zs])

    for ft in args.regrip_from_tip:
        pt, t = station(ft)
        u = np.cross(t, EZ); u /= np.linalg.norm(u)
        v = np.cross(u, t)
        cands = []                      # approaches around the local tangent, from above first
        for phi in range(0, 360, 15):
            a = np.cos(np.radians(phi)) * u + np.sin(np.radians(phi)) * v
            for zs in (1, -1):
                T = grip_T(s, a, zs * t, pt, off_g)
                if finger_low_z(T) >= TABLE + 0.012:
                    cands.append((a[2], zs, T))
        cands.sort(key=lambda c_: c_[0])
        T_rg = next((T for _, zs, T in cands if R.reachable(s, T, grip_open=False)
                     and R.reachable(s, backed(T, 0.09)) and feed_reachable_from(T, zs)), None)
        say(f"regrip{k + 1} at", ft, "from the tip:", "point", np.round(pt, 3), "tangent", np.round(t, 2),
            "approach", None if T_rg is None else np.round(T_rg[:3, 0], 2))
        if T_rg is not None:
            break
    else:
        stage_done(f"regrip{k + 1}_failed", reason="cannot re-grasp the rope", tip=tip()); finish()
    if not grasp_from_behind(s, T_rg, from_tip=ft):
        stage_done(f"regrip{k + 1}_failed", reason="missed the rope", held_offset=held_offset(s, ft)[0]); finish()
    if holder is not None:
        R.set_grip(holder, OPEN, 15)
        retreat(holder)
        move_or_goto(holder, R.tcp(holder, R.q_ready[holder]), 0.10)
        R.hold(10)
    T = cmd_T(s); T[:3, 3] += 0.08 * EZ
    move_or_goto(s, T, 0.03)
    R.hold(10)
    stage_done(f"regrip{k + 1}", from_tip=ft, held_offset=held_offset(s, ft)[0], tip=tip())
    return ft


def lay_regrip(s, k, s_hold):
    """(--lay [gx, gy, psi, f]) Arm s holds the end s_hold from the tip past ring k and feeds ring k+1 next. A drop leaves the rope
    hanging from ring k's rim ~100 deg off ring k+1's feed direction and no grasp of it rotates onto a feed frame (X6a). Instead:
    carry the end to the table and drag it (fingertips 6 mm above the table, approach top-down leaning --lay_tilt against u)
    --lay_drag along u = ring k+1's horizontal feed direction yawed by psi, so that the rope point GF = f from
    the tip ends at (gx, gy); let go; pinch the rope at GF (top-down fingertip pinch, z_tcp toward the tip) and lift --lay_lift.
    The tip side then points roughly along the feed direction and to_feed_frame turns it in place onto a feed frame (R2a: with a
    0.10 m drag the rope at GF still rose 6 cm toward ring k, the pinch held its chord 58.6 deg off z_tcp, corrected in full).
    Returns GF."""
    gx, gy, psi, GF = args.lay[k]
    h = RINGS[k + 1]["travel"].copy(); h[2] = 0.0; h /= np.linalg.norm(h)
    u = Rot.from_rotvec(EZ * np.radians(psi)).as_matrix() @ h
    off, _ = held_offset(s, s_hold)
    T0 = cmd_T(s); gp = T0[:3, :3] @ off + T0[:3, 3]
    zs = 1.0 if T0[:3, 2] @ (tip() - gp) > 0 else -1.0
    tl = np.radians(args.lay_tilt)
    Rm = frame_az(np.cos(tl) * a_down - np.sin(tl) * u, zs * u)[:3, :3]

    def low(g, dz=0.0):
        T = at_grip(Rm, g, off)
        T[:3, 3] += (TABLE + 0.006 + dz - finger_low_z(T)) * EZ
        return T
    g1 = np.array([gx, gy, TABLE]) + (GF - s_hold) * u
    g0 = g1 - args.lay_drag * u
    move_or_goto(s, low(g0, 0.08), 0.05)
    R.hold(10)
    R.move(s, low(g0), speed=0.03)
    R.move(s, low(g1), speed=0.03)
    R.hold(10)
    R.set_grip(s, OPEN, 15)
    retreat(s)
    R.hold(15)
    pt, t = station(GF)
    t_h = t - EZ * (t @ EZ)
    lay_deg = float(np.degrees(np.arccos(np.clip(t_h @ u / np.linalg.norm(t_h), -1, 1))))
    say(f"lay{k + 1}: rope point {GF} from the tip at", np.round(pt, 3), "tangent", np.round(t, 2), "off u (deg)", round(lay_deg, 1),
        "tip", np.round(tip(), 3))
    if pinch(GF, fail=False, s=s, zss=(1,)) is None:
        stage_done(f"lay{k + 1}_failed", reason="no reachable pinch at the laid rope", pt=pt); finish()
    check_closed(s, f"lay{k + 1}_pinch")
    safe_shift(s, (args.lay_lift - 0.03) * EZ, 0.03)
    R.hold(10)
    stage_done(f"lay{k + 1}", from_tip=GF, lay_off_u_deg=lay_deg, finger=R.finger(s), held_offset=held_offset(s, GF)[0],
               chord_deg=chord_deg(s, GF), tip=tip())
    return GF


# ======================================================================== main
if args.resume:
    st = R.restore(args.resume)
    R.hold(5)
    k0, s, GF = st["k"], st["s"], st["GF"]
    say("RESUMED from", args.resume, st)
else:
    R.hold(10)
    if args.variant == "nop":
        R.hold(args.nop_steps)
        finish()
    ready()
    GF = pick_hold() if args.turn_open == 2 else pick_turn() if args.turn_open else pick()
    k0, s = 0, PK
    assert ARM[args.chain[0][0]] == PK, "ring 1's feeder must be the arm that picks the fed tip"
    if args.save_ckpt:
        R.snapshot(os.path.join(args.out, "ckpt_ring1.pt"), dict(k=0, s=s, GF=GF))
clamped = bool(args.resume and st.get("clamped"))      # --resume from ckpt_clamp<k>.pt: ring k is fed, the clamp holds
s_hold = st.get("s_hold") if args.resume else None     # --resume from ckpt_recv<k>.pt: ring k is fed and received
for k in range(k0, len(RINGS)):
    if not clamped and s_hold is None:
        if args.turn_open == 2 and k == 0:
            feed_hold(s, k, GF)
        else:
            to_feed_frame(s, k, GF, vias=args.orient_vias if k == 0 else ())
            feed(s, k, GF)
    if k == len(RINGS) - 1:
        break
    r = ARM[args.chain[k][1]]
    if r == s and s_hold is None:      # the feeder also receives past ring k: re-push under a clamp, then let go under the clamp
        if args.repush[k] == 0 and not clamped:
            clamp(other(s), k)
        for i in range(args.repush[k]):
            repush(s, k, clamped or i > 0)
        clamped = False
        release_and_leave(s)
    if s_hold is None:
        s_hold = receive(r, k)
        if args.save_ckpt:
            R.snapshot(os.path.join(args.out, f"ckpt_recv{k + 1}.pt"), dict(k=k, s=s, GF=GF, s_hold=s_hold))
    if args.variant == "naive_nolast" and k == len(RINGS) - 2:
        R.hold(int(args.settle_max_s * 30))
        stage_done("naive_hold", success=R.first_success is not None)
        finish()
    s = ARM[args.chain[k + 1][0]]
    if args.handover[k] and s != r:     # in-air handover: the receiver keeps the tip until the next feeder holds
        # stage the rope so the feeder's grip point (regrip_from_tip[0] from the tip) lies on ring k+1's feed start,
        # the tip direction along d_{k+1}: the receiver's grip goes (regrip_from_tip[0] - s_hold) further along d_{k+1}
        rn = RINGS[k + 1]
        stage = feed_gps(k + 1)[0] + (args.regrip_from_tip[0] - s_hold) * rn["travel"]
        pull(r, k, s_hold, target=stage)
        GF = regrip(s, k, holder=r)
    elif args.lay and args.lay[k] is not None:
        assert s == r, "--lay: the receiver of ring k feeds ring k+1"
        GF = lay_regrip(s, k, s_hold)
    else:
        pull(r, k, s_hold)
        drop(r, k, s_hold)
        if s != r:      # the receiver goes back to ready: near ring k+1 it blocks the next feeder's feed frames (X3r3)
            move_or_goto(r, R.tcp(r, R.q_ready[r]), 0.10)
            R.hold(10)
        GF = regrip(s, k)
    if args.save_ckpt:
        R.snapshot(os.path.join(args.out, f"ckpt_ring{k + 2}.pt"), dict(k=k + 1, s=s, GF=GF))
    s_hold = None

if args.finish == "hold":
    # holding is allowed by the old task: keep the feeder still and wait for the goal to latch
    R.hold(int(args.settle_max_s * 30))
    stage_done("settle_hold", success=R.first_success is not None)
    finish()

# ======================================================================== release finish: the other arm receives past the last ring,
# pulls the end along --finish_wps and lays it on the table
k = len(RINGS) - 1
d = RINGS[k]["travel"]
s = other(s)
s_r2 = receive(s, k)
off_l2, _ = held_offset(s, s_r2)
for wp in args.finish_wps:
    wp = np.asarray(wp, float)
    T0 = cmd_T(s)
    zl = 1.0 if T0[:3, 2] @ d > 0 else -1.0
    done = False
    for Rm in [T0[:3, :3]] + [frame_az(a, zl * d)[:3, :3] for a in perp_approaches(d, s, wp)]:
        T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = wp - Rm @ off_l2
        if not R.reachable(s, T, grip_open=False):
            continue
        try:
            R.move_route(s, T, speed=args.speed)
            done = True
            break
        except RuntimeError as e:
            say("finish waypoint", np.round(wp, 3), "failed:", str(e)[:80])
    say("finish waypoint", np.round(wp, 3), "reached" if done else "SKIPPED", "tip", np.round(tip(), 3))
    R.hold(10)
stage_done("finish_pull", tip=tip())
# lower the grip point to the table and release
T = cmd_T(s); gp = T[:3, :3] @ off_l2 + T[:3, 3]
T[:3, 3] += (TABLE + 0.006 - gp[2]) * EZ
try:
    R.move(s, T, speed=0.03)
except RuntimeError as e:
    say("cannot lower to the table:", str(e)[:80])
R.hold(10)
R.set_grip(s, OPEN, 20)
retreat(s)
move_or_goto(s, R.tcp(s, R.q_ready[s]), 0.10)
stage_done("release")
# ======================================================================== settle
n_max = int(args.settle_max_s * 30)
for k in range(n_max):
    if R.step() or R.first_success is not None:
        break
R.hold(15)
stage_done("settle", success=R.first_success is not None)
finish()
