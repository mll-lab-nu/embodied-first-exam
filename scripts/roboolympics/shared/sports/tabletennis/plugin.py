"""Table tennis on the v0.2 core (docs/framework_zh.md §4.2): the legacy simulator of Season 1, unchanged (sim/), behind
contract ②. Two formats, both action levels, both plays:

  world + referee  match  arm_commands.Core (match.Match: one Franka + paddle against the scripted opponent inside the
                          world; the opponent serves every point; step = Core.rt_advance(1))
                   duel   duel.Duel (two arms, a neutral serve machine, the ITTF referee; step = Duel.advance())
                   A point end freezes the world for the reviews (Phase.review); first to 5 (lead by 2 from 4:4, cap 7).
  actions          low   the arm command layer: traj / slew / hold joint targets (action_low.validate)
                   high  the paddle state at contact (action_high.validate), lowered at the effect boundary to the
                         SAME low-level traj command: match - match.Match.plan_paddle (IK, swing, robot-only rehearsals,
                         seeded scatter) then a slew back to the ready pose; duel - IK off the world lock in the seat's
                         plan worker (workers.prepare), the swing at the boundary (workers.trajectory). The episode
                         holds low-level commands only.
  observation      observe(): own arm, score, heard bounces, the command in force (every position in the seat's own
                   frame); camera_job(): the legacy cameras (behind and beside the seat's robot, 4 frames 40 ms
                   apart), drawn by the sport itself (a frame history is not one renderer state).
Nothing in sim/ is edited: its seed and first receiver come from the config (duel.py reads them as module constants).
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
    """duel.py reads its seed and first receiver from the environment at import (module constants): set both from the
    config, also for a module imported by an earlier match of this process."""
    first = cfg.first or "A"
    os.environ["DUEL_SEED"], os.environ["FIRST_RECEIVER"] = str(cfg.seed), first
    import duel
    duel.SEED, duel.FIRST_RECEIVER = int(cfg.seed), first
    return duel


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
             "ball": "serve" if leg["kind"] == "serve" else "opponent's return", "t_since_played": R.t_since_launch(),
             "heard": heard, "q": st["q"].round(4).tolist(), "paddle_pos": st["paddle_pos"].round(3).tolist(),
             "paddle_normal": st["paddle_normal"].round(3).tolist(),
             "ball_in_play": R.in_play() and leg["state"] in ("incoming", "to_opp", "opp_missed"),
             "ball_state": {"incoming": "coming to you", "to_opp": "going to the opponent",
                            "opp_missed": "going to the opponent", "done": "dead"}.get(leg["state"], leg["state"]),
             "points": [{k: p[k] for k in ("point", "winner", "how", "score")} for p in R.points[-2:]],
             "shots": [{k: r.get(k) for k in ("returned", "summary", "speed_out")} for r in R.results[-2:]]}
        if not R.in_play():
            o["serve_in_s"] = round(max(0.0, (leg["launch"] - R.k) * DT), 3)
        o.update(R.plugin.state(R))                       # the command in force (low level: also qd, q_target)
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
                "points": R.points, "results": R.results, "shots": R.shots, "serves": R.serve_ids,
                "opponent": [lg.get("opp") for lg in R.legs if lg.get("opp")],
                "ladder": ladder.ladder(R.points, R.results, contacts=self.contacts.out)}


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
                 ball="serve" if g.rs["last_hitter"] is None else "return",
                 t_since_played=(g.k - g.rs["played_k"]) * self.dt,
                 serve_in_s=max(0., (g.rs["launch"] - g.k) * self.dt), ball_in_play=g.in_play(),
                 ball_state="coming to you" if g.rs["expect"] == seat else "going to opponent",
                 you_receive_serves=g.rs["receiver"] == seat, q=g.d.qpos[g.qadr[seat]].tolist(),
                 paddle_pos=p.tolist(), paddle_normal=normal.tolist(),
                 command=command if self.level == "high" else g.command_state(seat),
                 points=[{k: v for k, v in pt.items() if k != "receiver"} for pt in g.points[-2:]],
                 heard=[dict(event=heard.get(x["kind"], x["kind"]), t=x["t"] - g.rs["played_k"] * self.dt)
                        for x in g.events[-12:] if x["t"] >= g.rs["played_k"] * self.dt - .011])
        if self.level == "low":
            o.update(qd=g.d.qvel[g.vadr[seat]].round(4).tolist(), q_target=g.target[seat].round(6).tolist())
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
                "first_receiver": self.D.FIRST_RECEIVER, "serves": g.serve_ids}


# ================================================================================================ action levels
class _LowShim:
    """What action_low needs of a simulator (joint ranges, the ready pose), from the duel's model."""

    def __init__(self, g, D):
        self.s = type("S", (), dict(JOINT_LOW=g.JLOW, JOINT_HIGH=g.JHIGH, inst={"q0": D.Q0}))()


