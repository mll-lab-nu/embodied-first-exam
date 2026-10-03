"""Ten-pin bowling for the turn service (server.py): one 10-frame game per seat (bowling.py, MuJoCo).

In a duel each player bowls on its own lane; the lanes are identical (same oil pattern from the seed) and so is the
release scatter (seeded by seed, frame and ball), so the same release gives the same result on both lanes. Turns: a
player bowls a whole frame (with a review after each ball), then the other; FIRST_PLAYER leads every frame. A player
sees only its own lane; it hears the opponent's pin counts and score.
"""
import math
import os

SEED_DEFAULT = 20260930                      # the standard lane (bowling.BASE_SEED)
SEED = int(os.environ.get("TURN_SEED") or SEED_DEFAULT)
os.environ["BOWL_SEED"] = str(SEED)          # bowling.py reads the lane condition and the scatter seed from it
import bowling as B  # noqa: E402

NAME = "bowling"
LOWER_WINS = False
SUCCESS_MIN_TOTAL = 200                      # single player: the old task's line (bowling-interactive)
ACTION_KEYS = ("board", "angle_deg", "speed", "rpm", "axis_deg")
LIMITS = {"board": (1.0, 39.0), "angle_deg": (-10.0, 10.0), "speed": (3.0, 11.0), "rpm": (0.0, 700.0),
          "axis_deg": (-90.0, 90.0)}
# observe: one PNG; tile name -> (x, y, width, height) in pixels
TILES = {"approach": (0, 0, 960, 540), "pindeck": (0, 540, 960, 540), "pindeck_after": (0, 1080, 960, 540),
         "lane": (960, 0, 1000, 1360)}
IMAGE_SIZE = (1960, 1620)
IMAGE_LAYOUT = ("one PNG, 1960 x 1620: left column, top to bottom, approach, pindeck, pindeck_after (960 x 540 each; "
                "pindeck_after is black before your first ball); right, at x = 960, the lane from above (1000 x 1360, "
                "four stacked 5 m panels, top = foul line end; in each panel right = towards the pins, up = left; your "
                "previous ball's path as yellow dots). Boards: 1 (right gutter) to 39 (left), 20 = centre.")


def validate(body: dict):
    if body.get("type") != "roll":
        return "the action must be {'type': 'roll', 'board': b, 'angle_deg': a, 'speed': v, 'rpm': r, 'axis_deg': x}"
    out = {}
    for k, (lo, hi) in LIMITS.items():
        try:
            v = float(body[k])
        except (KeyError, TypeError, ValueError):
            return f"roll needs {', '.join(LIMITS)} (numbers)"
        if not math.isfinite(v) or not lo <= v <= hi:
            return f"{k} must be a number in [{lo:g}, {hi:g}]"
        out[k] = round(v, 4)
    return out


TIEBREAK_MAX = 3                 # duel: roll-off frames before the clock decides (USBC 118b: one frame scored like a 10th)
TIEBREAK_NAME = "roll-off frame"


def rolloff_game():
    """A roll-off: one frame scored like a 10th frame (USBC 118b), on a fresh rack; it stands alone."""
    g = B.Game(B.MAX_FRAMES)
    g.frames = [[0, 0] for _ in range(B.MAX_FRAMES - 1)] + [[]]
    return g


def score_of(g, clock_out=False, rolloffs=()) -> dict:
    out = {"total": g.total(), "frames": g.frames, "complete": g.done,
           "strikes": sum(1 for r in g.log if r["strike"]), "spares": sum(1 for r in g.log if r["spare"]),
           "gutter_balls": sum(1 for r in g.log if r["gutter"])}
    out["rolloffs"] = [{"total": r.total(), "balls": r.frames[-1], "complete": r.done} for r in rolloffs]
    return out


def decide(scores: dict):
    """From the two seats' scores (score_of): the seat ahead after the game and any complete roll-off frames, or None
    while level. Used by the live service and by the replay."""
    a, b = scores
    if scores[a]["total"] != scores[b]["total"]:
        return a if scores[a]["total"] > scores[b]["total"] else b
    for ra, rb in zip(scores[a]["rolloffs"], scores[b]["rolloffs"]):
        if ra["complete"] and rb["complete"] and ra["total"] != rb["total"]:
            return a if ra["total"] > rb["total"] else b
    return None


