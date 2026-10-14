"""Table tennis on the v0.2 core (docs/framework_zh.md §4.2): the simulator (sim/) behind contract ②. Two formats, both
action levels, both plays. Since revision wallclock-7 / duel-wallclock-5 the robots stand on x-y rail bases; since 8 / 6 the
players serve (sim/serve.py, ITTF 2.6, 2.13.3):

  world + referee  match  arm_commands.Core (match.Match: one Franka + paddle on its rail base against the scripted
                          opponent inside the world; you serve first, 2 each; step = Core.rt_advance(1))
                   duel   duel.Duel (two robots, the ITTF referee and serve judge; step = Duel.advance())
                   A point end freezes the world for the reviews (Phase.review); first to 5 (lead by 2 from 4:4, cap 7).
  actions          low   the arm command layer: traj / slew / hold targets of the 9 joints [base_x, base_y, q1..q7]
                         (action_low.validate), and toss
                   high  the paddle state at contact with an optional base position (action_high.validate), lowered at
                         the effect boundary to the SAME low-level traj command: match - match.Match.plan_paddle (base
                         go-to, IK, swing, robot-only rehearsals, seeded scatter) then the rest slew; duel - the base goal
                         and IK off the world lock in the seat's plan worker (workers.prepare), the base trajectory and
                         swing at the boundary (workers.trajectory); move (the base's rest position) and toss pass
                         through. The episode holds low-level commands only.
  observation      observe(): own robot (base_xy, joints), score, the serve (who, phase, clock, your own toss), heard
                   bounces, the command in force (every position in the seat's own frame); camera_job(): the cameras
                   (behind and beside the seat's robot, 4 frames 40 ms apart), drawn by the sport itself (a frame
                   history is not one renderer state).
The duel's seed and first server come from the config (duel.py reads them as module constants).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from core.sport import FINISHED, PLAYING, UNIT_OVER, MatchBase, Phase, Refused

HERE = Path(__file__).resolve().parent
SIM = HERE / "sim"
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))

import action_high  # noqa: E402
import action_low  # noqa: E402
import rcb_tt  # noqa: E402
from skill_api import CONTRACTS, HIT  # noqa: E402  (the skill API's contract: skill_api.py, skilleval/contract.py)

DT = rcb_tt.CONTROL_DT
SEATS = ("A", "B")
REST_SPEED = action_high.REST                      # the high level's return to the ready pose (60 % of the limits)
_INSTALL_KEYS = ("command", "first_row_used", "rows_left")
IMAGE_LAYOUT = ("2 rows x 4 columns. Row 1: camera behind your robot looking down the table; row 2: camera at the side. "
                "Columns: four camera frames 40 ms apart, oldest left, latest right; each tile is stamped with its "
                "control step k and its time t since the current ball was played (observation.view_steps, "
                "view_times). Yellow marks every 0.25 m along the table edges. Single format: the opponent is the red "
                "paddle on the far side. The side camera looks along +x: your robot is on the right.")


def _duel(cfg):
    """duel.py reads its seed and first server from the environment at import (module constants): set both from the
    config, also for a module imported by an earlier match of this process."""
    first = cfg.first or "A"
    os.environ["DUEL_SEED"], os.environ["FIRST_SERVER"] = str(cfg.seed), first
    import duel
    duel.SEED, duel.FIRST_SERVER = int(cfg.seed), first
    return duel


def _serve_state(you, phase, detail, opens_k, deadline_k, toss, k, extra):
    """The racket sports' common `serve` observation: phase waiting | open | tossed | done, court (singles table tennis
    has no service court: "any"), opens_in_s, deadline_in_s, tossed_at_step; table tennis extras: server, detail
    (ready, open, toss resting, toss rising/falling, struck, in play), the server's delay faults and its own toss."""
    import serve as SV
    out = {"phase": phase, "court": "any", "opens_in_s": round(max(0.0, (opens_k - k) * DT), 3),
           "deadline_in_s": round(max(0.0, (deadline_k - k) * DT), 3) if phase in ("waiting", "open") else 0.0,
           "tossed_at_step": None if toss is None else int(toss["k"]), "server": "you" if you else "opponent",
           "detail": detail, **extra}
    if you and toss is not None:
        out["toss"] = {"pos": toss["pos"], "height": toss["height"],
                       "projected_at_step": int(toss["k"]) + SV.TOSS_REST_STEPS}
    return out


def _match_serve(R) -> dict:
    """The service, for the match's observation (serve.py)."""
    import serve as SV
    leg = R.leg
    first = next((lg for lg in reversed(R.legs) if lg["kind"] in ("serve", "our_serve")), leg)
    clock = int(round(SV.SERVE_CLOCK_S / DT))
    if R.point_server == 1:                             # the opponent tosses as soon as the serve opens
        ok = first["toss_k"]
        if leg is first and R.k < ok:
            ph, det = "waiting", "ready"
        elif leg is first and R.k <= first["launch"]:
            ph, det = "tossed", "toss"
        else:
            ph, det = "done", "in play"
        return _serve_state(False, ph, det, ok, ok + clock, {"k": ok} if R.k >= ok else None, R.k, {})
    extra = {"delay_faults": R.delay_faults[0], "delay_limit": SV.DELAY_LIMIT, "lets_in_row": R.serve_lets,
             "let_limit": SV.LET_LIMIT}
    if leg is not first:
        return _serve_state(True, "done", "in play", first["open"], first["deadline"], first.get("toss"), R.k, extra)
    st = leg["state"]
    ph = {"waiting": "waiting" if R.k < leg["open"] else "open", "rest": "tossed", "toss": "tossed",
          "struck": "tossed"}.get(st, "done")
    det = {"waiting": "ready" if R.k < leg["open"] else "open", "rest": "toss resting", "toss": "toss rising/falling",
           "struck": "struck", "to_opp": "in play"}.get(st, st)
    return _serve_state(True, ph, det, leg["open"], leg["deadline"], leg.get("toss"), R.k, extra)