def _rows(m):
    return m.R if isinstance(m, TTMatch) else _LowShim(m.g, m.D)


def _vec(n, doc):
    return {"type": "vector", "len": n, "doc": doc}


LOW_SCHEMA = {
    "traj": {"k0": {"type": "integer", "min": 0, "doc": "control step of the first row"},
             "q": {"type": "rows", "len": 7, "max_rows": action_low.MAX_ROWS,
                   "doc": "row i = the 7 joint targets (rad) of control step k0 + i; consecutive rows within the "
                          "per-step speed limit (limits.max_target_step_rad)"}},
    "slew": {"q": _vec(7, "joint goal (rad)"),
             "speed": {"type": "number", "min": 0.0, "max": 1.0, "default": 1.0,
                       "doc": "fraction of each joint's speed limit, (0, 1]"}},
    "hold": {}}
HIGH_SCHEMA = {
    "act": {"t": {"type": "number", "min": 0.0, "max": 2.5, "unit": "s",
                  "doc": "time from the act's effect until contact, 0 < t <= 2.5"},
            "pos": _vec(3, "blade centre at contact (m, your frame): |x| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2"),
            "normal": _vec(3, "blade face normal at contact (non-zero)"),
            "vel": _vec(3, "blade velocity at contact (m/s), |vel| <= 8")},
    "none": {}}


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
        return dec

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
        return dec

    def snapshot(self, seat, cmd, match, ordinal):
        if cmd["type"] == "none" or isinstance(match, TTMatch):
            return None
        g = match.g
        return dict(decision=cmd, point=g.rs["point"], ordinal=ordinal, q=g.d.qpos[g.qadr[seat]].tolist(),
                    target=g.target[seat].tolist())

    def prepare(self, job):
        raise RuntimeError("runs in the plan worker")

    def lower(self, seat, cmd, prepared, match):
        if isinstance(match, TTMatch):
            return self._lower_match(cmd, match.R)
        g = match.g
        if cmd["type"] == "none":
            match.commands[seat] = None
            return {"type": "hold"}, {}
        from workers import trajectory
        prev = g.actions[seat][-2] if (len(g.actions[seat]) >= 2 and
                                       np.array_equal(g.target[seat], g.actions[seat][-1])) else g.target[seat]
        path, info = trajectory(g.target[seat], prev, prepared, cmd["t"], g.JLOW, g.JHIGH)
        match.commands[seat] = dict(pos=cmd["pos"], normal=cmd["normal"], vel=cmd["vel"],
                                    contact_step=g.k + info["contact_steps"])
        info.update(ik_residual=prepared["ik_residual"], speed_scale=prepared["speed_scale"])
        return {"type": "traj", "k0": g.k, "q": [q.tolist() for q in path]}, info

    @staticmethod
    def _lower_match(cmd, R):
        """= action_high.apply at the effect boundary (the legacy service planned there too), with the plan handed
        to the arm command layer as a low-level command instead of being submitted directly."""
        rest = {"type": "slew", "q": [float(x) for x in R.s.inst["q0"]], "speed": REST_SPEED}
        if cmd["type"] == "none":
            R._last_act = None
            R.contact_k = R.k
            return rest, {"stroke": "cleared: the arm returns to the ready pose"}
        T = float(cmd["t"])
        t_hit = (R.k - R.leg["launch"]) * DT + T
        R._ik_seed = R._planned_hit if R.traj_active() else None
        plan, info = R.plan_paddle(t_hit, cmd["pos"], cmd["normal"], cmd["vel"])
        info["T_from_now"] = round(T, 4)
        R.shots.append({"k": R.k, "leg": R.n_our_legs, **{k: info[k] for k in info if k != "paddle_vel_delivered"}})
        if not plan:
            return {"type": "noop"}, info
        R.contact_k = R.k + info["n_swing_steps_available"]
        R._last_act = info
        return {"type": "traj", "k0": R.k, "q": [np.asarray(q, float).tolist() for q in plan], "then": rest}, info

    def reply(self, seat, cmd, info, match):
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
    revision = "wallclock-6+duel-wallclock-4+core-0.2"
    source_dirs = [str(HERE)]
    workers = ("plan", "render")

    def build(self, cfg):
        return TTDuel(cfg) if len(cfg.seats) > 1 else TTMatch(cfg)

    def action_layer(self, level):
        return StrokeLayer() if level == "high" else JointLayer()

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
        return {"reference": bp.Reference, "idle": bp.Idle}

    def spec(self, cfg, seat, m):
        import match
        cams = [dict(c, fovy_deg=45.0, tile_px=[480, 360], focal_px=434.6, principal_point_px=[240, 180],
                     image_right="forward x up") for c in match.Match.CAM_INFO]
        out = dict(robot="franka-panda + paddle (MuJoCo Menagerie panda_nohand)", cameras=cams,
                   image="2 rows (behind, side) x 4 columns (camera frames 40 ms apart, oldest left); tile 480 x 360",
                   image_layout=IMAGE_LAYOUT,
                   frame="your robot's base is at (0, -1.75, 0) facing +y; your half is y < 0; table top z = 0, "
                         "|x| <= 0.7625, |y| <= 1.37, net at y = 0 (top z = 0.1525); every position you are given "
                         "or send is in this frame",
                   calls={"observe": "{} -> the state + the newest camera frames (observation.image_png_b64)",
                          "act": (action_high.ACT_CALL if cfg.action_level == "high" else action_low.ACT_CALL),
                          "wait": "{'dt': game seconds, 0 < dt <= 1}"})
        if isinstance(m, TTMatch):
            out["match"] = dict(win_points=5, win_by=2, cap_points=7, expedite_returns=13, opponent_level=m.level,
                                serves="the opponent serves every point; you always receive",
                                format="first to 5; from 4:4 lead by 2, up to 7 (at 6:6 the next point wins)")
        else:
            D = m.D
            out["match"] = dict(win_points=D.WIN_POINTS, win_by=D.WIN_BY, cap_points=D.CAP_POINTS,
                                expedite_returns=D.EXPEDITE_RETURNS, first_receiver=D.FIRST_RECEIVER,
                                serves="a neutral machine serves recorded real serves; the receiver changes every point",
                                format=f"first to {D.WIN_POINTS}; from {D.WIN_POINTS - 1}:{D.WIN_POINTS - 1} lead by "
                                       f"{D.WIN_BY}, up to {D.CAP_POINTS} (at {D.CAP_POINTS - 1}:{D.CAP_POINTS - 1} "
                                       "the next point wins); the receiver changes every point")
        if cfg.action_level == "low":
            import robot_model
            mm = m.R.s.m if isinstance(m, TTMatch) else m.g.m        # the duel: robot A's chain (= B's, own frame)
            out.update(action_interface="joint position targets at 100 Hz; no IK or stroke planner (your own frame: "
                                        "the same kinematic chain for both duel seats)",
                       kinematics=action_low.kinematics(mm), limits=action_low.limits(_rows(m).s),
                       robot_model={"robot_only_xml": robot_model.robot_only_xml(),
                                    "note": "the arm + paddle cut out of the simulator's scene (MJCF; the mesh files "
                                            "are MuJoCo Menagerie panda_nohand's); nothing of the world"})
        return out


SPORT = TableTennis()