def success(score: dict) -> bool:
    return score["complete"] and score["total"] >= SUCCESS_MIN_TOTAL


class Match:
    """Per seat: the 10-frame game, then (duel, tied) the roll-off frames."""

    def __init__(self, seats, order):
        self.g = {s: [B.Game(B.MAX_FRAMES)] for s in seats}
        self.v = None

    @property
    def n_tiebreaks(self):
        return len(next(iter(self.g.values()))) - 1

    def cur(self, s):
        return self.g[s][-1]

    def done(self, s):
        return self.cur(s).done

    def _units(self, s):
        """Frames completed, roll-off frames included: the turn goes to whoever has bowled fewer."""
        gs = self.g[s]
        n = B.MAX_FRAMES if gs[0].done else gs[0].frame
        return n + sum(1 for r in gs[1:] if r.done)

    def turn(self, order):
        live = [s for s in order if not self.done(s)]
        if not live:
            return None
        m = min(self._units(s) for s in live)
        return next(s for s in live if self._units(s) == m)

    def winner(self):
        return decide({s: self.score(s) for s in self.g})

    def start_tiebreak(self):
        for gs in self.g.values():
            gs.append(rolloff_game())

    def shoot(self, s, dec):
        g = self.cur(s)
        fi = g.frame
        rec, _ = g.bowl({k: dec[k] for k in ACTION_KEYS})
        out = {"frame": rec["frame"], "ball": rec["ball"], "pins_down": rec["count"], "strike": rec["strike"],
               "spare": rec["spare"], "gutter": rec["gutter"], "frame_finished": g.done or g.frame != fi}
        if len(self.g[s]) > 1:
            out["rolloff"] = len(self.g[s]) - 1
            out["rolloff_total"] = g.total()
        else:
            out["total_so_far"] = g.total()
        return out

    def decision(self, s):
        g = self.cur(s)
        d = {"frame": g.frame + 1, "ball": g.ball + 1, "fresh_rack": g.standing_count() == 10,
             "pins_standing": g.standing_count()}
        if len(self.g[s]) > 1:
            d["rolloff"] = len(self.g[s]) - 1
        if g.last:
            L = g.last
            d["last_ball"] = {"frame": L["frame"], "ball": L["ball"], "you_played": L["requested"],
                              "pins_down": L["count"], "strike": L["strike"], "spare": L["spare"], "gutter": L["gutter"]}
        return d

    def views(self, s):
        if self.v is None:
            self.v = B.Views(self.g[s][0].lane)      # the lanes are identical: one renderer serves every seat
        return self.v.decision_views(self.cur(s))

    def summary(self, s):
        g = self.g[s][0]
        out = {"total": g.total(), "frames_done": B.MAX_FRAMES if g.done else g.frame, "scorecard": g.scorecard()}
        if len(self.g[s]) > 1:
            out["rolloffs"] = [{"total": r.total(), "balls": r.frames[-1], "complete": r.done} for r in self.g[s][1:]]
        return out

    def score(self, s, clock_out=False):
        return score_of(self.g[s][0], clock_out, self.g[s][1:])

    def state_sha(self, s):
        return "/".join(g.state_sha() for g in self.g[s])


def replay(actions, clock_out=False, n_tiebreaks=0) -> dict:
    gs = [B.Game(B.MAX_FRAMES)] + [rolloff_game() for _ in range(n_tiebreaks)]
    i = 0
    for a in actions:
        while gs[i].done:
            i += 1
        gs[i].bowl({k: a[k] for k in ACTION_KEYS})
    return {"state_sha": "/".join(g.state_sha() for g in gs), "score": score_of(gs[0], clock_out, gs[1:])}


def render_video(actions, out):
    B.render_video(actions, out, B.MAX_FRAMES)      # the 10-frame game (it stops there; roll-off balls are not shown)


