"""Offline scan of the "drag the start tip left, turn it toward R3, re-grasp, feed R3" opening (numpy; OMP_NUM_THREADS=1).

Layout: ring group yaw 15 deg, t given; rope mirrored (rope_mirror_deg 90 convention: old x -> -x, then Rz(90) + rope_t);
route: START tip first, R3 -> R2 -> R1 (reverse); the LEFT arm handles the start tip; the right arm stays at its ready pose.
Model: the rope near the tip is a straight rigid segment of length `ell` (the first grasp point g0 is `ell` = 0.15 m from the tip, as oracle --drag1_from_tip; a re-grasp point farther from the tip lies on the straight extension of the segment); the
left hand pinches it at g0 (top-down, fingertips 2 mm above the table, z_tcp along the rope; either sign), drags it by D = (dx, dy)
and rotates the segment about the grip point by `rot` (toward the horizontal direction of R3's feed travel d3). Then it lets go and re-grasps
the rope `r` m from the tip (on the moved segment), lifts 7 cm and turns in place onto R3's feed frames.
Checks (all with the right arm at ready, left capsule clearance as Runner.reachable + 6 mm = 1 cm to fixtures/table/right arm):
  (a) drag: a continuous IK chain over 5 waypoints (grip point and tangent interpolated; start also needs the 8 cm pre-grasp), the moved
      rope segment keeps >= 1 cm from every stand base box / post and stays on the table; count = number of distinct chains (z_tcp sign x seed).
  (b) re-grasp: approach every 15 deg azimuth, tilt 0 / 15 / 30 deg from vertical (never from below), z_tcp along the rope tangent (either
      sign), TCP = rope point - 0.035 approach (tips ~2 mm above the table); fingertips >= `low_min` above the table (the pinch convention 0.0;
      the 0.015 asked for cannot hold for a rope lying on the table, reported separately); grasp pose and the pose backed off 9 cm reachable.
  (c) transition: the grasp pose lifted 7 cm is the start; the held chord is theta off z_tcp about the jaw axis (theta in 0, +-36, +-52);
      layout_eval.transition's logic with the held point at 0.035 along the approach: feed direction within 25 deg of the normal, chord correction
      fractions 1, 2/3, 1/3, 0, start / end grip poses (0.24 / 0.07 m before the plane) reachable, in-place rotation about the held point
      (slerp 13 steps, IK continuous, capsule clearance >= 8 mm, right arm at ready). z_tcp sign of the start pose = the sign of the frames.
Usage: python layout_drag.py --t 0.532 -0.241 [--nproc 6]   -> evidence/medium_layout/yaw15_drag_<tx>_<ty>.json
"""
import argparse, itertools, json, os, sys, time
import numpy as np
from scipy.spatial.transform import Rotation as Rot, Slerp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_eval as L
import medium_layout_search as M
import plan_np as PN
import yam_kin as K

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EZ = np.array([0, 0, 1.0])
TAB = M.TABLE
OFF_P = np.array([0.035, 0, 0])            # held rope point in the TCP frame after a table pinch (tips)
ROPE_T = (0.58, -0.1304)
ELL = 0.15
DRAGS, DXS, ROTS, RS = (0.05, 0.08, 0.11, 0.15), (0.0, 0.05, -0.05), (45, 60, 90, 120), (0.10, 0.14, 0.19)
THETAS = (0.0, 36.0, -36.0, 52.0, -52.0)
LOW_MIN = 0.0


def rope_xy():
    return (M.ROPE[:, :2] * np.array([-1, 1])) @ M.rot(90.0)[:2, :2].T + np.asarray(ROPE_T)


def rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s], [s, c]])


