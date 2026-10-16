"""billiards: the RoboOlympics v0.2 sport (docs/framework_zh.md §4.2), wrapping the unchanged legacy simulator.

One rack of American 8-ball (WPA Rules of Play, 2025-09-15) on pooltool 0.6.0's event-based physics. Two formats on
one plugin. `eightball`: one seat (A) against the scripted opponent of eightball.py (levels 1-3); `duel`: seat A
(player 0) against seat B (player 1). In both formats the seed's coin toss decides who breaks (breaker()).

The simulator files are the legacy ones (eightball.py since billiards-3: the planning opponent of levels 1-3 and the coin toss, the
rack, the shot and the rules unchanged): eightball.py (rack, shot simulation, rules, the scripted
opponent, eightball.Match), duel_core.py (duel_core.Duel = eightball.Game with two seats) and render.py (the PIL
pinhole renderer of the two cameras). The four groups of contract ②:
  world        BilliardsMatch wraps eightball.Match (eightball) or duel_core.Duel (duel); state_digest = their
               state_sha() (so the legacy golden recordings replay to the same hash)
  actions      low level only: {"type": "shoot", aim_deg, speed, spin_x, spin_y, [cue_x, cue_y], [call]}, checked
               against the schema and then by the rules (eightball.Game.check: ball in hand, the call) before it is
               logged; the chess clocks at the shot ride along (clock_left_s) for the tie rule at the shot limit
  referee      phase / scores (balls left in each player's group, 7 while the table is open) / tiebreaks / to_move;
               in `eightball` the scripted opponent plays inside apply(), right after the player's shot, until it is
               the player's turn again (the legacy service did that after the review)
  observation  observe (the score board, ball in hand, the call rule, the balls on the table by number, the shots
               since your last one; no coordinates) + the two cameras (top: fixed overhead; sight: behind the cue ball
               along an aim the observation query may choose, {"aim": DEG}), drawn by the sport itself (camera_job ->
               worker_call: render.py), one PNG of two tiles
The execution noise and the rack keep the legacy draws (numpy default_rng([seed, 7919, k]) and ([seed, 8])): moving
them to core.rng would change every shot and break the golden replays. The only other random number is the coin toss
for the break (breaker(): core.rng stream "coin_toss"; both formats since billiards-3).
"""
from __future__ import annotations

import copy
import math
import os
import sys
from collections import OrderedDict


def _writable_dirs() -> None:
    """pooltool writes its config under $HOME/.config/pooltool and caches its numba kernels next to its own files
    (compiled into the image at build time). A process that can write neither (a non-root user without a home, e.g.
    the checks' docker runs) fails at import: give it a home and a numba cache of its own under the temp directory
    (pooltool writes its default config there, numba compiles once). Never changes a result."""
    import importlib.util
    import tempfile
    tmp = tempfile.gettempdir()
    home = os.path.expanduser("~")
    if not os.access(home, os.W_OK):
        os.environ["HOME"] = os.path.join(tmp, f"home-{os.getuid()}")
        os.makedirs(os.environ["HOME"], exist_ok=True)
    spec = importlib.util.find_spec("pooltool")
    where = os.path.dirname(spec.origin) if spec and spec.origin else None
    if where and not os.access(where, os.W_OK) and not os.environ.get("NUMBA_CACHE_DIR"):
        os.environ["NUMBA_CACHE_DIR"] = os.path.join(tmp, f"numba-cache-{os.getuid()}")


_writable_dirs()
import duel_core as D  # noqa: E402
import eightball as E8  # noqa: E402
import render  # noqa: E402
from core.rng import stream  # noqa: E402
from core.sport import FINISHED, PLAYING, MatchBase, Phase, Refused, SchemaLayer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "billiards-3"                # v0.2 sport revision; billiards-1: FIRST_PLAYER broke in the duel (legacy:
                                        # eightball-turn-2, eightball-duel-turn-2); billiards-2: a seeded coin toss decides
                                        # (duel); billiards-3: the planning opponent (levels 1-3; its strokes checked
                                        # by the rules, a kick search when snookered), the toss in eightball too, the
                                        # sight camera at the cue ball's 5 cm cell, placements reported without where