def _duel_serve(g, seat) -> dict:
    import serve as SV
    rs, sv = g.rs, g.rs["serve"]
    you = rs["server"] == seat
    det = sv["phase"]
    if det == "ready" and g.k >= sv["open_k"]:
        det = "open"
    ph = {"ready": "waiting", "open": "open", "rest": "tossed", "toss": "tossed", "struck": "tossed"}.get(det, "done")
    det = {"rest": "toss resting", "toss": "toss rising/falling"}.get(det, det)
    extra = {"delay_faults": g.delay_faults[seat], "delay_limit": SV.DELAY_LIMIT, "lets_in_row": g.serve_lets,
             "let_limit": SV.LET_LIMIT} if you else {}
    return _serve_state(you, ph, det, sv["open_k"], sv["deadline_k"], sv["toss"], g.k, extra)


def _check_toss(seat, dec, match):
    """A toss that is not legal now is refused (409: not your service / not yet; 400: the toss point or speed)."""
    if dec.get("type") != "toss":
        return dec
    bad = (match.R.toss_check(dec["pos"], dec["height"]) if isinstance(match, TTMatch)
           else match.g.toss_check(seat, dec["pos"], dec["height"]))
    if bad:
        raise Refused(bad[0], bad[1])
    return dec


# ================================================================================================ format "match"
class TTMatch(MatchBase):
    """One seat (A) against the scripted opponent (arm_commands.Core)."""

    def __init__(self, cfg):
        self.cfg, self.level = cfg, int(cfg.level or 1)
        os.environ["MATCH_SEED"] = str(cfg.seed)          # match.Match reads it at construction: serves, opponent, scatter
        import arm_commands
        import ladder
        import levels
        self.R = arm_commands.Core(self.level, levels.plugin(cfg.action_level))
        self.contacts = ladder.PaddleContacts(self.R)     # read-only (the score ladder's blade speeds)
        self.dt = DT
        self.reviewed = 0

    @property
    def k(self):
        return self.R.k

    # world + referee
    def step(self):
        R = self.R
        n0, r0 = len(R.points), len(R.results)
        R.rt_advance(1)
        self.contacts.after_step(R.k)
        ev = [{"kind": "shot", **{k: r.get(k) for k in ("returned", "summary")}} for r in R.results[r0:]]
        return ev + [{"kind": "point", **p} for p in R.points[n0:]]

    def apply(self, seat, cmd):
        if cmd["type"] == "noop":                         # a high-level act whose stroke could not be planned
            return {}
        if cmd["type"] == "move":                         # the high level's base rest position
            return {"base_rest": self.R.set_base_rest(cmd["base"])}
        if cmd["type"] == "toss":                         # the service's toss (both levels)
            return self.R.toss(cmd["pos"], cmd["height"])
        return self.R.submit(cmd)

    def phase(self):
        R = self.R
        if R.done:
            return Phase(FINISHED, reason="match_over")
        if len(R.points) > self.reviewed:
            return Phase(UNIT_OVER, review=tuple(self.cfg.seats), reason=R.points[-1]["how"])
        return Phase(PLAYING)

    def resume(self):
        self.reviewed = len(self.R.points)

    def unit(self):
        return len(self.R.points)

    def scores(self):
        return {"A": self.R.score[0], "opponent": self.R.score[1]}

    def tiebreaks(self):
        return [("game", lambda m: {0: "A", 1: "opponent"}.get(m.R.winner))]   # first to 5, lead 2, cap 7; let guard

    def state_digest(self):
        """The simulator's own state hash (physics + the ball's contact events) and the points (score, how)."""
        return hashlib.sha256((self.R.s.state_sha() + json.dumps(self.R.points, sort_keys=True)).encode()).hexdigest()

    # observation
    def observe(self, seat, query=None):
        R = self.R
        st, leg = R.s.state(), R.leg
        heard = [{"event": {"table_opp": "bounce on the opponent's half", "table_own": "bounce on your half",
                            "net": "net"}.get(e["kind"], e["kind"]),
                  "t": round(e["t"] - leg["launch"] * DT, 3)} for e in R.s._events]
        o = {"score": {"you": R.score[0], "opponent": R.score[1]}, "point": len(R.points) + 1,
             "ball": {"serve": "serve", "our_serve": "your serve"}.get(leg["kind"], "opponent's return"),
             "t_since_played": R.t_since_launch(), "you_serve": R.point_server == 0,
             "you_receive_serve": R.point_server == 1, "serve": _match_serve(R),
             "heard": heard, "q": st["q"].round(4).tolist(), "base_xy": st["q"][:2].round(4).tolist(),
             "paddle_pos": st["paddle_pos"].round(3).tolist(),
             "paddle_normal": st["paddle_normal"].round(3).tolist(),
             "ball_in_play": R.in_play() and leg["state"] in ("incoming", "to_opp", "opp_missed", "rest", "toss",
                                                                 "struck"),
             "ball_state": {"incoming": "coming to you", "to_opp": "going to the opponent",
                            "opp_missed": "going to the opponent", "done": "dead", "waiting": "your serve",
                            "rest": "your serve", "toss": "your serve", "struck": "going to the opponent"}.get(
                                leg["state"], leg["state"]),
             "points": [{k: p[k] for k in ("point", "winner", "how", "score")} for p in R.points[-2:]],
             "shots": [{k: r.get(k) for k in ("returned", "summary", "speed_out")} for r in R.results[-2:]]}
        if not R.in_play():
            o["serve_in_s"] = round(max(0.0, (leg["launch"] - R.k) * DT), 3)
        o.update(R.plugin.state(R))                       # the command in force (low level: also qd, q_target, qd_target)
        return o

    def camera_job(self, seat):
        R = self.R
        reviewing = len(R.points) > self.reviewed and not R.done
        hist = list(R.review_hist if reviewing and hasattr(R, "review_hist") else R.hist)
        if not hist:                                      # before the first step: the current state (display only)
            hist = [{"k": R.k, "t": R.t_since_launch(), "qpos": R.s.d.qpos.copy(), "opp_x": R.opp_x(),
                     "leg_id": len(R.legs) - 1, "wall_mono": time.monotonic()}]
        import match
        sel = [hist[max(0, len(hist) - 1 - b)] for b in reversed(match.Match.VIEW_BACK)]
        snaps = [{"qpos": np.asarray(s["qpos"], float).copy(), "t": float(s["t"]), "opp_x": float(s["opp_x"]),
                  "k": int(s["k"])} for s in sel]
        meta = dict(view_times=[s["t"] for s in sel], view_steps=[s["k"] for s in sel],
                    view_leg_ids=[s.get("leg_id") for s in sel], view_sim_times=[round(s["k"] * DT, 4) for s in sel],
                    wall_mono=sel[-1].get("wall_mono", time.monotonic()), image_layout=IMAGE_LAYOUT)
        return {"format": "match", "seat": seat, "snaps": snaps}, meta

    def render_state(self):
        return {"qpos": self.R.s.d.qpos.tolist()}

    def broadcast_frame(self):
        return {"q": self.R.s.d.qpos.round(5).tolist(), "o": round(self.R.opp_x(), 4)}

    def final_fields(self):
        import ladder
        R = self.R
        return {"level": self.level, "seed": int(R.lv["seed"]), "points_for": R.score[0], "points_against": R.score[1],
                "win_points": 5, "won": R.winner == 0, "winner_side": {0: "you", 1: "opponent"}.get(R.winner),
                "returns": int(sum(r["returned"] for r in R.results)), "our_legs": R.n_our_legs,
                "our_shots": R.n_our_shots, "rejected_acts": R.n_rejected, "physics_steps": int(R.s.sim_steps_total),
                "points": R.points, "results": R.results, "shots": R.shots,
                "opponent_serves": R.serve_ids[:R.n_opp_serves], "our_serves": R.our_serves,
                "delay_faults": R.delay_faults[0], "disqualified": R.disqualified == 0,
                "opponent": [lg.get("opp") for lg in R.legs if lg.get("opp")],
                "ladder": ladder.ladder(R.points, R.results, contacts=self.contacts.out),
                "reflexes": int(R.s.servo.n_reflex),                      # velocity and collision reflexes (15/12)
                "collision_reflexes": int(R.s.servo.n_collision_reflex)}


