"""Offline screen of the medium R1 stage (D12 layout, start tip fed R3 -> R2 -> R1): which right-arm grasps of the rope past R2
reach an R1 feed frame. numpy only (OMP_NUM_THREADS=1); RT_RELAYOUT must be the run's (shift_env.sh s612).
State: a run's states.npz at a step index (rope links -> centreline, measured joints; the commanded targets = the logged actions).
Criteria are the oracle's (Runner.reachable / _path_ok / plan_line on an offline Runner; capsule model, min_clear 4 mm).
  frames  the right's R1 feed frames: direction d1 or 10/18/25 deg off it, approach every 15 deg around it, z_tcp sign, held point
          `off` in the TCP frame; start / end grip 0.24 (--start) / 0.07 m before the plane reachable (end with 2 mm, as feed_ok).
  hang    (variant d) the rope hanging from R2 (X6a drop2): regrip's grasp candidates at --from_tip, lift 8 cm, then (i) an in-place
          rotation (slerp_ok) or (ii) a joint-space route (direct or through Runner.via_poses) to a frame's start pose; the held
          tip (rigid, along z_tcp) must not cross R1's aperture on the way.
  table   (variant b) the end laid on the table along u = d1 yawed by --psi: top-down / tilted fingertip pinch at G (--from_tip
          from the tip, rope 2 mm above the fingertips) with z_tcp toward the tip, pre-grasp 8 cm above, lift 10 cm, in-place
          rotation onto a feed frame (to_feed_frame's check) + line / route to its start. The lay-down before it (the right holding
          0.071 m from the tip drags the end top-down along u so that G ends at its place) is reported as a continuous line.
Usage: python r1_screen.py --states X6a/states.npz --step 6373 hang
       python r1_screen.py --states X6a/states.npz --step 6148 table --psi 0 15 -15
"""
import argparse, json, os, sys
import numpy as np
import torch
from scipy.spatial.transform import Rotation as Rot, Slerp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "overlay/yamlab/envs/tasks/rope_threading_lib")
sys.path.insert(0, LIB)
import threading_geom as TH
import rope_chain as C
import rt_common as RT
import plan_np as PN
import yam_kin as K
import layout_eval as L

EZ = np.array([0, 0, 1.0])
TABLE = 0.75
OFF_AIR = np.array([0.012, 0, 0])      # in-air grasp: rope 12 mm inside the pads
OFF_PINCH = np.array([0.035, 0, 0])    # table pinch: rope 2 mm above the fingertips


class OffRunner(RT.Runner):
    """Runner's planning methods on a logged state (no env)."""
    def __init__(self, fix, q14, cur14):
        self.fix, self.min_clear = fix, 0.004
        self._q = {"left": np.asarray(q14[0:6], float), "right": np.asarray(q14[7:13], float)}
        self.cur = torch.tensor(np.asarray(cur14, np.float32)[None])

    def q(self, s):
        return self._q[s]

    def set_cur(self, s, q):
        self.cur[0, RT.SL[s]] = torch.tensor(q, dtype=torch.float32)


def load(states, step):
    scn = TH.scene("medium")
    S = np.load(states)
    joints = C.chain_points_from_links(S["rope_pos"][step].astype(float), S["rope_quat"][step].astype(float), 0.01)[0]
    rings = {r["name"]: r for r in scn["rings"]}
    r1 = dict(rings["R1"]); r1["travel"] = np.asarray(r1["normal"], float)      # start tip fed: R1's travel reversed (+n)
    R = OffRunner(PN.fixture_capsules(scn["rings"]), S["q"][step], S["actions"][step])
    return R, joints[::-1], r1, rings          # rope points with the fed tip LAST (as oracle.rope_pts)


def station(P, f):
    Q = P[::-1]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    i = min(max(int(np.searchsorted(s, f)), 1), len(Q) - 1)
    a = (f - s[i - 1]) / (s[i] - s[i - 1])
    t = Q[i - 1] - Q[i]
    return Q[i - 1] + a * (Q[i] - Q[i - 1]), t / np.linalg.norm(t)


def feed_dirs(d, cone=25.0):
    h = np.cross(EZ, d); h /= np.linalg.norm(h); v = np.cross(d, h)
    return [d] + [np.cos(np.radians(dv)) * d + np.sin(np.radians(dv)) * (np.cos(np.radians(az)) * h + np.sin(np.radians(az)) * v)
                  for dv in (10, 18, 25) if dv <= cone for az in range(0, 360, 45)]


