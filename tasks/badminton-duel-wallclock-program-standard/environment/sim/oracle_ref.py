"""Privileged reference decision for the badminton match (RCB_PLAYER_MODE=oracle only; runs in the advisor process
on an exact copy of the live match, never on the live match).

The same reference as the lock-step tasks' oracle (`solution/oracle_calls.json` there was generated with it):
  * contact: the first point of the TRUE predicted flight (bm.predict from the true shuttle state) at least 0.28 s
    ahead, 0.45-2.45 m high, on our half, whose forehand stance the base can reach in time (0.12 s spare), preferring
    1.7-2.45 m (overhead);
  * aim: a corner away from the opponent ("place": deep if it stands forward, short if it stands back);
  * racket state: scheme A's stroke planner (`Match.plan_stroke`, which aims with the true incoming shuttle velocity
    and rehearses the shot on a twin) run on the copy; the face normal is the launch direction it chose and the head
    velocity the planned one (divided by its joint-speed scale).
The player then sends this racket state through the ordinary `act` call, like a model.
"""
from __future__ import annotations

import numpy as np

import bm


def choose_contact(m, z_pref=(1.7, 2.45), margin=0.12):
    P, V = bm.predict(m.s.sh_p, m.s.sh_v)
    k0, launch = m.k, m.leg["launch"]
    base = m.s.d.qpos[m.s.qa[:2]].copy()
    cands = []
    for j in range(28, len(P) // 10):
        p = P[10 * j - 1]
        if not (0.45 <= p[2] <= 2.45 and p[1] < -0.4):
            continue
        st = bm.stance(p)
        if bm.base_time(float(np.hypot(*(st - base)))) <= j * 0.01 - margin:
            cands.append((j, p))
    if not cands:
        js = [j for j in range(10, len(P) // 10) if P[10 * j - 1][2] >= 0.45]
        if not js:                              # the shuttle comes down (or into the net) within 0.1 s: no contact
            return None, None
        j = js[-1]
        cands = [(j, P[10 * j - 1])]
    hi = [c for c in cands if z_pref[0] <= c[1][2] <= z_pref[1]]
    j, p = hi[0] if hi else max(cands, key=lambda c: c[1][2])
    return round((k0 + j - launch) * 0.01, 3), [round(float(x), 4) for x in p]


def aim_place(m):
    ox, oy = m.opp_xy()
    away = -1.0 if ox > 0 else 1.0
    ty = 5.9 if oy < 3.6 else 1.6
    return (away * 1.9, ty), "normal"


def to_racket(m, T, p, aim, power):
    """Scheme A's planner on the copy; the stroke it chose -> (face normal, head velocity)."""
    caught = []
    orig = m._swing

    def spy(c, goal, base_tg, n_avail):
        caught.append(c)
        return orig(c, goal, base_tg, n_avail)
    m._swing = spy
    m._ik_seed = None
    tg, info = m.plan_stroke(T, np.asarray(p, float), np.asarray(aim, float), power)
    m._swing = orig
    if not tg:
        return None
    qh = info["_q_hit"]
    c = next(c for c in caught if c["q_h"] is qh)
    scale = max(1.0, c["ratio"] / 0.9)
    return c["nrm"], c["v_p"] / scale


def advise(m) -> dict:
    leg = m.leg
    out = {"k_snap": int(m.k), "leg_id": len(m.legs) - 1, "launch": int(leg["launch"]), "leg_state": leg["state"]}
    if leg["state"] != "incoming" or not m.in_play() or m.done:
        out["none"] = "no shuttle coming to you"
        return out
    T, p = choose_contact(m)
    if T is None:
        out["none"] = "no contact point left"
        return out
    aim, power = aim_place(m)
    rs = to_racket(m, T, p, aim, power)
    if rs is None:
        out["none"] = "no stroke found"
        return out
    nrm, vp = rs
    out.update(t_hit=float(T), pos=[float(x) for x in p], normal=[round(float(x), 4) for x in nrm],
               vel=[round(float(x), 3) for x in vp], aim=[float(a) for a in aim])
    return out
