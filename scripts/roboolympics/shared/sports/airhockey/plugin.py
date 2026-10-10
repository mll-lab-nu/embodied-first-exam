"""airhockey: robot air hockey after the USAA rules on the v0.2 core (docs/framework_zh.md §4.2). Migrated from the
legacy tree (scripts/olympiad/airhockey, scripts/olympiad/shared/airhockey/sim) in stage 2; the simulator hockey.py
(two physically simulated KUKA iiwa arms with mallets, the Cartesian path, IK and torque controller, the puck, the
referee and the scripted opponent) and its robot files (scene/) are the legacy ones except the goal mouth, 0.35 m
since revision v4 (sport.toml D10; v3: 0.40 m; the legacy recordings of revision v2 no longer replay, golden/ holds
native recordings). The four groups of contract ② (core/sport.py):

  world        hockey.Hockey: one table, both arms in one MuJoCo world (physics 1 kHz); one control step (10 ms) =
               Hockey.step(): both arms' Cartesian paths, IK and joint torques, the scripted opponent (format match,
               seat B inside the world) and the referee after the step
  actions      low only: {"type": "target", x, y} (the mallet's target in the own workspace, hockey.validate_action)
               or {"type": "none"} (hold where the mallet is) -> Hockey.set_command, at the next control step
  referee      a unit = a rally (a goal, a seven-second foul or a dead puck ends it; the world freezes for the reviews);
               first to 7 goals, else the safety cap (120 s of play or 40 rallies) and Hockey.winner()'s chain:
               goals -> the last goal -> territory -> the player who did not have the first possession
  observation  observe = the seat's own arm and mallet and the referee's calls (score, rallies; no puck or opponent
               coordinate); cameras = the seat's fixed camera above and behind its end (the legacy front_<seat>),
               drawn by the task's renderer from scene() (hockey.scene_xml) and render_state() (the qpos)
"""
from __future__ import annotations

import os

import numpy as np

import hockey as H
from core.sport import FINISHED, PLAYING, UNIT_OVER, LowLayer, MatchBase, Phase, Refused, check_command

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "airhockey-program-v4+players-25k+core-0.2" + ("" if H.GOAL == H.GOAL_DEFAULT else f"+goal{H.GOAL:g}m")  # experiment knob
NUM = {"type": "number"}
SCHEMA = {
    "target": {"x": {**NUM, "min": -H.X_FAR, "max": H.X_FAR, "unit": "m",
                     "doc": f"the mallet centre's target x (world frame); own half only: {H.X_NEAR} <= |x| <= {H.X_FAR}"},
               "y": {**NUM, "min": -H.Y_MAX, "max": H.Y_MAX, "unit": "m",
                     "doc": f"target y; |y| <= {H.Y_MAX} and at most {H.REACH} m from your robot's base"}},
    "none": {}}
TIEBREAKS = ("goals", "last_goal", "territory", "first_possession")
LEGACY_DECIDED = {"score": "goals", "cap_points": "goals", "cap_last_goal": "last_goal",
                  "cap_territory": "territory", "cap_first_possession": "first_possession"}
CAM = {"width": H.CAM_W, "height": H.CAM_H, "fovy_deg": 48}


def front_camera(seat: str) -> dict:
    """The legacy fixed camera front_<seat> of hockey.scene_xml (pos, xyaxes) as a camera definition: forward is
    -(x_axis x y_axis), up the y axis."""
    pos, x, y = {"A": ((0, -1.3, 2.2), (1, 0, 0), (0, .861, .509)),
                 "B": ((0, 1.3, 2.2), (-1, 0, 0), (0, -.861, .509))}[seat]
    fwd = -np.cross(x, y)
    return {"name": "front", "pos": list(map(float, pos)), "lookat": (np.add(pos, fwd)).tolist(),
            "up": list(map(float, y)), **CAM}


def is_single(cfg) -> bool:
    return len(cfg.seats) == 1