def spec(duel: bool) -> dict:
    game = {"frames": B.MAX_FRAMES,
            "scoring": "standard ten-pin: strike = 10 + next two balls, spare = 10 + next ball; the 10th frame gives "
                       "bonus balls for a strike or spare; max 300",
            "deck": "a fresh rack for each frame's first ball (and in the 10th frame after a strike or spare); "
                    "otherwise the pins that fell are swept away and the standing pins stay where they are, even if "
                    "they were moved",
            "pin_down": f"a pin counts as down if it tilts more than {B.DOWN_TILT_DEG:g} deg or leaves the lane surface "
                        "(gutter, pit, kickbacks); a pin standing anywhere on the lane counts as standing (USBC 7b)",
            "gutter_ball": "a ball that leaves the lane before reaching the pins scores no pins; pins it moved are "
                           "respotted (USBC 6b.1)",
            "rulebook": "USBC Playing Rules 2025-2026"}
    if duel:
        game["duel"] = ("each player bowls its own game on its own lane; the lanes and the release scatter are "
                        "identical; a player bowls a whole frame, then the other; the first player leads every frame; "
                        "the higher total wins")
        game["tie"] = (f"roll-off (USBC 118b): each player bowls one more frame, scored like a 10th frame on a fresh "
                       f"rack, and the higher roll-off frame wins; repeated while level, at most {TIEBREAK_MAX} roll-off "
                       "frames; if still level, the player with more chess-clock time left wins")
    else:
        game["success"] = f"total >= {SUCCESS_MIN_TOTAL}"
    return {
        "simulator": "mujoco 3.3.7 (rigid-body lane, ball and pins; osmesa rendering)",
        "match": game,
        "release": {
            "roll": "{'type':'roll','board':b,'angle_deg':a,'speed':v,'rpm':r,'axis_deg':x}",
            "board": "where the ball's centre is laid down across the lane, 35 cm past the foul line, in boards from the "
                     "RIGHT edge (board k covers [k-1, k] x 27.03 mm from the right edge; 20 = centre); [1, 39]",
            "angle_deg": "launch direction from the lane's axis, + = towards the left (higher boards); [-10, 10]",
            "speed": "ball speed at release, m/s; [3, 11]",
            "rpm": "rev rate at release, revolutions per minute; [0, 700]",
            "axis_deg": "axis rotation: the spin axis is horizontal, the pure forward-roll axis turned by this angle "
                        "counter-clockwise seen from above; 0 = end over end (no hook), 90 = all side roll; + hooks "
                        "LEFT, - hooks right; [-90, 90]",
            "scatter": {"board_sd": B.SIG["board"], "angle_sd_deg": B.SIG["angle_deg"],
                        "speed_sd": f"{B.SIG['speed_frac'] * 100:g} %", "rpm_sd": f"{B.SIG['rpm_frac'] * 100:g} %",
                        "axis_sd_deg": B.SIG["axis_deg"],
                        "note": "each executed value scatters (Gaussian) around what you asked for"}},
        "lane": {"length_foul_line_to_head_pin_m": B.HEAD_PIN_X, "width_m": B.LANE_W, "boards": B.N_BOARDS,
                 "board_width_m": round(B.BOARD_W, 5), "gutter_width_m": B.GUTTER_W, "pin_deck_end_m": B.PIT_X,
                 "pin_spacing_m": B.PIN_SPACING,
                 "markings": "foul line at x = 0; aiming arrows between 3.9 and 4.6 m on boards 5, 10, ..., 35 (the "
                             "centre arrow furthest); dots at 2.13 m",
                 "oil": "the front of the lane is oiled (the ball skids), the back end is dry (a spinning ball hooks, "
                        "then rolls); the oil runs further down the middle boards than the outside boards; the pattern "
                        "is not given",
                 "frame": "x along the lane from the foul line towards the pins, y across (+ = left), z up; lane "
                          "surface z = 0"},
        "ball": {"diameter_m": 2 * B.R_BALL, "mass_kg": B.M_BALL, "radius_of_gyration_m": B.RG_BALL},
        "pin": {"height_m": round(B.PIN_H, 4), "max_diameter_m": round(4.766 * B.IN, 4), "mass_kg": B.M_PIN},
        "cameras": B.spec_cameras(),
        "hearing": "after each ball you are told how many pins fell (not which ones)",
    }
