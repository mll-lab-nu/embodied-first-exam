"""American 8-ball (one rack) on pooltool 0.6.0: rack, shot simulation, rules, the scripted opponent.

Physics: pooltool's event-based solver (deterministic, float64) on its default 7-ft pocket table; every shot starts
from the resting positions. Shot facts (first ball hit, balls pocketed and their pockets, cushion contacts) come from
pooltool's events through the helpers of pooltool.ruleset.utils (the same ones pooltool's own eight_ball ruleset
uses). The rules are implemented here, not by pooltool.ruleset.eight_ball (which is tied to pooltool's own game loop).
They follow the WPA Rules of Play, effective 2025-09-15 (https://wpapool.com/wp-content/uploads/2025/09/2025.09.15-WPA-Rules.pdf):
section 4 (8-Ball), the fouls of section 3 and the general rules of section 1, with the deviations listed in the README
and the prompt.

A game is a pure function of the seed, who breaks and the sequence of decisions (deterministic replay, state_sha()).
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
import pooltool as pt
from pooltool.events import EventType
from pooltool.ruleset.utils import get_id_of_first_ball_hit

TABLE = pt.Table.default()           # 7-ft pocket table: playing surface 0.9906 x 1.9812 m
W, L = float(TABLE.w), float(TABLE.l)
R = 0.028575
HEAD_SPOT = (W / 2, L / 4)
FOOT_SPOT = (W / 2, 3 * L / 4)
HEAD_STRING_Y = L / 4                # the head string; "above the head string" (WPA 8.1): 0 < y < L/4, the line excluded
KITCHEN_SPOT = (W / 2, HEAD_STRING_Y - 0.05)   # default cue position with ball in hand above the head string
SOLIDS = tuple(str(i) for i in range(1, 8))
STRIPES = tuple(str(i) for i in range(9, 16))
OBJ_IDS = SOLIDS + ("8",) + STRIPES
GROUPS = {"solids": SOLIDS, "stripes": STRIPES}
OTHER_GROUP = {"solids": "stripes", "stripes": "solids"}
POCKETS = {k: np.array(p.center[:2], dtype=float) for k, p in TABLE.pockets.items()}
POCKET_IDS = tuple(sorted(POCKETS))
POCKET_NAMES = {"lb": "corner (x=0, y=0)", "lc": "side (x=0, y=L/2)", "lt": "corner (x=0, y=L)",
                "rb": "corner (x=W, y=0)", "rc": "side (x=W, y=L/2)", "rt": "corner (x=W, y=L)"}
# aim points a little inside each pocket's mouth (corner pockets: along the diagonal; side pockets: towards the table)
POCKET_AIM = {}
for _k in POCKETS:
    if _k in ("lc", "rc"):
        POCKET_AIM[_k] = np.array([-0.012 if _k == "lc" else W + 0.012, L / 2])
    else:
        _c = np.array([0.0 if _k[0] == "l" else W, 0.0 if _k[1] == "b" else L])
        POCKET_AIM[_k] = _c + 0.02 * np.array([1.0 if _k[0] == "l" else -1.0, 1.0 if _k[1] == "b" else -1.0]) / math.sqrt(2)

EXEC_SIGMA = {"phi_deg": 0.06, "speed_rel": 0.02, "spin": 0.01}     # every shot, both players
V_RANGE = (0.3, 7.0)
SPIN_MAX = 0.5
MAX_SHOTS = 60                       # per player; then the game is decided on the balls left (see _check_cap)
RACK_JITTER = 0.002                  # rack: each ball displaced by N(0, RACK_JITTER R), gaps of 1e-3 R
LEVELS = {   # the scripted opponent (single player)
    1: {"aim_sigma_deg": 0.5, "speed_err": 0.08, "breaks": "you", "select": "easiest"},
    2: {"aim_sigma_deg": 0.25, "speed_err": 0.04, "breaks": "opponent", "select": "safe"},
}


# ----------------------------------------------------------------------------- rack and physics
def rack(seed: int) -> dict:
    """Standard 8-ball triangle, apex ball on the foot spot, rows towards the foot rail; the 8 in the middle of the
    third row, one solid and one stripe in the back corners, the other balls shuffled by the seed; each ball jittered
    by N(0, RACK_JITTER R). The cue ball starts on the head spot."""
    rng = np.random.default_rng([int(seed), 8])
    d = 2 * R * (1 + 1e-3)
    slots = [(r, c) for r in range(5) for c in range(r + 1)]
    xy = {s: (FOOT_SPOT[0] + (s[1] - s[0] / 2) * d, FOOT_SPOT[1] + s[0] * d * math.sqrt(3) / 2) for s in slots}
    solids, stripes = list(SOLIDS), list(STRIPES)
    rng.shuffle(solids); rng.shuffle(stripes)
    corners = [solids.pop(), stripes.pop()]
    if rng.random() < 0.5:
        corners.reverse()
    rest = solids + stripes
    rng.shuffle(rest)
    order = {(2, 1): "8", (4, 0): corners[0], (4, 4): corners[1]}
    for s in slots:
        if s not in order:
            order[s] = rest.pop()
    pos = {"cue": KITCHEN_SPOT}
    for s in slots:
        x, y = xy[s]
        pos[order[s]] = (float(x + rng.normal(0, RACK_JITTER * R)), float(y + rng.normal(0, RACK_JITTER * R)))
    return pos


def simulate(pos: dict, phi: float, V: float, a: float, b: float, continuous: bool = False, head_check: bool = False):
    """One shot from resting positions. head_check: also report whether the cue ball crossed the head string (its
    centre reached y > L/4) before its first contact with a ball (WPA 3.11), from the continuized cue-ball path."""
    balls = {k: pt.Ball.create(k, xy=(float(v[0]), float(v[1]))) for k, v in pos.items()}
    s = pt.System(cue=pt.Cue(cue_ball_id="cue"), table=TABLE, balls=balls)
    s.cue.set_state(V0=float(V), phi=float(phi) % 360.0, theta=0.0, a=float(a), b=float(b))
    pt.simulate(s, inplace=True, max_events=20000)
    if continuous:
        pt.continuize(s, dt=1 / 30, inplace=True)
    first = get_id_of_first_ball_hit(s, cue="cue")
    t_first = None
    pocketed, pocket_of, cushion_balls, cushion_after_first = [], {}, set(), False
    for e in s.events:
        if e.event_type == EventType.BALL_BALL and t_first is None and "cue" in e.ids:
            t_first = e.time
        elif e.event_type == EventType.BALL_POCKET:
            bid = e.ids[0]
            if bid not in pocketed:
                pocketed.append(bid); pocket_of[bid] = e.ids[1]
        elif e.event_type in (EventType.BALL_LINEAR_CUSHION, EventType.BALL_CIRCULAR_CUSHION):
            cushion_balls.add(e.ids[0])
            if t_first is not None and e.time >= t_first:
                cushion_after_first = True
    new = {}
    for k, bl in s.balls.items():
        if k in pocketed:
            continue
        xy = bl.state.rvw[0][:2]
        if not (-0.05 < xy[0] < W + 0.05 and -0.05 < xy[1] < L + 0.05):   # off the table: counts as pocketed
            pocketed.append(k); pocket_of[k] = "off_table"; continue
        new[k] = (float(xy[0]), float(xy[1]))
    crossed = None
    if head_check:
        c = pt.continuize(s, dt=0.002, inplace=False)
        rvw, _st, ts = c.balls["cue"].history_cts.vectorize()
        until = t_first if t_first is not None else float(ts[-1]) if len(ts) else 0.0
        crossed = bool(np.any(rvw[(ts <= until), 0, 1] > HEAD_STRING_Y)) or float(pos["cue"][1]) > HEAD_STRING_Y
    return s, {"first_hit": first, "crossed_head_string": crossed, "pocketed": pocketed, "pocket_of": pocket_of, "positions": new,
               "object_balls_to_cushion": sorted(cushion_balls - {"cue"}), "cushion_after_first": cushion_after_first}


def spot_ball(pos: dict) -> tuple:
    """WPA 1.5: on the long string as close as possible to the foot spot, between the foot spot and the foot rail; if
    that is all blocked, above the foot spot (towards the head), as close as possible to it."""
    step = 2 * R + 1e-3
    for sgn in (1, -1):
        for k in range(int(L / step)):
            p = (W / 2, FOOT_SPOT[1] + sgn * k * step)
            if not (R < p[1] < L - R):
                break
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) > 2 * R + 1e-3 for q in pos.values()):
                return p
    return free_spot(pos, *FOOT_SPOT)


def free_spot(pos: dict, x: float, y: float, step: float = 0.03) -> tuple:
    """(x, y) or the nearest free point on the table's long centre line (towards the head rail first)."""
    for k in range(80):
        for sgn in ((1,) if k == 0 else (-1, 1)):
            p = (x if k == 0 else W / 2, y + sgn * k * step)
            if R < p[1] < L - R and all(math.hypot(p[0] - q[0], p[1] - q[1]) > 2 * R + 1e-3 for q in pos.values()):
                return p
    return (W / 2, 0.1)