def around(t, step=15):
    u = np.cross(t, EZ); u /= np.linalg.norm(u); v = np.cross(u, t)
    return [np.cos(np.radians(p)) * u + np.sin(np.radians(p)) * v for p in range(0, 360, step)]


def at_grip(Rm, g, off):
    T = np.eye(4); T[:3, :3] = Rm; T[:3, 3] = g - Rm @ off
    return T


def reach(R, Ts, clear=0.01, grip_open=True):
    """Runner.reachable for many poses of the right (batched IK, layout_eval.reach_many), the left at its commanded q."""
    oq = R.cur[0, RT.SL["left"]].numpy().astype(float)
    qs = R.cur[0, RT.SL["right"]].numpy().astype(float)
    return L.reach_many("right", Ts, qs, R.fix, ("left", oq, True), clear=clear, grip_open=grip_open)


def feed_frames(R, r1, off, zs_list=(1, -1), start=0.24, stop=0.07, cone=25.0):
    """[(zs, dd, Rm)] with start + end grip poses reachable by the right (oracle.feed_ok)."""
    c = np.asarray(r1["center"], float)
    cands = [(zs, dd, PN.frame_az(a, zs * dd)[:3, :3]) for zs in zs_list for dd in feed_dirs(r1["travel"], cone)
             for a in around(dd) if a[2] <= 0.5]                                  # not from below
    ok0 = reach(R, [at_grip(Rm, c - start * dd - 0.01 * EZ, off) for _, dd, Rm in cands], grip_open=False)
    cands = [x for x, o in zip(cands, ok0) if o]
    ok1 = reach(R, [at_grip(Rm, c - stop * dd - 0.01 * EZ, off) for _, dd, Rm in cands], clear=-0.002, grip_open=False)
    return [x for x, o in zip(cands, ok1) if o]


def slerp_ok(R, T0, Rg, off, lift=0.0, n=13):
    """oracle.slerp_ok: in-place rotation about the held point after a lift, IK continuous, clearance >= 8 mm."""
    gp = T0[:3, :3] @ off + T0[:3, 3] + lift * EZ
    sl = Slerp([0, 1], Rot.from_matrix(np.stack([T0[:3, :3], Rg])))
    q = None
    oq = R.cur[0, RT.SL["left"]].numpy().astype(float)
    for f in np.linspace(0, 1, n):
        Rm = sl(f).as_matrix(); T = at_grip(Rm, gp, off)
        if q is None:
            q = PN.solve("right", T, margin=0.03)
            if q is None:
                return False
        else:
            qn, o, ep, er = K.ik(K.world_to_base(T, "right"), q, iters=200, margin=0.02)
            if not (o or (ep < 1.5e-3 and er < 3e-2)) or np.abs(qn - q).max() > 0.5:
                return False
            q = qn
        if min(PN.arm_clearance("right", q, R.fix, other=("left", oq, True), grip_open=False).values()) < 0.008:
            return False
    return True


def crosses_r1(r1, gp, tip):
    """The straight held segment gp -> tip crosses R1's plane inside the ring (radius + tube)."""
    c, n = np.asarray(r1["center"], float), r1["travel"]
    a, b = (gp - c) @ n, (tip - c) @ n
    if a * b > 0:
        return False
    p = gp + (a / (a - b)) * (tip - gp) if a != b else gp
    return np.linalg.norm(p - c - n * ((p - c) @ n)) < r1["radius"] + r1["tube"] + 0.004


def route_to(R, q0, T_goal, r1, off, L, zs):
    """Joint-space route q0 -> an IK solution of T_goal, direct or through one via pose (Runner.goto's search); the rigid held
    tip (L along zs*z_tcp from the held point) must not cross R1's aperture. Returns the joint waypoints or None."""
    def tip_ok(qa, qb, k=12):
        for f in np.linspace(0, 1, k):
            T = R.tcp("right", qa + (0.5 - 0.5 * np.cos(np.pi * f)) * (qb - qa))
            gp = T[:3, :3] @ off + T[:3, 3]
            if crosses_r1(r1, gp, gp + L * zs * T[:3, 2]):
                return False
        return True
    R.set_cur("right", q0)
    sols = R._ik_all("right", T_goal)
    for q in sols[:6]:
        if R._path_ok("right", q0, q)[0] and tip_ok(q0, q):
            return [q]
    for Tv in R.via_poses("right"):
        for qv in R._ik_all("right", Tv)[:2]:
            if not (R._path_ok("right", q0, qv)[0] and tip_ok(q0, qv)):
                continue
            for q in sols[:6]:
                if R._path_ok("right", qv, q)[0] and tip_ok(qv, q):
                    return [qv, q]
    return None


