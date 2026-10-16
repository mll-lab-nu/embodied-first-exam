"""American 8-ball (one rack) on pooltool 0.6.0: rack, shot simulation, rules, the scripted opponent (levels 1-3).

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
LEVELS = {   # the scripted opponent (single player); who breaks is the seed's coin toss (plugin.breaker), not the level.
    # billiards-3: every level plays plan_decision (safeties, ball in hand, defence of the 8); level 1 plays no
    # position (it takes the plain stroke of its best pot, never minding where the cue ball stops), levels 2 and 3 do;
    # level 3 aims more precisely and searches its safeties more widely (WIDE). billiards-2's levels 1 and 2 ("easiest"
    # / "safe": the easiest direct pot, a firm hit when there is none) lost most racks to the greedy player and are no
    # longer levels (the code paths stay, unused). A larger aiming error lets the greedy player win (about 0.3 degrees).
    # After the step-5 fixes (every stroke judged by the rules and its own scatter) level 1 at 0.2 degrees lost about
    # half its racks to the greedy player reading the true positions (52 %, 200 racks); at 0.15 degrees 38.5 %.
    1: {"aim_sigma_deg": 0.15, "speed_err": 0.03, "select": "plan", "search": "base", "position": False},
    2: {"aim_sigma_deg": 0.2, "speed_err": 0.03, "select": "plan", "search": "base"},
    3: {"aim_sigma_deg": 0.1, "speed_err": 0.03, "select": "plan", "search": "wide"},
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

    def void_shot(self, p: int, dec: dict, why: str) -> dict:
        """Deviation D10: a shot the physics engine cannot resolve even with the aim nudged (plugin.guard_engine) is
        void: nothing moves (a requested cue placement is undone too), no foul, the same player shoots again with
        the same ball in hand. The shot number advances (the next attempt gets a new execution draw, so the same
        command is not the same shot), the player's shot count does not. Deterministic: the replay voids it too."""
        err = self.check(p, dec)
        assert err is None, err
        self.decisions.append(dict(dec, player=p, void=True))
        c = None if not self.break_done else parse_call(dec.get("call"))
        rec = {"k": self.k, "player": p, "break": not self.break_done, "void": why,
               "requested": {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in dec.items()},
               "cue_placed_at": None, "first_hit": None, "potted": [], "pockets": {}, "cue_ball_pocketed": False,
               "off_table": [], "foul": None, "eight_respotted": False, "rerack": False,
               "call": None if c is None else ("safety" if c == "safety" else f"{c[0]}:{c[1]}"), "call_made": False,
               "group_assigned": None, "keeps_turn": True, "object_balls_to_cushion": 0, "game_over": False,
               "result": None}
        self.shots.append(rec)
        self.k += 1
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
                         "cut_deg": math.degrees(math.acos(min(1.0, cosc))), "difficulty": diff, "d1": d1, "d2": d2})
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


# ----------------------------------------------------------------------------- levels 1-3: a planning opponent
# The planning opponent (every level since billiards-3) looks ahead with the physics itself: every candidate stroke is
# simulated (simulate(), noise-free, from the current resting positions; never Game.shoot, which would change the game)
# and judged by the table it leaves. It plays position (the pot whose cue ball stops where its next pot is easiest),
# real safeties (the legal hit that leaves the other player the hardest best pot), clears from ball in hand (the
# placement and stroke with the best pot and leave) and defends when the other player is on the 8 (it pots only
# near-certain balls, else plays safe). Every stroke it plays is judged by the rules (verdict(): a legal hit, a foul,
# the 8 lost) at its own execution scatter as well (risk(): the stroke again with the aim and speed off by one and two
# sigma of its aiming error and the declared execution scatter); when it has neither a pot nor a safety on a clear
# path it searches every direction for a legal kick (kick_safety()) and, if there is none, the least bad foul (never
# one that loses the rack when another does not).
EXEC_AIM_DEG = EXEC_SIGMA["phi_deg"]
POCKET_TOL = {"lb": 0.028, "rb": 0.028, "lt": 0.028, "rt": 0.028, "lc": 0.022, "rc": 0.022}   # metres, see pot_prob
PLAN_STROKES = ((1.0, 0.0), (0.7, 0.0), (1.4, 0.0), (1.0, -0.35), (1.0, 0.35), (1.4, -0.35), (0.7, 0.35))
PLAN = {"pots": 3, "places": 4, "place_strokes": 4, "safety_balls": 3, "safety_cuts": (-0.8, -0.4, 0.0, 0.4, 0.8),
        "safety_speeds": (0.8, 1.6), "gamma": 0.7, "pot_min": 0.55, "pot_min_defend": 0.8}