def tip_segment(xy, ell):
    """rope polyline points within arc length ell of the start tip (tip first) + the point at ell."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    n = int(np.searchsorted(s, ell))
    f = (ell - s[n - 1]) / (s[n] - s[n - 1])
    return np.vstack([xy[:n], xy[n - 1] + f * (xy[n] - xy[n - 1])])


def moved_segment(seg, D, phi):
    """rotate the segment (tip first, last point = grip g0) by phi about g0, then translate by D."""
    g0 = seg[-1]
    return (seg - g0) @ rz(phi).T + g0 + D


def seg_clear(pts, rings, yaw):
    """min rope-surface distance of the points to stand base boxes and posts."""
    Rz = M.rot(yaw)[:2, :2]; out = 9.0
    for r in rings:
        loc = (pts - r["base_center"][:2]) @ Rz
        out = min(out, float(np.linalg.norm(loc - np.clip(loc, (-0.025, -0.04), (0.025, 0.04)), axis=1).min()) - 0.004,
                  float(np.linalg.norm(pts - r["stand_center"][:2], axis=1).min()) - 0.009)
    return out


def tip_dir(seg):
    d = seg[0] - seg[-1]; return d / np.linalg.norm(d)         # grip -> tip (horizontal)


def top_down(pt, t_h, zs, lift=0.035):
    T = PN.frame_az(np.array([0, 0, -1.0]), zs * np.r_[t_h, 0]); T[:3, 3] = np.r_[pt, TAB + 0.004] + (0, 0, lift)
    return T


def ik_chain(side, Ts_list, q_ready, fix, other, clear=0.006, margin=0.05):
    """Continuous IK chains through the pose sequence Ts_list (each (4,4)); returns the number of distinct chains. First pose: seeds_for + q_ready,
    then batched DLS from the previous solution (step <= 0.6 rad), capsule clearance at every waypoint."""
    from reach_map import seeds_for
    base = K.BASES[side]
    Tb = np.array(Ts_list[0], float); Tb[:3, 3] -= base
    seeds = np.array([q_ready] + seeds_for(Tb[:3, 3]))
    q, ep, er = M.ik_batch(np.repeat(Tb[None], len(seeds), 0), seeds, 200, margin)
    ok = (ep < 1e-4) & (er < 1e-3)
    chains = []
    for j in np.flatnonzero(ok):
        if all(np.abs(q[j] - c[0]).max() > 0.3 for c in chains) and min(PN.arm_clearance(side, q[j], fix, other=other, grip_open=True).values()) >= 0.004 + clear:
            chains.append([q[j]])
    for T in Ts_list[1:]:
        if not chains:
            return 0
        Tb = np.array(T, float); Tb[:3, 3] -= base
        prev = np.array([c[-1] for c in chains])
        qn, ep, er = M.ik_batch(np.repeat(Tb[None], len(chains), 0), prev, 100, 0.03)
        good = (ep < 1.5e-3) & (er < 3e-2) & (np.abs(qn - prev).max(1) < 0.6)
        chains = [c + [qn[j]] for j, c in enumerate(chains) if good[j] and
                  min(PN.arm_clearance(side, qn[j], fix, other=other, grip_open=True).values()) >= 0.004 + clear]
    return len(chains)


def approaches():
    out = []
    for tilt in (0, 15, 30):
        for az in (range(0, 360, 15) if tilt else [0]):
            p = np.radians(tilt); a = np.radians(az)
            out.append((tilt, az, np.array([np.sin(p) * np.cos(a), np.sin(p) * np.sin(a), -np.cos(p)])))
    return out


APPR = approaches()


def regrasp(side, pt, t_h, fix, q_ready, q_other, low_min=LOW_MIN):
    """-> list of (T_grasp, zs, tilt, az) with grasp + 9 cm back-off + 7 cm lift reachable and fingertips >= low_min above the table."""
    cands = []
    for tilt, az, a in APPR:
        for zs in (1, -1):
            T = PN.frame_az(a, zs * np.r_[t_h, 0]); T[:3, 3] = np.r_[pt, TAB + 0.004] - 0.035 * T[:3, 0]
            if PN.finger_low_z(T) < TAB + low_min:
                continue
            cands.append((T, zs, tilt, az))
    if not cands:
        return [], 0
    other = ("right", q_other, True)
    ok1 = L.reach_many(side, [c[0] for c in cands], q_ready, fix, other, clear=0.006, grip_open=True)
    ok1i = [i for i, o in enumerate(ok1) if o]
    back = []
    for i in ok1i:
        T = cands[i][0].copy(); T[:3, 3] -= 0.09 * T[:3, 0]; back.append(T)
    ok2 = L.reach_many(side, back, q_ready, fix, other, clear=0.006, grip_open=True)
    res = [cands[i] for i, o in zip(ok1i, ok2) if o]
    n_b = len(res)
    lift = []
    for c in res:
        T = c[0].copy(); T[:3, 3] += (0, 0, 0.07); lift.append(T)
    ok3 = L.reach_many(side, lift, q_ready, fix, ("right", q_other, True), clear=0.006, grip_open=False) if lift else []
    return [c + (T,) for c, T, o in zip(res, lift, ok3) if o], n_b


def slerp_off(side, T0, R_goal, fix, other, off, n=13):
    gp = T0[:3, :3] @ off + T0[:3, 3]
    sl = Slerp([0, 1], Rot.from_matrix(np.stack([T0[:3, :3], R_goal])))
    q = None
    for f in np.linspace(0, 1, n):
        Rm = sl(f).as_matrix(); T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = gp - Rm @ off
        if q is None:
            q = PN.solve(side, T, margin=0.03)
            if q is None:
                return False
        else:
            qn, o, ep, er = K.ik(K.world_to_base(T, side), q, iters=200, margin=0.02)
            if not (o or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.5:
                return False
            q = qn
        if min(PN.arm_clearance(side, q, fix, other=(other[0], other[1], True), grip_open=False).values()) < 0.008:
            return False
    return True


def feed_frames(side, ring, fix, q_ready, q_other, theta, zs, cone=25.0, start=0.24, stop=0.07):
    """feed frames (start/end grip poses reachable, held point at OFF_P) for chord angle theta and z_tcp sign zs: list of TCP orientations."""
    other = ("right", q_other, True)
    d, c = ring["travel"], ring["center"]
    th = np.radians(theta); c_t = np.array([np.sin(th), 0, zs * np.cos(th)])
    ax = np.cross(c_t, zs * EZ); n = np.linalg.norm(ax)
    q_rv = np.zeros(3) if n < 1e-9 else ax / n * np.arctan2(n, c_t @ (zs * EZ))
    fracs = (1.0, 2 / 3, 1 / 3, 0.0) if n > 1e-9 else (1.0,)
    cands, seen = [], set()
    for dd in L.feed_dirs(d, cone):
        for frac in fracs:
            Q = Rot.from_rotvec(frac * q_rv).as_matrix()
            for a in L.perp_approaches(dd, side, c):
                Rm = PN.frame_az(a, zs * dd)[:3, :3] @ Q
                key = (tuple(np.round(dd, 4)), tuple(np.round(Rm.ravel(), 4)))
                if key not in seen:
                    seen.add(key); cands.append((dd, Rm))
    g0 = lambda dd: c - start * dd - 0.01 * EZ
    g1 = lambda dd: c - stop * dd - 0.01 * EZ
    a_ok = L.reach_many(side, [L.at_grip(Rm, g0(dd), OFF_P) for dd, Rm in cands], q_ready, fix, other, grip_open=False)
    idx = [i for i, o in enumerate(a_ok) if o]
    b_ok = L.reach_many(side, [L.at_grip(cands[i][1], g1(cands[i][0]), OFF_P) for i in idx], q_ready, fix, other, clear=-0.002, grip_open=False)
    return [cands[i][1] for i, o in zip(idx, b_ok) if o]


def setup(t):
    M.RINGS_ONLY = True
    rings, _ = M.place(15.0, tuple(t)); fix = L.fixture(rings)
    order = [dict(x, travel=-x["sign"] * x["normal"]) for x in rings[::-1]]
    q = {}
    for side in ("left", "right"):
        sg = 1 if side == "left" else -1
        q[side] = M.goto_q(side, PN.frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, sg * 0.30, 0.95)), M.HOME, fix, ("right" if side == "left" else "left", M.HOME, True))
    return rings, fix, order, q


def frames_table(t, thetas=THETAS):
    """feed frames of R3 for the left arm per (theta, zs): computed once per t."""
    rings, fix, order, q = setup(t)
    return {(th, zs): feed_frames("left", order[0], fix, q["left"], q["right"], th, zs) for th in thetas for zs in (1, -1)}


def eval_config(t, drag, dx, rot, r, frames, cap=3, max_starts=6):
    rings, fix, order, q = setup(t)
    d3 = order[0]["travel"][:2]; a3 = np.arctan2(d3[1], d3[0])
    xy = rope_xy(); seg = tip_segment(xy, ELL)
    t0 = tip_dir(seg); a0 = np.arctan2(t0[1], t0[0])
    dphi = (a3 - a0 + np.pi) % (2 * np.pi) - np.pi
    sgn = 1.0 if dphi >= 0 else -1.0
    phi = sgn * np.radians(rot); D = np.array([dx, drag])
    row = dict(t=list(t), drag=drag, dx=dx, rot=rot, r=r, turn_needed_deg=round(float(np.degrees(dphi)), 1), final_tip_dir_off_d3_deg=None)
    other = ("right", q["right"], True)
    # (a) drag
    fr = [0, .25, .5, .75, 1.0]
    segs = [moved_segment(seg, f * D, f * phi) for f in fr]
    clr = min(seg_clear(np.vstack([s, s[-1] - 0.05 * tip_dir(s)]), rings, 15.0) for s in segs)
    onT = all(PN.TABLE_X[0] + 0.014 <= s[:, 0].min() and s[:, 0].max() <= PN.TABLE_X[1] - 0.014 and abs(s[:, 1]).max() <= PN.TABLE_Y - 0.014 for s in segs)
    final = segs[-1]; td = tip_dir(final)
    ext = final[-1] - 0.05 * td          # straight extension behind the grip (re-grasp at 0.19 m)
    row["final_tip_dir_off_d3_deg"] = round(float(np.degrees(np.arccos(np.clip(td @ (d3 / np.linalg.norm(d3)), -1, 1)))), 1)
    row["seg_clear_min_mm"] = round(clr * 1000, 1); row["on_table"] = bool(onT); row["final_tip"] = final[0].round(3).tolist()
    n_a = 0
    if clr >= 0.01 and onT:
        for zs in (1, -1):
            Ts = []
            for f, s in zip(fr, segs):
                Ts.append(top_down(s[-1], tip_dir(s), zs))
            pre = Ts[0].copy(); pre[:3, 3] += (0, 0, 0.08)
            n_a += ik_chain("left", [pre] + Ts, q["left"], fix, other)
    row["n_drag"] = n_a
    if clr < 0.01 or not onT:
        row["first_fail"] = "拖拽：转后绳段离底座/立柱 %.1f mm < 10 mm 或出桌面" % (clr * 1000)
    elif n_a == 0:
        row["first_fail"] = "拖拽：路点 IK 不可达/不连续或撞（左手，右手在 ready）"
    # (b) re-grasp
    pt = final[0] - r * td
    sols, n_b = regrasp("left", pt, td, fix, q["left"], q["right"])
    row["n_regrasp"] = n_b; row["n_regrasp_lift"] = len(sols)
    if "first_fail" not in row and not sols:
        row["first_fail"] = "再抓：抓位/后退 9 cm/抬 7 cm 无可达姿态（%d 个抓位+后退可达）" % n_b
    # (c) transition
    tr = {}
    for th in THETAS:
        plans = starts = 0
        for T, zs, tilt, az, Tl in sols[:max_starts]:
            got = 0
            for Rm in frames[(th, zs)]:
                if slerp_off("left", Tl, Rm, fix, ("right", q["right"]), OFF_P):
                    got += 1
                    if got >= cap:
                        break
            plans += got; starts += got > 0
        tr[str(th)] = dict(plans=plans, starts_ok=starts, n_starts=min(len(sols), max_starts))
    row["transition"] = tr
    row["n_theta_ok"] = sum(v["plans"] > 0 for v in tr.values())
    row["theta_ok"] = [float(k) for k, v in tr.items() if v["plans"] > 0]
    row["all_ok"] = bool(n_a > 0 and sols and row["n_theta_ok"] > 0)
    if "first_fail" not in row and row["n_theta_ok"] == 0:
        row["first_fail"] = "过渡：抓起末态→R3 喂入，所有 θ 都没有可行的原地转动方案（再抓后可抬起的起点 %d 个，喂入姿态 %d 个）" % (len(sols), sum(len(v) for v in frames.values()))
    return row


_FR = {}
def _job(a):
    t, drag, dx, rot, r = a
    key = tuple(t)
    if key not in _FR:
        _FR[key] = frames_table(key)
    t0 = time.time()
    row = eval_config(key, drag, dx, rot, r, _FR[key])
    row["secs"] = round(time.time() - t0, 1)
    print(row["t"], drag, dx, rot, r, "a", row["n_drag"], "b", row["n_regrasp_lift"], "c", {k: v["plans"] for k, v in row["transition"].items()}, row.get("first_fail", ""), row["secs"]); sys.stdout.flush()
    return row


if __name__ == "__main__":
    from multiprocessing import Pool
    ap = argparse.ArgumentParser()
    ap.add_argument("--t", type=float, nargs=2, default=[0.532, -0.241])
    ap.add_argument("--nproc", type=int, default=6)
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    t = tuple(a.t)
    jobs = [(t, *c) for c in itertools.product(DRAGS, DXS, ROTS, RS)]
    if a.test:
        jobs = jobs[:1]
    if not a.test or True:
        t0 = time.time(); _FR[t] = frames_table(t); print("feed frames", {k: len(v) for k, v in _FR[t].items()}, round(time.time() - t0)); sys.stdout.flush()
    out = []
    fn = W + "/evidence/medium_layout/yaw15_drag_%.3f_%.3f.json" % t
    with Pool(a.nproc) as pool:
        for row in pool.imap_unordered(_job, jobs, chunksize=1):
            out.append(row); json.dump(out, open(fn, "w"), indent=1, default=str)
    print("ALL DONE")
