"""The score ladder (analysis only; it never changes who wins): how far the agent got with each ball and in each point.

    touched   the paddle (blade) touched the ball
    active    ... with the blade moving at >= ACTIVE_SPEED at the contact (a swing or a push; a blade held still at the
              ready pose also meets some serves: the nop player "touches" 2-3 balls of 5 at L1)
    over_net  ... and after that touch the ball first came down beyond the net (y > 0: the opponent's half or the floor
              behind it; touching the net on the way is allowed)
    landed_in ... and that first contact was the opponent's half of the table
    returned  ... a good return (also: one own bounce before the hit, one paddle contact, no arm contact with the table)
    won       the point was won; split into `won_expedite` (the agent, as the receiver, made 13 good returns: the
              expedite rule, ITTF 2.15.4) and `won_rally` (every other won point: the opponent missed or hit out, or
              faulted; also the agent's own good services the opponent could not return)

Per point a rung counts if any of the agent's balls in that point reached it ("won" counts the point itself; a point
can be won without a touch, e.g. the opponent's ball passing the agent's half). Lets are not points. Computed from the
match's own per-ball results (`Match.results`) and points (`Match.points`), live and again in the replay.
"""
from __future__ import annotations

RUNGS = ("touched", "active", "over_net", "landed_in", "returned")
EXPEDITE_TAG = "(expedite rule)"   # in a point's `how` when the expedite rule decided it (match.py, duel.py)


def by_expedite(p: dict) -> bool:
    """Whether the expedite rule decided this point (from its `how`; the rules are unchanged, this only reports it)."""
    return EXPEDITE_TAG in str(p.get("how", ""))
ACTIVE_SPEED = 0.2                 # m/s, blade-centre speed at the paddle contact (a held blade: < 0.01 m/s)


def contact_speeds(results: list, contacts: list) -> list:
    """Per result, the largest blade speed of its paddle contacts. contacts: [(control step, blade speed m/s)] in
    order; a result's contacts are those after the previous result's close step up to its own (`step`)."""
    out, prev, i = [], -1, 0
    for r in results:
        v = None
        while i < len(contacts) and contacts[i][0] <= r["step"]:
            if contacts[i][0] > prev:
                v = max(v or 0.0, float(contacts[i][1]))
            i += 1
        out.append(v)
        prev = r["step"]
    return out


def ball_rungs(r: dict, speed: float | None = None) -> dict:
    """The rungs one of the agent's balls (one entry of Match.results) reached; `active` needs the contact speed."""
    kinds = list(r.get("events") or [])
    touched = bool(r.get("hit"))
    post = [k for k in kinds[kinds.index("paddle") + 1:] if k not in ("paddle", "net")] if "paddle" in kinds else []
    over = touched and bool(post) and float(r.get("landing_y", 0.0)) > 0.0
    landed = over and post[0] == "table_opp"
    return {"touched": touched, "active": touched and speed is not None and speed >= ACTIVE_SPEED, "over_net": over,
            "landed_in": landed, "returned": bool(r.get("returned"))}


def ladder(points: list, results: list, me: str = "you", contacts: list | None = None) -> dict:
    """Counts per match: `points_*` (points that reached the rung) and `balls_*` (the agent's balls that did).
    contacts: the paddle contacts with the blade speed (replay.py records them); without them `active` is -1."""
    speeds = contact_speeds(results, contacts) if contacts is not None else [None] * len(results)
    played = [i for i, p in enumerate(points) if p.get("winner") != "let"]
    per_point = {i: dict.fromkeys(RUNGS, False) for i in played}
    balls = dict.fromkeys(RUNGS, 0)
    for r, v in zip(results, speeds):
        rg = ball_rungs(r, v)
        for k in RUNGS:
            balls[k] += int(rg[k])
            if r.get("point") in per_point and rg[k]:
                per_point[r["point"]][k] = True
    out = {"points": len(played), "balls": len(results)}
    for k in RUNGS:
        out["points_" + k] = sum(per_point[i][k] for i in played)
    out["points_won"] = sum(points[i].get("winner") == me for i in played)
    out["points_won_expedite"] = sum(points[i].get("winner") == me and by_expedite(points[i]) for i in played)
    out["points_won_rally"] = out["points_won"] - out["points_won_expedite"]
    for k in RUNGS:
        out["balls_" + k] = balls[k]
    if contacts is None:
        out["points_active"] = out["balls_active"] = -1
    out["per_point"] = [{"point": i, **{k: int(per_point[i][k]) for k in RUNGS},
                         "won": int(points[i].get("winner") == me),
                         "expedite": int(points[i].get("winner") == me and by_expedite(points[i]))} for i in played]
    return out


# The flat reward.json fields (tests/grade.py LADDER_KEYS, prefixed `ladder_`; test_modes.py checks they agree).
REWARD_KEYS = tuple(["points", "balls"] + ["points_" + k for k in RUNGS] + ["points_won", "points_won_expedite", "points_won_rally"] + ["balls_" + k for k in RUNGS])


class PaddleContacts:
    """Records (control step, blade-centre speed) at every new paddle contact of a running match (replay.py calls
    after_step() after every control step). It also looks when the match closes one of the agent's balls (a contact
    and the end of the point can fall into the same control step, after which the step's events are cleared).
    Read-only: it never changes the simulation (the replay's hashes are unchanged)."""

    def __init__(self, match):
        import numpy as np
        self.m, self.s, self.out, self._n, self._first = match, match.s, [], 0, None
        self._v = np.zeros(6)
        close = match._close_our_leg

        def _close_our_leg(*a, **kw):
            self.after_step(match.k)
            return close(*a, **kw)
        match._close_our_leg = _close_our_leg

    def after_step(self, k: int) -> None:
        import mujoco as mj
        import numpy as np
        ev = self.s._events
        first = (ev[0]["t"], ev[0]["kind"]) if ev else None    # (an object id could be reused after the clear)
        if first != self._first:                # the per-leg event list was cleared (a new leg)
            self._first, self._n = first, 0
        n = sum(e["kind"] == "paddle" for e in ev)
        if n > self._n:
            mj.mj_objectVelocity(self.s.m, self.s.d, mj.mjtObj.mjOBJ_SITE, self.s._paddle_site, self._v, 0)
            self.out += [(int(k), round(float(np.linalg.norm(self._v[3:])), 3))] * (n - self._n)
            self._n = n
