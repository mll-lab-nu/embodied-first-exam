"""Mini-golf putting for the turn service (server.py): one 4-hole round per seat (golf.py: putting physics + MuJoCo
scene for rendering).

In a duel both players play the same holes, each with its own ball, and the balls never meet: a player plays a hole
alone, from the tee to the cup (a review after each stroke), then the other plays it. The player who plays a hole
second plays the next hole first (hole 1: FIRST_PLAYER), so the order is A B | B A | A B | B A for FIRST_PLAYER = A.
The stroke scatter is the same for both (seeded by seed, hole and stroke). A player sees only its own ball; it hears
the opponent's results and score. Fewest strokes wins; a tie goes to a sudden-death play-off (WMF 9.3), then the clock.
"""
import math
import os

SEED_DEFAULT = 20260928                      # the original course (golf.BASE_SEED)
SEED = int(os.environ.get("TURN_SEED") or SEED_DEFAULT)
os.environ["GOLF_SEED"] = str(SEED)          # golf.py reads the course layout and the scatter seed from it
import golf as G  # noqa: E402

NAME = "mini-golf putting"
LOWER_WINS = True
SUCCESS_MAX_TOTAL = sum(H["par"] for H in G.HOLES)   # single player: par (9), the old task's line
PAR_TOTAL = SUCCESS_MAX_TOTAL
FORFEIT_SCORE = G.MAX_STROKES + 1
ACTION_KEYS = ("aim_deg", "speed")
# observe: one PNG; tile name -> (x, y, width, height) in pixels
TILES = {"behind": (0, 0, 800, 500), "side": (0, 500, 800, 500), "overhead": (800, 0, 1200, 600)}
IMAGE_SIZE = (2000, 1000)
IMAGE_LAYOUT = ("one PNG, 2000 x 1000: left column, behind (top) and side (bottom), 800 x 500 each; right, at x = 800, "
                "y = 0, overhead (1200 x 600). behind: 2 m behind the ball, looking along +x; side: fixed, beyond the "
                "left wall at mid-green, looking along -y (image right = +x); overhead: the whole green from above "
                "(image right = +x, image up = +y), yellow dots = your previous stroke on this hole. White grid lines "
                "every 0.5 m follow the surface; the flagstick stands in the cup.")


def validate(body: dict):
    if body.get("type") != "putt":
        return "the action must be {'type': 'putt', 'aim_deg': a, 'speed': v}"
    try:
        a, v = float(body["aim_deg"]), float(body["speed"])
    except (KeyError, TypeError, ValueError):
        return "putt needs aim_deg and speed (numbers)"
    if not (math.isfinite(a) and math.isfinite(v)) or not -180.0 <= a <= 180.0:
        return "aim_deg must be a number in [-180, 180]"
    if not 0.05 <= v <= 6.0:
        return "speed must be a number in [0.05, 6.0] m/s"
    return {"aim_deg": round(a, 3), "speed": round(v, 4)}


def hole_scores(c, clock_out=False) -> list:
    """Per hole: strokes (+1 for a pick-up); when the clock ran out, the unfinished hole and the rest score 7."""
    n = len(G.HOLES)
    out = []
    for i in range(n):
        finished = c.done or i < c.hole
        if finished:
            out.append(c.hole_score(i))
        elif clock_out:
            out.append(FORFEIT_SCORE)
        else:
            out.append(None)
    return out


TIEBREAK_MAX = 4                 # duel: sudden-death play-off holes (holes 1-4 once, WMF 9.3) before the clock decides
TIEBREAK_NAME = "play-off hole"


class PlayoffHole:
    """One sudden-death play-off hole (WMF 9.3): hole h played again from its start; scored as in the round."""

    def __init__(self, h):
        self.h = h
        self.c = G.Course()
        self.c.hole, self.c.pos = h, tuple(G.HOLES[h]["ball"])
        self.done = False

    def putt(self, aim, speed):
        rec, r = self.c.putt(aim, speed)
        self.done = rec["hole_finished"]
        return rec, r

    def score(self):
        return self.c.hole_score(self.h) if self.done else None