def screen_hang(R, P, r1, a):
    fr = feed_frames(R, r1, OFF_AIR, zs_list=(1,), start=a.start)
    print(f"[hang] {len(fr)} feed frames (zs +1, start {a.start})")
    out = []
    q_cur = R.cur[0, RT.SL["right"]].numpy().astype(float).copy()
    for f in a.from_tip:
        pt, t = station(P, f)
        n_g = n_slerp = n_route = 0
        R.set_cur("right", q_cur)
        gr = [(ap, zs, PN.grip_T(ap, zs * t, pt, OFF_AIR)) for ap in around(t) for zs in (1, -1)]
        gr = [g for g in gr if PN.finger_low_z(g[2]) >= TABLE + 0.012]
        ok = reach(R, [g[2] for g in gr], grip_open=False)
        gr = [g for g, o in zip(gr, ok) if o]
        ok = reach(R, [RT_backed(g[2], 0.09) for g in gr])
        gr = [g for g, o in zip(gr, ok) if o]
        for ap, zs, T in gr:
                n_g += 1
                Tl = T.copy(); Tl[:3, 3] += 0.08 * EZ
                ql = R._ik_all("right", Tl)
                if not ql:
                    continue
                for zf, dd, Rm in fr:
                    if zf != zs:
                        continue
                    Tf = at_grip(Rm, np.asarray(r1["center"]) - a.start * dd - 0.01 * EZ, OFF_AIR)
                    if slerp_ok(R, T, Rm, OFF_AIR, lift=0.08):
                        n_slerp += 1
                        out.append(dict(kind="slerp", f=f, zs=zs, approach=ap.round(3).tolist(), frame_approach=Rm[:, 0].round(3).tolist(),
                                        dd=dd.round(3).tolist()))
                        break
                    rt = route_to(R, ql[0], Tf, r1, OFF_AIR, f, zs)
                    if rt is not None:
                        n_route += 1
                        out.append(dict(kind="route", f=f, zs=zs, approach=ap.round(3).tolist(), frame_approach=Rm[:, 0].round(3).tolist(),
                                        dd=dd.round(3).tolist(), n_wp=len(rt)))
                        break
        print(f"[hang] f {f}: point {np.round(pt, 3)} tangent {np.round(t, 2)}: grasps {n_g}, in-place {n_slerp}, joint route {n_route}")
    return out


def RT_backed(T, back):
    Tb = T.copy(); Tb[:3, 3] -= back * T[:3, 0]
    return Tb


def screen_table(R, r1, a):
    """Variant b on a grid of re-grasp points G (x, y) and lay directions u = Rz(psi) d1 (horizontal)."""
    fr = feed_frames(R, r1, OFF_PINCH, zs_list=(1,), start=a.start)
    print(f"[table] {len(fr)} feed frames for the pinch offset (zs +1, start {a.start})")
    d1 = r1["travel"].copy(); d1[2] = 0; d1 /= np.linalg.norm(d1)
    q_hold = R.cur[0, RT.SL["right"]].numpy().astype(float).copy()
    rows = []
    for psi in a.psi:
        u = np.r_[Rot.from_rotvec(EZ * np.radians(psi)).as_matrix()[:2, :2] @ d1[:2], 0.0]
        for gx in np.arange(a.gx[0], a.gx[1] + 1e-9, 0.03):
            for gy in np.arange(a.gy[0], a.gy[1] - 1e-9, -0.03):
                G = np.array([gx, gy, TABLE + 0.004])
                tip = G + a.from_tip[0] * u
                if seg_hits_base(G - 0.12 * u, tip + 0.02 * u, r1):
                    continue
                res = dict(psi=psi, G=G[:2].round(3).tolist(), pinch=[], feed=[])
                for tilt in (0, 15, 30):
                    for az in ([0] if tilt == 0 else range(0, 360, 45)):
                        p_, z_ = np.radians(tilt), np.radians(az)
                        ap = np.array([np.sin(p_) * np.cos(z_), np.sin(p_) * np.sin(z_), -np.cos(p_)])
                        T = PN.grip_T(ap, u, G, OFF_PINCH)
                        if PN.finger_low_z(T) < TABLE - 0.001:
                            continue
                        Tpre = T.copy(); Tpre[:3, 3] += 0.08 * EZ
                        Tl = T.copy(); Tl[:3, 3] += a.lift * EZ
                        R.set_cur("right", q_hold)
                        if not all(reach(R, [T, Tpre]) + reach(R, [Tl], grip_open=False)):
                            continue
                        res["pinch"].append((tilt, az))
                        for zf, dd, Rm in fr:
                            if slerp_ok(R, Tl, Rm, OFF_PINCH):
                                res["feed"].append(dict(tilt=tilt, az=az, frame_approach=Rm[:, 0].round(3).tolist(),
                                                        dd=dd.round(3).tolist()))
                                break
                        if res["feed"]:
                            break
                    if res["feed"]:
                        break
                res["lay"] = lay_ok(R, q_hold, G, u, a) if res["feed"] else None
                rows.append(res)
                print(f"[table] psi {psi:+.0f} G {res['G']}: pinch poses {len(res['pinch'])}, feed via in-place roll "
                      f"{res['feed'][:1]}, lay-down {res['lay']}")
    return rows


