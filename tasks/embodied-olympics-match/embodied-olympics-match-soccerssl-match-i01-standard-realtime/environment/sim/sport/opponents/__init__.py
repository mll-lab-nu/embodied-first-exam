"""The scripted opponents of wheeled 5 v 5 soccer (format `match`; interfaces §9, skill_api.py).

A scripted team reads the truth (World.truth_view(team): team frame, no images, no robot sensors) with a reaction
delay it applies itself (it buffers the truth), and plays through the same commands as the agent (move / kick /
dribble, the same robot limits; a lower speed cap is a choice of arrival times, not a different robot). The plugin
calls `ScriptedTeam(level, team, rng).act(truth)` every control step and executes the returned commands through
World.execute; the team decides every second call (20 ms) and repeats nothing in between.

Levels (the Embodied Olympics screening notes has the calibration):

  L1  warm-up    sees the world 0.4 s late, robots at most 1.5 m/s; keeper + four field robots that all chase the
                 ball; with the ball: shoots from the attacking half, else kicks it towards the goal. No passes.
  L2  official   0.2 s late, 2.5 m/s; man-to-man with a double press: the robot nearest the ball presses it and
                 a second one closes the ball's line to the goal at 0.35 m (HABIT: always two on the ball, so one
                 attacker is always free), the others mark the most advanced attackers loosely (0.6 m, ball side),
                 one stays forward as the outlet. With the ball: the reference's decisions (no chips), including its
                 shooting rule. Shot defence (10-13): the keeper keeps the angle (on the bisector of the angle the goal
                 mouth subtends from the ball, stepping out up to 0.5 m) and reads the shooter (an opponent with the
                 ball shoots along its heading: when that line enters the mouth, the keeper stands on it); when the
                 ball is within 5 m of the goal the second presser becomes a shot screen 0.9 m from the ball on that
                 bisector, the first job filled after the presser, and holds it. Without it, programs that shoot on
                 sight from 2-3.5 m beat the 0.2 s keeper (screening at the declared reaction delay D = 2 steps:
                 the Embodied Olympics screening notes).
  L3  official   no reaction delay (sees the truth now), 3.0 m/s; man-to-man: the nearest robot presses the ball,
                 a blocker on the ball's line to the goal when it is within 4.5 m, the others mark the most advanced
                 attackers tightly (0.4 m, ball side; HABIT: markers follow their man anywhere and stand ball-side, so runs that drag them open
                 lanes and the space behind them), one outlet forward; any robot that can reach a moving ball first
                 goes for it. With the ball: the reference's decisions (chips only as clearances), including its
                 shooting rule (shoots from within 6.5 m when the goal point's margin is above -0.4 s; user 10-12).
  Both official levels: when three or more of the other team's field robots are at the ball (a swarm), nobody marks;
  outlets wait deep on the wings (L2: two; L3: one, plus a second screen between the ball and the goal), and whoever
  wins the ball passes to them at once (the counter-attack habit that punishes an attack committing everybody to the
  ball). The ball is seen `delay` late but carried forward
  over that latency with the rolling model (a kick or deflection is seen late; a rolling ball where it is).
"""
from __future__ import annotations

import math
import os
import sys
from collections import deque
from dataclasses import replace

_sport = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _sport not in sys.path:
    sys.path.insert(0, _sport)
import builtin_players as BP  # noqa: E402

LEVELS = {
    1: dict(delay=0.4, vmax=1.5, scheme="chase", passing=False),
    2: dict(delay=0.2, vmax=2.5, scheme="man_mark", passing=True, double_press=True, blocker=False, mark_d=0.6,
            shoot_range=6.5, shoot_margin=-0.4,
            # shot defence (10-13, recalibrated at the declared reaction delay D = 2 control steps): angle keeping,
            # the keeper reads the shooter's heading, a shot screen within 5 m of the goal
            keeper="angle", keeper_read=True, screen_r=5.0, screen_prio=True),
    3: dict(delay=0.0, vmax=3.0, scheme="man_mark", passing=True, double_press=False, blocker=True, mark_d=0.4,
            swarm_screen=True, shoot_range=6.5, shoot_margin=-0.4),
}
# (scheme "zone_press": presser + second presser + one zone player + outlet; the L2 of 10-11 afternoon, kept for
# comparison: it lost the L2-L3 ordering, the Embodied Olympics screening notes 2.3)
OFFICIAL = (2, 3)
WARMUP = (1,)


