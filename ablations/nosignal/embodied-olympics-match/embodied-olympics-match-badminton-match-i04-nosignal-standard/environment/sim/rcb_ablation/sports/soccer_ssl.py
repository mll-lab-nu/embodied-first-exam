"""RoboCup SSL soccer (format match against the scripted team): the state table, and the no-success-signal edits.

Your team's frame (the observation's: you attack +x; team (x, y) = attack_sign * world (x, y), team yaw = world yaw
(+ pi when attack_sign = -1); the ends change at half time, so the frame follows attack_sign now). Every robot: its
position (the MuJoCo body's origin), its heading as a quaternion about z, its velocity and yaw rate, its extents and
box; the ball: position, velocity and box; the two goals: their box. Straight from the simulator (sim/world.py
World.robot_pose, World.ball, the MuJoCo model)."""
from __future__ import annotations

from . import _mj
from .soccer import hide  # noqa: F401  (a goal's stoppage keeps its kind, not the scoring team)

HIDE_KEYS = ("shootout", "winner_team", "end_how")

ROBOT = {"pos": "m (the robot body's origin)", "quat": "wxyz (its heading about z)", "lin_vel": "m/s",
         "ang_vel": "rad/s (its yaw rate about z)", **_mj.BOX}
BALL = {"pos": "m", "lin_vel": "m/s", **_mj.BOX}


def _teams(m, seat):
    from sim.frames import other                        # sport/sim/frames.py
    me = m.team_of_seat(seat)
    return me, other(me)


def entities(m, seat):
    me, them = _teams(m, seat)
    ents = {"ball": {"kind": "object", "fields": dict(BALL)}}
    for rid in m.w.ids:
        if rid[0] == me:
            ents[f"robot_{rid[1]}"] = {"kind": "robot", "fields": dict(ROBOT), "note": f"your robot {rid[1]}"}
    for rid in m.w.ids:
        if rid[0] == them:
            ents[f"opponent_{rid[1]}"] = {"kind": "robot", "fields": dict(ROBOT),
                                          "note": f"the opponent's robot {rid[1]}"}
    ents["own_goal"] = {"kind": "scene_feature", "fields": dict(_mj.GOAL)}
    ents["opponent_goal"] = {"kind": "scene_feature", "fields": dict(_mj.GOAL)}
    return {"frame": "your team's frame now (you attack +x; y to the left facing +x; z up; yaw counter-clockwise "
                     "from +x)", "quaternion_order": "wxyz", "entities": ents}


def _r(x, n=5):
    return [round(float(v), n) for v in x]


def read(m, seat, names):
    from sim.frames import to_team, vec_to_team
    w = m.w
    me, them = _teams(m, seat)
    s = w.sign(me)
    by = {f"robot_{rid[1]}": rid for rid in w.ids if rid[0] == me}
    by |= {f"opponent_{rid[1]}": rid for rid in w.ids if rid[0] == them}
    out = {}
    for n in names:
        if n == "ball":
            p, v = w.ball.pos, w.ball.vel
            x, y = to_team(s, float(p[0]), float(p[1]))
            vx, vy = vec_to_team(s, float(v[0]), float(v[1]))
            bx = _mj.free_box(w.model, w.data, "ball_free")
            out[n] = {"pos": _r([x, y, p[2]]), "lin_vel": _r([vx, vy, v[2]]), **(_mj.turn(bx) if s < 0 else bx)}
        elif n in ("own_goal", "opponent_goal"):
            out[n] = _mj.goals(w.model, w.data, lambda g: g.startswith("goal_"), s < 0)[n]
        elif n in by:
            rid = by[n]
            p, v = w.robot_pose(rid)
            _x, _y, yaw = to_team(s, p[0], p[1], p[2])
            vx, vy = vec_to_team(s, v[0], v[1])
            name = f"{rid[0]}{rid[1]}_robot"
            b = _mj.body_id(w.model, name)
            bb = {"pos": _mj.r(w.data.xpos[b]), **_mj.body_box(w.model, w.data, name, subtree=True)}
            out[n] = {**(_mj.turn(bb) if s < 0 else bb), "quat": _mj.yaw_quat(yaw),
                      "lin_vel": _r([vx, vy, 0.0]), "ang_vel": _r([0.0, 0.0, v[2]])}
    return out