OPP = "opponent"                        # the scripted opponent's side in the `eightball` format
CALLS = sorted(f"{b}:{p}" for b in E8.OBJ_IDS for p in E8.POCKET_IDS) + ["safety"]
NUM = {"type": "number"}
SCHEMA = {"shoot": {
    "aim_deg": {**NUM, "min": -360.0, "max": 360.0, "unit": "deg",
                "doc": "cue direction in the table plane, counter-clockwise from +x (taken modulo 360)"},
    "speed": {**NUM, "min": E8.V_RANGE[0], "max": E8.V_RANGE[1], "unit": "m/s", "doc": "cue stick speed at impact"},
    "spin_x": {**NUM, "min": -E8.SPIN_MAX, "max": E8.SPIN_MAX, "default": 0.0, "unit": "ball radii",
               "doc": f"tip offset to the right; sqrt(spin_x^2 + spin_y^2) <= {E8.SPIN_MAX}"},
    "spin_y": {**NUM, "min": -E8.SPIN_MAX, "max": E8.SPIN_MAX, "default": 0.0, "unit": "ball radii",
               "doc": "tip offset upwards (+ = follow, - = draw)"},
    "cue_x": {**NUM, "min": round(E8.R, 6), "max": round(E8.W - E8.R, 6), "default": None, "unit": "m",
              "doc": "ball in hand only: where to place the cue ball first (with cue_y)"},
    "cue_y": {**NUM, "min": round(E8.R, 6), "max": round(E8.L - E8.R, 6), "default": None, "unit": "m",
              "doc": "ball in hand only (with cue_x); above the head string (break, scratch on the break): y < L/4"},
    "call": {"type": "enum", "values": CALLS, "default": None,
             "doc": "every shot after the break (not the break): BALL:POCKET (a ball you may hit first, a pocket of "
                    f"{list(E8.POCKET_IDS)}), e.g. 3:rc or 8:lt; or safety"}}}
TILES = [{"camera": "top", "x": 0, "y": 0, "width": render.TOP["size"][0], "height": render.TOP["size"][1]},
         {"camera": "sight", "x": render.TOP["size"][0], "y": 0, "width": render.SIGHT["size"][0],
          "height": render.SIGHT["size"][1]}]
BALL_IN_HAND = {None: None, "kitchen": "above the head string (y < L/4)", "anywhere": "anywhere"}
# Shots the physics engine cannot resolve: pooltool 0.6.0 occasionally fails an internal assertion (e.g. a cushion
# contact found with the ball not approaching it). The legacy services ended the trial there as a simulator error,
# and the same seed and players hit the same failure again, so such a configuration could never be played. Here the
# shot is simulated again from the same state with the requested aim nudged by these amounts (degrees) until the
# engine resolves it; the shot record says so (physics_retry). Deterministic, so the replay does the same; a shot the
# engine resolves (every legacy record) is never touched.
AIM_NUDGES_DEG = [s * 0.001 * i for i in range(1, 31) for s in (1, -1)]   # +0.001, -0.001, +0.002, ... +-0.03 deg
# If none of them resolves the shot either, the shot is void (D10, eightball.Game.void_shot): nothing moves, no foul,
# the same player shoots again (the next attempt is a new shot number, so a new execution draw).
_VIEWS: OrderedDict = OrderedDict()     # rendered observations (state, aim) -> PNG, a small cache


def breaker(cfg) -> str:
    """The side that breaks (duel: a seat; eightball: the player's seat or OPP). A coin toss drawn from the seed decides it (core.rng stream "coin_toss"; deviation
    D9: replaces the lag of WPA 1.2 / 4.1, whose winner chooses who breaks): FIRST_PLAYER (cfg.first) breaks when it
    falls 0, the other seat when it falls 1. The toss depends on the seed only, so the two first orders of a seed are
    still the same rack mirrored (each seat breaks once), and over seeds the side named first breaks half the time:
    the break is worth about 6 pp of win rate between the reference players, which the legacy rule (FIRST_PLAYER
    always breaks) put entirely on the first side. Same rule as curling's hammer toss. eightball (billiards-3): the same
    toss, the player breaks when it falls 0 and the scripted opponent when it falls 1 (billiards-2: level 1 the player,
    level 2 the opponent, so the break's edge was part of the difference between the levels)."""
    toss = int(stream(cfg, "coin_toss").integers(2))
    if len(cfg.side_list()) == 1:
        return cfg.seats[0] if toss == 0 else OPP
    first = cfg.first if cfg.first in cfg.seats else cfg.seats[0]
    return first if toss == 0 else D.OTHER[first]


