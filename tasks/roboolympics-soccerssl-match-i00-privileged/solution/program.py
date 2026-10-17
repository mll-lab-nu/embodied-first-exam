"""The full-state reference program of the wheeled soccer privileged twin (solution/): the sport's reference team
(sports/soccer_ssl/builtin_players.py, the camera reference player's decision code) fed the true state of the formal
match instead of its overhead-camera tracker. It is the screening's "truth" variant of the reference player, with the
truth of now (no 40 ms vision delay). A smoke-tested gold standard, not a claim of the strongest possible program.
"""

import sys
from pathlib import Path

here = Path(__file__).resolve().parent
for p in (here, *(q / "sports/soccer_ssl" for q in here.parents)):
    if (p / "builtin_players.py").is_file():  # beside the program (solution/), else the checkout's sport
        sys.path.insert(0, str(p))
        break
import builtin_players as bp  # noqa: E402

TRUTH_KEYS = ("t", "step", "team", "ball", "us", "them", "referee")


def make_policy(config):
    return Policy(config.get("spec") or {})


class Policy:
    def __init__(self, spec):
        self.player = bp.TeamPlayer("reference", spec={**spec, "team_color": "blue"}, seat="A", seed=0,
                                    perception="truth")
        self.reviewed = None

    def act(self, view):
        st = view["state"]
        if st.get("phase") == "unit_over":
            self.player.review(None)  # the reference player's own review: a fresh outbox
            return {"type": "ready"}
        if st.get("phase") != "playing":
            return None
        truth = view["truth"]
        state = dict(st)
        state.setdefault("t_sim", round(int(st["step"]) * 0.01, 6))  # the development Session's state has no t_sim
        state["truth"] = {k: truth[k] for k in TRUTH_KEYS}
        return self.player.act({"state": state, "observation": {}})
