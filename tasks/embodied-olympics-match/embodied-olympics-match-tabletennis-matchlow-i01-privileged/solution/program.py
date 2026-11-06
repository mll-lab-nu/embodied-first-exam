"""The full-state reference program for table tennis at the LOW level (this privileged twin's oracle): the twin's
in-loop oracle (builtin_players.SkillReference: the reference strategy's decisions, its serve stance as a held traj)
with the ball's true state for the returns (as the match twins' full-state program), each stroke lowered to joint rows
in process by the twin's toolkit-only reference skill (hit.py: hit() for a stroke, step() back to the ready pose),
which the twin's simulator would call over its skill server. The program returns only low-level commands (traj /
slew / hold) and toss."""

import sys
from pathlib import Path

import builtin_players as bp
import hit as skill
import numpy as np

SPORT = "tabletennis"


def _seat_dir():
    """The twin's toolkit (its /opt/robot) inside the full simulator: sports/tabletennis/seat/ of the tree on sys.path
    (/opt/dev in the formal match, /opt/fullsim in development)."""
    for p in sys.path:
        d = Path(p) / "sports" / SPORT / "seat"
        if (d / "robot_only.xml").is_file():
            return d
    raise FileNotFoundError("sports/tabletennis/seat not found on sys.path")


def skill_spec(spec, scratch):
    """The `spec` the twin's skill gets (kinematics, limits, toolkit, skill_contract, timing), with the toolkit's files
    at their places in this tree: the robot's own model with its meshes (sim/scene/assets, the toolkit's source)."""
    seat = _seat_dir()
    xml = (seat / "robot_only.xml").read_text().replace('meshdir="assets"',
                                                          f'meshdir="{(seat.parent / "sim/scene/assets").resolve()}"')
    model = Path(scratch) / "robot_only.xml"
    model.write_text(xml)
    tk = dict(spec.get("toolkit") or {})
    tk["robot_model"] = str(model)
    for name in ("ik_library", "servo_model"):
        if isinstance(tk.get(name), dict):
            tk[name] = dict(tk[name], file=str(seat / "lib" / Path(tk[name]["file"]).name))
    dt, S = 0.01, float((spec.get("cfg") or {}).get("slowdown") or 10)
    timing = {"control_dt": dt, "slowdown": S, "period_s": round(dt * S, 6), "compute_counts": True, "mode": "sync",
              "step_wait_s": round(dt * S, 6)}
    return {"kinematics": spec["kinematics"], "limits": spec["limits"], "toolkit": tk,
            "skill_contract": spec.get("skill_contract"), "timing": timing}


def make_policy(config):
    return Policy(config["spec"])


class Policy:
    def __init__(self, spec):
        import tempfile
        self.sk_spec = skill_spec(spec, tempfile.mkdtemp(prefix="ttlow-"))
        seed = int((spec.get("cfg") or {}).get("seed", 0))
        self.sref = bp.SkillReference(spec, "A", seed)     # the twin's in-loop oracle: stance and toss as it sends them
        self.ref = self.sref.ref                           # its Reference (high-level decisions)
        self.ref_act = self.ref.act                        # the Reference's own act (serves, everything but returns)
        self.ref.act = self.high                           # SkillReference's loop with the full-state decisions
        self.last = None

    def high(self, view):
        """The match twins' full-state decision: the Reference's serve repertoire, the return predicted from the truth."""
        st = view["state"]
        if st["ball_state"] != "coming to you":
            return self.ref_act(view)
        tr = view["truth"]
        key = (st["point"], tr["leg"].get("launch"))
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

    def act(self, view):
        st = view["state"]
        if st["phase"] == "unit_over":
            self.last = None
            return {"type": "ready"}
        if st.get("phase") != "playing":
            return None
        a = self.sref.act(view)
        state = {k: v for k, v in st.items() if k not in ("service_phase",)}
        if a and a.get("type") == "hit":                   # the stroke: lowered by the skill, as the twin's simulator would
            return skill.hit(a["t"], a["pos"], a["normal"], a["vel"], state=state, spec=self.sk_spec)
        if a:
            return a                                       # toss, or the serve stance (a traj)
        return skill.step(state=state, spec=self.sk_spec)  # the skill's step(): back to the ready pose
