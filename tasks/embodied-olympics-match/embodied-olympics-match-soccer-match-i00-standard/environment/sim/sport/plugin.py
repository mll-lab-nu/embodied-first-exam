"""soccer: the RoboOlympics v0.2 sport (docs/framework_zh.md §4.2), wrapping the unchanged legacy simulator.

Robot soccer 2 v 2 under the RoboCup Humanoid Soccer League rules (sport.toml lists the deviations): four Booster T1
lower bodies on the released walking policy, one ball, a boarded 10 x 7 m pitch, two halves of 2.5 game minutes and a
penalty shoot-out when level. Three formats on one world (soccer.World):
  match   one seat (A) plays both robots of team A against the scripted team B inside the world (levels 1-3; 2 and 3
          official, 1 a warm-up)
  duel    format A: one seat per team (A, B), each commands its two robots
  team    format B: one seat per robot (A1, A2 against B1, B2; sides A and B); teammates talk only through the core's
          team channel (sport.toml [team_channel])
  team_match  one seat per robot of team A (A1, A2; one side A) against the scripted team B inside the world, the
          levels of `match`; the two seats talk only through the team channel

The simulator: soccer.py (world, walking policy batch, kick skill, referee, the scripted coach; since soccer-2v2-4 the
real T1's leg limits of bodies/booster_t1 and the swing kick of swing_kick.py), soccer_scene.py (the MuJoCo scene, the
head camera) and models/ (the walking policy). The four groups of contract ②:
  world        SoccerMatch.step() = World.advance() (one 20 ms control step); state_digest() = World.state_sha() (qpos,
               qvel, time, step, score)
  actions      low level only: walk [vx, vy, wz] | stand | kick power aim style, per robot = per entity ("1", "2": the robot's
               number in its team); one act in flight per (seat, robot); applied at the next control step, replacing
               the robot's command under way (World.command); a penalized or fallen robot's command is refused
  referee      phase(): a stoppage (goal, half time, dropped ball, each shoot-out kick, ...) is a unit end reviewed by
               every seat; resume() = World.resume(); tiebreaks(): goals -> shoot-out -> sudden death -> coin toss,
               the legacy winner rule split into named steps (the world decides, the core reads it)
  observation  observe(): own robots' state (team frame), the referee's information, the referee events of the
               current unit, no ball or opponent coordinates; cameras(): one head camera per own robot (its pose from
               the robot's current trunk pose, or from the last frame before the stoppage during a review), drawn by
               the task's renderer from scene() (soccer_scene's MJCF + the T1 meshes) and render_state() (qpos)
"""
from __future__ import annotations

import os
import threading
import tomllib
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DECL = tomllib.loads(open(os.path.join(HERE, "sport.toml"), "rb").read().decode())
REVISION = DECL["sport"]["revision"]
FORMAT_SEATS = {name: tuple(f["seats"]) for name, f in DECL["formats"].items()}
FORMAT_SIDES = {name: f.get("sides") for name, f in DECL["formats"].items()}
# perception (sport.toml [formats.<f>] perception): "onboard" = each robot's head camera (match, duel, team);
# "overhead" = the fixed overhead cameras of overhead.py, no head cameras (match_overhead, duel_overhead)
FORMAT_PERCEPTION = {name: f.get("perception", "onboard") for name, f in DECL["formats"].items()}


def _service_defaults():
    """Work around a setting the v0.2 generator does not pass to the sim service yet (tools/generate.py sim_env; see
    README "Core hooks"): the seats' sides of the team format (RO_SIDES; without them every seat would be its own side
    and the team channel would stay off). core.serve imports the plugin before it reads the environment, so this
    default reaches its MatchConfig; a set value always wins. (The slowdown comes from the generator: RCB_SLOWDOWN,
    default [timing] slowdown.)"""
    e = os.environ
    if e.get("RO_SPORT") != DECL["sport"]["name"] or e.get("RO_FORMAT") not in FORMAT_SEATS:
        return
    sides = FORMAT_SIDES.get(e["RO_FORMAT"])
    if sides and not e.get("RO_SIDES"):
        e["RO_SIDES"] = ",".join(f"{k}={v}" for k, v in sides.items())