# ================================================================================================ format "duel"
class TTDuel(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg
        self.D = D = _duel(cfg)
        self.g = D.Duel()
        self.g.rest_ready = cfg.action_level == "high"   # the high level returns the arm to the ready pose between strokes
        self.dt = D.CONTROL_DT
        self.level = cfg.action_level
        self.commands = {s: None for s in SEATS}          # the high level's stroke in force (shown in the observation)

    @property
    def k(self):
        return self.g.k

    def step(self):
        n = len(self.g.points)
        self.g.advance()
        if len(self.g.points) > n:
            self.commands = {s: None for s in SEATS}
            return [{"kind": "point", **self.g.points[-1]}]
        return []

    def apply(self, seat, cmd):
        if cmd["type"] == "noop":                         # the skill in the loop gave no valid command
            return {}
        if cmd["type"] == "move":
            return self.g.move(seat, cmd["base"])
        if cmd["type"] == "toss":
            return self.g.toss(seat, cmd["pos"], cmd["height"])
        return self.g.install(seat, cmd)

    def phase(self):
        if self.g.done:
            return Phase(FINISHED, reason="match_over")
        if self.g.review_due:
            return Phase(UNIT_OVER, review=SEATS, reason=self.g.points[-1]["how"])
        return Phase(PLAYING)

    def resume(self):
        self.g.review_done()

    def unit(self):
        return self.g.rs["point"]

    def scores(self):
        return dict(self.g.score)

    def tiebreaks(self):
        return [("game", lambda m: m.g.winner)]        # ITTF game to 5 (lead by 2, cap 7); the let guard inside Duel

    def state_digest(self):
        return self.g.state_sha()

    def observe(self, seat, query=None):
        g, D = self.g, self.D
        other = D.OTHER[seat]
        p = g.d.site_xpos[g.site_paddle[seat]].copy()
        normal = g.d.site_xmat[g.site_paddle[seat]].reshape(3, 3)[:, 0].copy()
        if seat == "B":
            p, normal = D.mir(p), D.mir(normal)
        command = copy.deepcopy(self.commands[seat])
        if command:
            command["contact_in_s"] = max(0., (command["contact_step"] - g.k) * self.dt)
        heard = {f"table_{seat}": "bounce on your half", f"table_{other}": "bounce on the opponent's half",
                 f"paddle_{seat}": "paddle", f"paddle_{other}": "opponent hit", f"robot_{seat}": "robot",
                 f"robot_{other}": "opponent arm"}
        o = dict(point=g.rs["point"] + 1, score=dict(you=g.score[seat], opponent=g.score[other]),
                 ball="serve" if g.rs["hits_in_point"] <= 1 else "return",
                 t_since_played=(g.k - g.rs["played_k"]) * self.dt,
                 serve_in_s=max(0., (g.rs["launch"] - g.k) * self.dt), ball_in_play=g.in_play(),
                 ball_state=("your serve" if g.rs["server"] == seat and g.rs["last_hitter"] is None else
                             "coming to you" if g.rs["expect"] == seat else "going to opponent"),
                 you_serve=g.rs["server"] == seat, you_receive_serve=g.rs["receiver"] == seat,
                 serve=_duel_serve(g, seat), q=g.d.qpos[g.qadr[seat]].tolist(),
                 base_xy=g.d.qpos[g.qadr[seat][:2]].round(4).tolist(),
                 paddle_pos=p.tolist(), paddle_normal=normal.tolist(),
                 command=command if self.level == "high" else g.command_state(seat),
                 points=[{k: v for k, v in pt.items() if k != "receiver"} for pt in g.points[-2:]],
                 heard=[dict(event=heard.get(x["kind"], x["kind"]), t=x["t"] - g.rs["played_k"] * self.dt)
                        for x in g.events[-12:] if x["t"] >= g.rs["played_k"] * self.dt - .011])
        if self.level == "low":
            o.update(qd=g.d.qvel[g.vadr[seat]].round(4).tolist(), q_target=g.target[seat].round(6).tolist(),
                     qd_target=g._target_vel(seat).round(6).tolist(),
                     servo=action_low.servo_state(g.servo[seat], g.d.time))
        return o

    def camera_job(self, seat):
        g = self.g
        hist = g.review_hist if g.review_due and hasattr(g, "review_hist") else list(g.hist)
        if not hist:
            hist = [dict(k=g.k, qpos=g.d.qpos.copy(), played_k=g.rs["played_k"], point=g.rs["point"],
                         wall_mono=time.monotonic())]
        hist = copy.deepcopy(list(hist))
        sel = [hist[max(0, len(hist) - 1 - b)] for b in reversed(g.VIEW_BACK)]
        meta = dict(view_steps=[x["k"] for x in sel], view_points=[x["point"] + 1 for x in sel],
                    view_sim_times=[x["k"] * self.dt for x in sel],
                    view_times=[round((x["k"] - x.get("played_k", g.rs["played_k"])) * self.dt, 3) for x in sel],
                    wall_mono=sel[-1].get("wall_mono", time.monotonic()), image_layout=IMAGE_LAYOUT)
        return {"format": "duel", "seat": seat, "snapshots": hist, "rs": copy.deepcopy(g.rs)}, meta

    def render_state(self):
        return {"qpos": self.g.d.qpos.tolist()}

    def broadcast_frame(self):
        return {"q": self.g.d.qpos.round(5).tolist()}

    def final_fields(self):
        g = self.g
        return {"score": dict(g.score), "points": g.points, "hits": g.hits, "rejected_acts": dict(g.rejected),
                "first_server": self.D.FIRST_SERVER, "serves": g.serve_log, "delay_faults": dict(g.delay_faults),
                "disqualified": g.disqualified,
                "reflexes": {st: int(sv.n_reflex) for st, sv in g.servo.items()},   # revision 15/12
                "collision_reflexes": {st: int(sv.n_collision_reflex) for st, sv in g.servo.items()}}


# ================================================================================================ action levels
class _LowShim:
    """What action_low needs of a simulator (joint ranges, the ready pose), from the duel's model."""

    def __init__(self, g, D):
        self.s = type("S", (), dict(JOINT_LOW=g.JLOW, JOINT_HIGH=g.JHIGH, inst={"q0": D.Q0[2:]}))()


def _rows(m):
    return m.R if isinstance(m, TTMatch) else _LowShim(m.g, m.D)


def _vec(n, doc):
    return {"type": "vector", "len": n, "doc": doc}


LOW_SCHEMA = {
    "traj": {"k0": {"type": "integer", "min": 0, "doc": "control step of the first row"},
             "q": {"type": "rows", "len": 9, "max_rows": action_low.MAX_ROWS,
                   "doc": "row i = the 9 joint targets [base_x, base_y (m), q1..q7 (rad)] of control step k0 + i; "
                          "consecutive rows within the per-step speed limit (limits.max_target_step)"}},
    "slew": {"q": _vec(9, "goal [base_x, base_y (m), q1..q7 (rad)]"),
             "speed": {"type": "number", "min": 0.0, "max": 1.0, "default": 1.0,
                       "doc": "fraction of each joint's speed limit, (0, 1]"}},
    "hold": {}}
HIGH_SCHEMA = {
    "act": {"t": {"type": "number", "min": 0.0, "max": 2.5, "unit": "s",
                  "doc": "time from the act's effect until contact, 0 < t <= 2.5"},
            "pos": _vec(3, "blade centre at contact (m, your frame): " + action_high.POS_LIMITS),
            "normal": _vec(3, "blade face normal at contact (non-zero)"),
            "vel": _vec(3, "blade velocity at contact (m/s), |vel| <= 8"),
            "base": {"type": "vector", "len": 2, "default": None,
                     "doc": "optional: the base position [bx, by] at contact (default: the stance rule: the base moves "
                            "only as much as needed); |bx| <= 1.0, -2.4 <= by <= -1.5"}},
    "move": {"base": _vec(2, "the base's rest position [bx, by] (where it goes when no stroke is under way; home "
                             "(0, -1.75) again at each point): |bx| <= 1.0, -2.4 <= by <= -1.5")},
    "none": {}}
HIGH_SCHEMA["hit"] = HIT.request_schema()["hit"]  # the skill API hit(t, pos, normal, vel) = act without `base`
                                                  # (skill_api.py: the contract's single source)


class JointLayer:
    """Low level: the player's joint-target commands go straight to the arm command layer."""
    level = "low"
    worker = None
    delay_steps = 0

    def schema(self, match, seat):
        return LOW_SCHEMA

    def parse(self, seat, body, match, ctx):
        dec = action_low.validate(body if isinstance(body, dict) else {}, _rows(match))
        if isinstance(dec, str):
            raise Refused(dec)
        return _check_toss(seat, dec, match)

    def snapshot(self, seat, cmd, match, ordinal):
        return None

    def prepare(self, job):
        return None

    def lower(self, seat, cmd, prepared, match):
        return cmd, {}

    def reply(self, seat, cmd, info, match):
        return {"result": info} if isinstance(match, TTMatch) else info


class StrokeLayer:
    """High level: the paddle state at contact, lowered at the effect boundary to a low-level traj command."""
    level = "high"
    worker = "plan"                                       # the duel's IK (the match plans at the boundary: no job)
    delay_steps = 0

    def schema(self, match, seat):
        return HIGH_SCHEMA

    def parse(self, seat, body, match, ctx):
        dec = action_high.validate(body if isinstance(body, dict) else {}, None)
        if isinstance(dec, str):
            raise Refused(dec)
        return _check_toss(seat, dec, match)

    def snapshot(self, seat, cmd, match, ordinal):
        if cmd["type"] in ("none", "move", "toss") or isinstance(match, TTMatch):
            return None
        g = match.g
        return dict(decision=cmd, point=g.rs["point"], ball=g.rs.get("ball_id"), ordinal=ordinal,
                    serving=bool(seat == g.rs["server"] and not g.rs.get("hits_in_point")),
                    q=g.d.qpos[g.qadr[seat]].tolist(),
                    target=g.target[seat].tolist(), prev=g.prev[seat].tolist(),
                    prev2=g.prev2[seat].tolist())

    def prepare(self, job):
        raise RuntimeError("runs in the plan worker")

    def lower(self, seat, cmd, prepared, match):
        if isinstance(match, TTMatch):
            return self._lower_match(cmd, match.R)
        g = match.g
        if cmd["type"] == "none":
            match.commands[seat] = None
            return {"type": "hold"}, {}
        if cmd["type"] in ("move", "toss"):
            return dict(cmd), {}
        from workers import trajectory, keep_better
        serving = seat == g.rs["server"] and not g.rs.get("hits_in_point")
        path, info = trajectory(g.target[seat], g.prev[seat], prepared, cmd["t"], g.JLOW, g.JHIGH, serve=serving,
                                acc=g._target_acc(seat))
        path, info = keep_better(path, info, g.plan[seat][g.plan_j[seat]:], cmd)
        match.commands[seat] = dict(pos=cmd["pos"], normal=cmd["normal"], vel=cmd["vel"],
                                    contact_step=g.k + info["contact_steps"])
        sc = prepared["speed_scale"]
        if info.get("plan_scale") is not None and info["plan_scale"] < 0.97:   # the arm limits cost paddle speed
            sc = sc / max(0.05, info["plan_scale"])
        info.update(ik_residual=prepared["ik_residual"], speed_scale=round(float(sc), 3),
                    base_short_m=prepared.get("base_short_m"))
        return {"type": "traj", "k0": g.k, "q": [q.tolist() for q in path]}, info

    @staticmethod
    def _lower_match(cmd, R):
        """= action_high.apply at the effect boundary (the legacy service planned there too), with the plan handed
        to the arm command layer as a low-level command instead of being submitted directly."""
        rest = {"type": "slew", "q": [float(x) for x in np.r_[R.base_rest, R.s.inst["q0"]]], "speed": REST_SPEED,
                "base_speed": 1.0, "rest": True}
        if cmd["type"] == "none":
            R._last_act = None
            R.contact_k = R.k
            return rest, {"stroke": "cleared: the arm returns to the ready pose"}
        if cmd["type"] in ("move", "toss"):
            return dict(cmd), {}
        T = float(cmd["t"])
        t_hit = (R.k - R.leg["launch"]) * DT + T
        R._ik_seed = R._planned_hit if R.traj_active() else None
        plan, info = R.plan_paddle(t_hit, cmd["pos"], cmd["normal"], cmd["vel"], cmd.get("base"))
        info["T_from_now"] = round(T, 4)
        R.shots.append({"k": R.k, "leg": R.n_our_legs, **{k: info[k] for k in info if k != "paddle_vel_delivered"}})
        if not plan:
            return {"type": "noop"}, info
        R.contact_k = R.k + info["n_swing_steps_available"]
        R._last_act = info
        return {"type": "traj", "k0": R.k, "q": [np.asarray(q, float).tolist() for q in plan], "then": rest}, info

    def reply(self, seat, cmd, info, match):
        if cmd.get("type") == "toss":
            return dict(info)
        if isinstance(match, TTMatch):
            return action_high.reply(cmd, info)
        return {k: v for k, v in info.items() if k not in _INSTALL_KEYS}


# ================================================================================================ the cameras
class _Tiles:
    """Draws camera tiles exactly as the legacy services did (render_worker.py for the match, Duel.render_views for the
    duel), with a cache: consecutive observations share most of their frames (a frame every 2 control steps, the 4
    tiles span 12), and a tile is a pure function of its snapshot, so a cached tile is the same picture."""

    def __init__(self, model, cams):
        import mujoco as mj
        self.mj = mj
        self.m = model
        self.r = mj.Renderer(self.m, height=360, width=480)
        self.rd = mj.MjData(self.m)
        self.cams, self.cache = [], {}
        for lookat, dist, az, el in cams:
            c = mj.MjvCamera()
            c.lookat[:] = lookat
            c.distance, c.azimuth, c.elevation = dist, az, el
            self.cams.append(c)

    def tile(self, ci, qpos, text, extra, key):
        from PIL import Image, ImageDraw
        key = (ci, key, text, np.asarray(qpos, float).tobytes())
        if key not in self.cache:
            mj = self.mj
            self.rd.qpos[:] = qpos
            mj.mj_forward(self.m, self.rd)
            self.r.update_scene(self.rd, camera=self.cams[ci])
            extra(self.r.scene)
            im = Image.fromarray(self.r.render())
            ImageDraw.Draw(im).text((6, 4), text, fill=(255, 255, 255))
            if len(self.cache) > 96:
                self.cache.clear()
            self.cache[key] = np.asarray(im)
        return self.cache[key]

    def sheet(self, tiles_per_cam):
        from core.observe import png
        return png(np.concatenate([np.concatenate(row, axis=1) for row in tiles_per_cam], axis=0))


def _players_model(live, scene_file):
    """The model the cameras draw: the players' presentation scene (presentation/presentation.toml `players`: the
    Franka Panda's visual meshes on the same bodies, renderer rule 6; same kinematics, checked) with the live model's
    marker settings, else the live model itself."""
    from renderers import Scene, players_model
    fine = players_model(HERE, Scene.from_file(scene_file))
    if fine is None:
        return live
    fine.site_pos[:], fine.site_size[:], fine.site_rgba[:] = live.site_pos, live.site_size, live.site_rgba
    return fine


class MatchView(_Tiles):
    """The single format's cameras (= the legacy render_worker.py): 2 cameras x 4 frames, 480 x 360 tiles."""

    def __init__(self):
        import match
        self.Match = match.Match
        m = rcb_tt.Session(instance=str(match.INSTANCE), scene=str(match.SCENE)).m   # the live match's model
        super().__init__(_players_model(m, match.SCENE), match.Match.CAMS)

    def draw(self, snaps):
        return self.sheet([[self.tile(ci, sn["qpos"], f"k={sn['k']} t={sn['t']:.2f}s",
                                      lambda scn, o=sn["opp_x"]: self.Match._extra_geoms(None, scn, o), sn["opp_x"])
                            for sn in snaps] for ci in range(len(self.cams))])


class DuelView(_Tiles):
    """A duel seat's cameras (= duel.Duel.render_views): behind and beside the seat's robot, in its own frame."""

    def __init__(self, seat):
        import duel
        self.D = duel
        cams = [(lk if seat == "A" else duel.mir(lk), dist, az if seat == "A" else az + 180.0, el)
                for lk, dist, az, el in duel.Duel.CAMS]
        import mujoco as mj
        super().__init__(_players_model(mj.MjModel.from_xml_path(str(duel.SCENE2)), duel.SCENE2), cams)   # = Duel()'s

    def draw(self, snapshots, rs):
        D, out = self.D, []
        sel = [snapshots[max(0, len(snapshots) - 1 - b)] for b in reversed(D.Duel.VIEW_BACK)]
        for ci in range(len(self.cams)):
            row = []
            for sn in sel:
                q = np.array(sn["qpos"], float)
                pk = sn.get("played_k", rs["played_k"])
                if sn["k"] <= pk:
                    q[:3] = [0, 0, -10]
                row.append(self.tile(ci, q, f"k={sn['k']} t={(sn['k'] - pk) * D.CONTROL_DT:.2f}s",
                                     lambda scn: D.Duel._extra_geoms(None, scn), pk))
            out.append(row)
        return self.sheet(out)


_LOCAL: dict = {}                                         # in-process views (core/local.py: no worker processes)


# ================================================================================================ the sport
class TableTennis:
    name = "tabletennis"
    protocol = "realtime"
    revision = "wallclock-15+duel-wallclock-12+low-inloop-1+core-0.2"
    source_dirs = [str(HERE)]
    workers = ("plan", "render")

    def build(self, cfg):
        return TTDuel(cfg) if len(cfg.seats) > 1 else TTMatch(cfg)

    def action_layer(self, level):
        if level == "high":
            return StrokeLayer()
        return inloop_layer() or JointLayer()             # the skill in the loop when the task names the seat's skill

    def worker_init(self, kind, seat, cfg):
        duel = len(cfg.seats) > 1
        if kind == "plan":
            return _duel(cfg).Planner(seat) if duel else None
        if duel:
            _duel(cfg)
            v = DuelView(seat)
        else:
            v = MatchView()
        v.tile(0, v.rd.qpos.copy(), "", lambda scn: None, "warm-up")   # creates the GL context before the handshake
        v.cache.clear()
        return v

    def worker_call(self, obj, kind, job):
        if kind == "plan":
            from workers import prepare
            return prepare(obj, job)
        if obj is None:                                   # in-process (core/local.py)
            key = (job["format"], job["seat"])
            if key not in _LOCAL:
                _LOCAL[key] = MatchView() if job["format"] == "match" else DuelView(job["seat"])
            obj = _LOCAL[key]
        if job["format"] == "match":
            return {"png": obj.draw(job["snaps"])}
        return {"png": obj.draw(job["snapshots"], job["rs"])}

    def scene(self, cfg):
        from renderers.base import Scene
        return Scene.from_file(SIM / "scene" / ("tt_duel.xml" if len(cfg.seats) > 1 else "tt_scene.xml"))

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "idle": bp.Idle, "skill_reference": bp.SkillReference}

    def spec(self, cfg, seat, m):
        import match
        cams = [dict(c, fovy_deg=45.0, tile_px=[480, 360], focal_px=434.6, principal_point_px=[240, 180],
                     image_right="forward x up") for c in match.Match.CAM_INFO]
        out = dict(robot=("franka-panda + paddle (MuJoCo Menagerie panda_nohand) on a pedestal carried by an x-y rail "
                          f"base: travel |x| <= {rcb_tt.BASE_HI[0]}, {rcb_tt.BASE_LO[1]} <= y <= {rcb_tt.BASE_HI[1]}, "
                          f"home {rcb_tt.HOME.tolist()}, up to {rcb_tt.BASE_VMAX} m/s, {rcb_tt.BASE_AMAX} m/s^2 and "
                          f"{rcb_tt.BASE_JMAX} m/s^3 (estimated) per axis; link0 at table-top height, facing +y; the arm "
                          "and the rail obey the real robot's limits (arm_limits)"),
                   arm_limits=rcb_tt.ARM_LIM.table(),
                   base=dict(travel_x=[float(rcb_tt.BASE_LO[0]), float(rcb_tt.BASE_HI[0])],
                             travel_y=[float(rcb_tt.BASE_LO[1]), float(rcb_tt.BASE_HI[1])], home=rcb_tt.HOME.tolist(),
                             max_speed_m_s=rcb_tt.BASE_VMAX, max_accel_m_s2=rcb_tt.BASE_AMAX,
                             max_jerk_m_s3=rcb_tt.BASE_JMAX,
                             stance=("high level, an act without `base`: the base moves only as much as needed to "
                                     "bring the contact within 0.25 m sideways and 0.10 m in depth of the point 0.45 m "
                                     "in front of the base, arriving at rest 5 steps before the contact (or as far as "
                                     "it gets)")),
                   cameras=cams,
                   image="2 rows (behind, side) x 4 columns (camera frames 40 ms apart, oldest left); tile 480 x 360",
                   image_layout=IMAGE_LAYOUT,
                   frame="your robot's base is at base_xy (home (0, -1.75), z = 0 at the table top) facing +y; your "
                         "half is y < 0; table top z = 0, |x| <= 0.7625, |y| <= 1.37, net at y = 0 (top z = 0.1525); "
                         "every position you are given or send is in this frame",
                   serve=dict(toss="{'type':'toss','pos':[x,y,z],'height':H}", toss_rest_s=0.1, height_min=0.16,
                              height_max=1.0, court="any (singles: no service court)",
                              toss_point="behind your end line and above the table: y <= -1.39, 0.02 <= z <= 0.9, "
                                         "within 0.9 m of your base horizontally",
                              opens_after_point_s=0.8, toss_within_s=5.0, delay_faults_to_lose=3,
                              lets_in_a_row_max=2,
                              rules="strike the toss as it falls, behind your end line and above the table; it must "
                                    "bounce on your court, then directly on your opponent's; a net touch on an "
                                    "otherwise good service is a let, at most 2 in a row: your 3rd service let since "
                                    "the last point scored is a failed service (your opponent's point)"),
                   calls={"observe": "{} -> the state + the newest camera frames (observation.image_png_b64)",
                          "act": (action_high.ACT_CALL if cfg.action_level == "high" else action_low.ACT_CALL),
                          "wait": "{'dt': game seconds, 0 < dt <= 1}"})
        if isinstance(m, TTMatch):
            out["match"] = dict(win_points=5, win_by=2, cap_points=7, expedite_returns=13, opponent_level=m.level,
                                first_server="you",
                                serves="the players serve (ITTF 2.6, 2.13.3): you serve the first 2 points, the "
                                       "opponent the next 2, ...; from 4:4 one each",
                                format="first to 5; from 4:4 lead by 2, up to 7 (at 6:6 the next point wins)")
        else:
            D = m.D
            out["match"] = dict(win_points=D.WIN_POINTS, win_by=D.WIN_BY, cap_points=D.CAP_POINTS,
                                expedite_returns=D.EXPEDITE_RETURNS,
                                first_server="you" if D.FIRST_SERVER == seat else "opponent",
                                serves="the players serve (ITTF 2.6, 2.13.3): the first server serves the first 2 "
                                       "points, the other the next 2, ...; from 4:4 one each",
                                format=f"first to {D.WIN_POINTS}; from {D.WIN_POINTS - 1}:{D.WIN_POINTS - 1} lead by "
                                       f"{D.WIN_BY}, up to {D.CAP_POINTS} (at {D.CAP_POINTS - 1}:{D.CAP_POINTS - 1} "
                                       "the next point wins)")
        if cfg.action_level == "low":
            import robot_model
            mm = m.R.s.m if isinstance(m, TTMatch) else m.g.m        # the duel: robot A's chain (= B's, own frame)
            out.update(action_interface="joint position targets at 100 Hz; no IK or stroke planner (your own frame: "
                                        "the same kinematic chain for both duel seats)",
                       kinematics=action_low.kinematics(mm), limits=action_low.limits(_rows(m).s),
                       robot_model={"robot_only_xml": robot_model.robot_only_xml(),
                                    "note": "the arm + paddle cut out of the simulator's scene (MJCF; the mesh files "
                                            "are MuJoCo Menagerie panda_nohand's); nothing of the world"},
                       toolkit=toolkit_spec())
            out["action_interface"] = ("joint position targets at 100 Hz; no stroke planner or hit skill (your toolkit "
                                       "has an optional kinematics library and a servo model, see toolkit; your own "
                                       "frame: the same kinematic chain for both duel seats)")
        lo = _decl()["modes"]["low"]
        out["skill_contract"] = HIT.describe(lo["deliverable"] if cfg.action_level == "low" else None)
        if cfg.action_level == "low":
            out["skill_contract"]["practice_requests"] = lo["cases"]["practice_path"]
            layer = inloop_layer()
            if layer is not None and seat in layer.loops:          # the skill in the loop (sport.toml [modes.low.inloop])
                il = lo["inloop"]
                out["calls"]["act"] = ("{'type':'hit','t':T,'pos':[x,y,z],'normal':[nx,ny,nz],'vel':[vx,vy,vz]} (your "
                                       f"{lo['deliverable']['path']} makes the stroke) | " + action_low.ACT_CALL)
                out["skill_in_loop"] = {
                    "skills": list(il.get("skills") or lo["implements"]), "deliverable": lo["deliverable"]["path"],
                    "step_every_steps": int(il.get("step_every", 2)), "free": list(il.get("free") or []),
                    "joint_commands": il.get("raw_rule"),
                    "timing": ("your skill's compute counts: the world runs on while it computes; its command takes "
                               "effect at the first control step after it returns; t counts from state['step'] (the "
                               "step your call arrived); the reply's skill field has the call's sha256, wall_s, "
                               "k_call, ok / error and status (loaded version, load error)"),
                    "reload": "at the start of every point, if the skill's files changed"}
        return out