class AirHockey(MatchBase):
    def __init__(self, cfg):
        self.cfg, self.seats = cfg, tuple(cfg.seats)
        if self.seats not in (("A",), ("A", "B")):
            raise ValueError("airhockey: one seat (A, against the scripted opponent) or two (A, B)")
        self.single = is_single(cfg)
        level = int(cfg.level or 1) if self.single else 1
        if level not in H.LEVELS:
            raise ValueError("level must be 1, 2, 3 or 4")
        first = cfg.first or "A"
        if first not in ("A", "B"):
            raise ValueError("first must be A or B")
        self.h = H.Hockey(seed=int(cfg.seed), level=level, duel=not self.single, first=first)
        self.dt = H.DT
        self.side = {"A": "A", "B": "opponent" if self.single else "B"}    # hockey seat -> side of the match

    @property
    def k(self):
        return self.h.k

    # ------------------------------------------------------------------ world
    def step(self):
        h = self.h
        n = len(h.results)
        contact = h.step()
        events = [{"kind": "contact", "with": sorted(contact)}] if contact else []
        if len(h.results) > n:
            events.append({"kind": "rally", **h.results[-1]})
        return events

    def state_digest(self):
        """hockey.Hockey.digest(): the full MuJoCo integration state, the controllers, the RNG, the scripted opponent
        and the referee."""
        return self.h.digest()

    # ------------------------------------------------------------------ actions
    def schema(self, seat):
        return SCHEMA

    def apply(self, seat, cmd):
        h = self.h
        if h.done or h.awaiting_review:
            return {"rejected": "the world is frozen"}
        h.set_command(seat, None if cmd["type"] == "none" else [cmd["x"], cmd["y"]])
        return {"command": [round(float(v), 5) for v in h.commands[seat]]}

    # ------------------------------------------------------------------ referee
    def phase(self):
        h = self.h
        if h.done:
            return Phase(FINISHED, reason="match_over")
        if h.awaiting_review:
            return Phase(UNIT_OVER, review=self.seats, reason=h.results[-1]["how"])
        return Phase(PLAYING)

    def resume(self):
        self.h.ready()

    def unit(self):
        return len(self.h.results)

    def scores(self):
        sc = self.h.scores()
        return {self.side[s]: sc[s]["points"] for s in ("A", "B")}

    def tiebreaks(self):
        """Hockey.winner() split into its named steps (USAA I.1 first to 7; the safety cap's chain)."""
        def goals(m):
            sc = m.h.scores()
            a, b = sc["A"]["points"], sc["B"]["points"]
            return None if a == b else m.side["A" if a > b else "B"]

        def last_goal(m):
            g = [r for r in m.h.results if r["how"] == "goal"]
            return m.side[g[-1]["winner"]] if g else None

        def territory(m):
            hs = m.h.half_steps
            return None if hs["A"] == hs["B"] else m.side["A" if hs["A"] < hs["B"] else "B"]

        def first_possession(m):
            return m.side[H.OTHER[m.h.first]]
        return list(zip(TIEBREAKS, (goals, last_goal, territory, first_possession)))

    # ------------------------------------------------------------------ observation
    def rally(self, res):
        sc = {s: sum(r["how"] == "goal" and r["winner"] == s for r in self.h.results[:res["rally"]]) for s in "AB"}
        return {"rally": res["rally"], "how": res["how"], "scored": res["winner"], "fouled": res["guilty"],
                "next_puck": res["next"], "score": sc, "t_play": round(res["k"] * H.DT, 2)}

    def observe(self, seat, query=None):
        h = self.h
        frozen = h.awaiting_review or h.done
        return {"rally": len(h.results) + (0 if frozen else 1), "t_play": round(h.k * H.DT, 3),
                "play_time_left_s": round(max(0.0, H.CAP_S - h.k * H.DT), 3), "score": h.scores(),
                "own": {"mallet_xyz": [round(float(x), 5) for x in h.position(seat)],
                        "command": [round(float(x), 5) for x in h.commands[seat]],
                        "joint_position": [round(float(x), 5) for x in h.data.qpos[h.qadr[seat]]],
                        "joint_velocity": [round(float(x), 5) for x in h.data.qvel[h.dadr[seat]]]},
                "rallies": [self.rally(r) for r in h.results],
                "last_rally": self.rally(h.results[-1]) if h.results else None}

    def cameras(self, seat, query=None):
        return [front_camera(seat)]

    def render_state(self):
        return {"qpos": np.asarray(self.h.data.qpos).tolist()}

    def final_fields(self):
        h = self.h
        return {"hockey_revision": H.REVISION, "goal_width_m": H.GOAL, "level": h.level, "first_player": h.first, "duel": h.duel,
                "scores": h.scores(), "results": h.results, "decided_by": h.decided_by,
                "match_limit": bool(h.decided_by and h.decided_by.startswith("cap")), "done": h.done,
                "half_steps": dict(h.half_steps), "rail_contact_steps": h.rail_contact_steps,
                "mallet_contact_steps": h.contact_steps}