def _restore(g, snap):
    g.__dict__.update(copy.deepcopy(snap))


def guard_engine(g: E8.Game) -> None:
    """Route every shot of this game (the player's and the scripted opponent's) through the engine-failure rule
    (AIM_NUDGES_DEG). The rules and the physics are eightball.Game.shoot unchanged."""

    def shoot(p, dec):
        snap = copy.deepcopy({k: v for k, v in g.__dict__.items() if k != "shoot"})
        try:
            return E8.Game.shoot(g, p, dec)
        except Exception as exc:  # noqa: BLE001  (pooltool's assertion or numerical failure inside simulate)
            first_error = repr(exc)[:200]
        for nudge in AIM_NUDGES_DEG:
            _restore(g, snap)
            try:
                rec = E8.Game.shoot(g, p, dict(dec, aim_deg=(float(dec["aim_deg"]) + nudge) % 360.0))
            except Exception:  # noqa: BLE001
                continue
            rec["physics_retry"] = {"engine_error": first_error, "aim_nudge_deg": round(nudge, 6)}
            return rec
        _restore(g, snap)
        return E8.Game.void_shot(g, p, dec, f"the physics engine could not resolve the shot: {first_error}")

    g.shoot = shoot


def caller_query():
    """The observation query of the current /observe call. WORKAROUND for a missing core hook: the core passes the
    query to Match.cameras(seat, query) but calls Match.camera_job(seat) (a sport that draws its own images) without
    it, so this reads the `query` local of the calling core frame (core.service.Service.camera_job or
    core.local.Views.view). Remove once the core passes the query to camera_job."""
    f = sys._getframe(2)
    for _ in range(6):
        if f is None:
            break
        if f.f_globals.get("__name__", "").startswith("core.") and "query" in f.f_locals:
            q = f.f_locals["query"]
            return q if isinstance(q, dict) else None
        f = f.f_back
    return None


def aim_of(query, pos) -> float:
    """The sighting direction: the query's {"aim": DEG}, else from the cue ball towards the table centre."""
    aim = (query or {}).get("aim")
    if aim is None:
        return render.default_sight_phi(pos)
    if isinstance(aim, bool) or not isinstance(aim, (int, float)) or not math.isfinite(aim):
        raise Refused("query aim must be a finite number (degrees)")
    return float(aim) % 360.0