class Scripted(BP.Reference):
    """the scripted team's decisions (see the module docstring); a BP team: update(TeamView) -> commands."""

    name = "scripted"

    def __init__(self, level=2, team="yellow", seed=0, rng=None, **over):
        P = dict(LEVELS[int(level)])
        P.update(over)
        self.level, self.P = int(level), P
        super().__init__(team=team, seed=seed, rng=rng, passing=P["passing"], vmax=P["vmax"], chip=int(level) >= 3,
                         lookahead=0.0, shoot_range=float(P.get("shoot_range", 0.0)),
                         shoot_margin=float(P.get("shoot_margin", 0.0)))
        self.delay = float(P["delay"])
        self.hist = deque()
        self.kick_lead = 0.02  # its commands take effect at the next control step
        self.kick_window = 0.3  # the beam is judged from positions: keep the kick armed a little longer

    # perception: the ball and the other team as they were `delay` seconds ago; the own robots now
    def update(self, view):
        self.hist.append((view.t, view.ball, view.ball_v, view.opp))
        while len(self.hist) > 1 and view.t - self.hist[1][0] >= self.delay - 1e-6:
            self.hist.popleft()
        t_seen, b, bv, opp = self.hist[0]
        lag = view.t - t_seen
        if any(r.on and BP.dist(r.p, view.ball) < 0.25 for r in view.own.values()):
            b, bv = view.ball, view.ball_v  # a ball at an own robot's dribbler is felt at once (its own sensors)
        elif lag > 0 and math.hypot(*bv) > 0.3:
            # what it saw, carried forward over its own latency with the rolling model: a ball that keeps rolling
            # is where it expects it; a kick or a deflection it sees `delay` late
            P = BP.BallPath(b, bv)
            sp = P.v_at(lag)
            b, bv = P.at(lag), (P.d[0] * sp, P.d[1] * sp)
        if lag > 0:
            opp = {k: replace(o, p=(o.p[0] + o.v[0] * lag, o.p[1] + o.v[1] * lag)) if o.on else o
                   for k, o in opp.items()}
        v2 = replace(view, ball=b, ball_v=bv, opp=opp)
        for r in v2.own.values():  # no sensors in the truth: the beam from (delayed) positions
            if r.on:
                r.beam = BP.geometric_beam(r, b) or BP.geometric_beam(r, view.ball)
        return super().update(v2)

    def play(self):
        v = self.v
        sc = self.P["scheme"]
        ids = [k for k in self.field_ids() if self.locked_until.get(k, -1) <= v.t]
        carrier = next((k for k in ids if self.has_ball(k)), None)
        for k in self.field_ids():
            if k not in ids:
                self.move(k, v.own[k].p, v.own[k].yaw)
        if sc == "chase":
            for k in ids:
                if k == carrier:
                    self.attack_l1(k)
                else:
                    self.collect(k, aim=BP.OPP_GOAL)
            self.keeper()
            return
        P = self.path()
        mine = {}
        for k in ids:
            r = v.own[k]
            it = BP.intercept(r.p, r.v, P, vmax=self.vmax)
            mine[k] = it if it is not None else (9.0, v.ball)
        theirs = 9.0
        for r in v.opp.values():
            if r.on:
                it = BP.intercept(r.p, r.v, P)
                if it is not None:
                    theirs = min(theirs, it[0])
        agent_ctrl = self.opp_with_ball()
        if self.pass_ is not None:
            pr = self.pass_
            if carrier is not None and carrier == pr["recv"]:
                self.stats["pass_ok"] += 1
                self.pass_ = None
            elif (carrier is not None and (carrier != pr.get("from") or v.t - pr["t"] > 0.4)) \
                    or (agent_ctrl is not None and v.t - pr["t"] > 0.3) or v.t > pr["deadline"]:
                self.stats["pass_lost"] += 1
                self.log.append((round(v.t, 2), "pass_lost", pr["recv"], [round(c, 2) for c in v.ball]))
                self.pass_ = None
        if carrier is not None or (self.pass_ is not None and self.pass_["recv"] in ids):
            g = carrier if carrier is not None else self.pass_["recv"]
            if g == carrier:
                self.attack(g)
            else:
                self.collect(g)
            rest = [k for k in ids if k != g]
            if sc == "counter":
                spots = self.counter_spots(len(rest), attacking=True)
            elif self.level >= 3:
                spots = self.attack_spots(len(rest), g)
            else:
                b = v.ball
                spots = [BP.clamp_play((b[0] + 1.5, 1.6)), BP.clamp_play((b[0] + 1.5, -1.6)),
                         BP.clamp_play((b[0] - 1.5, -b[1] * 0.5))]
                if self.in_shot_zone():  # in possession near the own goal: the safety stays on the shot's line
                    spots[2] = self.screen_spot(max(1.2, float(self.P.get("screen_d", 0.9))))
            for k, p in BP.assign(rest, spots[: max(len(rest), 1)], v).items():
                self.move(k, p, math.atan2(v.ball[1] - p[1], v.ball[0] - p[0]))
                self.dribble(k, 3000)
            self.keeper()
            return
        if not ids:
            self.keeper()
            return
        presser = min(ids, key=lambda k: mine[k][0])
        loose = agent_ctrl is None and math.hypot(*v.ball_v) > 1.0
        rest = [k for k in ids if k != presser]
        jobs = {}
        b = v.ball
        if sc == "counter":
            # compact: the presser goes only when the ball is in its half or it is clearly first to a loose ball;
            # otherwise it holds the line in front of the ball
            if b[0] < 0.5 or (loose and mine[presser][0] < theirs - 0.1):
                self.collect(presser, aim=BP.OPP_GOAL)
            else:
                ux, uy = BP.unit(-BP.HALF_L - b[0], -b[1])
                q = BP.push_out_of_own_da((b[0] + ux * 0.8, b[1] + uy * 0.8))
                self.move(presser, q, math.atan2(b[1] - q[1], b[0] - q[0]))
                self.dribble(presser, 0)
            spots = self.counter_spots(len(rest), attacking=False)
            pos = BP.assign(rest, spots[: max(len(rest), 1)], v)
            for k, p in pos.items():
                striker = p[0] > 0.5
                if loose and not striker and mine[k][0] < theirs - 0.05:
                    jobs[k] = "intercept"
                else:
                    jobs[k] = p
            for k, job in jobs.items():
                if job == "intercept":
                    self.collect(k)
                else:
                    self.move(k, job, math.atan2(b[1] - job[1], b[0] - job[0]))
                    self.dribble(k, 3000)
            self.keeper()
            return
        self.collect(presser, aim=BP.OPP_GOAL)
        if sc == "zone_press":
            ux, uy = BP.unit(-BP.HALF_L - b[0], -b[1])
            second = BP.push_out_of_own_da((b[0] + ux * 0.35, b[1] + uy * 0.35))
            zx = max(-3.2, min(-0.6, b[0] - 1.4))
            side = 1.0 if b[1] >= 0 else -1.0
            zones = [(zx, side * 1.0)]  # one zone player on the ball's side
            o1 = self.outlet()
            if self.swarm():  # the other team has committed everybody to the ball: a second outlet, no zone
                zones = []
                spots = [second, o1, (o1[0] - 0.6, -o1[1])]
            else:
                spots = [second] + zones + [o1]
            pos = BP.assign(rest, spots[: max(len(rest), 1)], v)
            for k, p in pos.items():
                if loose and p in zones and mine[k][0] < theirs - 0.05 and BP.dist(mine[k][1], p) < 1.4:
                    jobs[k] = "intercept"
                else:
                    jobs[k] = p
        else:  # man_mark
            # a blocker on the ball's line to the goal when the ball is within 4.5 m of it; all but one of the others
            # mark; the last one is the outlet
            spots = []
            ux, uy = BP.unit(-BP.HALF_L - b[0], -b[1])
            zone = self.in_shot_zone()
            screen = None
            if zone and len(rest) >= (1 if self.P.get("screen_prio") else 2):
                # the shooting zone: the second robot screens the shot (on the bisector of the goal's angle, between
                # the ball and the goal) instead of pressing
                screen = self.screen_spot(float(self.P.get("screen_d", 0.9)))
                spots.append(screen)
            elif self.P.get("double_press") and len(rest) >= 2:  # L2's habit: always two on the ball
                spots.append(BP.push_out_of_own_da((b[0] + ux * 0.35, b[1] + uy * 0.35)))
            elif self.P.get("blocker", True) and BP.dist(b, BP.OWN_GOAL) < 4.5 and len(rest) >= 2:
                spots.append(BP.push_out_of_own_da((b[0] + ux * 0.9, b[1] + uy * 0.9)))
            n_mark = max(0, len(rest) - 1 - len(spots))
            if self.swarm():  # nobody to mark away from the ball
                n_mark = 0
                o1 = self.outlet()
                if self.P.get("swarm_screen"):
                    # a second screen between the ball and the goal (blocks the swarm's shots) and one outlet
                    d2 = min(2.0, max(1.2, BP.dist(b, BP.OWN_GOAL) - 1.3))
                    spots.append(BP.push_out_of_own_da((b[0] + ux * d2, b[1] + uy * d2 + 0.35)))
                else:
                    spots.append((o1[0] - 0.6, -o1[1]))  # a second outlet on the other wing
            marks = sorted((r for r in v.opp.values() if r.on and BP.dist(r.p, b) > 0.4),
                           key=lambda r: r.p[0])[:n_mark]  # the most advanced attackers (lowest x here)
            for r in marks:
                mx, my = BP.unit(b[0] - r.p[0], b[1] - r.p[1])
                md = float(self.P.get("mark_d", 0.4))
                spots.append(BP.push_out_of_own_da((r.p[0] + mx * md, r.p[1] + my * md)))
            if len(rest) > len(spots):
                spots.append(self.outlet())
            while len(spots) < len(rest):
                spots.append((max(-3.3, b[0] - 2.0), 0.0))
            pos = BP.assign(rest, spots, v)
            for k, p in pos.items():
                if screen is not None and p == screen and self.P.get("screen_prio"):
                    jobs[k] = p  # the screen holds its place (a loose ball is the presser's)
                    continue
                jobs[k] = "intercept" if loose and mine[k][0] < theirs - 0.05 else p
        for k, job in jobs.items():
            if job == "intercept":
                self.collect(k)
            else:
                self.move(k, job, math.atan2(b[1] - job[1], b[0] - job[0]))
                self.dribble(k, 3000)
        self.keeper()

    # ------------------------------------------------------------------------------------------------ shot defence
    def in_shot_zone(self):
        """the ball within `screen_r` m of the own goal (0 = no shot screen)."""
        r = float(self.P.get("screen_r", 0.0))
        return r > 0 and BP.dist(self.v.ball, BP.OWN_GOAL) < r

    def bisector(self, b):
        """the unit direction from the ball that halves the angle the goal mouth subtends (posts at +-GOAL_HALF_W)."""
        gx = -BP.HALF_L
        u1 = BP.unit(gx - b[0], -BP.GOAL_HALF_W - b[1])
        u2 = BP.unit(gx - b[0], BP.GOAL_HALF_W - b[1])
        return BP.unit(u1[0] + u2[0], u1[1] + u2[1])

    def screen_spot(self, d):
        """a robot `d` m from the ball on the bisector of the goal's angle: its body covers the middle of every shot
        from there (at 2-4 m it covers the corners a shooter aims for), kept out of the own defense area."""
        b = self.v.ball
        ux, uy = self.bisector(b)
        dg = BP.dist(b, BP.OWN_GOAL)
        d = min(d, max(0.35, dg - 1.3))
        return BP.push_out_of_own_da((b[0] + ux * d, b[1] + uy * d))

    def keeper_spot(self, b):
        if self.P.get("keeper") != "angle":
            return super().keeper_spot(b)
        # angle keeping: on the bisector of the angle the goal mouth subtends from the ball (both posts equally far
        # off its body), stepping out as the ball comes closer to cut the angle, inside the own defense area
        gx = -BP.HALF_L
        ux, uy = self.bisector(b)
        if abs(ux) < 1e-6:
            return super().keeper_spot(b)
        t0 = (gx - b[0]) / ux                       # where the bisector meets the goal line
        y0 = b[1] + uy * t0
        d = BP.dist(b, (gx, 0.0))
        rad = min(float(self.P.get("keeper_out", 0.5)), max(0.15, 0.15 + (d - 1.2) * 0.2))
        rad = min(rad, max(0.1, t0 - 0.35))          # never closer than 0.35 m to the ball
        x, y = gx - ux * rad, y0 - uy * rad
        x = max(gx + 0.1, min(gx + BP.DA_DEPTH - 0.12, x))
        if self.P.get("keeper_read"):
            # reading the shooter: an opponent with the ball shoots along its heading (the kick leaves along the
            # robot's heading); when that line enters the goal mouth, the keeper stands on it at its depth
            k = self.opp_with_ball()
            o = self.v.opp.get(k) if k is not None else None
            if o is not None and BP.dist(b, BP.OWN_GOAL) < 6.0:
                yaw = o.yaw + o.w * min(0.15, self.delay)
                cx, cy = math.cos(yaw), math.sin(yaw)
                if cx < -0.2:
                    ty = b[1] + cy * (gx - b[0]) / cx
                    if abs(ty) < BP.GOAL_HALF_W + 0.2:
                        y = b[1] + cy * (x - b[0]) / cx
        y = max(-BP.GOAL_HALF_W + 0.05, min(BP.GOAL_HALF_W - 0.05, y))
        return x, y

    def outlet(self):
        """the robot left forward while defending: on the far side, ahead of the ball, where a quick pass after
        winning the ball finds it alone (it punishes an attack that commits everybody to the ball)."""
        b = self.v.ball
        side = -1.0 if b[1] >= 0 else 1.0
        x = max(0.5, min(3.0, b[0] + 3.2))
        if self.swarm():  # the other team has committed (almost) everybody to the ball: wait deep in its half
            x = 2.4
        q = (x, side * 1.6)
        # away from the nearest opponent
        o = min((r for r in self.v.opp.values() if r.on), key=lambda r: BP.dist(r.p, q), default=None)
        if o is not None and BP.dist(o.p, q) < 0.8:
            q = (q[0], q[1] - math.copysign(0.7, o.p[1] - q[1]))
        return BP.clamp_play(q, 0.3)

    def counter_spots(self, n, attacking):
        """the counter-attacking team's shape: one striker always high on the weak side; the others a compact screen
        between the ball and the own goal (defending) or safe supports behind the ball (attacking)."""
        b = self.v.ball
        side = -1.0 if b[1] >= 0 else 1.0
        sx = max(1.0, min(3.0, b[0] + 3.0))
        striker = (sx, side * 1.4)
        o = min((r for r in self.v.opp.values() if r.on), key=lambda r: BP.dist(r.p, striker), default=None)
        if o is not None and BP.dist(o.p, striker) < 0.8:
            striker = (striker[0], striker[1] - math.copysign(0.7, o.p[1] - striker[1]))
        striker = BP.push_out_of_opp_da(BP.clamp_play(striker, 0.3), 0.3)
        spots = [striker]
        ux, uy = BP.unit(-BP.HALF_L - b[0], -b[1])
        px, py = -uy, ux
        if attacking:
            spots += [BP.clamp_play((b[0] - 1.3, b[1] * 0.5 + 1.0), 0.3), BP.clamp_play((b[0] - 1.3, b[1] * 0.5 - 1.0), 0.3)]
        else:
            d1 = min(1.6, max(0.9, BP.dist(b, BP.OWN_GOAL) - 1.4))
            spots += [BP.push_out_of_own_da((b[0] + ux * d1 + px * 0.45, b[1] + uy * d1 + py * 0.45)),
                      BP.push_out_of_own_da((b[0] + ux * (d1 + 0.6) - px * 0.45, b[1] + uy * (d1 + 0.6) - py * 0.45))]
        while len(spots) < n:
            spots.append((max(-3.2, b[0] - 2.0), 0.0))
        return spots[:max(n, 1)]

    def swarm(self):
        """three or more of the other team's field robots within 1.5 m of the ball."""
        b = self.v.ball
        return sum(1 for k, o in self.v.opp.items() if o.on and k != BP.KEEPER and BP.dist(o.p, b) < 1.5) >= 3

    def decide(self, n, dd):
        """the reference's decision, plus the counter-attack habit: right after winning the ball with two or more
        opponents around it, the ball goes to the outlet (the robot left forward) if its lane is anywhere near open."""
        v = self.v
        b = v.ball
        if self.P["scheme"] == "counter" and b[0] < 1.5 and BP.dist(b, BP.OPP_GOAL) > 3.2:
            # the counter-attack: the ball goes forward to the most advanced teammate at once, through any lane that is
            # nearly open, else long towards it (a clearance it can run onto)
            mates = sorted((k for k in self.field_ids() if k != n), key=lambda k: -v.own[k].p[0])
            for k in mates[:2]:
                if v.own[k].p[0] < b[0] + 1.5:
                    continue
                best = None
                for q in self.pass_points(k):
                    o = self._pass_option(n, k, q)
                    if o is not None and o["margin"] > -0.25 and (best is None or o["margin"] > best["margin"]):
                        best = o
                if best is not None:
                    return dict(num=n, kind="pass", target=best["target"], speed=best["speed"], mode=best["mode"],
                                recv=k, T=best["T"], t=v.t, margin=best["margin"], redirect=best.get("redirect"))
            if mates and v.own[mates[0]].p[0] > b[0] + 2.0 and \
                    min((BP.dist(o.p, b) for o in v.opp.values() if o.on), default=9.0) < 0.8:
                s_ = v.own[mates[0]].p
                tgt = (min(s_[0] + 0.8, BP.HALF_L - 1.4), s_[1])
                return dict(num=n, kind="push", target=tgt, speed=min(5.5, 2.0 + 0.6 * BP.dist(b, tgt)), mode="flat",
                            t=v.t)
        crowd = sum(1 for o in v.opp.values() if o.on and BP.dist(o.p, b) < 1.0)
        if self.P["scheme"] != "chase" and crowd >= 2 and self.passing and BP.dist(b, BP.OPP_GOAL) > 3.2:
            best = None
            for k in self.field_ids():
                if k == n:
                    continue
                q = v.own[k].p
                if q[0] < b[0] + 1.0:
                    continue
                o = self._pass_option(n, k, q)
                if o is not None and o["margin"] > -0.2 and (best is None or q[0] > best[1]["target"][0]):
                    best = (k, o)
            if best is not None:
                k, o = best
                return dict(num=n, kind="pass", target=o["target"], speed=o["speed"], mode=o["mode"], recv=k,
                            T=o["T"], t=v.t, margin=o["margin"], redirect=o.get("redirect"))
        return super().decide(n, dd)

    def attack_l1(self, n):
        """L1 with the ball: shoot from the attacking half, else kick it towards the goal (no passes)."""
        r = self.v.own[n]
        b = self.v.ball
        if self.kick_cool.get(n, -1) > self.v.t:
            return
        sp = self.kick_speed if b[0] > 0 else 4.0
        if self.turn_and_kick(n, (BP.HALF_L, 0.0), sp, "flat", tol=0.08):
            self.kick_cool[n] = self.v.t + 0.4
            self.stats["shots" if b[0] > 0 else "clears"] += 1
        elif self.track_hold(n) > 0.7 and r.beam:
            self.kick(n, 3.0)
            self.kick_cool[n] = self.v.t + 0.4

    def formation(self):
        v = self.v
        ids = self.field_ids()
        if not ids:
            return {}
        nxt_ours = v.ref.next_ours if v.ref.state == "STOP" else v.ref.ours
        b = v.ball
        if nxt_ours:
            spots = [(min(2.9, b[0] + 1.5), 1.6), (min(2.9, b[0] + 1.5), -1.6),
                     BP.clamp_play((b[0] - 1.5, 0.0)), (max(-3.0, b[0] - 2.5), 0.0)]
        else:
            spots = self.defend_spots(len(ids))
        spots = [BP.push_out_of_opp_da(BP.push_out_of_own_da(q), 0.45) for q in spots]
        return BP.assign(ids, spots[: len(ids)], v)


class ScriptedTeam:
    """the plugin's interface: ScriptedTeam(level, team, rng).act(truth) -> [command bodies] (skill_api.py), called
    every control step with World.truth_view(team)."""

    def __init__(self, level, team="yellow", rng=None, every=2, **over):
        self.level = int(level)
        if self.level not in LEVELS:
            raise ValueError(f"opponent level must be one of {sorted(LEVELS)}")
        self.team = Scripted(level=self.level, team=team, rng=rng, **over)
        self.every = int(every)
        self.calls = 0

    def act(self, truth: dict) -> list:
        self.calls += 1
        if (self.calls - 1) % self.every:
            return []
        view = BP.view_from_truth(truth)
        return [BP.to_act(n, skill, args) for n, skill, args in self.team.update(view)]

    @property
    def stats(self):
        return self.team.stats
