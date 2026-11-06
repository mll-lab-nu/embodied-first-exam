"""foosball: table football after the ITSF Standard Matchplay Rules on the v0.2 core (docs/framework_zh.md §4.2).
Migrated from the legacy tree (scripts/olympiad/foosball, scripts/olympiad/shared/foosball/sim) in stage 2: the
simulator foos.py (the MuJoCo table, the 2 x 4 motor-driven rods with their speed- and acceleration-limited paths,
the referee, the scripted opponent) and foos_policy.py (the opponent's policy, unchanged). Revision v2: the rods have
KiRo's top speeds (2.0 m/s, 52 rad/s), held by the servo on the rods themselves (deviation D10); the legacy (v1)
recordings no longer replay (golden/convert.py). The four groups of contract ② (core/sport.py):

  world        FoosMatch: one foos.Foosball per match (duel: seats A and B; format match: seat A against the
               scripted team, which plays seat B inside the world, levels 1-4); one control step = Foosball.step()
               (10 ms, 10 physics substeps); state_digest = Foosball.digest() (the legacy hash)
  actions      low only: {"type": "rods", "rods": {ROD: {slide, angle[, omega][, speed]}}} for any subset of the four
               rods, checked by foos.validate_action; apply() hands it to Foosball.schedule, which makes it reach the
               motors 2 control steps (20 ms) later, as in the legacy service (the effect queue is in the state hash)
  referee      a unit = a rally (goal, possession-time foul, incomplete opening, illegal spin, dead ball, ball off
               table); the world freezes after every rally for the reviews, resume() = Foosball.ready() (the referee
               places the ball for the restart); phase / scores / tiebreaks (= Foosball.winner() split into its steps)
  observation  observe = the seat's own rods and the referee's information (score, fouls, clocks, restart, the
               rallies so far), never the ball or the opponent; cameras = the seat's fixed overhead camera (own goal
               on the left), drawn by the task's renderer from scene() (foos.scene_xml) and render_state() (qpos)
"""

from __future__ import annotations

import os

import foos
from foos import DT, OTHER
from core.sport import FINISHED, PLAYING, UNIT_OVER, LowLayer, MatchBase, Phase, Refused

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "foosball-program-v2+core-0.2"  # foos.REVISION (foosball-program-v2; legacy: v1) on the v0.2 core
OPP = "opponent"  # the scripted team's side in the `match` format
TIEBREAKS = ("goals", "last_goal", "territory", "first_kickoff")
NUM = {"type": "number"}
SCHEMA = {
    "rods": {
        "rods": {
            "type": "object",
            "keys": list(foos.RODS),
            "doc": "targets for any nonempty subset of your rods, {ROD: {slide, angle, omega, speed}}; each rod "
            "needs slide and/or angle; rods not named keep their targets",
            "per_rod": {
                "slide": {
                    **NUM,
                    "unit": "m",
                    "range_by_rod": {r: [-t, t] for r, t in foos.TRAVEL.items()},
                    "doc": "slide target along your local v (0 = centre)",
                },
                "angle": {
                    **NUM,
                    "min": -foos.ANGLE_MAX,
                    "max": foos.ANGLE_MAX,
                    "unit": "rad",
                    "doc": "rotation target: 0 = figures hanging straight down, + = feet towards the opponent's goal",
                },
                "omega": {
                    **NUM,
                    "min": 0.0,
                    "max": foos.SPIN_W,
                    "unit": "rad/s",
                    "exclusive_min": True,
                    "doc": "optional cap of the angular speed for this target (default the maximum)",
                },
                "speed": {
                    **NUM,
                    "min": 0.0,
                    "max": foos.SLIDE_V,
                    "unit": "m/s",
                    "exclusive_min": True,
                    "doc": "optional cap of the sliding speed for this target (default the maximum)",
                },
            },
        }
    }
}


def you(seat, team):
    return None if team is None else ("you" if team == seat else "opponent")


def overhead(seat) -> dict:
    """foos.scene_xml's camera overhead_<seat> as a camera definition: straight down from (0, 0, CAM_Z), image right =
    the seat's local +u (towards the opponent's goal), image up = its local +v."""
    s = foos.OWN[seat]
    return {
        "name": "overhead",
        "pos": [0.0, 0.0, foos.CAM_Z],
        "lookat": [0.0, 0.0, 0.0],
        "up": [0.0, s, 0.0],
        "fovy_deg": foos.CAM_FOVY,
        "width": foos.CAM_W,
        "height": foos.CAM_H,
    }