WIDE = {"safety_cuts": (-0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9), "safety_speeds": (0.6, 1.0, 1.6), "robust": 6,
        "perturb_deg": 0.3}                       # the safety search of the stronger levels (search = "wide")
# The execution risk of a stroke (risk()): (aim offset, speed offset) in units of the opponent's own sigmas (its aiming
# error and the execution scatter combined) and the weight of each point (about the normal mass of a half-sigma bin
# around each aim offset; two points vary the speed alone); the cost of an outcome: the rack lost (as much as a won
# rack is worth, 10, see _judge_pot) or a foul (ball in hand for the other player). Billiards is chaotic at this scale
# (a few hundredths of a degree turn a pot into a scratch), so this lowers the risk but cannot remove it.
RISK_POINTS = ((0.5, 1.0, 0.175), (-0.5, -1.0, 0.175), (1.0, -1.0, 0.121), (-1.0, 1.0, 0.121), (1.5, 1.0, 0.066),
               (-1.5, -1.0, 0.066), (2.0, -1.0, 0.028), (-2.0, 1.0, 0.028), (0.0, 1.5, 0.06), (0.0, -1.5, 0.06))
RISK_COST = {"lose": 10.0, "foul": 0.6}
RISK_CHECKS = 4                                   # strokes checked per choice, best noise-free value first
SAFETY_FLOOR = -0.25                              # a safety whose value net of its risk is lower: the kick search instead
KICK = {"step_deg": 1.0, "speed": 1.5, "speeds": (1.0, 2.2), "top": 6, "robust": 12}   # kick_safety's sweep


def pot_prob(o: dict, sigma_deg: float) -> float:
    """Chance that a direct pot option (pot_options) goes in, from geometry alone: an aim error e of the cue ball turns
    the object ball by about e d1 / (2R cos(cut)); the object ball must stay within POCKET_TOL of the pocket's aim
    point after rolling d2 (a floor of 0.004 rad for throw and the speed error)."""
    cosc = max(math.cos(math.radians(o["cut_deg"])), 0.2)
    s_ob = math.radians(sigma_deg) * o["d1"] / (2 * R * cosc) + 0.004
    tol = POCKET_TOL[o["pocket"]] / max(o["d2"], 0.05)
    return float(math.erf(tol / (math.sqrt(2.0) * s_ob)))


def best_pot_prob(cue, balls: dict, targets, sigma_deg: float) -> float:
    if cue is None or not targets:
        return 0.0
    opts = pot_options(cue, balls, targets, avoid_scratch=True)[:6]
    return max((pot_prob(o, sigma_deg) for o in opts), default=0.0)


def _sim(pos: dict, phi: float, V: float, b: float):
    try:
        return simulate(pos, phi, float(np.clip(V, *V_RANGE)), 0.0, b)[1]
    except Exception:  # noqa: BLE001  (an engine failure: the stroke is not considered)
        return None


def _next_targets(g: Game, p: int, ball: str, newpos: dict):
    """p's targets after legally potting `ball` (None: the 8, the game is won)."""
    if ball == "8":
        return None
    grp = g.group[p] or ("solids" if ball in SOLIDS else "stripes")
    left = [b for b in GROUPS[grp] if b in newpos]
    return left if left else (["8"] if "8" in newpos else [])


def _opp_targets(g: Game, p: int, newpos: dict):
    q = 1 - p
    if g.group[q] is None:
        return [b for b in newpos if b not in ("cue", "8")]
    left = [b for b in GROUPS[g.group[q]] if b in newpos]
    return left if left else (["8"] if "8" in newpos else [])


