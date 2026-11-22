"""Badminton (format match-wallclock, its low level, and the duel against the built-in learned seat): the state table.

Your frame (spec frame: x to your right, y towards the opponent, z up; your half y < 0). The shuttle is the sport's
point mass with drag (not a MuJoCo body): its position and velocity. Format match: the scripted opponent is a player
standing at a point of its half, moving on the court (sim/bm.py Match.opp_xy; it is drawn, it has no arm): its
position and velocity on the floor. Duel: the other robot runs in its own copy of the model in its own frame (sim/
bduel.py); its base, joints and racket are turned into your frame here."""
from __future__ import annotations

from . import _mj

ARM = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
ROBOT = {**_mj.POSE, **_mj.JOINTS, **_mj.BOX}
LINK = {**_mj.POSE, **_mj.BOX}
SHUTTLE = {"pos": "m (the cork's centre)", "lin_vel": "m/s", **_mj.BOX}
SHUTTLE_LO, SHUTTLE_HI = (-0.07, -0.07, -0.22), (0.07, 0.07, 0.06)   # the scene's shuttle (cork and skirt) around it
OPP_LO, OPP_HI = (-0.16, -0.16, 0.04), (0.16, 0.16, 1.67)            # sport/sim/bm.py: the drawn player (body, head)
FEATURE = {"pos": "m", **_mj.BOX}


def _duel(m):
    return hasattr(m.g, "sides")


def entities(m, seat):
    ents = {"robot": {"kind": "robot", "fields": dict(ROBOT),
                      "note": "your robot: the sliding base (body base) and its 9 joints (base_x, base_y, joint1-7)"},
            "racket": {"kind": "robot_link", "fields": dict(LINK), "note": "your racket head's centre"},
            "shuttle": {"kind": "object", "fields": dict(SHUTTLE)},
            "net": {"kind": "scene_feature", "fields": dict(FEATURE), "note": "the net with its tape and posts"},
            "court": {"kind": "scene_feature", "fields": dict(FEATURE)}}
    if _duel(m):
        ents["opponent"] = {"kind": "robot", "fields": dict(ROBOT),
                            "note": "the other robot (the same robot as yours): its base and its 9 joints"}
        ents["opponent_racket"] = {"kind": "object", "fields": dict(LINK), "note": "the other robot's racket"}
    else:
        ents["opponent"] = {"kind": "object", "fields": {"pos": "m", "lin_vel": "m/s", **_mj.BOX},
                            "note": "the scripted opponent: the point of the floor it stands on (z = 0); size / bbox: "
                                    "the player as drawn"}
    return {"frame": "your frame (x to your right, y towards the opponent, z up; your half y < 0)",
            "quaternion_order": "wxyz", "entities": ents}


def _robot(phys, turned):
    model, data = phys.m, phys.d
    rob = {**_mj.body(model, data, "base"), **_mj.joints(model, data, ARM),
           **_mj.body_box(model, data, "base", subtree=True)}
    rk = {**_mj.site(model, data, "racket_center"), **_mj.site_box(model, data, "racket_center")}
    return (_mj.turn(rob), _mj.turn(rk)) if turned else (rob, rk)


def _aabb(p, lo, hi):
    p = [float(x) for x in p]
    a, b = [p[i] + lo[i] for i in range(3)], [p[i] + hi[i] for i in range(3)]
    return {"size": _mj.r([b[i] - a[i] for i in range(3)]), "bbox": [_mj.r(a), _mj.r(b)]}


def _venue(phys, turned):
    model, data = phys.m, phys.d
    net = _mj.group_box(model, data, _mj.world_geoms(model, lambda n: n in ("net", "net_tape", "post_L", "post_R")))
    court = _mj.geom_box(model, data, "court")
    return (_mj.turn(net), _mj.turn(court)) if turned else (net, court)


def read(m, seat, names):
    g, out = m.g, {}
    duel = _duel(m)
    if duel:
        other = "B" if seat == "A" else "A"
        mine, theirs = g.sides[seat].s, g.sides[other].s
        # each robot's own model is in its own frame; the shuttle is in A's frame (the world)
        rob, rk = _robot(mine, False)
        orob, ork = _robot(theirs, True)
        sp, sv = g.sh_p, g.sh_v
        if seat == "B":
            sp, sv = _mj.turn({"pos": list(sp)})["pos"], _mj.turn({"pos": list(sv)})["pos"]
        net, court = _venue(mine, False)
    else:
        rob, rk = _robot(g.s, False)
        sp, sv = g.s.sh_p, g.s.sh_v
        net, court = _venue(g.s, False)
    for n in names:
        if n == "robot":
            out[n] = rob
        elif n == "racket":
            out[n] = rk
        elif n == "shuttle":
            out[n] = {"pos": _mj.r(sp), "lin_vel": _mj.r(sv), **_aabb(sp, SHUTTLE_LO, SHUTTLE_HI)}
        elif n == "net":
            out[n] = net
        elif n == "court":
            out[n] = court
        elif n == "opponent":
            if duel:
                out[n] = orob
            else:
                from bm import CONTROL_DT                 # sport/sim/bm.py
                p0 = g.opp_xy()                           # now, and a step back: its velocity now
                pm = g.opp_xy(g.k - 1) if g.k > 0 else p0
                out[n] = {"pos": _mj.r([p0[0], p0[1], 0.0]),
                          "lin_vel": _mj.r([(p0[0] - pm[0]) / CONTROL_DT, (p0[1] - pm[1]) / CONTROL_DT, 0.0]),
                          **_aabb([p0[0], p0[1], 0.0], OPP_LO, OPP_HI)}
        elif n == "opponent_racket" and duel:
            out[n] = ork
    return out
