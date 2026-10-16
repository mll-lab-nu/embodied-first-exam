"""darts: 501 double-out, best of 3 legs, turn-based (docs/framework_zh.md §4.2). The four groups of contract ②:
  world + referee  darts.py, the legacy simulator (the board, the RK4 flight under gravity and quadratic drag, the
                   seeded execution scatter, since darts-7 each player's per-match calibration bias, the 501 double-out
                   referee and the visit cap); format 501 = darts.Match
                   (seat A against the scripted thrower, which throws inside the world between A's darts), format duel
                   = darts.Duel (seats A and B; since revision darts-5 each player's scatter is its own stream, the
                   first player's 1 and the other's 2, so the two matches of a pair swap them: the legacy duel records
                   with throws no longer replay, the 501 records replay bit-exactly)
  actions          one low level: a throw {yaw, pitch, speed} (schema; 4 decimals as before); the chess clocks at the
                   throw go into the command (a leg level at the visit cap goes to the player with more time left)
  referee          phase / scores / tiebreaks / to_move / forfeit (the visit cap and its last resort are inside darts.py)
  observation      observe = the score board and the caller's calls (no coordinates); cameras = oche, board, side
                   (board.py: the scene and the darts of the latest visit as mocap bodies, drawn by the task renderer);
                   reply images (core 0.2.8): reply_views = the board close-up after each dart with the darts of the
                   thrower's current visit, the one just thrown included (as the legacy reply's landed image)
"""
from __future__ import annotations

import os

import board as B
import darts as D
from core.sport import FINISHED, PLAYING, MatchBase, Phase, SchemaLayer

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "darts-7+core-0.2"
NUM = {"type": "number", "digits": 4}
SCHEMA = {"throw": {
    "yaw": {**NUM, "min": -D.YAW_MAX, "max": D.YAW_MAX, "unit": "deg", "doc": "0 = along +x, + = to your left"},
    "pitch": {**NUM, "min": D.PITCH_MIN, "max": D.PITCH_MAX, "unit": "deg", "doc": "elevation, + = up"},
    "speed": {**NUM, "min": D.V_MIN, "max": D.V_MAX, "unit": "m/s", "doc": "release speed"}}}
OPPONENT = "opponent"                 # the scripted thrower's side in format 501 (it has no seat)


def call_of(r: dict) -> str:
    return r["call"] + (f" - {r['event']}" if r.get("event") else "")