def seg_hits_base(p0, p1, r1, clear=0.02):
    """The laid rope p0 -> p1 passes within `clear` of R1's stand base box (+4 mm rope) or post."""
    yaw = np.radians(r1.get("base_yaw_deg", TH.RELAYOUT["medium"]["yaw_deg"]))
    Rz = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
    for f in np.linspace(0, 1, 25):
        p = p0[:2] + f * (p1[:2] - p0[:2])
        loc = (p - np.asarray(r1["base_center"])[:2]) @ Rz
        if np.linalg.norm(loc - np.clip(loc, (-0.025, -0.04), (0.025, 0.04))) < clear + 0.004:
            return True
    return False


def lay_ok(R, q_hold, G, u, a):
    """The right holds 0.071 m from the tip (top-down, z_tcp = u, pinch offset) and drags 0.20 m along u on the table, ending with
    the rope point `from_tip` at G: is the drag a feasible straight line (plan_line) from a reachable start?"""
    g_end = G + (a.from_tip[0] - 0.071) * u
    g_start = g_end - 0.20 * u
    for tilt in (0, 15, 30):
        ap = np.array([-np.sin(np.radians(tilt)) * u[0], -np.sin(np.radians(tilt)) * u[1], -np.cos(np.radians(tilt))])
        T0 = PN.grip_T(ap, u, g_start + 0.006 * EZ, OFF_PINCH)
        T1 = PN.grip_T(ap, u, g_end + 0.006 * EZ, OFF_PINCH)
        R.set_cur("right", q_hold)
        sols = R._ik_all("right", T0)
        for q in sols[:4]:
            R.set_cur("right", q)
            try:
                R.plan_line("right", T1, 40)
                return dict(tilt=tilt, start=g_start[:2].round(3).tolist())
            except RuntimeError:
                continue
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["frames", "hang", "table"])
    ap.add_argument("--states", required=True)
    ap.add_argument("--step", type=int, required=True, help="index into states.npz (= action count - 1)")
    ap.add_argument("--start", type=float, default=0.24)
    ap.add_argument("--from_tip", type=float, nargs="+", default=[0.15, 0.17, 0.19])
    ap.add_argument("--psi", type=float, nargs="+", default=[0.0])
    ap.add_argument("--gx", type=float, nargs=2, default=[0.42, 0.60])
    ap.add_argument("--gy", type=float, nargs=2, default=[-0.36, -0.54])
    ap.add_argument("--lift", type=float, default=0.10)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    R, P, r1, rings = load(a.states, a.step)
    print("R1", np.round(r1["center"], 3), "travel", np.round(r1["travel"], 3), "fed tip", np.round(P[-1], 3))
    if a.mode == "frames":
        for off, nm in ((OFF_AIR, "in-air 12 mm"), (OFF_PINCH, "pinch 35 mm")):
            fr = feed_frames(R, r1, off, start=a.start)
            print(f"[frames] {nm}: {len(fr)}  (zs +1: {sum(z > 0 for z, _, _ in fr)})")
            for zs, dd, Rm in fr:
                print("   zs", zs, "dd", np.round(dd, 2), "approach", np.round(Rm[:, 0], 2),
                      "off d1 (deg)", round(float(np.degrees(np.arccos(np.clip(dd @ r1['travel'], -1, 1)))), 0))
        res = None
    elif a.mode == "hang":
        res = screen_hang(R, P, r1, a)
    else:
        res = screen_table(R, r1, a)
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1, default=lambda x: np.asarray(x).tolist())