def kitchen_spot(pos: dict) -> tuple:
    """A free point above the head string: KITCHEN_SPOT or the nearest free point across the table (then nearer the
    head rail)."""
    for dy in (0.0, -0.06, -0.12, -0.2):
        for k in range(30):
            for sgn in ((1,) if k == 0 else (-1, 1)):
                p = (KITCHEN_SPOT[0] + sgn * k * 0.03, KITCHEN_SPOT[1] + dy)
                if placement_error(pos, p, True) is None:
                    return p
    return (W / 2, 0.1)


def placement_error(pos: dict, xy, kitchen: bool) -> str | None:
    x, y = float(xy[0]), float(xy[1])
    if not (math.isfinite(x) and math.isfinite(y)):
        return "cue_x, cue_y must be finite"
    if not (R <= x <= W - R and R <= y <= L - R):
        return f"the cue ball must lie on the table: {R:.4f} <= x <= {W - R:.4f}, {R:.4f} <= y <= {L - R:.4f}"
    if kitchen and y >= HEAD_STRING_Y:
        return (f"the cue ball is in hand above the head string: place it at y < {HEAD_STRING_Y:.4f} "
                "(the head string itself is not part of that area; WPA 3.10)")
    for k, q in pos.items():
        if k != "cue" and math.hypot(x - q[0], y - q[1]) < 2 * R + 1e-4:
            return f"the cue ball would overlap ball {k}"
    for k, c in POCKETS.items():
        if math.hypot(x - c[0], y - c[1]) < float(TABLE.pockets[k].radius) + R:
            return "the cue ball would lie in a pocket opening"
    return None