class BilliardsMatch(MatchBase):
    def __init__(self, cfg):
        self.cfg, self.k = cfg, 0                            # k: the players' shots (commands) so far
        self.single = len(cfg.side_list()) == 1
        if self.single:
            level = int(cfg.level or 1)
            if level not in E8.LEVELS:
                raise ValueError(f"opponent level must be one of {sorted(E8.LEVELS)}")
            g = E8.Game(int(cfg.seed), 0 if breaker(cfg) != OPP else 1)
            guard_engine(g)
            self.mt = E8.Match.__new__(E8.Match)             # eightball.Match with the guarded game
            self.mt.level, self.mt.seed, self.mt.g = level, int(cfg.seed), g
            self.mt.opening = self.mt.follow()               # the opponent breaks (and runs while it pots) if the toss says so
            self.g = g
            self.player = {cfg.seats[0]: 0}
            self.sides = [cfg.side_of(cfg.seats[0]), OPP]
        else:
            self.d = D.Duel(int(cfg.seed), breaker(cfg))
            guard_engine(self.d.g)
            self.g = self.d.g
            self.player = {"A": 0, "B": 1}
            self.sides = ["A", "B"]

    # ---------------------------------------------------------------- world
    def state_digest(self):
        return self.g.state_sha()

    def schema(self, seat):
        return SCHEMA

    def decision(self, cmd) -> dict:
        """The legacy decision dict (eightball.Game.shoot) of a low-level command."""
        dec = {"type": "shoot", "aim_deg": cmd["aim_deg"], "speed": cmd["speed"],
               "spin_x": cmd.get("spin_x", 0.0), "spin_y": cmd.get("spin_y", 0.0)}
        if cmd.get("cue_x") is not None:
            dec["cue_xy"] = [cmd["cue_x"], cmd["cue_y"]]
        if cmd.get("call") is not None:
            dec["call"] = cmd["call"]
        return dec

    def apply(self, seat, cmd):
        g = self.g
        if g.done or self.to_move() != seat:
            raise Refused("it is not your turn", 409)
        dec = self.decision(cmd)
        err = g.check(self.player[seat], dec)
        if err:
            raise Refused(err, 409 if err == "it is not your turn" else 400)
        if self.single:
            rec = self.mt.shot(dec)
            self.settle_tie(cmd.get("clock_left_s"))
            opp = self.mt.follow()                           # the scripted opponent, up to the player's next shot
        else:
            rec = self.d.play(seat, dec)
            opp = []
        self.settle_tie(cmd.get("clock_left_s"))
        self.k += 1
        return {"rec": rec, "opp": opp}

    def settle_tie(self, clocks):
        """A tie at the shot limit goes to the player with more chess-clock time left (the legacy services' rule,
        recorded in the state like there). eightball: the scripted opponent's clock never runs, so a tie goes to it;
        duel: equal clocks -> the player who did not break."""
        g = self.g
        if not g.done or g.winner is not None:
            return
        clocks = clocks or {}
        if self.single:
            mine = round(float(clocks.get(self.cfg.seats[0], 0.0)), 3)
            budget = float(os.environ.get("CLOCK_S", "3600"))
            g.resolve_tiebreak(0 if mine > budget else 1, [mine, budget])
        else:
            c = {s: round(float(clocks.get(s, 0.0)), 3) for s in D.SIDES}
            w = "A" if c["A"] > c["B"] else "B" if c["B"] > c["A"] else D.OTHER[self.d.first]
            self.d.resolve_tie(w, c)

    # ---------------------------------------------------------------- referee
    def to_move(self):
        if self.g.done:
            return None
        if self.single:
            return self.cfg.seats[0] if self.g.turn == 0 else None
        return self.d.turn

    def phase(self):
        return Phase(FINISHED, reason="match_over") if self.g.done else Phase(PLAYING)

    def balls_left(self, p: int) -> int:
        return len(self.g.left_in_group(p)) if self.g.group[p] else 7

    def ball_share(self, p: int) -> float:
        """The continuous score: p's share of the rack's progress, (p's group balls down + 1 if p won) / (the same for
        both players); 0.5 while nothing counts (both groups untouched, no winner). A ball counts for the group it
        belongs to, whoever pots it (WPA 4.5); an open table counts 0 for both."""
        g = self.g

        def done(q):
            return (7 - self.balls_left(q)) + (1 if g.done and g.winner == q else 0)
        a, b = done(p), done(1 - p)
        return round(a / (a + b), 4) if a + b else 0.5

    def continuous_score(self):
        """sport.toml [score] (from = "hook"): ball_share of each side, larger is better. The scores are the balls LEFT
        in each group (lower is better), so core's "share" of the scores would invert it."""
        return {self.sides[0]: self.ball_share(0), self.sides[1]: self.ball_share(1)}

    def scores(self):
        """The balls left in each side's group (an open table counts 7): LOWER IS BETTER (0 = cleared). Not points:
        the rack is decided by the 8 (tiebreaks), and the continuous score is ball_share (continuous_score)."""
        return {self.sides[0]: self.balls_left(0), self.sides[1]: self.balls_left(1)}

    def tiebreaks(self):
        sides = self.sides

        def rack(m):                                         # the rack decided by its rules (the 8, a foul on it)
            g = m.g
            if g.done and g.winner is not None and not str(g.result).startswith("shot limit"):
                return sides[g.winner]
            return None

        def balls(m):                                        # the shot limit: fewer balls left in the own group
            a, b = m.balls_left(0), m.balls_left(1)
            return None if a == b else (sides[0] if a < b else sides[1])

        def clock(m):
            tb = getattr(m.g, "tiebreak", None)
            if not tb or tb["clock_left_s"][0] == tb["clock_left_s"][1]:
                return None
            return sides[tb["winner"]]

        last = (lambda m: OPP) if self.single else (lambda m: D.OTHER[m.d.first])
        return [("rack", rack), ("balls_left", balls), ("chess_clock", clock), ("did_not_break", last)]

    # ---------------------------------------------------------------- observation
    def who(self, p, seat):
        return "you" if p == self.player[seat] else "opponent"

    def shot_text(self, s: dict, seat: str) -> dict:
        """What a player at the table knows about a shot (the legacy shot texts): who, the break, the first ball hit,
        the balls potted and their pockets, the foul, the call and whether it was made, the groups, the cue placement."""
        o = {"shot": s["k"] + 1, "player": self.who(s["player"], seat), "break": s["break"],
             "first_hit": s["first_hit"], "potted": s["potted"], "pockets": s["pockets"], "foul": s["foul"],
             "cue_ball_pocketed": s["cue_ball_pocketed"], "keeps_turn": s["keeps_turn"]}
        if s["call"]:
            o["call"], o["call_made"] = s["call"], s["call_made"]
        if s.get("void"):
            o["void"] = ("the physics engine could not resolve this shot: it is void (nothing moved, no foul) and the "
                         "same player shoots again")
        if s["cue_placed_at"]:                    # whether, not where (E3: the placement is a ball's coordinates)
            o["cue_placed"] = True
        if s["eight_respotted"]:
            o["eight_respotted"] = "the 8 was potted on the break and spotted again on the foot spot"
        if s["rerack"]:
            o["rerack"] = "illegal break: the balls were racked again and the other player breaks"
        if s["group_assigned"]:
            g = s["group_assigned"]
            o["groups_assigned"] = {self.who(s["player"], seat): g,
                                    self.who(1 - s["player"], seat): E8.OTHER_GROUP[g]}
        if s["game_over"]:
            o["game_over"] = s["result"]
        if s["player"] == self.player[seat]:
            o["your_shot"] = s["requested"]
        return o

    def observe(self, seat, query=None):
        g, p = self.g, self.player[seat]
        mine = [i for i, s in enumerate(g.shots) if s["player"] == p]
        since = g.shots[mine[-1]:] if mine else g.shots
        out = {"shot_number": g.k + 1, "balls_on_table": g.objects_left(), "cue_ball_on_table": "cue" in g.pos,
               "breaker": self.who(g.breaker, seat), "your_group": g.group_name(p),
               "opponent_group": g.group_name(1 - p), "your_balls_left": self.balls_left(p),
               "opponent_balls_left": self.balls_left(1 - p), "your_shots": g.n_shots[p],
               "opponent_shots": g.n_shots[1 - p], "max_shots": E8.MAX_SHOTS,
               "shots_since_your_last": [self.shot_text(s, seat) for s in since]}
        if not g.done and g.turn == p:
            out.update(break_shot=not g.break_done, ball_in_hand=BALL_IN_HAND[g.ball_in_hand],
                       on_the_8=g.on_the_8(p), call_required=g.must_call(p))
        if g.done:
            out["result"] = g.result
        return out

    def camera_job(self, seat, query=None):
        if query is None:
            query = caller_query()
        pos = dict(self.g.pos)
        phi = aim_of(query, pos)
        c = pos.get("cue") or E8.HEAD_SPOT
        cams = [render.camera_info(render.top_camera(), "top"), render.camera_info(render.sight_camera(c, phi), "sight")]
        return ({"pos": pos, "phi": phi, "key": (self.g.state_sha(), round(phi, 3))},
                {"sight_aim_deg": round(phi, 3), "cameras": cams, "tiles": TILES})

    def broadcast_frame(self):
        g = self.g
        return {"q": [], "balls": {k: [round(v[0], 5), round(v[1], 5)] for k, v in sorted(g.pos.items())},
                "score": self.scores(), "shot": g.k}

    def final_fields(self):
        """The legacy final.json fields the Season-1 readers use (live_board, regrade_transient, the graders)."""
        g = self.g
        out = {"result": g.result, "game_over": g.done, "tiebreak": getattr(g, "tiebreak", None),
               "shots": g.shots, "decisions": g.decisions, "n_shots_total": g.k, "eight_on_table": "8" in g.pos,
               "breaker": self.sides[g.breaker]}
        if self.single:
            ours = [s for s in g.shots if s["player"] == 0]
            out.update(level=self.mt.level, ball_share=self.ball_share(0), your_group=g.group[0], opponent_group=g.group[1],
                       your_balls_left=self.balls_left(0), opponent_balls_left=self.balls_left(1),
                       our_shots=sum(1 for s in ours if not s.get("void")),
                       opponent_shots=sum(1 for s in g.shots if s["player"] != 0 and not s.get("void")),
                       our_pots=sum(len(s["potted"]) for s in ours if not s["foul"]),
                       our_fouls=sum(1 for s in ours if s["foul"]))
        else:
            out.update(first_player=self.cfg.first, n_shots=g.k,
                       balls_left={s: self.d.balls_left(s) for s in D.SIDES},
                       ball_share={s: self.ball_share(i) for i, s in enumerate(D.SIDES)})
        out["physics_retries"] = sum(1 for s in g.shots if s.get("physics_retry"))
        out["physics_voids"] = sum(1 for s in g.shots if s.get("void"))
        return out