def verdict(g: Game, p: int, out, call=None, targets=None, pos0=None) -> str:
    """How Game.shoot's rules would judge a simulated outcome (not the break): "lose" (the 8 down or off the table when
    that loses the rack), "win" (the 8 legally in the called pocket), "foul" (scratch, a ball off the table, no ball or
    a wrong ball hit first, no cushion after the contact and nothing down; with pos0 given and the cue ball in hand
    above the head string, the head-string rule of WPA 3.11 too) or "ok". out: simulate()'s outcome (None: the engine
    failed, counted as a foul); call: (ball, pocket) or None (safety); targets: the balls p may hit first (default
    g.targets(p))."""
    if out is None:
        return "foul"
    pk = out["pocket_of"]
    targets = g.targets(p) if targets is None else targets
    off = [x for x in out["pocketed"] if x != "cue" and pk.get(x) == "off_table"]
    potted = [x for x in out["pocketed"] if x != "cue" and x not in off]
    first = out["first_hit"]
    foul = ("cue" in out["pocketed"] or bool(off) or first is None or first not in targets
            or (not potted and not out["cushion_after_first"]))
    if not foul and pos0 is not None and out.get("crossed_head_string") is not None:
        foul = pos0[first][1] < HEAD_STRING_Y and not out["crossed_head_string"]
    if "8" in off:
        return "lose"
    if "8" in potted:
        ok8 = not foul and g.on_the_8(p) and call is not None and call[0] == "8" and pk["8"] == call[1]
        return "win" if ok8 else "lose"
    return "foul" if foul else "ok"


def _sigmas(lv: dict | None) -> tuple:
    """The opponent's own execution sigmas: aim (degrees) and relative speed, its error and the declared scatter."""
    lv = lv or {}
    return (math.hypot(lv.get("aim_sigma_deg", 0.2), EXEC_AIM_DEG),
            math.hypot(lv.get("speed_err", 0.03), EXEC_SIGMA["speed_rel"]))


def risk(g: Game, p: int, pos: dict, dec: dict, lv: dict | None, targets=None) -> float:
    """The expected cost of the stroke's execution scatter: the stroke simulated again at the RISK_POINTS (aim and
    speed off by up to two of the opponent's own sigmas), each outcome judged by verdict(); a lost rack costs
    RISK_COST["lose"] (as much as the won rack is worth), a foul RISK_COST["foul"], weighted by the points'
    weights."""
    sa, sv = _sigmas(lv)
    c = parse_call(dec.get("call"))
    call = None if c in (None, "safety") else c
    cost = 0.0
    for ka, kv, w in RISK_POINTS:
        out = _sim(pos, dec["aim_deg"] + ka * sa, dec["speed"] * (1.0 + kv * sv), dec.get("spin_y", 0.0))
        v = verdict(g, p, out, call, targets)
        cost += w * RISK_COST.get(v, 0.0)
    return cost


def _robust(g: Game, p: int, pos: dict, cands: list, lv: dict | None, targets=None, limit: int = RISK_CHECKS):
    """The best of (value, ..., dec) candidates after risk(): best noise-free value first, at most `limit` checked,
    stopping once no unchecked candidate can beat the best adjusted value (risk only lowers a value)."""
    best = None
    for c in sorted(cands, key=lambda r: -r[0])[:limit]:
        if best is not None and c[0] <= best[0]:
            break
        adj = c[0] - (risk(g, p, pos, c[-1], lv, targets) if c[0] > 0 else 0.0)
        if best is None or adj > best[0]:
            best = (adj,) + tuple(c[1:])
    return best


def _judge_pot(g, p, o, out, p0, sigma, gamma=None):
    """The value of a pot stroke from its noise-free outcome: p0 x (1 + gamma x the next pot's chance)."""
    if out is None:
        return -1.0
    pk = out["pocket_of"]
    if "cue" in out["pocketed"] or any(v == "off_table" for v in pk.values()):
        return -1.0
    if out["first_hit"] != o["ball"]:
        return 0.05 * p0
    if "8" in pk and o["ball"] != "8":
        return -1.0
    if pk.get(o["ball"]) != o["pocket"]:
        return 0.1 * p0
    newpos = {k: v for k, v in out["positions"].items() if k != "cue"}
    nxt = _next_targets(g, p, o["ball"], newpos)
    if nxt is None:
        return 10.0 * p0
    nq = best_pot_prob(out["positions"].get("cue"), newpos, nxt, sigma)
    return p0 * (1.0 + (PLAN["gamma"] if gamma is None else gamma) * nq)


