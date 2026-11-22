"""Table tennis (format match, its low level, and the duel against the built-in learned seat): the state table.

The world frame of the match is your frame (spec world: x to your right, y towards the opponent, z up, table top
z = 0). Format match: the scripted opponent is a paddle on the far end line, moved along x within the rail's limits
(sim/match.py `_opp_jl`; it is drawn, it has no arm): its paddle's centre and velocity. Duel: the other robot of the
duel world (bodies and joints *_b) and its paddle."""
from __future__ import annotations

from . import _mj

ARM = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
BALL = {"pos": "m", "quat": "wxyz", "lin_vel": "m/s", "ang_vel": "rad/s (the ball's spin)", **_mj.BOX}
ROBOT = {**_mj.POSE, **_mj.JOINTS, **_mj.BOX}
LINK = {**_mj.POSE, **_mj.BOX}
FEATURE = {"pos": "m", **_mj.BOX}
OPP_PADDLE = (0.15, 0.016, 0.15)          # sport/sim/match.py: the drawn paddle's box (full extents)


def _world(m):
    if hasattr(m, "R"):                                   # format match (TTMatch): the match's session
        return m.R.s.m, m.R.s.d, False
    return m.g.m, m.g.d, True                             # duel (TTDuel): the duel world


def entities(m, seat):
    _model, _data, duel = _world(m)
    ents = {"robot": {"kind": "robot", "fields": dict(ROBOT), "note": "your robot: the rail base (body base) and its "
                      "9 joints (base_x, base_y, joint1-7); size / bbox: the whole robot"},
            "paddle": {"kind": "robot_link", "fields": dict(LINK), "note": "your paddle's blade centre"},
            "ball": {"kind": "object", "fields": dict(BALL)},
            "table": {"kind": "scene_feature", "fields": dict(FEATURE)},
            "net": {"kind": "scene_feature", "fields": dict(FEATURE)}}
    if duel:
        ents["opponent"] = {"kind": "robot", "fields": dict(ROBOT),
                            "note": "the other robot: its rail base and joints (base_x_b, base_y_b, joint1_b-7_b)"}
        ents["opponent_paddle"] = {"kind": "object", "fields": dict(LINK), "note": "the other robot's paddle"}
    else:
        ents["opponent_paddle"] = {"kind": "object", "fields": {"pos": "m", "lin_vel": "m/s", **_mj.BOX},
                                   "note": "the scripted opponent's paddle (it moves along its end line)"}
    return {"frame": "the match world = your frame (x to your right, y towards the opponent, z up; table top z = 0)",
            "quaternion_order": "wxyz", "entities": ents}


def read(m, seat, names):
    model, data, duel = _world(m)
    out = {}
    for n in names:
        if n == "robot":
            out[n] = {**_mj.body(model, data, "base"), **_mj.joints(model, data, ARM),
                      **_mj.body_box(model, data, "base", subtree=True)}
        elif n == "paddle":
            out[n] = {**_mj.site(model, data, "paddle_center"), **_mj.site_box(model, data, "paddle_center")}
        elif n == "ball":
            out[n] = {**_mj.free_joint(model, data, "ball"), **_mj.free_box(model, data, "ball")}
        elif n == "table":
            out[n] = _mj.geom_box(model, data, "geom_table")
        elif n == "net":
            out[n] = _mj.geom_box(model, data, "geom_net")
        elif n == "opponent" and duel:
            out[n] = {**_mj.body(model, data, "base_b"), **_mj.joints(model, data, [a + "_b" for a in ARM]),
                      **_mj.body_box(model, data, "base_b", subtree=True)}
        elif n == "opponent_paddle":
            if duel:
                out[n] = {**_mj.site(model, data, "paddle_center_b"), **_mj.site_box(model, data, "paddle_center_b")}
            else:
                import match as M                         # sport/sim/match.py: where the paddle is drawn
                jl = m.R._opp_jl
                pos = [float(jl.q[0]), M.OPP_Y, M.OPP_Z]
                out[n] = {"pos": _mj.r(pos), "lin_vel": _mj.r([float(jl.qd[0]), 0.0, 0.0]),
                          **_mj.point_box(pos, OPP_PADDLE)}
    return out