def score_of(c, clock_out=False, playoffs=()) -> dict:
    hs = hole_scores(c, clock_out)
    return {"total": sum(x for x in hs if x is not None), "holes": hs, "strokes_per_hole": list(c.strokes),
            "picked_up": list(c.picked_up), "complete": c.done, "par": PAR_TOTAL,
            "par_of_holes_scored": sum(H["par"] for H, x in zip(G.HOLES, hs) if x is not None),
            "playoff": [{"hole": p.h + 1, "score": p.score(), "complete": p.done} for p in playoffs]}


def decide(scores: dict):
    """From the two seats' scores (score_of): the seat ahead (fewer strokes) after the round and any complete play-off
    holes, or None while level. Used by the live service and by the replay."""
    a, b = scores
    if scores[a]["total"] != scores[b]["total"]:
        return a if scores[a]["total"] < scores[b]["total"] else b
    for pa, pb in zip(scores[a]["playoff"], scores[b]["playoff"]):
        if pa["complete"] and pb["complete"] and pa["score"] != pb["score"]:
            return a if pa["score"] < pb["score"] else b
    return None


def success(score: dict) -> bool:
    return score["complete"] and score["total"] <= SUCCESS_MAX_TOTAL


class Match:
    """Per seat: the 4-hole round, then (duel, tied) the sudden-death play-off holes."""

    def __init__(self, seats, order):
        self.c = {s: G.Course() for s in seats}
        self.p = {s: [] for s in seats}
        self.v = None

    @property
    def n_tiebreaks(self):
        return len(next(iter(self.p.values())))

    def done(self, s):
        return self.p[s][-1].done if self.p[s] else self.c[s].done

    def _units(self, s):
        c = self.c[s]
        return (len(G.HOLES) if c.done else c.hole) + sum(1 for p in self.p[s] if p.done)

    def turn(self, order):
        """A hole is played by one player at a time; whoever played a hole second plays the next one first."""
        live = [s for s in order if not self.done(s)]
        if not live:
            return None
        h = min(self._units(s) for s in live)
        cands = [s for s in live if self._units(s) == h]
        lead = order[h % len(order)]
        return lead if lead in cands else cands[0]

    def winner(self):
        return decide({s: self.score(s) for s in self.c})

    def start_tiebreak(self):
        h = self.n_tiebreaks % len(G.HOLES)          # from hole 1, then the following holes
        for s in self.p:
            self.p[s].append(PlayoffHole(h))

    def _cur(self, s):
        return self.p[s][-1].c if self.p[s] else self.c[s]

    def shoot(self, s, dec):
        if self.p[s]:
            p = self.p[s][-1]
            rec, _ = p.putt(dec["aim_deg"], dec["speed"])
            out = {"playoff_hole": len(self.p[s]), "hole": rec["hole"], "stroke": rec["stroke"], "result": rec["result"],
                   "holed": rec["holed"], "wall_or_block_hits": rec["walls"], "roll_time_s": rec["roll_time_s"],
                   "hole_finished": p.done}
            if p.done:
                out.update(hole_score=p.score(), picked_up=p.c.picked_up[p.h])
            return out
        c = self.c[s]
        hi = c.hole
        rec, _ = c.putt(dec["aim_deg"], dec["speed"])
        out = {"hole": rec["hole"], "stroke": rec["stroke"], "result": rec["result"], "holed": rec["holed"],
               "wall_or_block_hits": rec["walls"], "roll_time_s": rec["roll_time_s"],
               "hole_finished": rec["hole_finished"]}
        if rec["hole_finished"]:
            out.update(hole_score=c.hole_score(hi), picked_up=c.picked_up[hi], par=G.HOLES[hi]["par"])
        out["total_so_far"] = sum(x for x in hole_scores(c) if x is not None)
        return out

    def decision(self, s):
        c = self._cur(s)
        hi = c.hole
        d = {"hole": hi + 1, "par": G.HOLES[hi]["par"], "stroke": c.strokes[hi] + 1, "max_strokes": G.MAX_STROKES}
        if self.p[s]:
            d["playoff_hole"] = len(self.p[s])
        if c.last:
            L = c.last
            d["last_putt"] = {"stroke": L["stroke"], "you_played": {"aim_deg": L["aim_deg"], "speed": L["speed"]},
                              "result": L["result"], "wall_or_block_hits": L["walls"], "roll_time_s": L["roll_time_s"]}
        return d

    def views(self, s):
        if self.v is None:
            self.v = G.Views()
        c = self._cur(s)
        return self.v.render(c.hole, c.pos, trail=c.last["trail"] if c.last else None)

    def summary(self, s):
        c = self.c[s]
        hs = hole_scores(c)
        done = [x for x in hs if x is not None]
        out = {"total": sum(done), "holes_done": len(G.HOLES) if c.done else c.hole,
               "par_of_holes_done": sum(H["par"] for H in G.HOLES[:len(done)]), "hole_scores": hs}
        if self.p[s]:
            out["playoff"] = [{"hole": p.h + 1, "score": p.score()} for p in self.p[s]]
        return out

    def score(self, s, clock_out=False):
        return score_of(self.c[s], clock_out, self.p[s])

    def state_sha(self, s):
        return "/".join([self.c[s].state_sha()] + [p.c.state_sha() for p in self.p[s]])