def parse_call(call):
    """'safety' or 'BALL:POCKET' -> 'safety' / (ball, pocket); None if malformed."""
    if not isinstance(call, str):
        return None
    c = call.strip().lower()
    if c == "safety":
        return "safety"
    if ":" not in c:
        return None
    ball, pocket = (x.strip() for x in c.split(":", 1))
    if ball not in OBJ_IDS or pocket not in POCKET_IDS:
        return None
    return ball, pocket


# ----------------------------------------------------------------------------- the game
class Game:
    """One rack between players 0 and 1. `breaker` breaks with ball in hand above the head string."""

    def __init__(self, seed: int, breaker: int, keep_systems: bool = False):
        self.seed, self.breaker = int(seed), int(breaker)
        self.pos = rack(self.seed)
        self.group = {0: None, 1: None}           # "solids" / "stripes" once assigned
        self.turn = self.breaker
        self.ball_in_hand = "kitchen"             # None, "kitchen" (above the head string: the break, a break scratch)
                                                  # or "anywhere" (after any other foul)
        self.break_done = False
        self.k = 0
        self.n_shots = {0: 0, 1: 0}
        self.shots: list[dict] = []
        self.decisions: list[dict] = []
        self.done = False
        self.winner = None                        # 0 / 1, None for a draw (or not over)
        self.result = None                        # why it ended
        self.keep_systems = keep_systems
        self.systems: list = []

    # --- what a player may hit
    def objects_left(self) -> list[str]:
        return [b for b in OBJ_IDS if b in self.pos]

    def left_in_group(self, p: int) -> list[str]:
        g = self.group[p]
        return [] if g is None else [b for b in GROUPS[g] if b in self.pos]

    def on_eight(self, p: int) -> bool:
        return self.group[p] is not None and not self.left_in_group(p)

    def a_group_cleared(self) -> bool:
        return any(all(b not in self.pos for b in GROUPS[g]) for g in GROUPS)

    def targets(self, p: int) -> list[str]:
        """The balls p may hit first (and call). WPA 4.4: on an open table any object ball but the 8, unless a group
        has been completely pocketed: then the shooter may claim it and shoot the 8."""
        if not self.break_done or self.group[p] is None:
            balls = [b for b in self.objects_left() if b != "8"]
            if self.break_done and self.a_group_cleared() and "8" in self.pos:
                balls.append("8")
            return balls
        return ["8"] if self.on_eight(p) else self.left_in_group(p)

    def group_name(self, p: int) -> str:
        if self.group[p] is None:
            return "open" + (" (a group is cleared: you may shoot the 8)" if self.break_done and self.a_group_cleared() else "")
        return self.group[p] + (" (on the 8)" if self.on_eight(p) else "")

    def must_call(self, p: int) -> bool:
        """Every shot after the break is called (a ball and a pocket, or safety)."""
        return self.break_done

    def on_the_8(self, p: int) -> bool:
        """p may legally shoot the 8 now (its group cleared, or WPA 4.4's claim on an open table)."""
        return self.break_done and "8" in self.targets(p)

    # --- a shot
    def check(self, p: int, dec: dict) -> str | None:
        """Why the decision is not allowed now (None: fine). Never changes the state."""
        if self.done or p != self.turn:
            return "it is not your turn"
        has_cue = dec.get("cue_xy") is not None
        if has_cue and self.ball_in_hand is None:
            return "you do not have ball in hand: leave out cue_x / cue_y"
        if has_cue:
            e = placement_error({k: v for k, v in self.pos.items() if k != "cue"}, dec["cue_xy"],
                                self.ball_in_hand == "kitchen")
            if e:
                return e
        call = dec.get("call")
        if not self.break_done:
            if call is not None:
                return "the break is not called: leave out call"
            return None
        if call is None:
            return ("every shot after the break is called: call=BALL:POCKET (pockets "
                    f"{', '.join(POCKET_IDS)}) or call=safety")
        c = parse_call(call)
        if c is None:
            return f"call must be BALL:POCKET (a ball number and one of {', '.join(POCKET_IDS)}) or safety"
        if c != "safety":
            ball, pocket = c
            if ball not in self.pos or ball == "cue":
                return f"ball {ball} is not on the table"
            if ball not in self.targets(p):
                return (f"you may not call ball {ball}: call one of your balls "
                        f"({', '.join(self.targets(p))})" + (" or safety" if ball != "8" else ""))
        return None

    def shoot(self, p: int, dec: dict) -> dict:
        err = self.check(p, dec)
        assert err is None, err
        self.decisions.append(dict(dec, player=p))
        self.n_shots[p] += 1
        placed = None
        if self.ball_in_hand:
            others = {k: v for k, v in self.pos.items() if k != "cue"}
            placed = tuple(dec["cue_xy"]) if dec.get("cue_xy") is not None else (
                self.pos["cue"] if "cue" in self.pos and placement_error(others, self.pos["cue"], self.ball_in_hand == "kitchen") is None
                else (kitchen_spot(others) if self.ball_in_hand == "kitchen" else free_spot(others, *HEAD_SPOT)))
            self.pos = dict(others, cue=(float(placed[0]), float(placed[1])))
        was_break = not self.break_done
        targets = self.targets(p)
        on8 = self.on_the_8(p)
        call = None if was_break else parse_call(dec["call"])
        called = None if call in (None, "safety") else call          # (ball, pocket)
        rng = np.random.default_rng([self.seed, 7919, self.k])
        S = EXEC_SIGMA
        ap = (dec["aim_deg"] + rng.normal(0.0, S["phi_deg"])) % 360.0
        aV = float(np.clip(dec["speed"] * (1.0 + rng.normal(0.0, S["speed_rel"])), *V_RANGE))
        aa = float(np.clip(dec["spin_x"] + rng.normal(0.0, S["spin"]), -SPIN_MAX, SPIN_MAX))
        ab = float(np.clip(dec["spin_y"] + rng.normal(0.0, S["spin"]), -SPIN_MAX, SPIN_MAX))
        pos0 = dict(self.pos)
        from_kitchen = self.ball_in_hand == "kitchen" and not was_break     # WPA 3.11 (the break has no such rule)
        s, out = simulate(self.pos, ap, aV, aa, ab, continuous=self.keep_systems, head_check=from_kitchen)
        if self.keep_systems:
            self.systems.append((self.k, p, pos0, s))
        off = [x for x in out["pocketed"] if x != "cue" and out["pocket_of"][x] == "off_table"]
        potted = [x for x in out["pocketed"] if x != "cue" and x not in off]
        scratch = "cue" in out["pocketed"]
        # --- fouls (WPA 3.1-3.3, 3.5, 3.11; the break 4.3)
        foul = None
        illegal_break = was_break and not potted and len(out["object_balls_to_cushion"]) < 4
        if scratch:
            foul = "cue ball pocketed"
        elif off:
            foul = "object ball driven off the table"
        elif was_break:
            if illegal_break:
                foul = "illegal break: no ball potted and fewer than 4 object balls reached a cushion"
        elif out["first_hit"] is None:
            foul = "no ball hit"
        elif out["first_hit"] not in targets:
            foul = f"the first ball hit ({out['first_hit']}) is not one of yours"
        elif from_kitchen and pos0[out["first_hit"]][1] < HEAD_STRING_Y and not out["crossed_head_string"]:
            foul = ("bad play from above the head string: the first ball hit lay above the head string and the cue "
                    "ball had not crossed the head string before that contact")
        elif not potted and not out["cushion_after_first"]:
            foul = "no ball reached a cushion after the first contact and none was potted"
        newpos = dict(out["positions"])
        result, winner = None, None
        respotted_8 = False
        if was_break and ("8" in potted or "8" in off):    # 4.3(e)-(g): the 8 on the break is spotted, play goes on
            newpos["8"] = spot_ball({k: v for k, v in newpos.items() if k != "8"})
            potted = [x for x in potted if x != "8"]; off = [x for x in off if x != "8"]; respotted_8 = True
        if "8" in off:                                     # 4.8(d)
            winner, result = 1 - p, "8 driven off the table"
        elif "8" in potted:
            if foul or not on8:
                winner, result = 1 - p, ("8 potted on a foul" if foul else "8 potted before clearing the group")
            elif called is None or called[0] != "8" or out["pocket_of"]["8"] != called[1]:
                winner, result = 1 - p, "8 potted in a pocket that was not called"
            else:
                winner, result = p, "8 potted legally in the called pocket"
        # the call is made iff the called ball went legally into the called pocket (WPA 4.5, 4.6)
        made = bool(called and not foul and out["pocket_of"].get(called[0]) == called[1])
        assigned = None
        if result is None and made and self.group[p] is None and called[0] != "8":   # open table: WPA 4.4
            g = "solids" if called[0] in SOLIDS else "stripes"
            self.group[p], self.group[1 - p] = g, OTHER_GROUP[g]
            assigned = g
        self.pos = newpos
        if result is not None:
            self.done, self.winner, self.result = True, winner, result
            keep = False
        else:
            # 4.3(c): a ball pocketed on a legal break (the 8 included, spotted again) keeps the breaker at the table
            keep = (not foul and (bool(potted) or respotted_8)) if was_break else made
        rerack = False
        if not self.done:
            if was_break and illegal_break:
                # 4.3(d)(2): the incoming player re-racks (the same rack: the seed) and breaks
                self.pos = rack(self.seed)
                self.ball_in_hand, rerack = "kitchen", True
            elif foul:
                # 4.3(g)(2)/(h)(2): a foul on the break: ball in hand above the head string; 4.9: otherwise anywhere
                self.ball_in_hand = "kitchen" if was_break else "anywhere"
                if scratch:
                    self.pos.pop("cue", None)
            else:
                self.ball_in_hand = None
            self.turn = p if keep else 1 - p
        if not rerack:
            self.break_done = True
        rec = {"k": self.k, "player": p, "break": was_break,
               "requested": {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in dec.items()},
               "cue_placed_at": None if placed is None else [round(placed[0], 4), round(placed[1], 4)],
               "first_hit": out["first_hit"], "potted": potted + (["8"] if respotted_8 else []),
               "pockets": {x: out["pocket_of"][x] for x in out["pocketed"] if x != "cue"},
               "cue_ball_pocketed": scratch, "off_table": off, "foul": foul, "eight_respotted": respotted_8,
               "rerack": rerack,
               "call": None if was_break else ("safety" if call == "safety" else f"{called[0]}:{called[1]}"),
               "call_made": made, "group_assigned": assigned, "keeps_turn": bool(keep) and not self.done,
               "object_balls_to_cushion": len(out["object_balls_to_cushion"]),
               "game_over": self.done, "result": result}
        self.shots.append(rec)
        self.k += 1
        if not self.done:
            self._check_cap()
        return rec

    def _check_cap(self) -> None:
        if all(self.n_shots[q] >= MAX_SHOTS for q in (0, 1)):
            left = {q: (len(self.left_in_group(q)) if self.group[q] else 7) for q in (0, 1)}
            self.done = True
            self.winner = None if left[0] == left[1] else (0 if left[0] < left[1] else 1)
            self.result = f"shot limit: balls left in own group {left[0]} - {left[1]}"
            # a tie at the cap (winner None) is decided by the chess clocks: the service calls resolve_tiebreak()
        elif self.n_shots[self.turn] >= MAX_SHOTS:          # out of shots: the turn passes (ball in hand stays)
            self.turn = 1 - self.turn

    def resolve_tiebreak(self, winner: int, clock_left_s) -> None:
        """The last-resort rule for a tie at the shot limit: the player with more chess-clock time left wins (the
        service supplies the clocks; they are recorded in the trajectory and applied again on replay)."""
        assert self.done and self.winner is None
        self.winner = int(winner)
        self.tiebreak = {"winner": int(winner), "clock_left_s": [float(c) for c in clock_left_s]}
        self.result += f"; tie broken by chess-clock time left ({clock_left_s[0]:.1f} s - {clock_left_s[1]:.1f} s)"

    def state_sha(self) -> str:
        h = hashlib.sha256()
        for k in sorted(self.pos):
            h.update(k.encode()); h.update(np.array(self.pos[k], dtype=np.float64).tobytes())
        h.update(repr((self.group[0], self.group[1], self.turn, self.ball_in_hand, self.break_done, self.k,
                       self.n_shots[0], self.n_shots[1], self.done, self.winner, self.result)).encode())
        return h.hexdigest()