# ================================================================================================ the skill in the loop
_INLOOP: dict = {}


def _ball_in_play(match, seat) -> bool:
    """A ball in play that the seat's robot may meet: then joint commands are refused (skill in the loop)."""
    if isinstance(match, TTMatch):
        R = match.R
        return bool(R.in_play() and R.leg["state"] in ("incoming", "to_opp", "opp_missed", "rest", "toss", "struck"))
    return match.g.rs.get("state") in ("rest", "live")


def inloop_skill_spec(m=None) -> dict:
    """What every in-loop call of the player's hit receives as `spec` (= the post-match evaluator's skill_spec)."""
    import arm_commands
    R = m.R if isinstance(m, TTMatch) else arm_commands.Core(1, action_low)
    lo = _decl()["modes"]["low"]
    return {"kinematics": action_low.kinematics(R.s.m), "limits": action_low.limits(R.s), "toolkit": toolkit_spec(),
            "skill_contract": HIT.describe(lo["deliverable"])}


def inloop_layer():
    """The low level with `hit` lowered by the player's own /app/output/skill/hit.py (skilleval/inloop.py,
    sport.toml [modes.low.inloop]) when the environment names a seat's skill (RCB_SKILL_INLOOP_<seat>: the seat's
    skill container's socket in a generated task, or a directory; RCB_SKILL_INLOOP_LOG, RCB_SKILL_INLOOP_TIMING), else
    None. Joint commands only while no ball is in play; toss at any time. One layer per process."""
    if "layer" not in _INLOOP:
        from skilleval.inloop import layer_from_env
        _INLOOP["layer"] = layer_from_env(JointLayer(), CONTRACTS, _decl(), spec=inloop_skill_spec, control_dt=DT,
                                          seats=SEATS, raw_allowed=lambda seat, m, cmd: not _ball_in_play(m, seat))
    return _INLOOP["layer"]