def _plan_pots(g, p, cue, balls, targets, sigma, opts=None, lv=None, rng=None):
    """The best pot stroke from this cue position: (value, p0, decision fields) or None; the value net of the
    stroke's execution risk (risk(): the 8 lost or a foul at the opponent's own scatter). lv may weaken it: gamma (the
    weight of the leave), position=False (the plain stroke only; a shot at the 8 still tries every stroke, to keep the
    cue ball out of the pockets), mistake (the chance of taking the second-best ball and pocket instead of the best;
    drawn from rng)."""
    lv = lv or {}
    gamma = lv.get("gamma", PLAN["gamma"])
    pos = dict(balls, cue=tuple(cue))
    opts = opts if opts is not None else pot_options(cue, balls, targets, avoid_scratch=True)
    opts = sorted(opts, key=lambda o: -pot_prob(o, sigma))[:PLAN["pots"]]
    per, every = [], []                             # the best stroke of each ball and pocket; every stroke judged
    for o in opts:
        p0 = pot_prob(o, sigma)
        best = None
        eight = o["ball"] == "8"
        strokes = PLAN_STROKES if lv.get("position", True) or eight else PLAN_STROKES[:1]
        for k, (vm, b) in enumerate(strokes):
            u = _judge_pot(g, p, o, _sim(pos, o["phi"], o["V"] * vm, b), p0, sigma, gamma)
            r = (u, p0, {"aim_deg": o["phi"], "speed": float(np.clip(o["V"] * vm, *V_RANGE)), "spin_y": b,
                         "call": f"{o['ball']}:{o['pocket']}"})
            every.append(r)
            if best is None or u > best[0]:
                best = r
            if not eight and best[0] >= p0 * (1.0 + gamma):
                break
        per.append(best)
    if not per:
        return None
    per.sort(key=lambda r: -r[0])
    if lv.get("mistake", 0.0) > 0 and len(per) > 1 and per[1][0] > 0 and rng is not None \
            and float(rng.random()) < lv["mistake"]:
        return _robust(g, p, pos, [per[1]], lv, targets)
    return _robust(g, p, pos, every, lv, targets)


def _placements(balls: dict, targets, kitchen: bool, sigma: float) -> list:
    """Ball in hand: candidate cue positions behind each target ball for each pocket (straight and cut by 20 degrees,
    at three distances), the best few by the pot's chance (one per ball and pocket)."""
    cands = []
    for bid in targets:
        if bid not in balls:
            continue
        ob = np.asarray(balls[bid], dtype=float)
        for pk, tgt in POCKET_AIM.items():
            u = (tgt - ob) / np.linalg.norm(tgt - ob)
            best = None
            for ang in (0.0, 20.0, -20.0):
                c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                w = np.array([c * u[0] - s_ * u[1], s_ * u[0] + c * u[1]])
                for back in (0.2, 0.35, 0.12):
                    xy = ob - 2 * R * u - back * w
                    if placement_error(balls, xy, kitchen):
                        continue
                    opts = [o for o in pot_options(xy, balls, [bid], avoid_scratch=True) if o["pocket"] == pk]
                    if opts:
                        q = pot_prob(opts[0], sigma)
                        if best is None or q > best[0] + 1e-9:
                            best = (q, (float(xy[0]), float(xy[1])), opts[0])
            if best is not None:
                cands.append(best)
    cands.sort(key=lambda c: -c[0])
    return cands


def _leave_value(g, p, out, sigma):
    """1 - the other player's best pot chance from the table a stroke leaves."""
    newpos = {k: v for k, v in out["positions"].items() if k != "cue"}
    return 1.0 - best_pot_prob(out["positions"].get("cue"), newpos, _opp_targets(g, p, newpos), sigma)


def _safety_value(g, p, pos, t, phi, V, sigma):
    """1 - the other player's best pot chance after the safety stroke, or None if it is not legal (first hit not t, a
    scratch, a ball off the table, the 8 down, nothing down and no cushion after the first contact)."""
    out = _sim(pos, phi, V, 0.0)
    if out is None or out["first_hit"] != t or "cue" in out["pocketed"]:
        return None
    if any(v == "off_table" for v in out["pocket_of"].values()) or "8" in out["pocket_of"]:
        return None
    potted = [x for x in out["pocketed"] if x != "cue"]
    if not potted and not out["cushion_after_first"]:
        return None
    return _leave_value(g, p, out, sigma)


