"""The full-state reference program of the privileged soccer twin (the task's solution/program.py).

It plays the screening's truth reference (sports/soccer/reference_check.py, perception "truth"): the frozen scripted
coach at the "reference" level, soccer.Coach("A", "reference"): both robots go for the ball at the reference's speed
and precision and kick with the in-walk kick, the strongest play the screening found. Here it is an ordinary program:
it sees only the formal view (the declared truth and the seat's observation), never the world, and its commands go
through the original action layer (one per robot, taking effect at the next control step after they arrive). The
coach's code is imported from the public simulator copy (/opt/fullsim in development, /opt/dev in the verifier).
"""
from __future__ import annotations

import sys
from pathlib import Path


def _import_soccer():
    try:
        import soccer  # noqa: F401
    except ImportError:
        for p in [*sys.path, "/opt/dev", "/opt/fullsim", str(Path(__file__).resolve().parents[3])]:
            d = Path(p or ".") / "sports/soccer"
            if (d / "soccer.py").is_file():
                sys.path.insert(0, str(d))
                break
    import soccer
    # the reference level is the solution's own (the agent's copy leaves it, level 3 and their parameter set "ref" out,
    # H.2, #282 review): the frozen sport's "ref" parameters (sports/soccer/soccer.py COACH_LEVELS["ref"], soccer-2v2-10)
    # with the chase plan and the in-walk kick
    ref = dict(delay_s=0.0, vmax=0.8, vlat=0.4, wmax=1.0, pos_tol=0.05, yaw_tol=0.08, every=1, shoot_m=7.5, feet="both")
    assert soccer.COACH_LEVELS.get("ref", ref) == ref, "the frozen sport's reference parameters changed"
    soccer.COACH_LEVELS.setdefault("reference", dict(ref, style="chase", step=True))
    return soccer


class _World:
    """The attributes of soccer.World that Coach.decide reads, rebuilt from one formal view."""

    def __init__(self, S, view, prog, seed):
        tr = view["truth"]
        np = S.np
        self.k = int(tr["k"])
        self.seed = seed
        ref = tr["referee"]
        self.state = ref["state"]
        ko, fk, cur = ref["kickoff"], ref["free_kick"], ref["shootout"]
        self.ko = None if ko is None else dict(ko)
        self.fk = None if fk is None else dict(fk, spot=np.asarray(fk["spot"], float))
        self.pso = None if cur is None else {"cur": dict(cur)}
        self.prog = prog
        robots = {r: dict(xy=np.asarray(v["xy"], float), yaw=float(v["yaw"]), fallen=bool(v["fallen"]),
                          bench=bool(v["bench"]), kicking=bool(v["kicking"])) for r, v in tr["robots"].items()}
        self._tr = dict(ball=np.asarray(tr["ball"]["pos"][:2], float), ball_v=np.asarray(tr["ball"]["vel"][:2], float),
                        k=self.k, robots=robots)

    def truth(self, team):
        if team != "A":
            raise ValueError("seat A only")
        return self._tr

    def kicking(self, r):
        return self._tr["robots"][r]["kicking"]


class Reference:
    def __init__(self, config):
        self.S = _import_soccer()
        cfg = config["spec"].get("cfg") or {}
        self.seed = int(cfg.get("seed", 0))
        self.coach = self.S.Coach("A", "reference")
        self.stoppages = None

    def act(self, view):
        st = view["state"]
        if st.get("phase") == "unit_over":
            return {"type": "ready"}
        if st.get("phase") != "playing" or not view.get("truth"):
            return None
        n = st.get("stoppages")
        if n != self.stoppages:                     # a restart: the coach starts afresh, as the world's own coaches
            self.stoppages = n
            self.coach.reset()
        prog = {}                                   # each robot's command under way, as the world holds it
        for num, rs in (st.get("robots") or {}).items():
            c = rs.get("command") or {}
            prog["A" + str(num)] = ({"type": "walk", "v": [float(x) for x in c["v"]]} if c.get("type") == "walk" else
                                    {"type": "stand"} if c.get("type") == "stand" else {"type": "kick"})
        w = _World(self.S, view, prog, self.seed)
        out = []
        for r, cmd in sorted(self.coach.decide(w).items()):
            if cmd is None:
                continue
            out.append({**cmd, "entity": r[1]})
        return out or None


def make_policy(config):
    return Reference(config)