def _decl() -> dict:
    import tomllib
    return tomllib.loads((HERE / "sport.toml").read_text())


def toolkit_spec() -> dict:
    """The low level's toolkit as /spec names it (seat/toolkit.toml, the seat's /opt/robot; skilleval/toolkit.py)."""
    import tomllib
    lo = _decl()["modes"]["low"]
    tk = tomllib.loads((HERE / lo["toolkit"]).read_text())
    tools = {t["name"]: t for t in tk["tools"]}
    lib = {n: tools[n] for n in ("ik_library", "servo_model")}
    return {"manifest": lo["toolkit_path"], "id": tk["toolkit"]["id"], "version": tk["toolkit"]["version"],
            "robot_model": tools["robot_model"]["file"],
            **{n: {"file": t["file"], "module": t["module"], "class": t["class"], "version": t["version"],
                   "sha256": t["sha256"], "api": t["api"], "algorithm": t["algorithm"],
                   "use": f"import sys; sys.path.insert(0, '/opt/robot/lib'); from {t['module']} import {t['class']}"}
               for n, t in lib.items()},
            "optional": True, "tools": lo["tools"],
            "not_provided": tk["forbidden"]["skills"], "yours_to_develop": tk["forbidden"]["develop"]}


SPORT = TableTennis()
