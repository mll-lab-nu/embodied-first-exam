"""curling: the RoboOlympics v0.2 sport (docs/framework_zh.md §4.2), wrapping the unchanged legacy simulator.

Two formats on one plugin. `match`: one seat (A, yellow) against the scripted red team of curling.py (levels 1-3);
`duel`: seat A (yellow) against seat B (red). 4 ends of 5 stones per team, up to 3 extra ends while tied, the free
guard zone (five-rock rule), DigitalCurling's FCV1 ice model with impulse collisions (pure Python, 1 ms steps).

The simulator files are the legacy ones: curling.py (ice, collisions, rules, scripted team, curling.Match),
duel_core.py (duel_core.Duel = curling.Match with two seats) and render.py (the MuJoCo scene and the two camera
poses), changed for the execution-noise streams (revision curling-2) and for the hidden ice and scripted level 3
(curling-3: the deceleration scale kd of the ice, ice_kd() below, is drawn per seed and never shown; the scripted
team plays on the true ice, deviation D8). The four groups of contract ②:
  world        CurlingMatch wraps curling.Match (match) or duel_core.Duel (duel); state_digest = their state_sha()
               (so the legacy golden recordings replay to the same hash)
  actions      low level only: {"type": "throw", speed, angle, spin} (the release at the hack), checked against the
               schema; the chess clocks at the throw ride along in the command (clock_left_s), because a tie after
               the last extra end goes to the player with more clock left and the replay must see the same clocks
  referee      phase / scores / tiebreaks / to_move; in `match` the scripted team throws inside apply(), right after
               the player's throw, until it is the player's turn again (the legacy service did that after the review)
  observation  observe (score board, end, hammer, stones left, the throws since your last one: what a player on the
               ice hears, no coordinates) + cameras (house: top-down over the far house; hack: behind the hack), drawn
               by the task's renderer from scene() and render_state()
The execution noise (revision curling-2, 2026-10-08): each team its own stream, numpy default_rng([seed, end, stream,
n]) for its n-th stone of the end (match: the player 1, the scripted team 2; duel: the first player 1, the other 2, so
the two first orders of a seed swap them). Until curling-1 both teams' n-th stones drew the same numbers
(default_rng([seed, end, n])), which a team throwing later could read off the other's stone and pre-compensate.
"""
from __future__ import annotations

import math
import os

import curling as C
import duel_core as D
import render
from core.rng import stream
from core.sport import FINISHED, PLAYING, MatchBase, Phase, Refused, SchemaLayer

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "curling-4"                  # v0.2 sport revision (legacy: match turn-2, duel duel-turn-2; 2: noise streams;
                                        # 3: hidden ice kd, scripted level 3; 4: level 2 = level 3's planner, noisier)
OPP = "opponent"                        # the scripted team's side in the `match` format
COLOUR = {0: "yellow", 1: "red"}        # team 0 = seat A, team 1 = seat B or the scripted team
NUM = {"type": "number"}
SCHEMA = {"throw": {
    "speed": {**NUM, "min": C.V_MIN, "max": C.V_MAX, "unit": "m/s", "doc": "release speed at the hack"},
    "angle": {**NUM, "min": -C.ANGLE_MAX_DEG, "max": C.ANGLE_MAX_DEG, "unit": "deg",
              "doc": "release direction from the centre line, + = to the right (+x)"},
    "spin": {"type": "enum", "values": ["ccw", "cw"], "doc": "ccw curls to the left (-x), cw to the right (+x)"}}}


def camera_defs() -> list[dict]:
    """The legacy cameras (render.CAMERAS) as renderer camera definitions (same pose, field of view and size)."""
    out = []
    for c in render.CAMERAS:
        ax = c["axes_world"]
        pos = c["pos"]
        fwd = ax["optical_axis_forward"]
        t = -pos[2] / fwd[2]                                  # where the optical axis meets the ice (z = 0)
        out.append({"name": c["name"], "pos": list(pos), "lookat": [round(pos[i] + t * fwd[i], 6) for i in range(3)],
                    "up": [0.0, 1.0, 0.0] if c["name"] == "house" else [0.0, 0.0, 1.0],
                    "fovy_deg": c["fovy_deg"], "width": c["width_px"], "height": c["height_px"]})
    return out


CAMERAS = camera_defs()


def stone_share(points_for, points_against) -> float:
    """The sport's continuous score (curling-3): the share of the match's points a side scored, points_for /
    (points_for + points_against); 0.5 when nobody scored."""
    tot = points_for + points_against
    return 0.5 if tot == 0 else round(points_for / tot, 6)


