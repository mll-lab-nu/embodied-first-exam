"""Nominal (open-loop) object keyframes, grasps and a YAM IK feasibility check for the Cast Keyhole oracle.

The oracle (task/oracle.py) uses the same functions with measured object poses; this script only checks
that every waypoint has an IK solution with joint margin and no large joint jumps.

usage: python plan.py <tier> [--gamma DEG] [--split F] [--work dx dy h]
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

import keyhole_geometry as kg
import route as rt
import yam_kin as yk
from layout import Scene, TABLE_Z, T_from


def frame(a, j):
    """TCP rotation from approach a and jaw j (orthonormalised): columns [a, j, a x j]."""
    a = np.asarray(a, float); a /= np.linalg.norm(a)
    j = np.asarray(j, float); j = j - a * (j @ a); j /= np.linalg.norm(j)
    return np.c_[a, j, np.cross(a, j)]


@dataclass
class Grasps:
    """TCP poses in the plate frames (m)."""
    gold_tcp: tuple = (0.059, -0.040, 0.0)       # side band of the gold +x prong, outside the silver sweep
    silver_tcp: tuple = (-0.037, 0.090, 0.0)     # silver cap, approached from the -x edge
    gold_jaw: float = -1.0                       # jaw = gold_jaw * plate z (sign picks the wrist roll / camera side)
    silver_jaw: float = -1.0

    def T_gold(self):
        return T_from(frame([-1, 0, 0], [0, 0, self.gold_jaw]), self.gold_tcp)

    def T_silver(self):
        return T_from(frame([1, 0, 0], [0, 0, self.silver_jaw]), self.silver_tcp)


def rot_about(T, R, pivot):
    """Rotate pose T by world rotation R about a world pivot."""
    out = T.copy()
    out[:3, :3] = R @ T[:3, :3]
    out[:3, 3] = R @ (T[:3, 3] - pivot) + pivot
    return out


def translate(T, d):
    out = T.copy(); out[:3, 3] += d
    return out


@dataclass
class Plan:
    tier: str
    gamma_deg: float = 0.0          # gold yaw during the key turn (silver yaw = gamma - 90)
    split: float = 0.5              # fraction of the channel translation done by the gold (opposite direction)
    work: tuple = (0.0, 0.0, 0.10)  # bar point at work pose: (dx, dy) from its start, height above the table
    tilt_deg: float = -45.0         # assembly rotation about world X for the work pose (gold flat)
    grasps: Grasps = field(default_factory=Grasps)

    def __post_init__(self):
        self.scene = Scene(self.tier)
        self.rec = self.scene.record
        self.r0, self.c0 = rt.nominal_relative(self.rec)
        self.guides = rt.channel_guides(self.tier, self.rec["scale"])

    def set_initial_from_parts(self, gold_pose7, silver_pose7):
        """Initial plate frames from measured part-frame poses (pos + quat wxyz), e.g. the settled state."""
        for name, st, attr in (("gold", gold_pose7, "Tg_init"), ("silver", silver_pose7, "Ts_init")):
            st = np.asarray(st, float)
            T = T_from(Rotation.from_quat(st[[4, 5, 6, 3]]), st[:3])
            setattr(self, attr, T @ self.scene.T_part_plate[name])

    def bar_world(self, Tg, c=None):
        c = self.c0 if c is None else c
        return Tg[:3, :3] @ c + Tg[:3, 3]

    def silver_from_rel(self, Tg, R_rel, c):
        """Silver plate world pose from the gold plate world pose and a relative configuration."""
        p = rt.silver_plate_pose_in_gold(R_rel, c, self.rec["scale"])
        return Tg @ T_from(R_rel, p)

    def keyframes(self, Tg0=None, Ts0=None):
        """Object keyframes [(name, T_gold_plate, T_silver_plate, phase)]; densely sampled."""
        Tg0 = getattr(self, "Tg_init", self.scene.T_plate0["gold"]) if Tg0 is None else Tg0
        Ts0 = getattr(self, "Ts_init", self.scene.T_plate0["silver"]) if Ts0 is None else Ts0
        out = [("start", Tg0, Ts0, "start")]
        bar0 = self.bar_world(Tg0)
        bw = bar0 + np.r_[self.work[0], self.work[1], 0.0]
        bw[2] = TABLE_Z + self.work[2]
        # lift + tilt (rigid assembly motion), first a straight lift of 3 cm
        for u in np.linspace(0, 1, 16)[1:]:
            d = np.r_[0, 0, .03 * u]
            out.append(("lift0", translate(Tg0, d), translate(Ts0, d), "lift"))
        Tg_l, Ts_l = out[-1][1], out[-1][2]
        b_l = self.bar_world(Tg_l)
        # rigid re-orientation: gold to its work orientation Rx(tilt) * (authored start orientation)
        R_work = Rotation.from_euler("x", self.tilt_deg, degrees=True).as_matrix() @ self.scene.T_plate0["gold"][:3, :3]
        rv = Rotation.from_matrix(R_work @ Tg_l[:3, :3].T).as_rotvec()
        for u in np.linspace(0, 1, 41)[1:]:
            R = Rotation.from_rotvec(rv * u).as_matrix()
            d = (bw - b_l) * u
            out.append(("tilt", translate(rot_about(Tg_l, R, b_l), d), translate(rot_about(Ts_l, R, b_l), d), "tilt"))
        Tg1, Ts1 = out[-1][1], out[-1][2]
        # align: silver relative to gold back to the nominal (authored) relative configuration
        r_m = Rotation.from_matrix(Tg1[:3, :3].T @ Ts1[:3, :3])
        c_m = Tg1[:3, :3].T @ ((Ts1[:3, :3] @ rt.bar_point(self.rec["scale"]) + Ts1[:3, 3]) - Tg1[:3, 3])
        sl = Slerp([0, 1], Rotation.from_quat([r_m.as_quat(), self.r0.as_quat()]))
        for u in np.linspace(0, 1, 21)[1:]:
            out.append(("align", Tg1, self.silver_from_rel(Tg1, sl(u), c_m + u * (self.c0 - c_m)), "align"))
        # key turn: the relative rotation follows the route (two slerp stages), split between both pieces
        path = rt.route(self.rec, self.tier, +1, n_turn=30)
        turn = [(r, c) for r, c, s in path if s.startswith("turn")]
        Rg1 = Tg1[:3, :3]
        for r, c in turn[1:]:
            ang = (r * self.r0.inv()).magnitude()       # relative turn angle so far (rad), 0..pi/2
            yaw = np.radians(self.gamma_deg) * ang / (np.pi / 2)
            Rz = Rotation.from_euler("z", yaw).as_matrix()
            Tg = rot_about(Tg1, Rz, bw)
            Ts = self.silver_from_rel(Tg, r, c)
            out.append(("turn", Tg, Ts, "turn"))
        Tg2 = out[-1][1]
        r_fin = turn[-1][0]
        # channel: relative bar point along the guides; gold moves -split, silver +(1-split) of the world displacement
        chan = [(r, c) for r, c, s in path if s.startswith("channel")]
        extra = self.guides[-1] + np.array([0, -0.03, 0])        # 30 mm past the route end
        n_extra = 30
        chan += [(r_fin, self.guides[-1] + (extra - self.guides[-1]) * u) for u in np.linspace(0, 1, n_extra + 1)[1:]]
        for k, (r, c) in enumerate(chan[::3] + [chan[-1]]):
            dw = Tg2[:3, :3] @ (c - self.c0)                     # bar displacement relative to gold, world
            Tg = translate(Tg2, -self.split * dw)
            Ts = self.silver_from_rel(Tg, r, c)
            out.append(("channel", Tg, Ts, "channel"))
        return out

    def tcp_targets(self, frames, Tgg=None, Tsg=None):
        Tgg = self.grasps.T_gold() if Tgg is None else Tgg
        Tsg = self.grasps.T_silver() if Tsg is None else Tsg
        return [(n, Tg @ Tgg, Ts @ Tsg, ph) for n, Tg, Ts, ph in frames]


def seed_ik(Tw, side, tries=200, rng=None):
    """Multi-start IK for a world TCP pose; returns the solution with the best joint margin."""
    rng = np.random.default_rng(0) if rng is None else rng
    Tb = yk.world_to_base(Tw, side)
    best = None
    for _ in range(tries):
        q0 = yk.LOWER + rng.random(6) * (yk.UPPER - yk.LOWER)
        q, ok, ep, er = yk.ik(Tb, q0, iters=150)
        if ok:
            m = float(np.min(np.minimum(q - yk.LOWER, yk.UPPER - q)))
            if best is None or m > best[1]:
                best = (q, m)
    return best


def track(targets, side, q_seed):
    """Sequential IK along a list of world TCP poses; returns joint path and stats."""
    q = np.array(q_seed, float)
    qs, worst_margin, worst_jump, fails, oks = [], np.inf, 0.0, 0, []
    for Tw in targets:
        qn, ok, ep, er = yk.ik(yk.world_to_base(Tw, side), q, iters=100, margin=0.0)
        oks.append(ok)
        if not ok:
            fails += 1
        worst_jump = max(worst_jump, float(np.max(np.abs(qn - q))))
        worst_margin = min(worst_margin, float(np.min(np.minimum(qn - yk.LOWER, yk.UPPER - qn))))
        q = qn
        qs.append(qn)
    return np.array(qs), dict(fails=fails, min_margin_rad=worst_margin, max_jump_rad=worst_jump, oks=oks)


def check(plan, verbose=True):
    frames = plan.keyframes()
    tcps = plan.tcp_targets(frames)
    res = {}
    for side, idx in (("left", 1), ("right", 2)):
        T0 = tcps[0][idx]
        # pregrasp: 6 cm back along the approach
        pre = T0.copy(); pre[:3, 3] -= 0.06 * T0[:3, 0]
        s = seed_ik(pre, side)
        if s is None:
            res[side] = "no IK at pregrasp"; continue
        appr = [pre.copy() for _ in range(1)]
        for u in np.linspace(0, 1, 13)[1:]:
            T = T0.copy(); T[:3, 3] = pre[:3, 3] + u * (T0[:3, 3] - pre[:3, 3]); appr.append(T)
        qs, st = track(appr + [t[idx] for t in tcps], side, s[0])
        phases = ["approach"] * len(appr) + [t[3] for t in tcps]
        per = {}
        for ph in dict.fromkeys(phases):
            m = np.array([p == ph for p in phases])
            q = qs[m]
            per[ph] = dict(q_first=q[0].round(3).tolist(), q_last=q[-1].round(3).tolist(),
                           fails=int(sum(1 for o, pp in zip(st["oks"], phases) if pp == ph and not o)),
                           margin=float(np.min(np.minimum(q - yk.LOWER, yk.UPPER - q))))
        st.pop("oks")
        res[side] = dict(stats=st, seed_margin=s[1], phases=per)
        res[side + "_path"] = qs
    if verbose:
        for side in ("left", "right"):
            print(side, json.dumps(res[side] if isinstance(res[side], str) else
                                   {"stats": res[side]["stats"], "seed_margin": round(res[side]["seed_margin"], 3)}))
            if not isinstance(res[side], str):
                for ph, v in res[side]["phases"].items():
                    print("   ", ph, v)
    return res, frames, tcps


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tier")
    ap.add_argument("--gamma", type=float, default=0.0)
    ap.add_argument("--split", type=float, default=0.5)
    ap.add_argument("--work", type=float, nargs=3, default=(0.0, 0.0, 0.10))
    a = ap.parse_args()
    p = Plan(a.tier, gamma_deg=a.gamma, split=a.split, work=tuple(a.work))
    fr = p.keyframes()
    print("bar start", p.bar_world(fr[0][1]).round(4), "bar work", p.bar_world(fr[56][1]).round(4))
    T = p.tcp_targets(fr)
    for i in (0, 15, 55, len(fr) - 1):
        print(fr[i][0], "left tcp", T[i][1][:3, 3].round(3), "appr", T[i][1][:3, 0].round(2),
              "| right tcp", T[i][2][:3, 3].round(3), "appr", T[i][2][:3, 0].round(2))
    check(p)
