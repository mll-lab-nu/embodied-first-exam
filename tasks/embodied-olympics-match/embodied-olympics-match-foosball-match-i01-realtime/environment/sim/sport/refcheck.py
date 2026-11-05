"""tools/check stage 5 (sport.toml [reference] match = "refcheck:reference_match", docs/screening/README.md "Reference
check"): one match of foosball's reference against the scripted team, with truth or camera perception. Also the
true-ball program the screening hooks use (sports/foosball/screen/hooks.py). A module of its own because the reference
player (builtin_players) imports no framework.

  truth   the shared player policy (foos_policy.Policy, style team, as the camera reference plays it) on the TRUE
          ball 30 ms ago, extrapolated by its velocity then (as the scripted team reads it), every 5 control steps
          (the camera reference's 50 ms observation period); it sees the opposing figures' true places
  camera  the [players] reference unchanged (builtin_players.Reference: the overhead image only), through core.local
"""
from __future__ import annotations

import os

import numpy as np


class TrueBall:
    """The shared policy (style team) on the true ball `delay` control steps ago, extrapolated by its velocity then,
    as the scripted team reads it (research gradient.py TrueBall). mode "slide_only" holds every rod's angle at 0,
    "spin_only" every rod's slide at 0, None changes nothing. observe(r) records the ball once per control step,
    before it; act() needs self.world (the foos.Foosball) and decides every 5 control steps."""

    def __init__(self, mode=None, delay=3):
        self.mode, self.delay, self.hist, self.pol, self.rally, self.k, self.world = mode, delay, [], None, None, -1, None

    def observe(self, r):
        if r.k == self.k:
            return
        self.k = r.k
        import foos_policy
        if self.rally != len(r.results):
            self.rally = len(r.results)
            self.hist = []
            self.pol = foos_policy.Policy(style="team")
            mine = r.restart_where[1] == "A"
            self.pol.reset(("goalie" if r.restart_where[0] == "goalie" else "midfield") if mine else None)
        self.hist.append(r.ball()[:2].copy())
        self.hist = self.hist[-(self.delay + 3):]

    def act(self, view=None):
        import foos as F
        r = self.world
        if r is None or r.done or r.awaiting_review:
            return None
        self.observe(r)
        if r.k % 5:
            return None
        P = self.hist[0]
        W = (self.hist[2] - self.hist[0]) / (2 * F.DT) if len(self.hist) > 2 else np.zeros(2)
        P = P + W * self.delay * F.DT
        rods = {x: dict(slide=float(r.data.qpos[r.sq[r.rod_index("A", x)]]),
                        angle=float(r.data.qpos[r.aq[r.rod_index("A", x)]])) for x in F.RODS}
        opp = {x: list(r.figure_y("B", x)) for x in F.RODS}
        c = self.pol.update(r.point_k * F.DT, (float(P[0]), float(P[1])), (float(W[0]), float(W[1])), rods, opp,
                            opening_done=r.opening["done"] or r.opening["team"] != "A")
        out = {}
        for x, d in c.items():
            d = dict(slide=float(np.clip(d["slide"], -F.TRAVEL[x], F.TRAVEL[x])),
                     angle=float(np.clip(d["angle"], -F.ANGLE_MAX, F.ANGLE_MAX)),
                     omega=float(min(d["omega"], F.SPIN_W)), speed=float(min(d["speed"], F.SLIDE_V)))
            if self.mode == "slide_only":
                d["angle"] = 0.0
            if self.mode == "spin_only":
                d["slide"] = 0.0
            out[x] = d
        return {"type": "rods", "rods": out}


def reference_match(format="match", level=None, seed=1, perception="truth") -> dict:
    """One match of the reference against the scripted team of `level` (seed `seed`; the first kick-off alternates
    with the seed: odd A, even B). Returns {"won", "scores": [ours, theirs], "report"}; report: the scripted team's own
    goals among ours (the last touch was its own; a known weakness of foos_policy) and the safety net's rod-steps."""
    from core import local
    from core.episode import load_plugin
    from core.sport import FINISHED, UNIT_OVER, MatchConfig, parse_action
    plugin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin.py")
    sport = load_plugin(plugin)
    cfg = MatchConfig(sport="foosball", format=format, seats=("A",), seed=int(seed), first="A" if int(seed) % 2 else "B",
                      action_level="low", level=None if level is None else int(level))
    if perception == "camera":
        res = local.play(sport, cfg, local.make_players(sport, cfg, {"A": "reference"}, plugin=plugin), render=True,
                         plugin=plugin)
        f, won = res["final_fields"], res["winner"] == "A"
    elif perception == "truth":
        m = sport.build(cfg)
        layer = sport.action_layer("low")
        p = TrueBall()
        p.world = m.r
        while m.phase().state != FINISHED:
            if m.phase().state == UNIT_OVER:
                m.resume()
                continue
            body = p.act() if m.k % 5 == 0 else None
            p.observe(m.r)
            if body is not None:
                cmd = parse_action(layer, "A", body, m, {})
                m.apply("A", layer.lower("A", cmd, None, m)[0])
            m.step()
        f = m.final_fields()
        won = f["legacy_winner"] == "A"
    else:
        raise ValueError(f"perception must be truth or camera, not {perception!r}")
    sc = f["legacy_scores"]
    ours, theirs = int(sc["A"]["points"]), int(sc["B"]["points"])
    own = sum(1 for x in f["results"] if x.get("how") == "goal" and x.get("winner") == "A" and x.get("own_goal"))
    return {"won": bool(won), "scores": [ours, theirs],
            "report": {"our goals that were the scripted team's own goals": [own, ours],
                       "matches with a safety-net rod-step (D11)": [int(f.get("rod_speed_governed_steps", 0) > 0), 1]}}
