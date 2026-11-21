"""Soccer (T1 humanoids 2 v 2, format match against the scripted team; the high level and the joint level): the
state table, and the no-success-signal edits.

Your team's frame (spec frame: you attack the goal at x = +5, defend x = -5, y to the left facing +x, z up). Every
robot: its trunk's pose and velocity, its leg joints and its whole body's extents and box; the ball (a free body)
with its box; both goals (posts, bar, net) as boxes. Straight from the simulator's MuJoCo
data, turned from the world into your team's frame (sport soccer.py to_team: a 180 degree turn for team B)."""
from __future__ import annotations

from . import _mj

HIDE_KEYS = ("shootout",)
ROBOT = {**_mj.POSE, **_mj.JOINTS, **_mj.BOX}
BALL = {"pos": "m", "quat": "wxyz", "lin_vel": "m/s", "ang_vel": "rad/s", **_mj.BOX}
GOAL_PARTS = ("post_", "bar_", "net_", "goal_")          # the venue's goal geoms (posts, bar, net, floor)


def hide(obj):
    """A stoppage for a goal keeps its kind (the restart follows from it) but not which team scored."""
    def walk(x):
        if isinstance(x, dict):
            st = x.get("stoppage")
            if isinstance(st, dict) and "goal" in str(st.get("kind", "")).lower():
                x = {**x, "stoppage": {k: v for k, v in st.items() if k != "team"}}
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(obj)


def _robots(seat):
    import soccer as S                                  # sport/soccer.py
    team = seat[0]
    return team, S.TEAM_ROBOTS[team], S.TEAM_ROBOTS[S.OTHER[team]]


def entities(m, seat):
    team, mine, theirs = _robots(seat)
    ents = {"ball": {"kind": "object", "fields": dict(BALL)}}
    for r in mine:
        ents[f"robot_{r[1:]}"] = {"kind": "robot", "fields": dict(ROBOT),
                                  "note": f"your robot {r[1:]}: its trunk and its leg joints"}
    for r in theirs:
        ents[f"opponent_{r[1:]}"] = {"kind": "robot", "fields": dict(ROBOT),
                                     "note": f"the opponent's robot {r[1:]}: its trunk and its leg joints"}
    ents["own_goal"] = {"kind": "scene_feature", "fields": dict(_mj.GOAL), "note": "posts, bar and net"}
    ents["opponent_goal"] = {"kind": "scene_feature", "fields": dict(_mj.GOAL), "note": "posts, bar and net"}
    return {"frame": "your team's frame (you attack the goal at x = +5 and defend x = -5; y to the left facing +x; z "
                     "up)", "quaternion_order": "wxyz", "entities": ents}


def _robot(model, data, r, turned):
    js = [n for n in _mj.joint_names(model, rf"^{r}:")]
    out = {**_mj.body(model, data, f"{r}:Trunk"), **_mj.joints(model, data, js),
           **_mj.body_box(model, data, f"{r}:Trunk", subtree=True)}
    _mj.strip(out, sep=":")
    return _mj.turn(out) if turned else out


def read(m, seat, names):
    data = m.w.d
    model = data.model
    team, mine, theirs = _robots(seat)
    turned = team != "A"
    by = {f"robot_{r[1:]}": r for r in mine} | {f"opponent_{r[1:]}": r for r in theirs}
    out = {}
    for n in names:
        if n == "ball":
            b = {**_mj.free_joint(model, data, "ball"), **_mj.free_box(model, data, "ball")}
            out[n] = _mj.turn(b) if turned else b
        elif n in ("own_goal", "opponent_goal"):
            out[n] = _mj.goals(model, data, lambda g: g.startswith(GOAL_PARTS), turned)[n]
        elif n in by:
            out[n] = _robot(model, data, by[n], turned)
    return out
