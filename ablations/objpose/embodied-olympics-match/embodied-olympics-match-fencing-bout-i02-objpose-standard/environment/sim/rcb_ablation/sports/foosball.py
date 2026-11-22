"""Foosball (format match against the scripted opponent): the state table.

Your local frame (spec geometry frame: u towards the opponent goal, v to your left, z up; playfield z = 0, centre
(0, 0)). The ball, your four rods and the opponent's four rods: each rod's body (its figures' bar) and its two joints
(slide along the bar, spin about it) straight from the simulator."""
from __future__ import annotations

from . import _mj

BALL = {"pos": "m", "quat": "wxyz", "lin_vel": "m/s", "ang_vel": "rad/s", **_mj.BOX}
ROD = {**_mj.POSE, **_mj.JOINTS, **_mj.BOX}           # joints: slide (along the bar, m), spin (about it, rad)


def _foos():
    import foos                                         # sport/foos.py
    return foos


def _sides(seat):
    return seat[0], ("B" if seat[0] == "A" else "A")


def entities(m, seat):
    F = _foos()
    ents = {"ball": {"kind": "object", "fields": dict(BALL)}}
    for r in F.RODS:
        ents[f"rod_{r}"] = {"kind": "robot_link", "fields": dict(ROD),
                            "note": f"your {r} rod: its bar body, joints slide and spin"}
    for r in F.RODS:
        ents[f"opponent_rod_{r}"] = {"kind": "articulation", "fields": dict(ROD),
                                     "note": f"the opponent's {r} rod: its bar body, joints slide and spin"}
    ents["own_goal"] = {"kind": "scene_feature", "fields": dict(_mj.GOAL)}
    ents["opponent_goal"] = {"kind": "scene_feature", "fields": dict(_mj.GOAL)}
    ents["playfield"] = {"kind": "scene_feature", "fields": {"pos": "m", **_mj.BOX}}
    return {"frame": "your local frame (u towards the opponent goal, v to your left, z up; playfield z = 0, centre "
                     "(0, 0)); fields pos / lin_vel / ang_vel are (u, v, z)",
            "quaternion_order": "wxyz", "entities": ents}


def _rod(model, data, side, rod, turned):
    b = _mj.body_id(model, f"{side}_{rod}")
    js = _mj.strip(_mj.joints(model, data, [f"{side}_{rod}_slide", f"{side}_{rod}_spin"]),
                   prefix_len=len(f"{side}_{rod}_"))
    out = {**_mj.body(model, data, b), **js, **_mj.body_box(model, data, b, subtree=True)}
    return _mj.turn(out) if turned else out


def read(m, seat, names):
    F = _foos()
    data = m.r.data
    model = data.model
    me, them = _sides(seat)
    turned = F.OWN[me] < 0                              # world (u, v) = OWN * local (u, v)
    out = {}
    for n in names:
        if n == "ball":
            b = {**_mj.free_joint(model, data, "ball"), **_mj.free_box(model, data, "ball")}
            out[n] = _mj.turn(b) if turned else b
        elif n in ("own_goal", "opponent_goal"):
            out[n] = _mj.goals(model, data, lambda g: g.startswith("goal_"), turned)[n]
        elif n == "playfield":
            v = _mj.geom_box(model, data, "playfield")
            out[n] = _mj.turn(v) if turned else v
        elif n.startswith("opponent_rod_"):
            out[n] = _rod(model, data, them, n[len("opponent_rod_"):], turned)
        elif n.startswith("rod_"):
            out[n] = _rod(model, data, me, n[len("rod_"):], turned)
    return out