def _plan_safety(g, p, cue, balls, targets, sigma, wide: bool = False, lv=None):
    """The safety that leaves the other player the hardest best pot: hits on the nearest target balls with a clear
    path, full and cut, soft and firm; only legal outcomes (_safety_value). wide (level 3): more cuts and speeds
    (WIDE), and the best few judged again with the aim off by +-WIDE["perturb_deg"] (the worst counts, a foul -0.5).
    Then the best few net of their execution risk (risk()). (value, decision fields) or None."""
    cue = np.asarray(cue, dtype=float)
    pos = dict(balls, cue=(float(cue[0]), float(cue[1])))
    obs = {k: np.asarray(v, dtype=float) for k, v in balls.items()}
    order = sorted((t for t in targets if t in obs), key=lambda t: float(np.linalg.norm(obs[t] - cue)))
    clear = [t for t in order if all(_seg_dist(q, cue, obs[t]) >= 2 * R + 0.002 for oid, q in obs.items() if oid != t)]
    cuts, speeds = (WIDE["safety_cuts"], WIDE["safety_speeds"]) if wide else (PLAN["safety_cuts"], PLAN["safety_speeds"])
    cands = []
    for t in clear[:PLAN["safety_balls"]]:
        d = obs[t] - cue
        n = np.linalg.norm(d)
        perp = np.array([-d[1], d[0]]) / n
        for c in cuts:
            aim = obs[t] + c * 2 * R * perp - cue
            phi = math.degrees(math.atan2(aim[1], aim[0])) % 360.0
            for V in speeds:
                val = _safety_value(g, p, pos, t, phi, V, sigma)
                if val is not None:
                    cands.append((val, t, phi, V))
    if not cands:
        return None
    if wide:
        rob = []
        for val, t, phi, V in sorted(cands, key=lambda c: -c[0])[:WIDE["robust"]]:
            vals = [val] + [_safety_value(g, p, pos, t, phi + da, V, sigma) for da in (WIDE["perturb_deg"], -WIDE["perturb_deg"])]
            rob.append((min(-0.5 if x is None else x for x in vals), t, phi, V))
        cands = rob
    best = _robust(g, p, pos, [(val, {"aim_deg": phi, "speed": V, "spin_y": 0.0, "call": "safety"})
                                for val, t, phi, V in cands], lv, targets)
    return best


def kick_safety(g: Game, p: int, cue, balls: dict, targets, sigma: float, lv=None, kitchen: bool = False) -> dict:
    """No pot and no safety on a clear path (snookered): every direction (KICK["step_deg"]) at one speed, then the
    best legal ones at more speeds; the legal hit (verdict "ok") that leaves the other player the hardest best pot,
    net of its execution risk. With none legal, the least bad stroke: a foul that does not lose the rack (the one
    leaving the hardest pot), and only if every direction loses, the first one. Kicks are long and chaotic, so the
    risk of KICK["robust"] candidates is checked; if every checked legal kick still risks the rack (adjusted value
    below -1), the stroke with the lowest risk among the legal kicks and the fouls is played. kitchen: the cue ball in hand above
    the head string (the head-string rule of WPA 3.11 is judged too). Decision fields (call safety)."""
    pos = dict(balls, cue=(float(cue[0]), float(cue[1])))

    def run(phi, V):
        if kitchen:
            try:
                return simulate(pos, phi, float(np.clip(V, *V_RANGE)), 0.0, 0.0, head_check=True)[1]
            except Exception:  # noqa: BLE001
                return None
        return _sim(pos, phi, V, 0.0)

    seen = []
    for phi in np.arange(0.0, 360.0, KICK["step_deg"]):
        out = run(float(phi), KICK["speed"])
        v = verdict(g, p, out, None, targets, pos if kitchen else None)
        seen.append((v, float(phi), KICK["speed"], out))
    legal = [(_leave_value(g, p, o, sigma), phi, V) for v, phi, V, o in seen if v == "ok"]
    if legal:
        more = []
        for _, phi, _V in sorted(legal, key=lambda c: -c[0])[:KICK["top"]]:
            for V in KICK["speeds"]:
                out = run(phi, V)
                if verdict(g, p, out, None, targets, pos if kitchen else None) == "ok":
                    more.append((_leave_value(g, p, out, sigma), phi, V))
        cands = [(val, {"aim_deg": phi, "speed": V, "spin_y": 0.0, "call": "safety"}) for val, phi, V in legal + more]
        best = _robust(g, p, pos, cands, lv, targets, limit=KICK["robust"])
        if best[0] > -RISK_COST["lose"] * 0.1:          # else every checked kick risks the rack: the safest foul below
            return dict(best[-1], plan="kick safety (legal)")
    fouls = [(_leave_value(g, p, o, sigma) if o is not None else 0.0, phi, V) for v, phi, V, o in seen if v == "foul"]
    if legal:                                           # the legal kicks compete with the fouls on risk alone
        fouls += [(val - 1.0, phi, V) for val, phi, V in legal]
    if fouls:                                           # the least bad: the lowest risk (of losing the rack above all)
        ranked = sorted(fouls, key=lambda c: -c[0])[:KICK["robust"]]
        pick = min(ranked, key=lambda c: (risk(g, p, pos, {"aim_deg": c[1], "speed": c[2], "call": "safety"}, lv,
                                                targets), -c[0]))
        return {"aim_deg": pick[1], "speed": pick[2], "spin_y": 0.0, "call": "safety",
                "plan": "no safe legal hit: the least risky stroke"}
    return {"aim_deg": seen[0][1], "speed": KICK["speed"], "spin_y": 0.0, "call": "safety", "plan": "every hit loses"}