def ice_kd(cfg) -> float:
    """The ice's deceleration scale kd of the match (curling-3): uniform in curling.KD_RANGE, drawn from the seed's
    own named stream (core.rng stream "ice"), so it never depends on any other draw; the same for both seats and for
    both first orders of a duel seed. The players are told the law and the range ([spec] ice), never kd."""
    lo, hi = C.KD_RANGE
    return float(stream(cfg, "ice").uniform(lo, hi))


def match_hammer(cfg) -> int:
    """match format (curling-3, deviation D6): the team with the hammer in end 1, by a coin toss drawn from the seed
    (core.rng stream "coin_toss", as the duel's): 0 -> the scripted team has it (1; seat A throws first, as the
    legacy match), 1 -> the player has it (0). The official match seeds are balanced: per level, as many seeds give the
    player the hammer as give it to the scripted team."""
    return 1 if int(stream(cfg, "coin_toss").integers(2)) == 0 else 0


def starter(cfg) -> str:
    """duel: the seat that throws the first stone of end 1 (the other has the hammer). A coin toss decides it (WCF
    R5(a)), drawn from the seed (core.rng stream "coin_toss"): FIRST_PLAYER (cfg.first) throws first when it falls 0,
    the other seat when it falls 1. The two first orders of a seed still give each seat the hammer once, and over
    seeds the side named first throws first half the time: the hammer is worth about 14 pp of win rate between the
    reference players, so the legacy rule (FIRST_PLAYER always throws first) fails the fairness check. The toss falls
    0 for the official seeds 1-3, so there FIRST_PLAYER throws first exactly as in the legacy duel."""
    first = cfg.first if cfg.first in cfg.seats else cfg.seats[0]
    toss = int(stream(cfg, "coin_toss").integers(2))
    return first if toss == 0 else D.OTHER[first]