class Darts(MatchBase):
    def __init__(self, cfg):
        self.cfg, self.k = cfg, 0
        self.single = len(cfg.seats) == 1
        if self.single:
            self.level = 1 if cfg.level is None else int(cfg.level)
            if self.level not in D.LEVELS:
                raise ValueError(f"opponent level must be one of {sorted(D.LEVELS)}")
            self.d = D.Match(self.level, cfg.seed)
            self.d.run_to_decision()                     # the opponent throws first in leg 1
        else:
            self.level = None
            self.d = D.Duel(cfg.seed, cfg.first if cfg.first in D.SEATS else "A")

    # who threw / who is who: format 501 numbers the throwers (0 = seat A, 1 = the scripted opponent)
    def side_of_rec(self, r):
        return r["seat"] if "seat" in r else (self.cfg.seats[0] if r["who"] == 0 else OPPONENT)

    def side_of_idx(self, i):
        return self.cfg.seats[0] if i == 0 else OPPONENT

    def sides(self):
        return [self.cfg.seats[0], OPPONENT] if self.single else list(D.SEATS)

    def legs(self):
        return {s: self.d.legs[i] for i, s in enumerate(self.sides())} if self.single else dict(self.d.legs)

    def rem(self):
        return {s: self.d.rem[i] for i, s in enumerate(self.sides())} if self.single else dict(self.d.rem)

    # world + referee
    def state_digest(self):
        return self.d.state_sha()

    def schema(self, seat):
        return SCHEMA

    def apply(self, seat, cmd):
        y, p, s = cmd["yaw"], cmd["pitch"], cmd["speed"]
        if self.single:
            rec = self.d.player_throw(y, p, s)
            self.d.run_to_decision()
        else:
            rec = self.d.throw(seat, y, p, s, cmd.get("clock_left_s"))
        self.k += 1
        return {"caller": call_of(rec), "leg": rec["leg"], "visit": rec["visit"], "dart": rec["dart"]}

    def forfeit(self, seat, why):
        if self.single:
            if why == "clock":
                self.d.player_forfeit()
            elif not self.d.done:
                self.d.forfeit, self.d.done, self.d.winner, self.d.reason = True, True, 1, why
        else:
            self.d.lose(seat, why)
        return True

    def to_move(self):
        if self.d.done:
            return None
        return self.cfg.seats[0] if self.single else self.d.turn

    def phase(self):
        return Phase(FINISHED, reason=self.d.reason or "") if self.d.done else Phase(PLAYING)

    def unit(self):
        return len(self.d.visits)

    def scores(self):
        return self.legs()

    def continuous_score(self):
        """sport.toml [score] points_per_dart (core/score.py, from = "hook"): each side's points per dart thrown (a
        bust visit scores 0; 0 before its first dart)."""
        if self.single:
            return {self.cfg.seats[0]: self.d.stats(0)["points_per_dart"], OPPONENT: self.d.stats(1)["points_per_dart"]}
        return {s: self.d.stats(s)["points_per_dart"] for s in D.SEATS}

    def tiebreaks(self):
        # best of 3 legs; the leg rules (checkout, visit cap, lower remaining, clocks, the non-starter) are in darts.py
        def legs(m):
            w = m.d.winner
            return None if w is None else (m.side_of_idx(w) if m.single else w)
        return [("legs", legs)]

    # observation
    def observe(self, seat, query=None):
        M, me = self.d, self.cfg.side_of(seat)

        def who(side):
            return "you" if side == me else "opponent"
        legs, rem = self.legs(), self.rem()
        other = next(s for s in self.sides() if s != me)
        starter = self.side_of_idx(M.starter) if self.single else M.starter
        out = {"legs": {"you": legs[me], "opponent": legs[other]}, "leg": M.leg, "leg_first_thrower": who(starter),
               "remaining": {"you": rem[me], "opponent": rem[other]}}
        if not M.done:
            v = M.visit
            by = self.side_of_idx(v["who"]) if self.single else v["seat"]
            out.update({"visit_by": who(by), "visit": v["n"], "dart_in_visit": len(v["darts"]) + 1,
                        "darts_left_in_visit": M.darts_left(), "visit_start_score": v["start"],
                        "this_visit_so_far": [call_of(r) for r in v["darts"]]})
        mine = [i for i, r in enumerate(M.log) if self.side_of_rec(r) == me]
        last = M.log[mine[-1]] if mine else None
        out["your_last_dart"] = None if last is None else {
            "sent": {"yaw": last["cmd"][0], "pitch": last["cmd"][1], "speed": last["cmd"][2]}, "leg": last["leg"],
            "visit": last["visit"], "dart": last["dart"], "call": call_of(last), "remaining_after": last["after"]}
        out["darts_since_your_last"] = [
            {"by": who(self.side_of_rec(r)), "leg": r["leg"], "visit": r["visit"], "dart": r["dart"],
             "call": call_of(r), "remaining_after": r["after"]} for r in M.log[(mine[-1] + 1 if mine else 0):]]
        return out

    def cameras(self, seat, query=None):
        return [dict(c) for c in B.CAMERAS]

    def visit_darts(self):
        """The dart records of the latest visit (on the board until the next visit's first dart)."""
        log = self.d.log
        if not log:
            return []
        key = lambda r: (self.side_of_rec(r), r["leg"], r["visit"])  # noqa: E731
        return [r for r in log if key(r) == key(log[-1])]

    def render_state(self):
        return B.mocap(self.visit_darts())

    def reply_views(self, seat, cmd, info):
        """The board close-up right after the dart landed (the legacy landed image): the board camera with the darts
        of the thrower's current visit, the one just thrown included. Its own visit, also in format 501 where the
        scripted opponent's visit may already follow inside apply() and in the duel after its third dart, when the
        latest visit on the board is still its own but the next observation may show the opponent's."""
        me = self.cfg.side_of(seat)
        darts = [r for r in self.d.log
                 if (self.side_of_rec(r), r["leg"], r["visit"]) == (me, info["leg"], info["visit"])]
        board = next(dict(c) for c in B.CAMERAS if c["name"] == "board")
        return {"frames": [{"cameras": [board], "state": B.mocap(darts)}],
                "note": "board close-up after this dart: the darts of your current visit (flights yellow 1, cyan 2, "
                        "magenta 3)"}

    def final_fields(self):
        M = self.d
        if self.single:
            a = self.cfg.seats[0]
            return {"level": self.level, "won": M.done and M.winner == 0, "legs": list(M.legs),
                    "leg_results": M.leg_results, "you_remaining": M.rem[0], "opponent_remaining": M.rem[1],
                    "stats_you": M.stats(0), "stats_opponent": M.stats(1), "clock_forfeit": bool(M.forfeit),
                    "points_per_dart": {"you": M.stats(0)["points_per_dart"],
                                        "opponent": M.stats(1)["points_per_dart"]},
                    "match_reason": M.reason, "decisions": M.decisions, "log": M.log,
                    "visits": [{"by": "you" if v["who"] == 0 else "opponent", "leg": v["leg"], "visit": v["n"],
                                "darts": [r["call"] for r in v["darts"]], "scored": v.get("scored"),
                                "bust": v["bust"], "checkout": v["checkout"], "remaining": v.get("remaining")}
                               for v in M.visits],
                    "seats": {a: M.stats(0)}}
        fo = M.forfeit or {}
        return {"legs": dict(M.legs), "leg_results": M.leg_results, "remaining": dict(M.rem), "forfeit": M.forfeit,
                "clock_forfeit": fo.get("seat") if fo.get("why") == "clock" else None,
                "abandoned": fo.get("seat") if fo.get("why") == "abandoned" else None,
                "first_player": M.first, "decisions": M.decisions, "log": M.log,
                "points_per_dart": {s: M.stats(s)["points_per_dart"] for s in D.SEATS},
                "seats": {s: M.stats(s) for s in D.SEATS}}


class DartsSport:
    name, protocol, revision, source_dirs, workers = "darts", "turn", REVISION, [HERE], ()

    def build(self, cfg):
        return Darts(cfg)

    def action_layer(self, level):
        return SchemaLayer(ctx_keys=("clock_left_s",))

    def spec(self, cfg, seat, m):
        if len(cfg.seats) == 1:
            L = D.LEVELS[m.level]
            return {"first_player": "opponent", "opponent": {
                "level": m.level, "name": L["name"], "execution_scatter_1sigma": L["scatter"],
                "release_speed_m_s": L["speed"], "aim": "the optimal aim for its own scatter (minimum expected visits "
                "to check out); it uses no chess-clock time", "calibration_bias": "none (only your release mechanism has one)",
                "levels": "1-4: higher levels are stronger (execution scatter 1.2 / 1.1 / 1.0 / 0.9 x yours)"}}
        return {"first_player": cfg.first or "A"}

    def scene(self, cfg):
        from renderers.base import Scene
        return Scene(xml=B.scene_xml(), assets={B.TEX_FILE: B.board_texture()})

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "rival": bp.Rival, "random": bp.Random}


SPORT = DartsSport()
