"""Example full-state program: existing serve repertoire + truth-based return prediction.

This is a smoke controller, not a claimed strong/winning baseline. It can create
Session(level=..., seed=...) to experiment in its own local full-simulator copy.
"""

import sys
from pathlib import Path


import builtin_players as bp
import numpy as np


def make_policy(config):
    return Policy(config["spec"])


class Policy:
    def __init__(self, spec):
        self.ref = bp.Reference(spec, "A", 22)
        self.last = None

    def act(self, view):
        st = view["state"]
        if st["phase"] == "unit_over":
            self.last = None
            return {"type": "ready"}
        if st["ball_state"] != "coming to you":
            return self.ref.act(view)
        tr = view["truth"]
        key = (st["point"], view["truth"]["leg"].get("launch"))
        if key == self.last:
            return None
        heard = st.get("heard") or []
        bounced = any(x["event"] == "bounce on your half" for x in heard)
        pr = bp.predict_contact(0, np.asarray(tr["ball_pos"]), np.asarray(tr["ball_vel"]), need_bounce=not bounced)
        if pr is None:
            return None
        t, p, v = pr
        if not 0.08 < t <= 2.5:
            return None
        self.ref.P._new_leg((st["point"], st["ball"], st["step"]), st)
        self.ref.P.opp_x = lambda: tr["opponent_x"]
        pc, normal, vel, _ = self.ref.P.stroke(p, v)
        action = {"type": "act", "t": float(t), "pos": pc.tolist(), "normal": normal.tolist(), "vel": vel.tolist()}
        if not bp._in_range(action):
            return None
        self.last = key
        return action