_service_defaults()
# Mesa's llvmpipe (MUJOCO_GL=osmesa) starts one render thread per host CPU in every render worker: with four seats'
# camera workers that alone exceeds the generated sim container's pids_limit (256) and the service cannot fork. Two
# threads per worker draw the same pixels (the thread count never changes an image).
os.environ.setdefault("LP_NUM_THREADS", "2")

import soccer as S  # noqa: E402  (the legacy simulator; reads its own defaults from the environment at import)
import soccer_scene as SC  # noqa: E402
import overhead as OH  # noqa: E402
from core.sport import FINISHED, PLAYING, UNIT_OVER, MatchBase, Phase, Refused, SchemaLayer  # noqa: E402

OPP = "opponent"                        # the scripted team's side in the `match` format
PRIVATE_EVENTS = ("pass", "fall", "get_up", "kick_cancelled", "kick_late")
VEC = {"type": "vector", "len": 3, "min": -1.0, "max": 1.0, "digits": 4}
SCHEMA = {
    "walk": {"v": {**VEC, "unit": "[m/s, m/s, rad/s]",
                   "doc": "body-frame velocity command [vx forward, vy left, wz counter-clockwise], each in [-1, 1]"}},
    "stand": {},
    "kick": {"power": {"type": "number", "min": 0.0, "max": 1.0, "digits": 4, "default": 1.0,
                       "doc": "swing: the swing's speed (nominal peak foot speed 0.8 + 3.2 power m/s; a clean hit sends "
                              "the ball off at about 1.2 m/s at power 0 to 4.3 m/s at power 1); step: the in-walk "
                              "swing's speed (2.4 + 1.6 power m/s; the ball off at about 2.7-3.9 m/s); push: the run "
                              "speed 0.6 + 0.4 power m/s"},
             "aim": {"type": "number", "min": -S.SWING["aim_max"], "max": S.SWING["aim_max"], "digits": 4,
                     "default": 0.0, "unit": "rad",
                     "doc": "swing and step: the kick's direction relative to the robot's heading (+ = to the left); "
                            "up to %g rad away from the support foot's side (right foot: to the right, left foot: to "
                            "the left) and up to %g rad across it (a larger value across is clipped)"
                            % (S.SWING["aim_max"], S.SWING["aim_in_max"])},
             "at": {"type": "vector", "len": 3, "min": -10.0, "max": 10.0, "digits": 3, "default": None,
                    "unit": "[s, m, m]",
                    "doc": "swing only, optional: the timed kick [t, x, y]: the ball's centre will be at (x, y) "
                           "(your team's frame) t seconds from now (0 <= t <= %g); the kick does not wait for the "
                           "ball to be still and does not look at it: the swing is timed so that the strike point "
                           "meets (x, y) at t (preparation about 2.6 s: a shorter t strikes as soon as it can, the "
                           "event kick_late says by how much). The same command again (same foot and aim) before "
                           "the swing starts updates t and (x, y) without a new preparation" % S.SWING["at_t_max"]},
             "foot": {"type": "enum", "values": ["right", "left"], "default": "right",
                      "doc": "swing and step: the kicking foot (the strike zones are mirrored for the left foot)"},
             "v": {**VEC, "default": None, "unit": "[m/s, m/s, rad/s]",
                   "doc": "step only, optional: the walking command while the robot walks on to the kicking step "
                          "(default: the walk under way, else [%g, 0, 0])" % S.STEP["v_default"][0]},
             "style": {"type": "enum", "values": ["swing", "push", "step"], "default": "swing",
                       "doc": "swing: the right leg's swing kick from a standing stance (about 5 s, the ball hit after "
                              "about 2.5 s; the ball should lie in strike_zone.swing); push: the toe-poke run-up (walk "
                              "straight through the ball; strike_zone.push; about 2.6 s, slower balls, never falls); "
                              "step: the in-walk kick (the robot walks on with v; the first swing of the kicking foot "
                              "that can reach the ball kicks it: the ball 0.16-0.40 m ahead of the support foot on the "
                              "kicking foot's line, strike_zone.step; contact about 0.5-1.5 s after the command; called "
                              "off after %g s without such a step)" % S.STK.PARAMS["approach_max_s"]}},
}


def robots_of(seat: str) -> tuple[str, ...]:
    """The robots a seat commands: a team seat (A, B) both of its team's, a robot seat (A1 ... B2) its own."""
    return (seat,) if seat in SC.ROBOTS else S.TEAM_ROBOTS[seat[0]]