def _call_the_8(g: Game, p: int, pos: dict, dec: dict, lv: dict | None) -> str:
    """On the 8 a stroke called safety loses the rack if the 8 drops; called into a pocket it wins if it drops there
    and is otherwise the same miss. So a safety or kick of a player on the 8 calls the pocket the 8 most often
    reaches over the stroke and its RISK_POINTS (if it reaches none: the pocket nearest the 8)."""
    sa, sv = _sigmas(lv)
    hits: dict = {}
    for ka, kv, w in ((0.0, 0.0, 0.2),) + RISK_POINTS:
        out = _sim(pos, dec["aim_deg"] + ka * sa, dec["speed"] * (1.0 + kv * sv), dec.get("spin_y", 0.0))
        pk = None if out is None else out["pocket_of"].get("8")
        if pk and pk != "off_table":
            hits[pk] = hits.get(pk, 0.0) + w
    if hits:
        pk = max(sorted(hits), key=lambda k: hits[k])
    else:
        e = np.asarray(pos["8"], dtype=float)
        pk = min(POCKET_IDS, key=lambda k: float(np.linalg.norm(POCKETS[k] - e)))
    return f"8:{pk}"


def plan_decision(g: Game, p: int, lv: dict, rng: np.random.Generator) -> dict:
    """The planning opponent (levels 1-3; everything but the break, which opponent_decision plays)."""
    sigma = math.hypot(lv["aim_sigma_deg"], EXEC_AIM_DEG)
    balls = {k: v for k, v in g.pos.items() if k != "cue"}
    targets = g.targets(p)
    kitchen = g.ball_in_hand == "kitchen"
    if kitchen:
        targets = [t for t in targets if balls[t][1] >= HEAD_STRING_Y]
    cue = g.pos.get("cue")
    dec = {"type": "shoot", "spin_x": 0.0, "spin_y": 0.0}
    defend = lv.get("defend", True) and g.group[1 - p] is not None and g.on_eight(1 - p) and not g.on_eight(p)
    pot_min = PLAN["pot_min_defend"] if defend else lv.get("pot_min", PLAN["pot_min"])
    mode = lv.get("safety", "plan")                 # plan | simple (a firm hit on the nearest ball) | none
    pot, place = None, None
    if g.ball_in_hand and targets:
        for q, xy, o in _placements(balls, targets, kitchen, sigma)[:PLAN["places"]]:
            r = _plan_pots(g, p, xy, balls, targets, sigma, opts=[o], lv=lv)
            if r is not None and (pot is None or r[0] > pot[0]):
                pot, place = r, xy
        if place is None:
            cue = cue if cue is not None and not placement_error(balls, cue, kitchen) else (
                kitchen_spot(balls) if kitchen else free_spot(balls, *HEAD_SPOT))
            place = cue
        cue = place
        dec["cue_xy"] = (float(place[0]), float(place[1]))
    elif targets:
        pot = _plan_pots(g, p, cue, balls, targets, sigma, lv=lv, rng=rng)
    if not targets:            # in hand above the head string with all its balls above it: a kick from the kitchen
        cue = kitchen_spot(balls)
        dec["cue_xy"] = cue
        dec.update({k: v for k, v in kick_safety(g, p, cue, balls, g.targets(p), sigma, lv, kitchen=True).items()
                    if k != "plan"})
    elif pot is not None and pot[0] > 0 and (pot[1] >= pot_min or mode == "none"):
        dec.update(pot[2])
    else:
        sf = _plan_safety(g, p, cue, balls, targets, sigma, wide=lv.get("search") == "wide", lv=lv) \
            if mode == "plan" else None
        if sf is not None and sf[0] > SAFETY_FLOOR and (pot is None or pot[0] <= 0 or sf[0] > pot[1]):
            dec.update(sf[1])
        elif pot is not None and pot[0] > 0 and mode != "simple":
            dec.update(pot[2])
        elif mode == "simple":
            s0 = safety(cue, balls, targets)
            dec.update(aim_deg=s0["phi"], speed=s0["V"], call="safety")
        else:                   # snookered, or every pot and safety risks the rack: the kick search
            dec.update({k: v for k, v in kick_safety(g, p, cue, balls, targets, sigma, lv).items() if k != "plan"})
    if dec.get("call") == "safety" and g.on_the_8(p) and "8" in g.pos:     # never a safety on the 8 (_call_the_8)
        dec["call"] = _call_the_8(g, p, dict(balls, cue=tuple(dec.get("cue_xy") or cue)), dec, lv)
    dec["aim_deg"] = (dec["aim_deg"] + float(rng.normal(0.0, lv["aim_sigma_deg"]))) % 360.0
    dec["speed"] = float(np.clip(dec["speed"] * (1.0 + rng.normal(0.0, lv["speed_err"])), *V_RANGE))
    return dec