class TargetLayer(LowLayer):
    """The only action level: the schema's types and finite numbers (core.sport.check_command), then the legacy
    hockey.validate_action (own half, the workspace box and the reach; 400 otherwise). A body without a type is a
    target, as in the legacy `POST /act {"x": X, "y": Y}`."""

    def __init__(self):
        super().__init__(None)

    def parse(self, seat, body, match, ctx):
        if isinstance(body, dict) and "type" not in body and "x" in body:
            body = {"type": "target", **body}
        cmd = check_command(SCHEMA, body)
        if "entity" in cmd:
            raise Refused("the mallet takes no entity")
        if seat not in match.seats:
            raise Refused("unknown seat")
        if cmd["type"] == "target":
            try:
                H.validate_action({"type": "target", "x": cmd["x"], "y": cmd["y"]}, seat)
            except ValueError as exc:
                raise Refused(str(exc)) from exc
        return cmd


class AirHockeySport:
    name, protocol, revision, source_dirs, workers = "airhockey", "realtime", REVISION, [HERE], ("render",)

    def build(self, cfg):
        return AirHockey(cfg)

    def action_layer(self, level):
        return TargetLayer()

    def scene(self, cfg):
        from renderers.base import Scene
        return Scene(xml=H.scene_xml())

    def spec(self, cfg, seat, match):
        """hockey.py's public constants (no seed): the action workspace, the limits, the geometry and the timing."""
        h = match.h
        out = {"match": {"first_player": h.first, "points_to_win": H.POINTS_TO_WIN,
                         **({"opponent_level": h.level, "opponent_seat": "B"} if match.single else {})},
               "workspace": {"x_abs_m": [H.X_NEAR, H.X_FAR], "y_abs_max_m": H.Y_MAX, "reach_m": H.REACH,
                             "robot_base": {"A": [-H.BASE_X, 0.0], "B": [H.BASE_X, 0.0]}},
               "mallet_path": {"max_speed_m_s": H.MAX_SPEED, "max_accel_m_s2": H.MAX_ACCEL,
                               "takes_effect": "at the next control step", "hold": "until replaced"},
               "referee_timing": {"seven_second_rule_s": H.SEVEN_S, "dead_puck_s": H.DEAD_S, "centre_line_s": H.LINE_S,
                                  "play_time_cap_s": H.CAP_S, "max_rallies": H.MAX_RALLIES},
               "geometry": {"length_m": H.LENGTH, "width_m": H.WIDTH, "goal_width_m": H.GOAL,
                            "puck_radius_m": H.PUCK_R, "mallet_radius_m": H.MALLET_R, "puck_plane_z_m": 0.012,
                            "mallet_centre_z_m": 0.0645, "home": {"A": [-H.HOME_X, 0.0], "B": [H.HOME_X, 0.0]},
                            "puck_spot_abs_x_m": H.SPOT_X}}
        if H.GOAL != H.GOAL_DEFAULT:                 # the experiment knob RO_AIRHOCKEY_GOAL_M: the rules text follows
            g = H.GOAL
            out["table"] = (f"metres, seconds; the table frame: x along the table (seat A's end at x < 0, seat B's at "
                            f"x > 0), y across, z up. Playing surface 1.948 x 1.038 m (|x| <= 0.974, |y| <= 0.519), "
                            f"surrounded by rails; a goal mouth {g:g} m wide (|y| <= {g / 2:g}) in the middle of each "
                            f"end rail; the centre line is x = 0 (experiment setting: this goal width replaces the "
                            f"default {H.GOAL_DEFAULT:g} m)")
        return out

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "random": bp.Random}


SPORT = AirHockeySport()