class CurlingMatch(MatchBase):
    def __init__(self, cfg):
        self.cfg, self.k = cfg, 0
        self.single = len(cfg.side_list()) == 1
        if self.single:
            level = int(cfg.level or 1)
            if level not in C.LEVELS:
                raise ValueError(f"opponent level must be one of {sorted(C.LEVELS)}")
            self.g = C.Match(level, ice_kd(cfg))
            self.g.L["seed"] = int(cfg.seed)                 # the execution noise of both teams
            self.g.hammer = self.hammer1 = match_hammer(cfg)  # D6: the coin toss for the hammer in end 1
            self.g.run_to_decision()                         # the scripted team's stones before the player's first
            self.team = {cfg.seats[0]: 0}
            self.sides = [cfg.side_of(cfg.seats[0]), OPP]
        else:
            self.g = D.Duel(int(cfg.seed), starter(cfg), ice_kd(cfg))
            self.team = {"A": 0, "B": 1}
            self.sides = ["A", "B"]

    # ---------------------------------------------------------------- world
    def state_digest(self):
        return self.g.state_sha()

    def schema(self, seat):
        return SCHEMA

    def apply(self, seat, cmd):
        g = self.g
        if g.done or self.to_move() != seat:
            raise Refused("it is not your turn", 409)
        if self.single:
            rec = g.player_throw(cmd["speed"], cmd["angle"], cmd["spin"])
            after = self.at_rest()
            opp = g.run_to_decision()                        # the scripted team, up to the player's next stone
        else:
            rec = g.play(seat, {"v": cmd["speed"], "angle": cmd["angle"], "spin": cmd["spin"]})
            after = self.at_rest()
            opp = []
        self.settle_tie(cmd.get("clock_left_s"))
        self.k += 1
        return {"rec": rec, "opp": opp, "after": after}

    def at_rest(self):
        """The render state right after the throw just made came to rest (the end's last stones if it ended the end),
        before any other stone: the reply image (reply_views)."""
        g = self.g
        return self.render_state(g.sheet.stones if g.k > 0 else g.end_sheet.stones)

    def settle_tie(self, clocks):
        """A tie after the last extra end goes to the player with more chess-clock time left (the legacy services'
        rule, recorded in the state like there). match: the scripted team's clock never runs, so the tie goes to it;
        duel: equal clocks -> the player who did not throw first in end 1 (it had the hammer)."""
        g = self.g
        if not g.done or g.score[0] != g.score[1] or getattr(g, "tiebreak", None) is not None:
            return
        clocks = clocks or {}
        if self.single:
            mine = round(float(clocks.get(self.cfg.seats[0], 0.0)), 3)
            budget = float(os.environ.get("CLOCK_S", "3600"))
            g.resolve_tiebreak(0 if mine > budget else 1, [mine, budget])
        else:
            c = {s: round(float(clocks.get(s, 0.0)), 3) for s in D.SIDES}
            w = "A" if c["A"] > c["B"] else "B" if c["B"] > c["A"] else D.OTHER[g.first]
            g.resolve_tie(w, c)

    # ---------------------------------------------------------------- referee
    def to_move(self):
        if self.g.done:
            return None
        if self.single:
            return self.cfg.seats[0]
        return self.g.turn

    def phase(self):
        return Phase(FINISHED, reason="match_over") if self.g.done else Phase(PLAYING)

    def unit(self):
        return self.g.end

    def scores(self):
        return dict(zip(self.sides, self.g.score))

    def tiebreaks(self):
        a, b = self.sides

        def points(m):
            s = m.g.score
            return None if s[0] == s[1] else (a if s[0] > s[1] else b)

        def clock(m):
            tb = getattr(m.g, "tiebreak", None)
            if not tb or tb["clock_left_s"][0] == tb["clock_left_s"][1]:
                return None
            return a if tb["winner"] == 0 else b

        last = (lambda m: b) if self.single else (lambda m: D.OTHER[m.g.first])
        return [("points", points), ("chess_clock", clock), ("hammer_in_end_1", last)]

    # ---------------------------------------------------------------- observation
    def who(self, team, seat):
        return "you" if team == self.team[seat] else "opponent"

    def heard(self, r, seat):
        """What a player on the ice knows about a throw: who threw, the spin, collisions heard, stones removed (no
        coordinates); your own release; the end's result if the throw was the end's last stone."""
        if "pass" in r:
            return {"end": r["end"] + 1, "throw": r["k"] + 1, "by": self.who(r["team"], seat), "pass": r["pass"]}
        rem, why = {"you": 0, "opponent": 0}, []
        for sid, reason in r["removed"]:
            t = 0 if sid < C.N_STONES else 1
            rem[self.who(t, seat)] += 1
            why.append(f"{'your' if t == self.team[seat] else 'an opponent'} stone"
                       f"{' (the thrown one)' if sid == r.get('sid') else ''}: {reason}")
        h = {"end": r["end"] + 1, "throw": r["k"] + 1, "by": self.who(r["team"], seat), "spin": r["spin"],
             "collisions_heard": r["collisions"], "stones_removed": rem, "removed_why": why}
        if r.get("fgz_violation"):
            h["free_guard_zone_violation"] = ("the thrown stone moved an opposition guard out of play: it was removed "
                                              "and the stones were put back")
        if r["team"] == self.team[seat]:
            h["your_release"] = {"speed": r["v"], "angle_deg": r["angle"], "spin": r["spin"]}
        if r["k"] == 2 * C.N_STONES - 1:
            e = next((e for e in self.g.ends if e["end"] == r["end"]), None)
            if e is not None:
                h["end_finished"] = self.end_summary(e, seat)
        return h

    def end_summary(self, e, seat):
        t = self.team[seat]
        return {"end": e["end"] + 1, "scored_by": "blank" if e["team"] < 0 else self.who(e["team"], seat),
                "points": e["points"], "score_after": {"you": e["score"][t], "opponent": e["score"][1 - t]}}

    def observe(self, seat, query=None):
        g, t = self.g, self.team[seat]
        log = g.log
        mine = [i for i, r in enumerate(log) if r["team"] == t and "pass" not in r]
        since = log[mine[-1]:] if mine else log
        out = {"score": {"you": g.score[t], "opponent": g.score[1 - t]}, "your_colour": COLOUR[t],
               "regulation_ends": C.N_ENDS, "ends_so_far": [self.end_summary(e, seat) for e in g.ends],
               "throws_since_your_last": [self.heard(r, seat) for r in since]}
        if not g.done:
            out.update({"end": g.end + 1, "extra_end": g.end >= C.N_ENDS, "throw_in_end": g.k + 1,
                        "your_stone": C.N_STONES - g.stones_left(t) + 1,
                        "hammer": "you" if g.hammer == t else "opponent",
                        "stones_left_to_throw": {"you": g.stones_left(t), "opponent": g.stones_left(1 - t)},
                        "stones_in_play": {"you": sum(1 for s in g.sheet.stones if s["team"] == t),
                                           "opponent": sum(1 for s in g.sheet.stones if s["team"] != t)}})
        return out

    def cameras(self, seat, query=None):
        return CAMERAS

    def render_state(self, stones=None):
        pos = [[20.0 + i, -20.0, 0.0] for i in range(render.NSLOT)]   # unused stones wait off the sheet
        quat = [[1.0, 0.0, 0.0, 0.0] for _ in range(render.NSLOT)]
        for s in (self.g.sheet.stones if stones is None else stones):
            pos[s["id"]] = [s["x"], s["y"], 0.0]
            quat[s["id"]] = [math.cos(s["a"] / 2), 0.0, 0.0, math.sin(s["a"] / 2)]
        return {"qpos": [], "mocap_pos": pos, "mocap_quat": quat}

    def reply_views(self, seat, cmd, info):
        """The house camera right after the throw came to rest, before the next stone (curling-3): in the match format
        the scripted team's reply follows inside the same action, so without it a player would never see where its
        own stone stopped whenever the reply moves it, and could not learn the hidden ice from its throws (the legacy
        service let the player look before the scripted team threw). Duel: the same image (the other player has not
        thrown yet)."""
        house = next(dict(c) for c in CAMERAS if c["name"] == "house")
        return {"frames": [{"cameras": [house], "state": info["after"], "label": "your throw at rest"}],
                "note": "the house camera right after your throw came to rest (and every stone it moved), before the "
                        "next stone"}

    def broadcast_frame(self):
        st = self.render_state()
        return {"q": [x for p in st["mocap_pos"] for x in p[:2]], "score": self.scores(), "end": self.g.end + 1}

    def final_fields(self):
        """The legacy final.json fields the Season-1 readers use (live_board, regrade_transient)."""
        g = self.g
        out = {"ends": g.ends, "n_ends_played": len(g.ends), "throws": g.n_throws, "log": g.log,
               "decisions": g.decisions, "tiebreak": getattr(g, "tiebreak", None),
               "ice_kd": g.kd}                                 # after the match only (final.json), never to a player
        if self.single:
            out.update(level=g.level, points_for=g.score[0], points_against=g.score[1],
                       hammer_end_1="you" if self.hammer1 == 0 else "opponent",
                       stone_share=stone_share(g.score[0], g.score[1]))
        else:
            out.update(n_shots=len(g.decisions), first_player=self.cfg.first, threw_first_in_end_1=g.first,
                       stone_share={"A": stone_share(g.score[0], g.score[1]), "B": stone_share(g.score[1], g.score[0])})
        return out