class FoosMatch(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg
        self.duel = len(cfg.side_list()) == 2
        if not self.duel and tuple(cfg.seats) != ("A",):
            raise ValueError("foosball: format match has the one seat A (the scripted team plays B)")
        if self.duel and tuple(cfg.seats) != ("A", "B"):
            raise ValueError("foosball: the duel has the seats A and B")
        level = 1 if self.duel else int(cfg.level or 1)
        first = cfg.first if cfg.first in ("A", "B") else "A"
        self.r = foos.Foosball(seed=int(cfg.seed), level=level, duel=self.duel, first=first)
        self.dt = DT
        self.sides = {"A": cfg.side_of("A"), "B": cfg.side_of("B") if self.duel else OPP}

    @property
    def k(self):
        return self.r.k

    # ------------------------------------------------------------------ world
    def step(self):
        n = len(self.r.results)
        self.r.step()
        return [{"kind": "rally_end", **res} for res in self.r.results[n:]]

    def state_digest(self):
        return self.r.digest()

    # ------------------------------------------------------------------ actions
    def schema(self, seat):
        return SCHEMA

    def apply(self, seat, cmd):
        r = self.r
        if r.done or r.awaiting_review:
            return {"rejected": "the world is frozen"}
        if seat not in self.cfg.seats:
            return {"rejected": f"no seat {seat}"}
        r.schedule(seat, cmd["rods"])
        return {"taken_step": r.k, "effect_step": r.k + foos.LATENCY_STEPS}

    # ------------------------------------------------------------------ referee
    def phase(self):
        r = self.r
        if r.done:
            return Phase(FINISHED, reason=f"game over ({r.decided_by})")
        if r.awaiting_review:
            return Phase(
                UNIT_OVER, review=tuple(self.cfg.seats), reason=f"rally {len(r.results)}: {r.results[-1]['how']}"
            )
        return Phase(PLAYING)

    def resume(self):
        self.r.ready()

    def unit(self):
        return len(self.r.results)

    def scores(self):
        sc = self.r.scores()
        return {self.sides[s]: sc[s]["points"] for s in ("A", "B")}

    def tiebreaks(self):
        """foos.Foosball.winner() as a chain: more goals (the game to 5, or the cap with a lead); at the cap with equal
        goals the scorer of the last goal; at 0:0 the player with the ball less time in its own half; last resort
        (not from the rulebook): the player who did not have the first kick-off."""
        side = self.sides

        def goals(m):
            sc = m.r.scores()
            a, b = sc["A"]["points"], sc["B"]["points"]
            return None if a == b else side["A" if a > b else "B"]

        def last_goal(m):
            g = [x for x in m.r.results if x["how"] == "goal"]
            return side[g[-1]["winner"]] if g else None

        def territory(m):
            h = m.r.half_steps
            return None if h["A"] == h["B"] else side["A" if h["A"] < h["B"] else "B"]

        def first_kickoff(m):
            return side[OTHER[m.r.first]]

        return [("goals", goals), ("last_goal", last_goal), ("territory", territory), ("first_kickoff", first_kickoff)]

    # ------------------------------------------------------------------ observation
    def rally_summary(self, res, seat):
        """One ended rally as the seat sees it (the legacy service's news entry)."""
        sc = {s: sum(r["how"] == "goal" and r["winner"] == s for r in self.r.results[: res["rally"]]) for s in "AB"}
        out = {
            "rally": res["rally"],
            "how": res["how"],
            "scored": you(seat, res["winner"]),
            "fouled": you(seat, res["guilty"]),
            "restart": {
                "rod": "goalie" if res["next"][0] == "goalie" else "midfield",
                "team": you(seat, res["next"][1]),
            },
            "score": {"you": sc[seat], "opponent": sc[OTHER[seat]]},
            "t_play": round(res["k"] * DT, 2),
            "rally_s": round(res["steps"] * DT, 2),
        }
        for k in ("group", "where", "own_goal", "goal_disallowed"):
            if k in res:
                out[k] = res[k]
        return out

    def observe(self, seat, query=None):
        r = self.r
        live = not (r.awaiting_review or r.done)
        sc = r.scores()
        rallies = [self.rally_summary(x, seat) for x in r.results]
        return {
            "rally": len(r.results) + (1 if live else 0),
            "t_play": round(r.k * DT, 3),
            "t_rally": round(r.point_k * DT, 3),
            "play_time_left_s": round(max(0.0, foos.CAP_S - r.k * DT), 3),
            "awaiting_review": r.awaiting_review,
            "game_over": r.done,
            "score": {"you": sc[seat]["points"], "opponent": sc[OTHER[seat]]["points"]},
            "fouls": {"you": sc[seat]["fouls"], "opponent": sc[OTHER[seat]]["fouls"]},
            "restart": {
                "rod": "goalie" if r.restart_where[0] == "goalie" else "midfield",
                "team": you(seat, r.restart_where[1]),
                "opening_complete": bool(r.opening["done"]),
            },
            "rods": r.rod_state(seat),
            "last_rally": rallies[-1] if rallies else None,
            "rallies": rallies,
        }

    def cameras(self, seat, query=None):
        return [overhead(seat)]

    def render_state(self):
        return {"qpos": self.r.data.qpos.tolist()}

    def final_fields(self):
        """The legacy final.json fields the Season-1 readers and grade.py use."""
        r = self.r
        return {
            "results": r.results,
            "level": r.level,
            "first_player": r.first,
            "legacy_decided_by": r.decided_by,
            "match_limit": bool(r.decided_by and r.decided_by.startswith("cap")),
            "game_over": r.done,
            "legacy_scores": r.scores(),
            "legacy_winner": r.winner(),
            "half_steps": dict(r.half_steps),
            "wall_contact_steps": r.wall_contacts,
            "figure_contact_steps": r.contact_steps,
            "rod_speed_governed_steps": r.governed,
            "simulator_revision": foos.REVISION,
        }


class RodsLayer(LowLayer):
    """The only action level: foos.validate_action (the legacy body {"rods": {...}}, "type": "rods" optional), the
    command logged and applied is {"type": "rods", "rods": the normalised targets}."""

    def __init__(self):
        super().__init__(None)

    def parse(self, seat, body, match, ctx):
        try:
            rods = foos.validate_action(body, seat)
        except (TypeError, ValueError) as exc:
            raise Refused(str(exc)) from exc
        return {"type": "rods", "rods": rods}

    def reply(self, seat, cmd, info, match):
        return info


class Foosball:
    name, protocol, revision, source_dirs, workers = "foosball", "realtime", REVISION, [HERE], ("render",)

    def build(self, cfg):
        return FoosMatch(cfg)

    def action_layer(self, level):
        if level != "low":
            raise ValueError("foosball has one action level: low (the rod targets)")
        return RodsLayer()

    def scene(self, cfg):
        from renderers.base import Scene

        return Scene(xml=foos.scene_xml())

    def spec(self, cfg, seat, m):
        """The legacy /spec (match, limits, action ranges, camera calibration, geometry). Its "timing" part is renamed
        "game_timing" so that it does not shadow the core's /spec timing (slowdown, control step)."""
        lim = {
            "command_latency_s": foos.LATENCY_STEPS * DT,
            "points_to_win": foos.POINTS_TO_WIN,
            "play_time_cap_s": foos.CAP_S,
            "max_rallies": foos.MAX_RALLIES,
            "possession_limit_s": {g: foos.LIMIT_S[g] for g in ("goalie_rods", "midfield", "attack")},
            "dead_ball_s": foos.DEAD_S,
        }
        match = {"format": cfg.format, "first_kickoff": you(seat, m.r.first)}
        if not m.duel:
            match.update(opponent="scripted computer team (seat B, red)", opponent_level=m.r.level)
        return {
            "match": match,
            "game_timing": lim,
            "action": {
                "rods": list(foos.RODS),
                "slide_range_m": {r: foos.TRAVEL[r] for r in foos.RODS},
                "angle_range_rad": foos.ANGLE_MAX,
                "max_angular_speed_rad_s": foos.SPIN_W,
                "max_angular_accel_rad_s2": foos.SPIN_A,
                "max_slide_speed_m_s": foos.SLIDE_V,
                "max_slide_accel_m_s2": foos.SLIDE_A,
                "slide_force_limit_n": foos.SLIDE_F,
                "spin_torque_limit_nm": foos.SPIN_T,
                "takes_effect": f"{foos.LATENCY_STEPS} control steps after the control step that takes it",
                "out_of_range": "HTTP 400",
                "hold": "until replaced; rods not named keep their command; one request in flight",
            },
            "camera": {
                "name": "overhead",
                "width": foos.CAM_W,
                "height": foos.CAM_H,
                "fovy_deg": foos.CAM_FOVY,
                "position": [0.0, 0.0, foos.CAM_Z],
                "looking": "straight down",
                "image_right": "towards the opponent goal (local +u)",
                "image_up": "local +v",
                "ball_centre_z_m": foos.BALL_R,
            },
            "geometry": {
                "frame": "local: u towards the opponent goal, v to the left, z up; playfield z = 0, centre " "(0, 0)",
                "length_m": foos.LENGTH,
                "width_m": foos.WIDTH,
                "goal_width_m": foos.GOAL_W,
                "ball_radius_m": foos.BALL_R,
                "ball_mass_kg": foos.BALL_M,
                "rod_height_m": foos.ROD_Z,
                "own_rods_u_m": dict(foos.ROD_X),
                "opponent_rods_u_m": {r: -x for r, x in foos.ROD_X.items()},
                "figures_v_at_slide_0_m": {r: list(foos.MEN[r]) for r in foos.RODS},
                "foot": {"radius_m": foos.FOOT_R, "half_length_m": foos.FOOT_HL, "axis_below_rod_m": -foos.FOOT_Z},
                "reach_along_u_m": round(foos.X_REACH, 4),
                "cover_height_m": foos.LID_Z,
            },
        }

    def players(self):
        import builtin_players as bp

        return {"reference": bp.Reference, "random": bp.Random}


SPORT = Foosball()