class ShootLayer(SchemaLayer):
    """The low level: the shot as the schema says, normalized (aim modulo 360, the optional fields dropped when
    absent), checked by the rules of the moment (eightball.Game.check), plus the chess clocks at the shot (ctx) for
    the tie rule at the shot limit."""

    def __init__(self):
        super().__init__(ctx_keys=("clock_left_s",))

    def parse(self, seat, body, match, ctx):
        if isinstance(body, dict):
            body = dict(body)
            body.setdefault("type", "shoot")
            if isinstance(body.get("call"), str):
                body["call"] = body["call"].strip().lower() or None
            for k in ("cue_x", "cue_y", "call"):
                if k in body and body[k] is None:
                    del body[k]
        cmd = super().parse(seat, body, match, ctx)
        cmd["aim_deg"] = cmd["aim_deg"] % 360.0
        if math.hypot(cmd["spin_x"], cmd["spin_y"]) > E8.SPIN_MAX:
            raise Refused(f"tip offset too far from centre: sqrt(spin_x^2 + spin_y^2) must be <= {E8.SPIN_MAX} "
                          "(a miscue)")
        if (cmd["cue_x"] is None) != (cmd["cue_y"] is None):
            raise Refused("cue_x and cue_y go together (ball in hand: where to place the cue ball)")
        for k in ("cue_x", "cue_y", "call"):
            if cmd[k] is None:
                del cmd[k]
        if match.to_move() == seat:
            err = match.g.check(match.player[seat], match.decision(cmd))
            if err:
                raise Refused(err)
        return cmd

    def reply(self, seat, cmd, info, match):
        out = {"accepted": {k: v for k, v in cmd.items() if k != "clock_left_s"},
               "your_shot": match.shot_text(info["rec"], seat)}
        if match.single:
            out["opponent_shots"] = [match.shot_text(r, seat) for r in info["opp"]]
        return out