def head_camera(m, d, robot: str) -> dict:
    """The robot's head camera as a renderer camera definition (pose from MjData d after mj_kinematics + mj_camlight)."""
    c = m.camera(f"{robot}:egocentric").id
    pos, R = d.cam_xpos[c], d.cam_xmat[c].reshape(3, 3)          # MuJoCo camera: looks along -z, image up = +y
    return {"name": f"robot{robot[1]}", "pos": [float(x) for x in pos],
            "lookat": [float(x) for x in pos - R[:, 2]], "up": [float(x) for x in R[:, 1]],
            "fovy_deg": SC.CAM_FOVY_DEG, "width": SC.TILE[0], "height": SC.TILE[1]}


class SoccerMatch(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg
        self.single = len(set(cfg.side_of(s) for s in cfg.seats)) == 1   # one side (match, team_match): vs Coach
        self.level = int(cfg.level or 2) if self.single else 0   # default: level 2, the lowest official level
        if self.single and self.level not in S.COACH_LEVELS:
            raise ValueError(f"opponent level must be one of {sorted(k for k in S.COACH_LEVELS if isinstance(k, int))}")
        first = str(cfg.first or "A")[:1]
        self.first = first if first in S.TEAMS else "A"
        self.w = S.World(scripted={"B": self.level} if self.single else None, seed=int(cfg.seed),
                         first_kickoff=self.first)
        self.dt = S.CONTROL_DT
        self.forfeited = None                 # (seat, why): a core decision (the world itself never changes on it)
        self.refused = {s: 0 for s in cfg.seats}     # acts refused at the request (robot penalized or fallen)
        self.overhead = FORMAT_PERCEPTION.get(getattr(cfg, "format", None) or "", "onboard") == "overhead"
        self._lag = max(0, int(round(OH.VISION_LATENCY_S / S.CONTROL_DT)))   # overhead images: steps behind
        self._qhist = deque(maxlen=self._lag + 1)    # the last qpos per control step (the overhead images' frame)
        self._kin, self._kin_lock = None, threading.Lock()

    @property
    def k(self):
        return self.w.k

    # ---------------------------------------------------------------- sides
    def side_of_team(self, team):
        """The side of a world team: the side of its seats (A, B; the team format's sides A and B); the scripted team
        B of the match format (no seat) is "opponent"."""
        seats = [s for s in self.cfg.seats if s[0] == team]
        if not seats:
            return OPP
        sides = {self.cfg.side_of(s) for s in seats}
        return sides.pop() if len(sides) == 1 else team

    # ---------------------------------------------------------------- world
    def step(self):
        n = len(self.w.events)
        self.w.advance()
        if self.overhead:
            self._qhist.append(self.w.d.qpos.copy())
        return self.w.events[n:]

    def state_digest(self):
        return self.w.state_sha()

    def schema(self, seat):
        return SCHEMA

    def entities(self, seat):
        return tuple(r[1] for r in robots_of(seat))

    def robot(self, seat, entity) -> str:
        num = str(entity or self.entities(seat)[0])
        for r in robots_of(seat):
            if r[1] == num:
                return r
        raise Refused(f"you command robot(s) {list(self.entities(seat))}")

    def why_not(self, robot):
        w = self.w
        if w.penalty[robot] is not None:
            return f"robot {robot[1]} is penalized ({w.penalty[robot]['why']})"
        if w.fallen[robot] is not None:
            return f"robot {robot[1]} has fallen; it is stood up {S.GETUP_S:g} s after the fall"
        return None

    def apply(self, seat, cmd):
        """A low-level command takes effect at this control step (World.command, the legacy act). A robot that is
        penalized or fallen at the boundary keeps still: the command is refused (the legacy service dropped it)."""
        w = self.w
        robot = self.robot(seat, cmd.get("entity"))
        if w.stopped or w.done:
            return {"rejected": "the world is stopped"}
        why = self.why_not(robot)
        if why:
            return {"rejected": why}
        t = cmd["type"]
        w.command(robot, {"type": "walk", "v": list(cmd["v"])} if t == "walk" else
                  {"type": "kick", "power": cmd["power"], "aim": cmd.get("aim", 0.0), "style": cmd.get("style", "swing"),
                   "foot": cmd.get("foot", "right"), **({"at": list(cmd["at"])} if cmd.get("at") is not None and
                                                         cmd.get("style", "swing") == "swing" else {}),
                   **({"v": list(cmd["v"])} if cmd.get("v") is not None and cmd.get("style") == "step" else {})}
                  if t == "kick" else {"type": "stand"})
        return {"robot": int(robot[1])}

    # ---------------------------------------------------------------- referee
    def phase(self):
        w = self.w
        if w.done:
            return Phase(FINISHED, reason=w.end_reason or "match_over")
        if w.stopped:
            return Phase(UNIT_OVER, review=tuple(self.cfg.seats), reason=w.stopped["kind"])
        return Phase(PLAYING)

    def resume(self):
        self.w.resume()

    def unit(self):
        return len(self.w.stops)

    def forfeit(self, seat, why):
        self.forfeited = (seat, why)
        return False

    def scores(self):
        out = {}
        for t in S.TEAMS:
            out[self.side_of_team(t)] = self.w.score[t]
        return out

    def tiebreaks(self):
        """The legacy winner rule (soccer.World: _finish / _pso_winner), named: more goals (in regulation or by the
        mercy rule) -> the shoot-out's 3 kicks each -> sudden death ranked by the HSL kick categories -> the seeded
        coin toss (the last resort, not from the rulebook)."""
        def by(*hows):
            return lambda m: m.side_of_team(m.w.winner) if m.w.done and m.w.end_reason in hows else None
        return [("goals", by("regulation", "mercy")), ("shootout", by("pso")),
                ("sudden_death", by("pso_sudden_death")),
                ("coin_toss", lambda m: m.side_of_team(m.w.winner) if m.w.done else None)]

    def ranking(self):
        """Only when the core gives every seat of the team format its own side (no MatchConfig.sides): the winning
        team's seats first."""
        if not self.w.done:
            return None
        win = self.w.winner
        return [s for s in self.cfg.seats if s[0] == win] + [s for s in self.cfg.seats if s[0] != win]

    # ---------------------------------------------------------------- observation
    def rname(self, team, robot):
        return ("us" if robot[0] == team else "them") + robot[1]

    def events_for(self, team):
        """The referee's events of the current unit (since the previous stoppage; during a review, the unit that
        just ended), as the team sees them: touches and passes are not announced, falls only of its own robots;
        robots as us1 / them2, teams as us / them. Pure: computed from the world's event list."""
        w = self.w
        stops = w.stops[:-1] if (w.stopped or w.done) else w.stops
        k0 = stops[-1]["k"] if stops else -1
        out = []
        for e in w.events:
            if e["k"] <= k0:
                continue
            if e["ev"] in PRIVATE_EVENTS and not (e.get("robot") or "?")[0] == team:
                continue
            e2 = {}
            for key, v in e.items():
                if key in ("robot", "to", "striker", "keeper") and isinstance(v, str) and v in SC.ROBOTS:
                    v = self.rname(team, v)
                elif key == "team" and v in S.TEAMS:
                    v = "us" if v == team else "them"
                elif key == "score" and isinstance(v, dict):
                    v = {"us": v[team], "them": v[S.OTHER[team]]}
                elif key == "winner" and v in S.TEAMS:
                    v = "us" if v == team else "them"
                elif key == "spot":
                    continue
                e2[key] = v
            out.append(e2)
        return out[-30:]

    def observe(self, seat, query=None):
        w, team = self.w, seat[0]
        out = {"team": team, "your_robots": [int(r[1]) for r in robots_of(seat)], "stoppages": len(w.stops),
               "referee": w.referee(team),
               "robots": {r[1]: w.self_state(r) for r in robots_of(seat)}, "events": self.events_for(team)}
        if w.stopped:
            st = w.stopped
            out["stoppage"] = {"kind": st["kind"], "score": {"us": st["score"][team], "them": st["score"][S.OTHER[team]]},
                               **({"team": "us" if st.get("team") == team else "them"} if st.get("team") else {}),
                               **({"robot": self.rname(team, st["robot"])} if st.get("robot") else {})}
        if w.done:
            pso = w.pso_score()
            out["result"] = {"score": {"us": w.score[team], "them": w.score[S.OTHER[team]]},
                             "winner": "us" if w.winner == team else "them", "how": w.end_reason,
                             "shootout": None if not pso else {"us": pso[team], "them": pso[S.OTHER[team]]}}
        return out

    def frame_qpos(self):
        """The qpos the cameras show: now, or during a review (and after the end) the last frame before the stoppage
        (the world has already placed the restart; the legacy service showed the same frame)."""
        w = self.w
        if (w.stopped or w.done) and w.review_hist:
            return w.review_hist[-1]["qpos"]
        if self.overhead and self._qhist:              # the overhead vision: the world VISION_LATENCY_S ago
            return self._qhist[0]
        return w.d.qpos

    def cameras(self, seat, query=None):
        if self.overhead:                                  # fixed cameras: no robot pose in them
            return OH.camera_defs(seat[0])
        import mujoco
        with self._kin_lock:                               # /spec reads the cameras without the core's world lock
            if self._kin is None:
                self._kin = mujoco.MjData(self.w.m)        # our own data: the world's MjData is never touched
            d = self._kin
            d.qpos[:] = self.frame_qpos()
            mujoco.mj_kinematics(self.w.m, d)
            mujoco.mj_camlight(self.w.m, d)                # the cameras' world poses
            return [head_camera(self.w.m, d, r) for r in robots_of(seat)]

    def render_state(self):
        return {"qpos": [float(x) for x in self.frame_qpos()]}

    def broadcast_frame(self):
        w = self.w
        return {"q": [round(float(x), 5) for x in w.d.qpos], "score": dict(w.score), "period": w.period,
                "clock": round(w.clock(), 2), "state": w.state}

    def final_fields(self):
        """The legacy final.json fields the Season-1 readers use (live_board, broadcast, regrade_transient)."""
        w = self.w
        out = {"level": self.level, "first_kickoff": w.first_kickoff, "half_s": S.HALF_S, "score": dict(w.score),
               "end_reason": w.end_reason, "summary": w.summary(), "world_revision": S.REVISION,
               "forfeit": None if not self.forfeited else {"seat": self.forfeited[0], "team": self.forfeited[0][0],
                                                           "why": self.forfeited[1]}}
        if any(self.refused.values()):
            out["seats"] = {s: {"refused_robot": n} for s, n in self.refused.items()}
        return out


class RobotLayer(SchemaLayer):
    """The one action level: the schema's command for one robot ("entity": its number; "robot" is accepted as an
    alias, as in the legacy service). A command for a robot that is penalized or fallen now is refused (409)."""

    def parse(self, seat, body, match, ctx):
        if isinstance(body, dict) and "robot" in body:
            body = dict(body)
            r = body.pop("robot")
            if "entity" in body and str(body["entity"]) != str(r):
                raise Refused("robot and entity disagree")
            body["entity"] = str(r)
        cmd = super().parse(seat, body, match, ctx)
        why = match.why_not(match.robot(seat, cmd.get("entity")))
        if why:
            match.refused[seat] = match.refused.get(seat, 0) + 1
            raise Refused(why, 409)
        return cmd

    def reply(self, seat, cmd, info, match):
        return {"robot": int(cmd["entity"]), **info}


def scene_xml():
    """soccer_scene's model as MJCF text plus the T1 meshes (the renderer compiles its own copy): the team colours
    that build_model() sets on the compiled model go into the spec first."""
    spec = SC.build_spec()
    for r in SC.ROBOTS:
        spec.geom(f"{r}:Trunk").rgba = list(SC.TEAM_RGBA[r])
    mesh = os.path.join(SC.T1_ASSETS, "meshes")
    assets = {f: open(os.path.join(mesh, f), "rb").read() for f in sorted(os.listdir(mesh))}
    return spec.to_xml(), assets


class Soccer:
    name, protocol, revision, source_dirs, workers = "soccer", "realtime", REVISION, [HERE], ("render",)

    def build(self, cfg):
        return SoccerMatch(cfg)

    def action_layer(self, level):
        if level != "low":
            raise ValueError("soccer has one action level: low (walk / stand / kick per robot)")
        return RobotLayer()

    def scene(self, cfg):
        from renderers.base import Scene
        xml, assets = scene_xml()
        return Scene(xml=xml, assets=assets)

    def spec(self, cfg, seat, m):
        out = self._spec(cfg, seat, m)
        if m.overhead:
            out["camera"] = {
                "overhead": OH.calibration(seat[0]),
                "tiles": "two overhead cameras, one per half, in this order: overhead0 over your own half (your "
                         "x < 0), overhead1 over the opponents' half; no head cameras in this format",
                "frame": "every tile is a map of its half in YOUR team's frame: image right = your +x (you attack "
                         "x = +5), image up = your +y; the cameras look straight down from height %g m (pos, lookat, "
                         "up, fovy_deg in your frame; pinhole: u = cx + f * x_right / depth, v = cy - f * y_up / "
                         "depth, depth = height above the point's plane)" % OH.CAMERA_HEIGHT,
                "latency_s": OH.VISION_LATENCY_S,
                "latency": "the images show the world latency_s ago (as RoboCup SSL's shared vision); your robots' "
                           "own state is exact and current",
                "heights_m": {"ball_centre": S.BALL_R, "trunk_top_about": 0.85, "head_top_about": OH.ROBOT_TOP},
                "note": "ideal images (no noise, no lens distortion); the ball is orange, team A wears blue, team B "
                        "red; a robot seen from above shows its head and shoulders, displaced outwards from the "
                        "point under it by height / camera height x its distance from the camera's axis"}
        return out

    def _spec(self, cfg, seat, m):
        team = seat[0]
        robots = robots_of(seat)
        ents = [int(r[1]) for r in robots]
        return {
            "team": team, "your_robots": ents,
            "act": ('{"type": "walk", "v": [vx, vy, wz], "entity": "N"} | {"type": "stand", "entity": "N"} | '
                    '{"type": "kick", "power": P, "aim": A, "foot": "right"|"left", "at": [t, x, y] (optional: the timed kick of a '
                    'rolling ball), "entity": "N"}; N = your robot\'s number ' + str(ents) +
                    ' ("robot": N is accepted too); one act in flight per robot'),
            "player_identity": SC.identity_spec(),
            "simulator": "mujoco 3.3.7; Booster T1 lower bodies (sai-mujoco 0.1.30 model) on the released walking "
                         "policy",
            "match": {"players_per_team": 2, "halves": 2, "half_s": S.HALF_S,
                      "first_kickoff": "us" if m.first == team else "them",
                      "opponent": "scripted team" if m.single else "another player", "opponent_level":
                          m.level if m.single else None,
                      "shootout": {"kicks_per_team": S.PSO_KICKS, "sudden_death_rounds": S.PSO_SD_ROUNDS,
                                   "time_per_kick_s": S.PSO_TIME_S}},
            "frame": "your team's frame: you attack the goal at x = +5 and defend the goal at x = -5; y to the left "
                     "when facing +x; z up; yaw counter-clockwise from +x",
            "pitch": {"field_length": 2 * S.HALF_L, "field_width": 2 * S.HALF_W, "goal_width": S.GOAL_W,
                      "goal_height": S.GOAL_H, "centre_circle_radius": S.CENTER_R,
                      "penalty_mark_from_goal_line": S.PEN_MARK, "penalty_area": {"length": 2.0, "width": 4.0},
                      "boards": "on the touchlines and goal lines (open goal mouths)"},
            "ball": {"radius": S.BALL_R, "mass_kg": 0.452, "colour": "orange", "rolling_deceleration_mps2": S.ROLL_DECEL},
            "robot": {"body": "Booster T1 (bodies/booster_t1: the real robot's leg limits)",
                      "walk_limits": dict(S.CMD_LIMITS),
                      "walk_command_rate_per_s": dict(zip(("vx", "vy", "wz"), S.T1["limits"]["walk"]["command_accel"])),
                      "leg_limits": {"joints": ["hip_pitch", "hip_roll", "hip_yaw", "knee_pitch", "ankle_pitch",
                                                "ankle_roll"],
                                     "velocity_rad_s": S.T1["limits"]["leg"]["speed_rad_s"],
                                     "torque_nm": S.T1["limits"]["leg"]["torque_nm"],
                                     "rated_torque_nm": [round(S.T1["motors"]["thermal"]["rated_frac"] * x, 2)
                                                         for x in S.T1["limits"]["leg"]["torque_nm"]],
                                     "thermal": "a motor's limit folds back from torque_nm to rated_torque_nm when it is "
                                                "held near its peak (about %g s from cold at the peak; I^2 t, an estimate)"
                                                % S.T1["motors"]["thermal"]["peak_s"],
                                     "bus_power_w": S.T1["motors"]["bus"]["power_w"],
                                     "torque_speed": "full torque up to 64 % of velocity_rad_s, then linearly to 0 "
                                                     "at it (braking keeps full torque; an estimate)"},
                      "strike_zone": {"swing": S.SWING_ZONE, "push": S.STRIKE_ZONE,
                                      "step": {"ahead_of_support_foot": [S.STK.PARAMS["reach_min"], S.STK.PARAMS["reach_max"]],
                                               "off_kicking_foot_line_max": S.STK.PARAMS["side_max"],
                                               "kicking_foot_line_right_of_trunk": S.STEP["line_m"],
                                               "note": "checked at each lift-off of the kicking foot while the robot "
                                                       "walks on"},
                                      "swing_by_aim": {"right_foot": [{"aim": a, "ahead": x, "left": y}
                                                                      for a, x, y in S.SWING_ZONE_AIM],
                                                       "left_foot": "mirrored: aim -> -aim, left -> -left"},
                                      "note": "where the ball's centre should lie when the kick starts: metres ahead "
                                              "of and to the right of the trunk (robot frame)"},
                      "kick": {"swing": {"foot": "right (default) or left", "power_to_foot_speed_mps": "%g + %g power" % (
                                   S.SWING["speed_min"], S.SWING["speed_max"] - S.SWING["speed_min"]),
                                         "aim_max_rad": S.SWING["aim_max"], "aim_across_max_rad": S.SWING["aim_in_max"],
                                         "phases": S.SWING_DOC,
                                         "timed": {"at": "[t, x, y]: the ball's centre at (x, y) of your frame t s from "
                                                         "now; no wait for a still ball, the ball is never read",
                                                   "preparation_s": 2.6, "t_max_s": S.SWING["at_t_max"],
                                                   "update": "the same kick (foot, aim) again before the swing: new "
                                                             "t and (x, y), no new preparation",
                                                   "late": "event kick_late (own robots) and command.late_s"}},
                               "step": {"foot": "right (default) or left",
                                        "power_to_foot_speed_mps": "%g + %g power" % (
                                            S.STK.PARAMS["speed_min"], S.STK.PARAMS["speed_max"] - S.STK.PARAMS["speed_min"]),
                                        "aim_max_rad": S.STEP["aim_max"], "aim_across_max_rad": S.STEP["aim_in_max"],
                                        "phases": S.STEP_DOC},
                               "push": {"stand_s": S.KICK["stand_s"], "run_up_m": S.KICK["run_m"],
                                        "after_s": S.KICK["after_s"], "run_speed_mps": "0.6 + 0.4 power",
                                        "run": "until a foot is past the ball's centre (at most %g x the nominal run)"
                                               % S.KICK["run_max_factor"]}},
                      "fall_trunk_height_m": S.FALL_Z, "get_up_after_s": S.GETUP_S},
            "camera": {"per_robot": "head camera (tile robotN of the observation)", "tile_px": list(SC.TILE),
                       "fovy_deg": SC.CAM_FOVY_DEG, "intrinsics": SC.intrinsics(), "cam_to_trunk": SC.cam_to_trunk(),
                       "note": "cam_to_trunk maps camera coordinates (x right, y down, z forward) to the trunk frame "
                               "(x forward, y left, z up); the trunk's pose is your robot's pose (x, y, yaw) with the "
                               "IMU's roll and pitch, at trunk_height above the floor. The `cameras` list of this spec "
                               "holds world poses of the moment the spec was read: use the robot's state instead"},
            "penalties": {"removal_s": S.PENALTY_S, "increment_s": S.PENALTY_INC_S, "ball_holding_s": S.HOLD_S},
        }

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "chase": bp.Chase, "stand": bp.Stand, "random": bp.Random,
                "reference_step": bp.StepReference, "chase_step": bp.StepChase,
                "reference_overhead": bp.OverheadReference, "chase_overhead": bp.OverheadChase}


SPORT = Soccer()