# ----------------------------------------------------------------------------- shot planning (geometry only)
def _seg_dist(p, a, b) -> float:
    ab = b - a
    t = float(np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def scratch_risk(ghost, d, u) -> bool:
    t = d - np.dot(d, u) * u
    dirs = [d] if np.linalg.norm(t) < 0.03 else [t / np.linalg.norm(t), (t / np.linalg.norm(t) + 0.5 * d)]
    for e in dirs:
        e = e / np.linalg.norm(e)
        for c in POCKET_AIM.values():
            w = c - ghost
            along = float(np.dot(w, e))
            if 0.0 < along < 1.3 and abs(float(e[0] * w[1] - e[1] * w[0])) < 0.07:
                return True
    return False


def pot_options(cue, balls: dict, targets, margin: float = 0.005, avoid_scratch: bool = False) -> list[dict]:
    """Direct ghost-ball pots of any target ball, easiest first; blocked paths removed.
    balls: id -> (x, y) of the object balls on the table; targets: the ids that may be hit first."""
    cue = np.asarray(cue, dtype=float)
    obs = {k: np.asarray(v, dtype=float) for k, v in balls.items()}
    opts = []
    for bid in targets:
        if bid not in obs:
            continue
        ob = obs[bid]
        for pk, tgt in POCKET_AIM.items():
            d2v = tgt - ob; d2 = float(np.linalg.norm(d2v)); u = d2v / d2
            ghost = ob - 2 * R * u
            d1v = ghost - cue; d1 = float(np.linalg.norm(d1v))
            if d1 < 1e-6:
                continue
            cosc = float(np.dot(d1v / d1, u))
            if cosc < math.cos(math.radians(70)):
                continue
            if pk in ("lc", "rc") and (abs(u[0]) < math.cos(math.radians(45)) or (u[0] > 0) != (pk == "rc")):
                continue
            if any(_seg_dist(q, cue, ghost) < 2 * R + margin or _seg_dist(q, ob, tgt) < 2 * R + margin
                   for oid, q in obs.items() if oid != bid):
                continue
            diff = (d1 + 1.6 * d2) / max(cosc, 0.2) ** 1.5
            if avoid_scratch and scratch_risk(ghost, d1v / d1, u):
                diff += 10.0
            V = float(np.clip(0.9 + 0.55 * d1 + 0.9 * d2 / max(cosc, 0.35), 1.0, 4.5))
            opts.append({"ball": bid, "pocket": pk, "phi": math.degrees(math.atan2(d1v[1], d1v[0])) % 360.0, "V": V,
                         "cut_deg": math.degrees(math.acos(min(1.0, cosc))), "difficulty": diff})
    opts.sort(key=lambda o: o["difficulty"])
    return opts


def place_for_pot(balls: dict, targets, kitchen: bool = False):
    """Ball in hand: a cue position for a straight pot of a target ball, (xy, option) or None."""
    best = None
    for bid in targets:
        if bid not in balls:
            continue
        ob = np.asarray(balls[bid], dtype=float)
        for pk, tgt in POCKET_AIM.items():
            u = (tgt - ob) / np.linalg.norm(tgt - ob)
            for back in (0.25, 0.4, 0.15, 0.6):
                xy = ob - (2 * R + back) * u
                if placement_error(balls, xy, kitchen):
                    continue
                opts = [o for o in pot_options(xy, balls, [bid]) if o["pocket"] == pk]
                if opts and (best is None or opts[0]["difficulty"] < best[1]["difficulty"]):
                    best = ((float(xy[0]), float(xy[1])), opts[0])
                break
    return best


def safety(cue, balls: dict, targets) -> dict:
    """No pot: a firm, full hit on the nearest target ball with a clear path (so that a cushion is reached)."""
    cue = np.asarray(cue, dtype=float)
    obs = {k: np.asarray(v, dtype=float) for k, v in balls.items()}
    order = sorted((t for t in targets if t in obs), key=lambda t: float(np.linalg.norm(obs[t] - cue)))
    pick = None
    for t in order:
        if all(_seg_dist(q, cue, obs[t]) >= 2 * R + 0.002 for oid, q in obs.items() if oid != t):
            pick = t; break
    pick = pick or (order[0] if order else None)
    if pick is None:
        return {"phi": 90.0, "V": 2.0, "plan": "no target"}
    d = obs[pick] - cue
    return {"phi": math.degrees(math.atan2(d[1], d[0])) % 360.0, "V": 2.2, "plan": f"safety on {pick}", "ball": pick}


def opponent_decision(g: Game, p: int, level: int, rng: np.random.Generator) -> dict:
    """The scripted opponent's decision for player p: the break; with ball in hand a cue position for a straight pot;
    the easiest legal pot, called (ball and pocket); with no pot, a firm hit on its nearest ball. Level 1 then still
    calls that ball into the pocket nearest to it; level 2 calls safety, avoids shots whose cue ball heads for a pocket,
    and also plays safe when its best pot is a hard one."""
    lv = LEVELS[level]
    balls = {k: v for k, v in g.pos.items() if k != "cue"}
    targets = g.targets(p)
    dec = {"type": "shoot", "spin_x": 0.0, "spin_y": 0.0}
    cue = g.pos.get("cue")
    if not g.break_done:
        apex = min(balls.items(), key=lambda kv: kv[1][1])[1]
        cue = (W / 2 + float(rng.normal(0.0, 0.01)), KITCHEN_SPOT[1])
        d = np.asarray(apex) - np.asarray(cue)
        dec.update(cue_xy=cue, aim_deg=math.degrees(math.atan2(d[1], d[0])) % 360.0 + float(rng.normal(0, lv["aim_sigma_deg"])),
                   speed=6.0)
        return dec
    kitchen = g.ball_in_hand == "kitchen"
    if kitchen:                    # WPA 3.11: only balls on or below the head string may be hit first directly
        reachable = [t for t in targets if balls[t][1] >= HEAD_STRING_Y]
        if not reachable:          # all its balls lie above the head string: go down the table and back
            cue = kitchen_spot(balls)
            dec.update(cue_xy=cue, aim_deg=(90.0 + float(rng.normal(0.0, lv["aim_sigma_deg"]))) % 360.0, speed=2.6,
                       call="safety")
            return dec
        targets = reachable
    if g.ball_in_hand:
        pl = place_for_pot(balls, targets, kitchen=kitchen)
        if pl is not None:
            cue = pl[0]
            dec["cue_xy"] = cue
        elif cue is None or placement_error(balls, cue, kitchen):
            cue = kitchen_spot(balls) if kitchen else free_spot(balls, *HEAD_SPOT)
            dec["cue_xy"] = cue
    safe = lv["select"] == "safe"
    opts = pot_options(cue, balls, targets, avoid_scratch=safe)
    if opts and not (safe and opts[0]["difficulty"] > 9.0):
        o = opts[0]
        phi, V = o["phi"], o["V"]
        dec["call"] = f"{o['ball']}:{o['pocket']}"
    else:
        sf = safety(cue, balls, targets)
        phi, V = sf["phi"], sf["V"]
        b = sf.get("ball") or (targets[0] if targets else "8")
        near = min(POCKET_AIM, key=lambda k: float(np.linalg.norm(POCKET_AIM[k] - np.asarray(balls.get(b, (W / 2, L / 2))))))
        dec["call"] = "safety" if safe else f"{b}:{near}"
    dec["aim_deg"] = (phi + float(rng.normal(0.0, lv["aim_sigma_deg"]))) % 360.0
    dec["speed"] = float(np.clip(V * (1.0 + rng.normal(0.0, lv["speed_err"])), *V_RANGE))
    return dec


# ----------------------------------------------------------------------------- single player: the match
class Match:
    """The player (0) against the scripted opponent (1) of a level: one rack. Lock-step: after the player's shot (and
    review) the opponent plays its turn in `follow()`. If the opponent breaks, it does so at construction."""

    def __init__(self, level: int, seed: int, keep_systems: bool = False):
        self.level, self.seed = int(level), int(seed)
        lv = LEVELS[self.level]
        self.g = Game(self.seed, 0 if lv["breaks"] == "you" else 1, keep_systems=keep_systems)
        self.opening = self.follow()

    def follow(self) -> list[dict]:
        recs = []
        while not self.g.done and self.g.turn == 1:
            d = opponent_decision(self.g, 1, self.level, np.random.default_rng([self.seed, 104729, self.g.k]))
            recs.append(self.g.shoot(1, d))
        return recs

    def shot(self, dec: dict) -> dict:
        return self.g.shoot(0, dec)

    def state_sha(self) -> str:
        return self.g.state_sha()