def opponent_decision(g: Game, p: int, level: int, rng: np.random.Generator) -> dict:
    """The scripted opponent's decision for player p: the break; with ball in hand a cue position for a straight pot;
    the easiest legal pot, called (ball and pocket); with no pot, a firm hit on its nearest ball. Level 1 then still
    calls that ball into the pocket nearest to it; level 2 calls safety, avoids shots whose cue ball heads for a pocket,
    and also plays safe when its best pot is a hard one (but on the 8 it calls the 8 into its nearest pocket, like level
    1). select "plan" (every level since billiards-3): plan_decision() after the break."""
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
    if lv["select"] == "plan":
        return plan_decision(g, p, lv, rng)
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
        dec["call"] = "safety" if safe and b != "8" else f"{b}:{near}"   # billiards-3: level 2 no longer plays a
        # firm "safety" on the 8 (it sank the 8 uncalled and lost: random shots beat level 2 in 60% of racks)
    dec["aim_deg"] = (phi + float(rng.normal(0.0, lv["aim_sigma_deg"]))) % 360.0
    dec["speed"] = float(np.clip(V * (1.0 + rng.normal(0.0, lv["speed_err"])), *V_RANGE))
    return dec


# ----------------------------------------------------------------------------- single player: the match
class Match:
    """The player (0) against the scripted opponent (1) of a level: one rack. Lock-step: after the player's shot (and
    review) the opponent plays its turn in `follow()`. If the opponent breaks, it does so at construction."""

    def __init__(self, level: int, seed: int, breaker: int = 0, keep_systems: bool = False):
        self.level, self.seed = int(level), int(seed)
        self.g = Game(self.seed, int(breaker), keep_systems=keep_systems)
        self.opening = self.follow()

    MAX_VOIDS = 20                       # consecutive void shots of the opponent (D10) before it is an engine error

    def follow(self) -> list[dict]:
        recs, voids = [], 0
        while not self.g.done and self.g.turn == 1:
            d = opponent_decision(self.g, 1, self.level, np.random.default_rng([self.seed, 104729, self.g.k]))
            recs.append(self.g.shoot(1, d))
            voids = voids + 1 if recs[-1].get("void") else 0       # a void shot: a new draw next time (k advanced)
            if voids > self.MAX_VOIDS:
                raise RuntimeError("the physics engine voided the scripted opponent's shot too many times")
        return recs

    def shot(self, dec: dict) -> dict:
        return self.g.shoot(0, dec)

    def state_sha(self) -> str:
        return self.g.state_sha()