class ThrowLayer(SchemaLayer):
    """The low level: the throw as the schema says, plus the chess clocks at the throw (ctx) for the tie rule."""

    def __init__(self):
        super().__init__(ctx_keys=("clock_left_s",))

    def reply(self, seat, cmd, info, match):
        out = {"accepted": {k: cmd[k] for k in ("speed", "angle", "spin")},
               "your_throw": match.heard(info["rec"], seat)}
        if match.single:
            out["opponent_throws"] = [match.heard(r, seat) for r in info["opp"]]
        return out


class Curling:
    name, protocol, revision, source_dirs, workers = "curling", "turn", REVISION, [HERE], ()

    def build(self, cfg):
        return CurlingMatch(cfg)

    def action_layer(self, level):
        if level != "low":
            raise ValueError("curling has one action level: low (the release)")
        return ThrowLayer()

    def scene(self, cfg):
        from renderers.base import Scene
        return Scene(xml=render.scene_xml())

    def spec(self, cfg, seat, m):
        single = len(cfg.side_list()) == 1
        t = 0 if single else D.TEAM[seat]
        match = {"format": cfg.format, "ends": C.N_ENDS, "max_extra_ends": C.MAX_EXTRA_ENDS,
                 "stones_per_team_per_end": C.N_STONES, "free_guard_zone_stones": C.FGZ_STONES,
                 "your_colour": COLOUR[t], "opponent_colour": COLOUR[1 - t]}
        if single:
            match.update(opponent="scripted computer team", opponent_level=m.g.level,
                         hammer_end_1="you" if m.hammer1 == 0 else "opponent",
                         throws_first_in_end_1="opponent" if m.hammer1 == 0 else "you",
                         coin_toss="the team with the hammer in end 1 is drawn from the seed (R5(a)); the other team "
                                   "throws the first stone")
        else:
            match.update(first_player=cfg.first, throws_first_in_end_1=m.g.first,
                         you_throw_first_in_end_1=seat == m.g.first, hammer_end_1=D.OTHER[m.g.first],
                         coin_toss="the seat that throws first in end 1 is drawn from the seed (R5(a)); the other "
                                   "seat has the hammer in end 1")
        return {"match": match,
                "world": {"origin": "release point at the hack", "+y": "down the sheet towards the far house",
                          "+x": "right", "tee": [0.0, C.TEE_Y], "far_hog_line_y": C.HOG_Y, "back_line_y": C.BACK_Y,
                          "house_radius": C.HOUSE_R, "sheet_half_width": C.HALF_W, "stone_radius": C.R,
                          "stone_top_z": 0.112, "handle_top_z": 0.146}}

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "random": bp.Random}


SPORT = Curling()