def replay(actions, clock_out=False, n_tiebreaks=0) -> dict:
    c = G.Course()
    ps = [PlayoffHole(k % len(G.HOLES)) for k in range(n_tiebreaks)]
    i = -1
    for a in actions:
        if i < 0 and not c.done:
            c.putt(a["aim_deg"], a["speed"])
            continue
        i = max(i, 0)
        while ps[i].done:
            i += 1
        ps[i].putt(a["aim_deg"], a["speed"])
    return {"state_sha": "/".join([c.state_sha()] + [p.c.state_sha() for p in ps]), "score": score_of(c, clock_out, ps)}


def render_video(actions, out):
    c = G.Course()                                   # the 4-hole round only (play-off strokes are not shown)
    n = 0
    for a in actions:
        if c.done:
            break
        c.putt(a["aim_deg"], a["speed"])
        n += 1
    G.render_video(actions[:n], out)


def spec(duel: bool) -> dict:
    rnd = {"holes": G.spec_holes(), "par_total": PAR_TOTAL, "max_strokes_per_hole": G.MAX_STROKES,
           "rulebook": "WMF Rulebook 2.3 (World Minigolf Sport Federation); scoring as WMF 9.1",
           "pick_up": f"not holed after {G.MAX_STROKES} strokes: the hole scores {FORFEIT_SCORE}",
           "clock_out": f"the unfinished hole and the holes not played score {FORFEIT_SCORE} each"}
    if duel:
        rnd["duel"] = ("both players play the same holes with their own ball (the balls never meet); a player plays a "
                       "hole out alone, then the other plays it; whoever plays a hole second plays the next hole "
                       "first (hole 1: the first player); the stroke scatter is the same for both; fewest strokes "
                       "wins")
        rnd["tie"] = (f"sudden-death play-off (WMF 9.3): holes 1, 2, ... are played again, each scored alone; the "
                      f"lower score on a play-off hole wins; the starter keeps alternating; at most {TIEBREAK_MAX} "
                      "play-off holes; if still level, the player with more chess-clock time left wins")
    else:
        rnd["success"] = f"round complete and total <= {SUCCESS_MAX_TOTAL} (par); fewer strokes is better"
    return {
        "simulator": "deterministic putting model (rolling ball on a height field, walls, cup) + MuJoCo 3.3.7 scene "
                     "for rendering (osmesa)",
        "match": rnd,
        "stroke": {"putt": "{'type':'putt','aim_deg':a,'speed':v}",
                   "aim_deg": "the putter face's heading = the ball's start direction, in the green's frame: 0 = +x "
                              "(along the green towards its far end), + = counter-clockwise seen from above (90 = +y); "
                              "[-180, 180]",
                   "speed": "the ball's initial rolling speed, m/s; [0.05, 6.0]",
                   "scatter": f"N(0, {G.AIM_SIGMA_DEG} deg) on the aim and N(0, {G.SPEED_SIGMA * 100:g} %) on the speed"},
        "ball_and_green": {"ball_radius_m": G.R_BALL, "cup_radius_m": G.R_CUP, "stimpmeter_ft": 10,
                           "green_speed": f"on a flat green a ball starting at {G.V_STIMP} m/s rolls {G.D_STIMP} m",
                           "walls": "restitution about 0.7 into the wall, 0.92 along it; red blocks are obstacles"},
        "cameras": G.spec_cameras(),
        "world": "each hole has its own frame: the green is x in [0, L], y in [-W/2, W/2] (holes[]), z up",
    }