class Billiards:
    name, protocol, revision, source_dirs, workers = "billiards", "turn", REVISION, [HERE], ()

    def build(self, cfg):
        return BilliardsMatch(cfg)

    def action_layer(self, level):
        if level != "low":
            raise ValueError("billiards has one action level: low (the shot)")
        return ShootLayer()

    def worker_call(self, obj, kind, job):
        """Draw a camera job (BilliardsMatch.camera_job): the top and sighting views of render.py, one PNG of two
        tiles (TILES). The sighting view is set up at the cue ball's 5 cm cell (render.sight_anchor). With the cue
        ball off the table (ball in hand after a scratch) there is no stick and the sighting view looks from the head
        spot's cell."""
        key = job["key"]
        if key not in _VIEWS:
            import numpy as np
            from core.observe import compose, png
            pos, phi = job["pos"], job["phi"]
            c = pos.get("cue") or E8.HEAD_SPOT
            stick = phi if "cue" in pos else None
            top = render.render(render.top_camera(), pos, stick_phi=stick,
                                label="top view (image right = +y, image down = +x)")
            lab = f"sighting view along aim {phi:.2f} deg" + ("" if "cue" in pos else
                                                              " (cue ball in hand: from the head spot)")
            sight = render.render(render.sight_camera(c, phi), pos, stick_phi=stick, label=lab)
            sheet, _ = compose([np.asarray(top), np.asarray(sight)], ["top", "sight"], columns=2)
            _VIEWS[key] = png(sheet)
            while len(_VIEWS) > 16:
                _VIEWS.popitem(last=False)
        return {"png": _VIEWS[key], "tiles": TILES}

    def spec(self, cfg, seat, m):
        p = m.player[seat]
        match = {"type": "8-ball, one rack", "format": cfg.format, "solids": list(E8.SOLIDS),
                 "stripes": list(E8.STRIPES), "max_shots_each": E8.MAX_SHOTS, "you_break": m.g.breaker == p}
        if m.single:
            match.update(opponent="scripted computer opponent", opponent_level=m.mt.level,
                         breaker="you" if m.g.breaker == 0 else "opponent",
                         first_player_rule="a coin toss drawn from the seed decides who breaks (it replaces the lag of "
                                           "WPA 1.2): you if it falls 0, else the scripted opponent")
        else:
            match.update(first_player=cfg.first, breaker=m.d.first,
                         coin_toss="FIRST_PLAYER breaks" if m.d.first == cfg.first else "the other player breaks",
                         first_player_rule="a coin toss drawn from the seed decides who breaks (it replaces the lag of "
                                           "WPA 1.2): FIRST_PLAYER if it falls 0, else the other player")
        return {
            "simulator": "pooltool 0.6.0 (event-based billiards physics)",
            "rules": "WPA Rules of Play, effective 2025-09-15, 8-Ball (with the deviations listed in the instructions)",
            "match": match,
            "action": {"shoot": {"aim_deg": "cue direction in the table plane, degrees counter-clockwise from +x",
                                 "speed": f"cue stick speed at impact, m/s, in [{E8.V_RANGE[0]}, {E8.V_RANGE[1]}]",
                                 "spin_x, spin_y": f"tip offset in ball radii, sqrt(x^2+y^2) <= {E8.SPIN_MAX}",
                                 "cue_x, cue_y": "ball in hand only: where to place the cue ball first (optional)",
                                 "call": ("every shot after the break (not the break): BALL:POCKET with a ball you may "
                                          f"hit first and a pocket of {list(E8.POCKET_IDS)}, e.g. 3:rc or 8:lt; or "
                                          "safety")},
                       "execution_scatter_sigma": E8.EXEC_SIGMA},
            "table": {"playing_surface": {"x": [0.0, round(E8.W, 4)], "y": [0.0, round(E8.L, 4)]},
                      "ball_radius": E8.R, "cloth_z": 0.0, "ball_centre_z": E8.R,
                      "pockets": {k: {"centre_xy": [round(float(c[0]), 4), round(float(c[1]), 4)],
                                      "radius": float(E8.TABLE.pockets[k].radius), "where": E8.POCKET_NAMES[k]}
                                  for k, c in E8.POCKETS.items()},
                      "head_spot": [round(E8.HEAD_SPOT[0], 4), round(E8.HEAD_SPOT[1], 4)],
                      "foot_spot": [round(E8.FOOT_SPOT[0], 4), round(E8.FOOT_SPOT[1], 4)],
                      "head_string_y": round(E8.HEAD_STRING_Y, 4)},
            "cameras": {"top": render.camera_info(render.top_camera(), "top"),
                        "sight": {"anchor": "the cue ball's position rounded to a 5 cm grid (x and y to multiples "
                                            "of 0.05 m): the camera is set up at its cell, not at the ball, so its "
                                            "pose does not give the cue ball's position",
                                  "eye": "0.75 m behind the anchor along -aim, 0.32 m above the cloth",
                                  "looks_at": "the cloth 1.0 m ahead of the anchor along the aim",
                                  "aim": "observe with the query {\"aim\": DEG} (game observe '{\"aim\": 87.5}'); "
                                         "default: from the anchor towards the table centre; the cue stick is drawn "
                                         "along the aim through the cue ball itself",
                                  "image_px": list(render.SIGHT["size"]), "fx": render.SIGHT["f"],
                                  "fy": render.SIGHT["f"],
                                  "note": "its exact pose for each image is in the observation's `cameras`"},
                        "image": "one PNG of two tiles, left to right: top, sight (observation.tiles)"},
        }

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "greedy": bp.Greedy, "nosafety": bp.NoSafety, "blindopp": bp.BlindOpp,
                "random": bp.Random, "fixed": bp.Fixed}


SPORT = Billiards()
