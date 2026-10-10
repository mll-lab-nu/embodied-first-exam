"""RoboOlympics sports behind eai-standard/2.3 (docs/PROTOCOL.md §4b; docs/benchmarks/roboolympics.md): the adapter
that puts one RoboOlympics match (a sport plugin under sport/, core/sport.py's contract ②) behind rcb_service's `Sim`
contract. The protocol itself -- the endpoints, RCB1, the realtime clock and its plan, budgets, evidence, crash
recovery, finalize -- is rcb_realtime.py + rcb_service.py, unchanged (copied from HumanoidBench's 2.3 layer).

The world. One control step of the service is one control step of the match (Match.step(), 10 ms of game time), with
one exception, the break: when a unit ends (a point, a rally) the match stands still for BREAK_S of game time -- the
clock keeps running (the service's control steps go on at 1/S of real speed, the agent's plan is consumed), nothing
moves, nothing scores -- and play resumes by itself when the break is over, or at the agent's `ready` row, whichever
comes first. Like a break in a real match: the time passes, the game does not.

Actions. The agent's rows are the sport's own commands (the RoboOlympics action layer of the task's level), one row per
command: table tennis and badminton (high level) `stroke` (the paddle's / racket's state at contact, t seconds after
the command takes effect; the service plans the swing), badminton's `toss` (the serve), `rest` (back to the ready
pose), air hockey (low level) `mallet` (the mallet's target, a row per control step, interpolable) and `stop`; every
sport `ready`. A command takes effect at the control step its row is planned for: the sport's action layer parses it
there, plans it from the state of that step and lowers it to a low-level command (core/sport.py ActionLayer.lower),
which Match.apply() installs before the step runs -- the RoboOlympics realtime service's effect boundary. A row the
sport refuses at that moment (e.g. a toss when it is not your serve) changes nothing and is counted in proprio.

The journal. A sim row is [command id, ready]: the id of the low-level command that took effect at that step (-1:
none), and 1 when the step carries the agent's ready. The low-level commands themselves are kept in
DATA/commands.jsonl (one JSON line per id, written before the row that names it), so the journal plus that table is the
whole record: a replay re-applies exactly the commands the live match applied, at their steps, and never plans again.
The match is bit-exact (the RoboOlympics sports' golden replays), so a crash resumes by replaying the journal and a
fresh-process replay decides the verdict (`success` = a finished match the agent won).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import spec as spec_mod  # noqa: E402
from core.outcome import decide  # noqa: E402
from core.sport import FINISHED, UNIT_OVER, MatchConfig, Refused, parse_action  # noqa: E402

BREAK_S = 12.0                     # game seconds of the break after every unit (120 s of wall time at S = 10)
NAN = float("nan")
READY_DOC = ("end the break now (between units only; ignored during play): play resumes at the next control step "
             "(the row's value is ignored; put your review in submit's note)")


def load_plugin(path: str):
    """The sport's plugin module at `path` (its directory first on sys.path, so its simulator modules import); its
    SPORT is the sport."""
    path = os.path.abspath(path)
    if os.path.dirname(path) not in sys.path:
        sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("ro_plugin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _f(x, default=NAN) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _json(x):
    """JSON-exact Python values: what DATA/commands.jsonl holds, so the live match applies what a replay reads back."""
    return json.loads(json.dumps(x, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))


def _clip_box(row, i, lo, hi, name, out, k):
    v = float(row[i])
    c = min(max(v, lo), hi)
    if c != v:
        out.append({"row": k, "index": i, "reason": f"{name} clipped to [{lo:g}, {hi:g}]"})
    row[i] = c


def _clip_norm(row, sl, cap, name, out, k):
    v = np.asarray(row[sl], float)
    n = float(np.linalg.norm(v))
    if n > cap:
        row[sl] = v * (cap / n)
        out.append({"row": k, "index": sl.start, "reason": f"|{name}| = {n:.3f} scaled to {cap:g}"})


def _heard(o: dict, names: dict) -> list:
    """The first time of each heard event (seconds on the current ball's clock), NaN if not heard."""
    out = []
    for key in names.values():
        out.append(next((_f(h.get("t")) for h in o.get("heard") or [] if h.get("event") == key), NAN))
    return out


def _last_point(points, you="you") -> float:
    if not points:
        return NAN
    w = points[-1].get("winner")
    return 1.0 if w == you else 0.0 if w in (None, "let") else -1.0


# ================================================================================================ per-sport profiles
class _Profile:
    """What differs between the sports: the agent's action types (as rows), their limits, the proprio columns, the
    cameras and how they are drawn."""
    types: dict = {}
    interp: tuple = ()
    cams: dict = {}
    drop: tuple = ()                   # sport.toml [spec] / Sport.spec() entries about RoboOlympics' own interface
    rules: dict = {}                   # ... and what replaces them here

    def __init__(self, sim):
        self.sim = sim

    def body(self, typ, row):          # an agent row -> the sport's act body (None: nothing new)
        raise NotImplementedError

    def clip(self, typ, rows):
        return rows, []

    def command(self, typ):
        """The command of this type in force (rcb_realtime: an interpolable target's chunk is interpolated from it, and
        it is held through a gap before the chunk's `at`): for a command that is not a target there is none, zeros,
        which to_sim reads as no command. No agent row is all zeros after clip() (Olympics.clip). The service never
        interpolates or repeats a command that is not a target: a gap before one is held steps (hold())."""
        return np.zeros(int(self.types[typ]["dim"]))

    def proprio(self) -> list:
        raise NotImplementedError

    def images(self, cams) -> dict:
        raise NotImplementedError


def _stroke_type(what, t_max, box, extra=""):
    return {"dim": 10, "layout": ["t", "x", "y", "z", "nx", "ny", "nz", "vx", "vy", "vz"],
            "units": "s, m, unit-free normal, m/s (your frame)",
            "limits": {"t": [0.0, t_max], **box, "normal": "non-zero", "speed_max": 8.0},
            "semantics": (f"the {what}'s state at contact t seconds after the command takes effect: centre x y z, face "
                          f"normal nx ny nz (pointing where the ball should go), velocity vx vy vz; it replaces the "
                          f"stroke under way; the service plans the swing (IK, joint speed limits) and the robot goes "
                          f"back to its ready pose after it. Out-of-range values are clipped (meta.clipped){extra}"),
            "interpolable": False}


class TableTennis(_Profile):
    types = {
        "stroke": _stroke_type("paddle blade", 2.5, {"x": [-1.2, 1.2], "y": [-2.5, -0.5], "z": [0.0, 1.2]},
                               "; the delivered state scatters by about 4 mm, 0.6 degrees and 2 %"),
        "rest": {"dim": 1, "layout": ["unused"], "interpolable": False,
                 "semantics": "cancel the stroke under way: the arm returns to its ready pose (the value is ignored)"},
        "ready": {"dim": 1, "layout": ["unused"], "interpolable": False, "semantics": READY_DOC}}
    drop = ("duel", "observation", "action_high", "action_low", "real_time", "scatter_and_seed")
    rules = {"scatter": "the serves, the opponent's returns and your strokes' execution scatter are drawn from the "
                        "task's frozen seed (never shown)"}
    HEARD = {"opp_bounce": "bounce on the opponent's half", "own_bounce": "bounce on your half", "net": "net",
             "paddle": "paddle", "robot": "robot", "floor": "floor"}
    layout = (["score_you", "score_opponent", "point", "ball_is_serve", "t_since_played", "serve_in_s",
               "ball_in_play", "ball_coming", "ball_going"]
              + [f"heard_{k}_t" for k in HEARD]
              + [f"q{i}" for i in range(1, 8)] + ["paddle_x", "paddle_y", "paddle_z", "paddle_nx", "paddle_ny", "paddle_nz"]
              + ["stroke_active", "stroke_contact_in_s", "stroke_speed_scale", "stroke_blade_error_m",
                 "stroke_normal_error_deg", "stroke_ik_residual", "last_point_won"])

    def __init__(self, sim):
        super().__init__(sim)
        import match
        self.cams = {c["name"]: dict(c, fovy_deg=45.0, hw=[360, 480], focal_px=434.6, principal_point_px=[240, 180])
                     for c in match.Match.CAM_INFO}
        self.view = None

    def body(self, typ, row):
        if typ == "rest":
            return {"type": "none"}
        r = [float(x) for x in row]
        return {"type": "act", "t": r[0], "pos": r[1:4], "normal": r[4:7], "vel": r[7:10]}

    def clip(self, typ, rows):
        out = []
        if typ != "stroke":
            return rows, out
        rows = np.array(rows, dtype=np.float64)
        for k, row in enumerate(rows):
            _clip_box(row, 0, 0.01, 2.5, "t", out, k)
            for i, (lo, hi) in zip((1, 2, 3), ((-1.2, 1.2), (-2.5, -0.5), (0.0, 1.2))):
                _clip_box(row, i, lo, hi, "xyz"[i - 1], out, k)
            if np.linalg.norm(row[4:7]) < 1e-6:
                row[4:7] = [0.0, 1.0, 0.0]
                out.append({"row": k, "index": 4, "reason": "a zero normal replaced by (0, 1, 0)"})
            _clip_norm(row, slice(7, 10), 8.0, "vel", out, k)
        return rows, out

    def proprio(self):
        m = self.sim.m
        o = m.observe(self.sim.seat)
        R = m.R
        bs = o.get("ball_state")
        cmd = o.get("command")
        la = getattr(R, "_last_act", None) or {}
        active = isinstance(cmd, dict)
        return ([_f(o["score"]["you"]), _f(o["score"]["opponent"]), _f(o.get("point")),
                 1.0 if o.get("ball") == "serve" else 0.0, _f(o.get("t_since_played")), _f(o.get("serve_in_s"), 0.0),
                 float(bool(o.get("ball_in_play"))), float(bs == "coming to you"), float(bs == "going to the opponent")]
                + _heard(o, self.HEARD) + [_f(x) for x in o["q"]] + [_f(x) for x in o["paddle_pos"]]
                + [_f(x) for x in o["paddle_normal"]]
                + [float(active), _f(cmd.get("contact_in_s")) if active else NAN,
                   _f(la.get("speed_scale")) if active else NAN, _f(la.get("blade_error_m")) if active else NAN,
                   _f(la.get("normal_error_deg")) if active else NAN, _f(la.get("ik_residual")) if active else NAN,
                   _last_point(R.points)])

    def images(self, cams):
        if self.view is None:
            self.view = self.sim.mod.MatchView()
        import match
        R = self.sim.m.R
        names = list(self.cams)
        q, ox = R.s.d.qpos.copy(), R.opp_x()
        text = f"k={R.k} t={R.t_since_launch():.2f}s"
        return {c: self.view.tile(names.index(c), q, text, lambda scn, o=ox: match.Match._extra_geoms(None, scn, o), ox)
                for c in cams}


class Badminton(_Profile):
    types = {
        "stroke": _stroke_type("racket head", 5.0, {"x": [-3.4, 3.4], "y": [-7.5, -0.3], "z": [0.2, 3.0]},
                               "; it takes effect spec.rules.act.lead_steps control steps after its row's step (the "
                               "planning time), and t counts from then; a stroke or toss sent before the previous one "
                               "took effect is refused"),
        "toss": {"dim": 4, "layout": ["x", "y", "z", "height"], "units": "m (your frame)", "interpolable": False,
                 "limits": {"z": [0.5, 1.8], "height": [0.0, 0.5], "y_max": -0.5, "reach_from_base": 1.0},
                 "semantics": ("your serve: the shuttle appears at x y z (from rest, or rising `height` straight up) "
                               "when the command takes effect (the same lead as a stroke); only the server, once per "
                               "serve, from the step the receiver is ready (proprio serve_phase = 1, open); then hit "
                               "it with a stroke (which may be sent before the toss)")},
        "rest": {"dim": 1, "layout": ["unused"], "interpolable": False,
                 "semantics": "cancel the stroke under way: the robot returns to its ready pose, the base home"},
        "ready": {"dim": 1, "layout": ["unused"], "interpolable": False, "semantics": READY_DOC}}
    drop = ("duel", "observation", "lowlevel", "act")
    PHASES = {"waiting": 0.0, "open": 1.0, "tossed": 2.0, "done": 3.0}
    layout = (["score_you", "score_opponent", "point", "you_serve", "serve_court_right", "serve_phase",
               "serve_opens_in_s", "serve_deadline_in_s", "serve_tossed_at_step", "ball_kind", "t_since_played",
               "ball_in_play", "ball_not_served", "ball_tossed", "ball_coming", "ball_going",
               "base_x", "base_y"] + [f"q{i}" for i in range(1, 8)]
              + ["racket_x", "racket_y", "racket_z", "racket_nx", "racket_ny", "racket_nz",
                 "stroke_active", "stroke_contact_in_s", "stroke_traj_steps_left", "stroke_pending_effect_step",
                 "stroke_head_speed_limited", "stroke_pose_not_delivered", "last_point_won"])

    def __init__(self, sim):
        super().__init__(sim)
        import bm
        FOCAL_PX = sim.mod.FOCAL_PX
        self.TOSS_Z, self.TOSS_H = tuple(bm.TOSS_Z), float(bm.TOSS_H_MAX)
        self.types = dict(self.types)
        self.types["toss"] = dict(self.types["toss"], limits={"z": list(bm.TOSS_Z), "height": [0.0, bm.TOSS_H_MAX],
                                                              "y_max": -0.5, "reach_from_base": bm.TOSS_REACH})
        lead = sim.mod.lead_steps(sim.cfg.slowdown)
        self.rules = {"act": {"lead_steps": lead, "lead_game_s": round(lead * bm.CONTROL_DT, 4),
                              "rule": (f"a stroke, a toss or a rest takes effect {lead} control steps after the step "
                                       "its row is planned for (the stroke is planned meanwhile; proprio "
                                       "stroke_pending_effect_step shows it); a stroke's t counts from that effect "
                                       "step; another stroke, toss or rest planned before then is refused")},
                      "serve": {"command": ("a `toss` row: the shuttle appears at x y z when the command takes effect "
                                            "(the same lead as a stroke) and rises `height` straight up (0: released "
                                            "from rest); then hit it with a stroke (it may be sent before the toss)"),
                                "phases": ("proprio serve_phase: 0 waiting (the receiver is getting ready), 1 open "
                                           "(toss now), 2 tossed, 3 done")}}
        w, h = bm.Match.TILE
        self.cams = {c["name"]: dict(c, fovy_deg=45.0, hw=[h, w], focal_px=FOCAL_PX, principal_point_px=[w / 2, h / 2])
                     for c in bm.Match.cam_info()}
        self.view = None

    def body(self, typ, row):
        r = [float(x) for x in row]
        if typ == "rest":
            return {"type": "none"}
        if typ == "toss":
            return {"type": "toss", "pos": r[0:3], "height": r[3]}
        return {"type": "act", "t": r[0], "pos": r[1:4], "normal": r[4:7], "vel": r[7:10]}

    def clip(self, typ, rows):
        out = []
        rows = np.array(rows, dtype=np.float64)
        if typ == "stroke":
            for k, row in enumerate(rows):
                _clip_box(row, 0, 0.01, 5.0, "t", out, k)
                for i, (lo, hi) in zip((1, 2, 3), ((-3.4, 3.4), (-7.5, -0.3), (0.2, 3.0))):
                    _clip_box(row, i, lo, hi, "xyz"[i - 1], out, k)
                if np.linalg.norm(row[4:7]) < 1e-6:
                    row[4:7] = [0.0, 1.0, 0.0]
                    out.append({"row": k, "index": 4, "reason": "a zero normal replaced by (0, 1, 0)"})
                _clip_norm(row, slice(7, 10), 8.0, "vel", out, k)
        elif typ == "toss":
            for k, row in enumerate(rows):
                _clip_box(row, 1, -7.5, -0.5, "y", out, k)
                _clip_box(row, 2, self.TOSS_Z[0], self.TOSS_Z[1], "z", out, k)
                _clip_box(row, 3, 0.0, self.TOSS_H, "height", out, k)
        return rows, out

    def proprio(self):
        m = self.sim.m
        o = m.observe(self.sim.seat)
        sv = o.get("serve") or {}
        bs = str(o.get("ball_state") or "")
        cmd = o.get("command")
        active = isinstance(cmd, dict) and "contact_in_s" in cmd
        notes = str(cmd.get("stroke") or "") if active else ""
        pend = o.get("pending_commands") or []
        kind = {"serve": 0.0, "your serve": 1.0}.get(o.get("ball"), 2.0)
        return ([_f(o["score"]["you"]), _f(o["score"]["opponent"]), _f(o.get("point")), float(bool(o.get("you_serve"))),
                 float(sv.get("court") == "right"), self.PHASES.get(sv.get("phase"), NAN), _f(sv.get("opens_in_s")),
                 _f(sv.get("deadline_in_s")), _f(sv.get("tossed_at_step")), kind, _f(o.get("t_since_played")),
                 float(bool(o.get("ball_in_play"))), float(bs == "not yet served"), float(bs.startswith("tossed")),
                 float(bs == "coming to you"), float(bs == "going to the opponent")]
                + [_f(x) for x in o["robot_base_xy"]] + [_f(x) for x in o["q_arm"]] + [_f(x) for x in o["racket_pos"]]
                + [_f(x) for x in o["racket_normal"]]
                + [float(active), _f(cmd.get("contact_in_s")) if active else NAN,
                   _f(cmd.get("traj_steps_left"), 0.0) if isinstance(cmd, dict) else 0.0,
                   _f(pend[0].get("takes_effect_at_step")) if pend else NAN,
                   float("head speed limited" in notes), float("pose not delivered" in notes),
                   _last_point(m.g.points)])

    def images(self, cams):
        if self.view is None:
            self.view = self.sim.mod.Views(True, "A")
        g = self.sim.m.g
        sn = {"qpos": g.s.d.qpos.copy(), "sh": tuple(float(x) for x in g.s.sh_p),
              "shv": tuple(float(x) for x in g.s.sh_v), "opp": [float(x) for x in g.opp_xy()],
              "k": int(g.k), "t": float(g.t_since_launch())}
        names = list(self.cams)
        return {c: self.view.tile(names.index(c), sn) for c in cams}


class AirHockey(_Profile):
    types = {
        "mallet": {"dim": 2, "layout": ["x", "y"], "units": "m (the table frame)", "interpolable": True,
                   "semantics": ("the mallet centre's target; the robot drives the mallet there along a speed- and "
                                 "acceleration-limited path (spec.sport.mallet_path) and holds it until replaced; "
                                 "own half only: a target outside the workspace (spec.sport.workspace) is moved to "
                                 "its nearest point (meta.clipped)")},
        "stop": {"dim": 1, "layout": ["unused"], "interpolable": False,
                 "semantics": "the mallet stops where it is (its target becomes its position)"},
        "ready": {"dim": 1, "layout": ["unused"], "interpolable": False, "semantics": READY_DOC}}
    interp = ("mallet",)
    drop = ("real_time", "action", "observation")
    rules = {"review": ("every goal, foul or dead puck ends the rally: both mallets return home, the break follows "
                        "(spec.break), then the next rally starts")}
    HOW = {"goal": 1.0, "seven_second_foul": 2.0, "dead_puck": 3.0, "time_cap": 4.0}
    layout = (["score_you", "score_opponent", "rally", "t_play", "play_time_left_s",
               "mallet_x", "mallet_y", "mallet_z", "target_x", "target_y"]
              + [f"q{i}" for i in range(1, 8)] + ["q_striker1", "q_striker2"]
              + [f"qd{i}" for i in range(1, 8)] + ["qd_striker1", "qd_striker2"]
              + ["last_rally_how", "last_rally_scored", "last_rally_fouled", "last_rally_next_puck"])

    def __init__(self, sim):
        super().__init__(sim)
        from renderers.base import CameraDef
        self.P = sim.mod
        self.camdefs = [CameraDef.from_dict(c) for c in sim.m.cameras(sim.seat)]
        self.cams = {c.name: dict(c.to_dict(), **c.intrinsics(), hw=[c.height, c.width]) for c in self.camdefs}
        self.renderer = None

    def body(self, typ, row):
        h = self.sim.m.h
        if typ == "stop":
            return {"type": "none"}
        x, y = float(row[0]), float(row[1])
        cur = h.commands.get(self.sim.seat) if isinstance(h.commands, dict) else None
        if cur is not None and abs(float(cur[0]) - x) < 1e-9 and abs(float(cur[1]) - y) < 1e-9:
            return None                                  # the target in force: nothing new
        return {"type": "target", "x": x, "y": y}

    def clip(self, typ, rows):
        out = []
        rows = np.array(rows, dtype=np.float64)
        if typ != "mallet":
            return rows, out
        H = self.P.H
        for k, row in enumerate(rows):
            w = H.workspace(self.sim.seat, row)
            if not H.in_workspace(self.sim.seat, w, eps=0.0):    # the box-then-radial clip may land a hair outside
                w = H.workspace(self.sim.seat, [w[0] * 0.999999, w[1] * 0.999999])
            w = [round(float(w[0]), 6), round(float(w[1]), 6)]
            if abs(w[0] - row[0]) > 1e-9 or abs(w[1] - row[1]) > 1e-9:
                out.append({"row": k, "index": 0, "reason": "outside the mallet workspace: moved to its nearest point"})
                row[0], row[1] = w
        return rows, out

    def command(self, typ):
        if typ == "mallet":
            h = self.sim.m.h
            return np.asarray(h.commands[self.sim.seat], np.float64)
        return super().command(typ)

    def proprio(self):
        m = self.sim.m
        o = m.observe(self.sim.seat)
        h = m.h
        sc = h.scores()
        last = h.results[-1] if h.results else None
        side = lambda s: NAN if last is None else (1.0 if s == "A" else -1.0 if s == "B" else 0.0)  # noqa: E731
        return ([_f(sc["A"]["points"]), _f(sc["B"]["points"]), _f(o["rally"]), _f(o["t_play"]),
                 _f(o["play_time_left_s"])] + [_f(x) for x in o["own"]["mallet_xyz"]]
                + [_f(x) for x in o["own"]["command"]] + [_f(x) for x in o["own"]["joint_position"]]
                + [_f(x) for x in o["own"]["joint_velocity"]]
                + [NAN if last is None else self.HOW.get(last["how"], 5.0), side(last and last["winner"]),
                   side(last and last["guilty"]), side(last and last["next"])])

    def images(self, cams):
        if self.renderer is None:
            import renderers
            from core.observe import players_scene
            sim = self.sim
            self.renderer = renderers.load(sim.cfg.renderer or renderers.DEFAULT)(
                players_scene(sim.sport, sim.plugin, sim.cfg))
        imgs = self.renderer.render(self.sim.m.render_state(), self.camdefs)
        return {c.name: img for c, img in zip(self.camdefs, imgs) if c.name in cams}


PROFILES = {"tabletennis": TableTennis, "badminton": Badminton, "airhockey": AirHockey}


# ================================================================================================ the Sim contract
class Olympics:
    """One RoboOlympics match against the scripted opponent (seat A) behind rcb_service.Sim (module docstring)."""

    raw_dim = 2                                   # [command id (-1: none), ready]
    depth_cameras: tuple = ()

    def __init__(self, plugin: str, cfg: MatchConfig, data: str | None = None, task_text: str = "",
                 episode_text: str = "", break_s: float = BREAK_S):
        self.plugin, self.cfg, self.data = os.path.abspath(plugin), cfg, data
        self.mod = load_plugin(self.plugin)
        self.sport = self.mod.SPORT
        self.decl = spec_mod.load(self.plugin)
        self.seat = cfg.seats[0]
        self.task_text, self.episode_text = task_text, episode_text
        self.commands: list = []
        self.cmd_path = os.path.join(data, "commands.jsonl") if data else None
        if self.cmd_path and os.path.exists(self.cmd_path):          # a resumed service: the table so far
            with open(self.cmd_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        break                            # a line cut by a crash: no journal row names it
                    if rec.get("id") == len(self.commands):
                        self.commands.append(rec["low"])
        self._new_match()
        self.control_dt = float(self.m.dt)
        self.break_steps = max(1, int(round(break_s / self.control_dt)))
        self.max_control_steps = 10 ** 8               # no step cap: the match ends by its rules, else the wall clock
        self.profile = PROFILES[self.sport.name](self)
        self.cameras = tuple(self.profile.cams)
        self.proprio_layout = (["match_step", "break", "break_left_s", "finished"] + list(self.profile.layout)
                               + ["commands_applied", "commands_refused", "last_refused_step"])

    def _new_match(self):
        self.m = self.sport.build(self.cfg)
        self.layer = self.sport.action_layer(self.cfg.action_level)
        self.steps = 0                                 # control steps of this episode, breaks included
        self.in_break, self.break_left, self.breaks = False, 0, []
        self.finished = self.won = False
        self.applied = self.refused = self.dropped = 0
        self.last_refused = -1

    # ------------------------------------------------------------------ facts
    def spec(self) -> dict:
        sport = dict(self.decl.get("spec") or {})              # as RoboOlympics' public_spec: sport.toml, then Sport.spec()
        sport.update(self.sport.spec(self.cfg, self.seat, self.m))
        for k in ("calls", "image", "image_layout", "cameras", "action_interface") + tuple(self.profile.drop):
            sport.pop(k, None)
        for k, v in self.profile.rules.items():
            sport[k] = {**sport[k], **v} if isinstance(v, dict) and isinstance(sport.get(k), dict) else v
        if (self.decl.get("tiebreaks") or {}).get("text"):
            sport["tiebreaks"] = self.decl["tiebreaks"]["text"]
        types = {k: {kk: vv for kk, vv in v.items() if kk != "interpolable"} for k, v in self.profile.types.items()}
        s = self.decl.get("sport") or {}
        return {"simulator": "RoboOlympics on MuJoCo 3.3.7 (CPU)", "sport": s.get("name", self.sport.name),
                "title": s.get("title"), "revision": self.sport.revision, "robot": sport.pop("robot", None),
                "task_text": self.task_text, "episode": self.episode_text,
                "match": {"format": self.cfg.format, "opponent_level": self.cfg.level, "action_level":
                          self.cfg.action_level, "you": self.seat},
                "action_types": types, "cameras": self.profile.cams, "rules": sport,
                "break": {"game_s": self.break_steps * self.control_dt, "control_steps": self.break_steps,
                          "rule": ("after every unit (a point, a rally) the match stands still for this much game "
                                   "time: the clock runs on (control steps, wall time, your plan), nothing moves and "
                                   "nothing scores; play resumes by itself at the end of the break, or at the control "
                                   "step of your `ready` row. proprio: break (1 during it), break_left_s")},
                "proprio_notes": ("one row per frame, columns proprio_layout; NaN = not applicable now; match_step = "
                                  "the match's own control step (it stands still in a break; meta.control_steps "
                                  "counts every step); times in game seconds; positions in your frame")}

    def interpolable(self, typ: str) -> bool:
        return typ in self.profile.interp

    # ------------------------------------------------------------------ observation
    def images(self, cameras, depth):
        return self.profile.images(list(cameras)), {}

    def proprio(self) -> np.ndarray:
        own = [float(self.m.k), float(self.in_break), self.break_left * self.control_dt if self.in_break else 0.0,
               float(self.finished)]
        return np.asarray(own + self.profile.proprio() + [float(self.applied), float(self.refused),
                                                          float(self.last_refused)], np.float32)

    # ------------------------------------------------------------------ actions
    def clip(self, typ, rows):
        """The profile's limits; a one-value command (rest, stop, ready: the value is ignored) becomes 1, so that no
        agent row is all zeros, which to_sim reads as no command (command())."""
        try:
            if int(self.profile.types.get(typ, {}).get("dim", 0)) == 1 and typ not in self.profile.interp:
                return np.ones((len(rows), 1)), []
            return self.profile.clip(typ, rows)
        except Exception as exc:  # noqa: BLE001 -- clip must never fail a request that passed the checks
            return np.asarray(rows, np.float64), [{"row": 0, "index": 0, "reason": f"unchecked: {exc!r}"[:200]}]

    def command(self, typ):
        try:
            return self.profile.command(typ)
        except Exception:  # noqa: BLE001
            return np.zeros(int(self.profile.types.get(typ, {"dim": 1})["dim"]))

    def hold(self):
        return "hold", np.zeros(1)

    def to_sim(self, typ, row) -> np.ndarray:
        """At the step the row is planned for (rcb_service._step, right before step()): the row as a sim row. A
        command is parsed, planned and lowered here, from this step's state, and enters the command table. A held step
        (hold(): the plan ran out, or a gap in it) and an all-zero row of a command type (command(); clip() leaves no
        agent row so) are no command."""
        if typ not in self.profile.interp and not np.any(np.asarray(row, dtype=np.float64)):
            return np.array([-1.0, 0.0])
        if typ == "ready":
            return np.array([-1.0, 1.0])
        if typ not in self.profile.types or self.finished:
            return np.array([-1.0, 0.0])
        if self.in_break:
            self.dropped += 1
            return np.array([-1.0, 0.0])
        body = self.profile.body(typ, row)
        if body is None:
            return np.array([-1.0, 0.0])
        rec = {"id": len(self.commands), "step": self.steps, "match_k": int(self.m.k), "type": typ,
               "row": [float(x) for x in row]}
        try:
            cmd = parse_action(self.layer, self.seat, body, self.m, {})
            job = self.layer.snapshot(self.seat, cmd, self.m, self.applied + self.refused + 1)
            prepared = self.layer.prepare(job) if job is not None else None
            low, info = self.layer.lower(self.seat, cmd, prepared, self.m)
        except Refused as exc:
            self.refused += 1
            self.last_refused = int(self.m.k)
            self._log({**rec, "id": None, "refused": str(exc)[:300]})
            return np.array([-1.0, 0.0])
        rec.update(low=_json(low), info=_json(info))
        self.commands.append(rec["low"])
        self._log(rec)
        return np.array([float(rec["id"]), 0.0])

    def _log(self, rec):
        if self.cmd_path:
            with open(self.cmd_path, "a") as f:
                f.write(json.dumps(rec, default=float) + "\n")
                f.flush()

    def step(self, row) -> tuple[bool, bool, dict]:
        cid, ready = int(round(float(row[0]))), float(row[1]) > 0.5
        self.steps += 1
        if self.finished:
            return True, self.won, {}
        if self.in_break:
            if ready or self.break_left <= 1:
                self.in_break = False
                self.breaks[-1].update(end=self.steps, by="ready" if ready else "time")
                self.m.resume()
            else:
                self.break_left -= 1
            return False, False, {}
        if cid >= 0:
            info = self.m.apply(self.seat, self.commands[cid]) or {}
            if isinstance(info, dict) and "rejected" in info:
                self.refused += 1
                self.last_refused = int(self.m.k)
            else:
                self.applied += 1
        self.m.step()
        ph = self.m.phase()
        if ph.state == FINISHED:
            self.finished = True
            out = decide(self.m, None, None, self.cfg.side_list(), self.cfg.side_of)
            self.won = out.winner == self.cfg.side_of(self.seat)
            return True, self.won, {}
        if ph.state == UNIT_OVER:
            self.in_break, self.break_left = True, self.break_steps
            self.breaks.append({"start": self.steps, "match_k": int(self.m.k), "reason": ph.reason})
        return False, False, {}

    # ------------------------------------------------------------------ episode
    def reset(self) -> None:
        self._new_match()
        self.profile = PROFILES[self.sport.name](self)

    def state_sha(self) -> str:
        own = json.dumps([self.steps, self.in_break, self.break_left, self.finished, self.won], sort_keys=True)
        return hashlib.sha256((self.m.state_digest() + own).encode()).hexdigest()

    def summary(self) -> dict:
        out = decide(self.m, None, None, self.cfg.side_list(), self.cfg.side_of)
        scores = self.m.scores()
        you = self.cfg.side_of(self.seat)
        them = [s for s in scores if s != you]
        return {"sport": self.sport.name, "revision": self.sport.revision, "finished": self.finished,
                "won": bool(self.finished and out.winner == you), "winner": out.winner, "decided_by": out.decided_by,
                "scores": scores, "points_for": scores.get(you), "points_against": scores.get(them[0]) if them else None,
                "match_steps": int(self.m.k), "control_steps": self.steps, "breaks": self.breaks,
                "commands_applied": self.applied, "commands_refused": self.refused,
                "rows_dropped_in_breaks": self.dropped, "cfg": self.cfg.to_json(), "break_steps": self.break_steps,
                "sport_fields": _json(self.m.final_fields())}

    # ------------------------------------------------------------------ the record, the replay, the video
    def save_trajectory(self, rows, path, meta) -> None:
        np.savez_compressed(path, rows=np.asarray(rows, np.float64).reshape(-1, self.raw_dim),
                            commands=np.array(json.dumps(self.commands)), cfg=np.array(json.dumps(self.cfg.to_json())),
                            break_steps=np.array(self.break_steps), meta=np.array(json.dumps(meta, default=str)),
                            layout=np.array(json.dumps(["command_id", "ready"])))

    def _sub(self, mode: str, rows, out: str) -> dict:
        """A fresh process (python rcb_olympics.py MODE ...): the replay never shares state with the live match."""
        fd, tmp = tempfile.mkstemp(suffix=".npz", dir=self.data or None)
        os.close(fd)
        try:
            self.save_trajectory(rows, tmp, {"for": mode})
            env = dict(os.environ, RO_TASK_TEXT=self.task_text, RO_EPISODE_TEXT=self.episode_text)
            r = subprocess.run([sys.executable, os.path.abspath(__file__), mode, self.plugin, tmp, out],
                               capture_output=True, text=True, env=env, timeout=3600)
            if r.returncode:
                raise RuntimeError(f"{mode} failed: {r.stderr[-1500:]}")
            return json.loads(r.stdout.strip().splitlines()[-1])
        finally:
            os.unlink(tmp)

    def verify(self, rows) -> dict:
        out = os.path.join(self.data, "match.json") if self.data else os.devnull
        rep = self._sub("replay", rows, out)
        return {"success": bool(rep["won"]), "state_sha": rep["state_sha"]}

    def render_video(self, rows, path) -> None:
        self._sub("video", rows, path)


# ================================================================================================ fresh processes
def _rebuild(plugin: str, npz: str) -> tuple[Olympics, np.ndarray]:
    z = np.load(npz)
    cfg = MatchConfig.from_json(json.loads(str(z["cfg"])))
    sim = Olympics(plugin, cfg, None, os.environ.get("RO_TASK_TEXT", ""), os.environ.get("RO_EPISODE_TEXT", ""))
    sim.break_steps = int(z["break_steps"])
    sim.commands = json.loads(str(z["commands"]))
    return sim, np.asarray(z["rows"], np.float64).reshape(-1, sim.raw_dim)


def replay_main(plugin: str, npz: str, out: str) -> dict:
    sim, rows = _rebuild(plugin, npz)
    for row in rows:
        sim.step(row)
    summary = {**sim.summary(), "state_sha": sim.state_sha()}
    with open(out, "w") as f:
        json.dump(summary, f, default=float)
    return {"won": summary["won"], "state_sha": summary["state_sha"], "scores": summary["scores"]}


def video_main(plugin: str, npz: str, out: str, max_frames: int = 1500) -> dict:
    """The replay for humans: the cameras side by side, one frame every 4 control steps of play (game time at real speed:
    25 fps; sparser for a long match, at most about max_frames frames), breaks skipped; the score in the corner.
    Writes out and out.last.png."""
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    sim, rows = _rebuild(plugin, npz)
    every = max(4, math.ceil(len(rows) / max_frames))
    cams = list(sim.cameras)
    w = imageio.get_writer(out, fps=round(1.0 / (every * sim.control_dt)), macro_block_size=8, codec="libx264",
                           output_params=["-pix_fmt", "yuv420p"])
    last, n = None, 0

    def frame():
        imgs = sim.images(cams, False)[0]
        h = max(i.shape[0] for i in imgs.values())
        row = np.concatenate([np.pad(imgs[c], ((0, h - imgs[c].shape[0]), (0, 0), (0, 0))) for c in cams], axis=1)
        im = Image.fromarray(np.ascontiguousarray(row[..., :3]))
        sc = sim.m.scores()
        ImageDraw.Draw(im).text((8, im.height - 16), "  ".join(f"{k} {v}" for k, v in sc.items()), fill=(255, 255, 0))
        return np.asarray(im)

    try:
        for i, row in enumerate(rows):
            was = sim.in_break
            sim.step(row)
            if (not was and i % every == 0) or sim.finished:
                last = frame()
                w.append_data(last)
                n += 1
                if sim.finished:
                    break
        if last is None:
            last = frame()
            w.append_data(last)
            n += 1
    finally:
        w.close()
    Image.fromarray(last).save((out[:-4] if out.endswith(".mp4") else out) + ".last.png")   # replay.last.png
    return {"frames": n, "every": every}


if __name__ == "__main__":
    mode, plugin_path, npz_path, out_path = sys.argv[1:5]
    res = replay_main(plugin_path, npz_path, out_path) if mode == "replay" else video_main(plugin_path, npz_path,
                                                                                            out_path)
    print(json.dumps(res, default=float))
