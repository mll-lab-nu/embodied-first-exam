"""The full-state reference program for the joint-level soccer twins (their oracle): the twin's joint-level reference
team (solution/joint_oracle.py: Ctl, the DCM walker and the team strategy of team.py) on the formal match's views
instead of the HTTP service; the same observation fields (the twin's observation holds the same truth)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for root in ("/opt/dev", "/opt/fullsim"):       # soccer_scene (the T1 model the walker builds on): the public copy
    p = os.path.join(root, "sports", "soccer")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)

from joint_oracle import Ctl  # noqa: E402


def make_policy(config):
    return Policy()


class Policy:
    def __init__(self):
        self.ctl = Ctl()

    def act(self, view):
        st = view.get("state") or {}
        if st.get("phase") == "unit_over":
            return {"type": "ready"}
        if st.get("world") != "running" or "robots" not in st:
            return None
        rows = self.ctl.rows({**st, "truth": view.get("truth") or {}})
        return [{"type": "joints", "q": q, "entity": n} for n, q in rows.items()] or None
