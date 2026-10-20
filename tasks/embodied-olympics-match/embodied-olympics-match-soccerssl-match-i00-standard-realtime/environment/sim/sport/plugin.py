"""soccer_ssl: wheeled robot soccer 5 v 5 after the RoboCup Small Size League, Division B (docs/framework_zh.md §4.2).

Ten SSL robots after TIGERs Mannheim's v2020 (bodies/ssl_robot: omnidirectional base, kicker, chip kicker, dribbler)
and an orange golf ball on the 9 x 6 m field, two halves of 300 s of playing time, the automatic referee of
sim/referee.py. Three formats on one world (sim/world.py World):
  match   one seat (A) commands the blue team against the scripted yellow team (levels 1-3: L1 warm-up, L2 and L3
          official); the scripted team uses the same skills through the same checks (skill_api.py)
  duel    seat A commands blue, seat B yellow (one program per team, as in real SSL)
  team    one seat per robot (A0..A4 blue, B0..B4 yellow; sides A and B); teammates talk only through the core's team
          channel (sport.toml [team_channel]); an experimental condition SSL does not have (deviation S6)

The four groups of contract ②:
  world        SSLMatch.step(): the scripted team's commands (match format), then World.step() (one 10 ms control
               step = 10 physics steps of 1 ms); state_digest(): qpos, qvel, time, step and the referee's score
  actions      the skill API (skill_api.py, its single source): move / kick / dribble per robot (entity = robot
               number), the robot handler's substitute, and batch (several robots' commands at one boundary); every
               command is carried out at the control-step boundary where the core applies it (World.execute) and the
               reply carries its immediate status; the low level is the robot's servo interface (move without a time or
               an end velocity), declared because the framework requires one, without tasks
  referee      phase(): a goal, half time, full time before a shoot-out and every shoot-out kick end a unit (the world
               freezes for the reviews); tiebreaks(): goals -> shoot-out -> coin toss, the referee's own decision
  observation  observe(): the team's own robots' state (their own sensors), the game controller's information and the
               unit's events (team frame, us / them), the vision frame's capture time; no ball, no opponent, no seed;
               cameras(): the four overhead cameras of sim/camera.py (camera_defs()), drawn by the task's renderer from
               scene() and render_state(), the state VISION_DELAY_STEPS control steps ago (40 ms of game time)
"""

from __future__ import annotations

import hashlib
import importlib
import math
import os
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
DECL = tomllib.loads(open(os.path.join(HERE, "sport.toml"), "rb").read().decode())
REVISION = DECL["sport"]["revision"]
SPEC = DECL["spec"]
# a match never runs on the stand-in robot (sim/stub_robot.py): without bodies/ssl_robot (sport.toml [body] copies it
# into a task) the world raises (sim/field.py default_body)
os.environ.setdefault("RCB_SSL_BODY", "library")
# Mesa's llvmpipe starts one thread per host CPU in each render worker; two per worker draw the same pixels
os.environ.setdefault("LP_NUM_THREADS", "2")

import numpy as np  # noqa: E402

import skill_api as K  # noqa: E402
from core.rng import stream  # noqa: E402
from core.sport import FINISHED, PLAYING, UNIT_OVER, MatchBase, Phase, Refused, check_command  # noqa: E402
from sim import camera as CAM  # noqa: E402
from sim import onboard as ONB  # noqa: E402
from sim import field as F  # noqa: E402
from sim import world as W  # noqa: E402
from sim.frames import TEAMS, other, to_team  # noqa: E402

N = K.ROBOTS_PER_TEAM
TEAM_OF = {"A": "blue", "B": "yellow"}  # side -> world team (blue = team A, attacks +x in the first half)
OPP = "opponent"  # the scripted team's side in the match format
VISION_DELAY_STEPS = int(round(float(SPEC["vision"]["latency_s"]) / W.CONTROL_DT))
DEFAULT_LEVEL = int(DECL["formats"]["match"].get("default_level", 2))
LEVELS = tuple(DECL["formats"]["match"]["levels"])
UNIT_ENDS = {"GOAL": "goal", "HALF_TIME": "half_time", "FULL_TIME": "full_time", "SHOOTOUT_KICK": "shootout_kick"}
POS_KEYS = ("location", "kick_location", "start", "end")
ROBOT_KEYS = ("robot", "victim", "kicked_by", "kicker")

# ---------------------------------------------------------------------------------------------- the schemas
SUBST = {"to": dict(K.SUBSTITUTE["args"]["to"])}
BATCH = {"commands": dict(K.BATCH["args"]["commands"])}
SCHEMA = {**{n: c.request_schema()[n] for n, c in K.CONTRACTS.items()}, "substitute": SUBST, "batch": BATCH}
# the low level: the robot's servo interface (no timed or moving arrival: that planning is the skill)
LOW_SCHEMA = {
    "move": {k: v for k, v in SCHEMA["move"].items() if k in ("x", "y", "theta")},
    "kick": SCHEMA["kick"],
    "dribble": SCHEMA["dribble"],
    "substitute": SUBST,
    "batch": BATCH,
}
SINGLE = ("move", "kick", "dribble", "substitute")


def robots_of(seat: str) -> tuple[int, ...]:
    """The robots a seat commands: a team seat (A, B) all five, a robot seat (A0 ... B4) its own."""
    return (int(seat[1:]),) if len(seat) > 1 else tuple(range(N))


def check_act(schema: dict, body, robots: tuple, on_field) -> dict:
    """One act body (single command or batch) -> the clean command, for a player's seat and for the scripted team
    alike (raises Refused: 400 malformed, 409 a robot that is off the field). `robots`: the numbers it commands;
    on_field(number) -> bool."""
    if not isinstance(body, dict):
        raise Refused("the action must be a JSON object")
    if body.get("type") == "batch":
        if set(body) - {"type", "commands"}:
            raise Refused(f"unknown field(s) {sorted(set(body) - {'type', 'commands'})} for batch")
        cmds = body.get("commands")
        if not isinstance(cmds, list) or not 1 <= len(cmds) <= K.BATCH_MAX:
            raise Refused(f"batch: commands must be a list of 1 to {K.BATCH_MAX} commands")
        out, seen = [], set()
        for c in cmds:
            if not isinstance(c, dict) or c.get("type") not in SINGLE:
                raise Refused(f"batch: each command is one of {list(SINGLE)}")
            if "entity" not in c and len(robots) > 1:
                raise Refused("batch: every command needs its entity (the robot's number)")
            one = check_act(schema, c, robots, on_field)
            key = (one["entity"], one["type"])
            if key in seen:
                raise Refused(f"batch: robot {one['entity']} has two {one['type']} commands")
            seen.add(key)
            out.append(one)
        return {"type": "batch", "commands": out}
    if body.get("type") not in SINGLE:
        raise Refused(f"unknown action type {body.get('type')!r}; one of {list(SINGLE) + ['batch']}")
    cmd = check_command({k: v for k, v in schema.items() if k in SINGLE}, body)
    ents = tuple(str(r) for r in robots)
    ent = cmd.get("entity") if "entity" in cmd else (ents[0] if len(ents) == 1 else None)
    if ent is None:
        raise Refused(f"entity: which robot? one of {list(ents)}")
    if ent not in ents:
        raise Refused(f"entity must be one of {list(ents)}")
    cmd["entity"] = ent
    if cmd["type"] != "substitute" and not on_field(int(ent)):
        raise Refused(f"robot {ent} is off the field (`substitute` with to = on brings it back)", 409)
    return cmd


# ---------------------------------------------------------------------------------------------- the opponents
def scripted_team(level: int, team: str, rng):
    """The scripted team of a level (line D: sports/soccer_ssl/opponents ScriptedTeam(level, team, rng)); until it
    is delivered, the placeholder below."""
    try:
        mod = importlib.import_module("opponents")
        return mod.ScriptedTeam(int(level), team, rng)
    except ModuleNotFoundError as e:
        if e.name != "opponents":
            raise
        return Placeholder(int(level), team, rng)


class Placeholder:
    """PLACEHOLDER scripted team until line D delivers sports/soccer_ssl/opponents (not an official level): the keeper
    follows the ball across its goal; the field robot nearest to the ball goes behind it and kicks it towards the
    opponent goal with an armed flat kick; the others hold their spots. Reads the truth with a reaction delay (0.4 s
    at level 1, 0.3 at 2, 0.2 at 3), decides every 0.1 s. Commands through the same skills and checks."""

    SPOTS = {1: (-1.5, 1.2), 2: (-1.5, -1.2), 3: (-2.6, 0.6), 4: (-2.6, -0.6)}

    def __init__(self, level, team, rng):
        self.level, self.team, self.rng = level, team, rng
        self.delay = {1: 40, 2: 30, 3: 20}.get(level, 30)
        self.buf: list = []
        self.last: dict = {}

    def act(self, truth):
        self.buf.append(truth)
        if len(self.buf) <= self.delay or truth["step"] % 10:
            if len(self.buf) > self.delay + 1:
                del self.buf[0]
            return []
        seen = self.buf[-1 - self.delay]
        del self.buf[: max(0, len(self.buf) - self.delay - 1)]
        ref, now = seen["referee"], truth["t"]
        bx, by = seen["ball"]["pos"][:2]
        us = {n: r for n, r in seen["us"].items() if r["on_field"]}
        cmds = []
        play = ref["command"] in ("RUNNING",) or (
            ref["command"] in ("KICKOFF", "FREE_KICK", "PENALTY") and ref["for_team"] == "us"
        )
        chaser = None
        if play:
            field = [n for n in us if n != 0]
            if field:
                chaser = min(field, key=lambda n: math.hypot(us[n]["pose"][0] - bx, us[n]["pose"][1] - by))
        for n, r in us.items():
            x, y = r["pose"][:2]
            if n == 0:
                gx, gy, th = -4.35, float(np.clip(by, -0.45, 0.45)), 0.0
            elif n == chaser:
                th = math.atan2(-by, 4.5 - bx)
                gx, gy = bx - 0.1 * math.cos(th), by - 0.1 * math.sin(th)
                cmds.append({"type": "kick", "entity": str(n), "speed": 4.0, "armed_for": 0.5})
            else:
                gx, gy = self.SPOTS.get(n, (-2.0, 0.0))
                th = 0.0
            if not play and math.hypot(gx - bx, gy - by) < 0.7:  # keep away from the ball in a stop
                gy += 0.8 if gy >= by else -0.8
            d = math.hypot(gx - x, gy - y)
            move = {"type": "move", "entity": str(n), "x": round(gx, 3), "y": round(gy, 3), "theta": round(th, 3)}
            if not play:
                move["t"] = round(now + 0.2 + d / 1.0, 3)  # slow in a stop (1.5 m/s limit)
            prev = self.last.get(n)
            if (
                prev is None
                or math.hypot(prev[0] - gx, prev[1] - gy) > 0.05
                or abs(prev[2] - th) > 0.1
                or prev[3] != play
            ):
                cmds.append(move)
                self.last[n] = (gx, gy, th, play)
        return cmds


# ---------------------------------------------------------------------------------------------- the match
class SSLMatch(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg
        sides = cfg.side_list()
        self.single = len(sides) == 1
        self.level = int(cfg.level or DEFAULT_LEVEL) if self.single else 0
        if self.single and self.level not in LEVELS:
            raise ValueError(f"opponent level must be one of {list(LEVELS)}")
        first = str(cfg.first or "A")[:1]
        self.first_team = TEAM_OF.get(first, "blue")
        self.onboard = is_onboard(cfg.format)
        self.w = W.World(
            seed=int(cfg.seed),
            first_kickoff=self.first_team,
            n_per_team=N,
            vision_delay_steps=VISION_DELAY_STEPS,
            vision_period=ONBOARD_PERIOD if self.onboard else 1,
            onboard=self.onboard,
        )
        self.dt = W.CONTROL_DT
        self.opp = scripted_team(self.level, "yellow", stream(cfg, "opponent:yellow")) if self.single else None
        if self.opp is not None:  # the scripted team commands true poses (it reads the truth), never odometry ones
            self.w.truth_frame_teams.add("yellow")
        self.opp_refused = 0
        self.stopped = None  # the unit end now under review
        self.stops: list = []
        self.unit_ev0 = 0  # first event of the current unit
        self.n_ev = 0
        self.forfeited = None

    @property
    def k(self):
        return self.w.k

    # ------------------------------------------------------------------------------------------ sides
    def team_of_seat(self, seat):
        """blue for side A (seats A, A0..A4), yellow for side B."""
        return TEAM_OF[seat[0]]

    def side_of_team(self, team):
        seats = [s for s in self.cfg.seats if self.team_of_seat(s) == team]
        return self.cfg.side_of(seats[0]) if seats else OPP

    def entities(self, seat):
        return tuple(str(r) for r in robots_of(seat))

    def on_field_fn(self, team):
        return lambda n: bool(self.w.on_field.get((team, int(n)), False))

    def parse(self, seat, body, schema):
        return check_act(schema, body, robots_of(seat), self.on_field_fn(self.team_of_seat(seat)))

    # ------------------------------------------------------------------------------------------ world
    def step(self):
        w = self.w
        if self.opp is not None and w.referee.stage != "POST_GAME":
            for body in self.opp.act(w.truth_view("yellow")) or []:
                try:
                    cmd = check_act(SCHEMA, body, tuple(range(N)), self.on_field_fn("yellow"))
                except Refused:
                    self.opp_refused += 1
                    continue
                self.execute("yellow", cmd)
        w.step()
        new = w.events[self.n_ev :]
        self.n_ev = len(w.events)
        for e in new:
            kind = UNIT_ENDS.get(e.get("type"))
            if kind and self.stopped is None and w.referee.stage != "POST_GAME":
                self.stopped = dict(kind=kind, k=w.k, score=dict(w.referee.score), team=e.get("team"))
                self.stops.append(self.stopped)
        return [e for e in new if e.get("type") not in ("skill", "robot_event")]

    def execute(self, team, cmd) -> dict:
        if cmd["type"] == "batch":
            return {"results": [self.execute(team, c) for c in cmd["commands"]]}
        args = {k: v for k, v in cmd.items() if k not in ("type", "entity")}
        r = self.w.execute(team, int(cmd["entity"]), cmd["type"], args)
        out = {"robot": int(cmd["entity"]), "skill": cmd["type"], "status": r.get("status")}
        for k in ("eta", "target", "wait_s", "reason"):
            if k in r:
                out[k] = r[k]
        return out

    def state_digest(self):
        w, d = self.w, self.w.data
        h = hashlib.sha256()
        for a in (d.qpos, d.qvel, d.act, np.array([d.time, w.k], float)):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        ref = w.referee
        h.update(
            repr(
                (
                    ref.stage,
                    ref.state,
                    ref.half,
                    round(ref.play_time, 6),
                    sorted(ref.score.items()),
                    sorted(ref.fouls.items()),
                    ref.winner,
                    sorted((f"{t}{n}", v) for (t, n), v in w.on_field.items()),
                )
            ).encode()
        )
        return h.hexdigest()

    def schema(self, seat):
        return SCHEMA if self.cfg.action_level != "low" else LOW_SCHEMA

    def apply(self, seat, cmd):
        """A command takes effect now (the control-step boundary). A robot that left the field since the request was
        checked: that command is not carried out ({"rejected"} for a single command)."""
        team = self.team_of_seat(seat)
        if self.w.referee.stage == "POST_GAME" or self.stopped is not None:
            return {"rejected": "the world is stopped"}
        if cmd["type"] != "batch" and cmd["type"] != "substitute" and not self.on_field_fn(team)(cmd["entity"]):
            return {"rejected": f"robot {cmd['entity']} is off the field"}
        return self.execute(team, cmd)

    # ------------------------------------------------------------------------------------------ referee
    def phase(self):
        if self.w.referee.stage == "POST_GAME":
            return Phase(FINISHED, reason="match_over")
        if self.stopped is not None:
            return Phase(UNIT_OVER, review=tuple(self.cfg.seats), reason=self.stopped["kind"])
        return Phase(PLAYING)

    def resume(self):
        self.stopped = None
        self.unit_ev0 = len(self.w.events)

    def unit(self):
        return len(self.stops)

    def forfeit(self, seat, why):
        self.forfeited = (seat, why)
        return False

    def scores(self):
        return {self.side_of_team(t): self.w.referee.score[t] for t in TEAMS}

    def end_how(self):
        e = next((e for e in reversed(self.w.referee.events) if e.get("type") == "MATCH_END"), None)
        return e.get("how") if e else None

    def tiebreaks(self):
        """The referee's decision, named: more goals after two halves (or the early end at 10 goals, §4.4.3) -> the
        shoot-out (§10: 5 kicks each, then sudden death) -> after 10 rounds a seeded coin toss (S5, the last resort,
        not from the rulebook)."""

        def by(test):
            def rule(m):
                ref = m.w.referee
                if ref.stage != "POST_GAME" or ref.winner is None or not test(m):
                    return None
                return m.side_of_team(ref.winner)

            return rule

        coin = lambda m: (m.w.referee.shootout or {}).get("coin") is not None  # noqa: E731
        return [
            ("goals", by(lambda m: m.end_how() in ("REGULAR_TIME", "EARLY_TERMINATION"))),
            ("shootout", by(lambda m: m.end_how() == "SHOOTOUT" and not coin(m))),
            ("coin_toss", by(lambda m: True)),
        ]

    # ------------------------------------------------------------------------------------------ observation
    def team_event(self, e: dict, team: str):
        """A referee event as `team` sees it (team frame, us / them), or its own robot's event; None otherwise."""
        if e.get("type") in ("skill", "robot_event"):
            return self.w.own_event(e, team)
        s = self.w.sign(team)
        out = {}
        for k, v in e.items():
            if k == "type":
                out["kind"] = v
            elif k in ("team", "winner"):
                out[k] = None if v is None else ("us" if v == team else "them")
            elif k in ROBOT_KEYS and isinstance(v, str) and v[:-1] in TEAMS:
                out[k] = ("us" if v.startswith(team) else "them") + v[-1]
            elif k in POS_KEYS and isinstance(v, (list, tuple)) and len(v) == 2:
                out[k] = [round(c, 3) for c in to_team(s, float(v[0]), float(v[1]))]
            elif isinstance(v, dict) and set(v) == set(TEAMS):
                out[k] = {"us": v[team], "them": v[other(team)]}
            elif k == "stage" or k == "half" or k == "t" or k == "play_time" or not isinstance(v, (dict, list)):
                out[k] = v
            elif isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
                out[k] = v
        return out

    def events_for(self, team):
        out = []
        for e in self.w.events[self.unit_ev0 :]:
            x = self.team_event(e, team)
            if x is not None:
                out.append(x)
        return out[-40:]

    def observe(self, seat, query=None):
        w, team = self.w, self.team_of_seat(seat)
        k_cap, _ = w.vision_frame()
        out = {
            "team": {
                "colour": team,
                "your_robots": list(robots_of(seat)),
                "keeper": 0,
                "opponent": "scripted" if self.single else "player",
            },
            "frame": {
                "attack_sign": w.sign(team),
                "age_s": round((w.k - k_cap) * W.CONTROL_DT, 3),
                "note": (
                    "your commands and this observation: your team's frame (you attack +x); the images: each robot's "
                    "front camera (spec onboard_camera); your robots' poses: odometry (robots[N].odom), not global"
                    if self.onboard
                    else "your commands and this observation: your team's frame (you attack +x); the images: the "
                    "world frame; team (x, y) = attack_sign * world (x, y), team theta = world theta (+ pi when "
                    "attack_sign = -1)"
                ),
            },
            "vision": {
                "t_capture": round(k_cap * W.CONTROL_DT, 3),
                "step_capture": k_cap,
                "latency_s": round(w.vision_delay * W.CONTROL_DT, 3),
            },
            "robots": {str(n): w.own_state((team, n)) for n in robots_of(seat)},
            "referee": w.referee_view(team),
            "events": self.events_for(team),
        }
        if self.stopped is not None:
            st = self.stopped
            out["stoppage"] = {
                "kind": st["kind"],
                "score": {"us": st["score"][team], "them": st["score"][other(team)]},
                **({"team": "us" if st["team"] == team else "them"} if st.get("team") else {}),
            }
        ref = w.referee
        if ref.stage == "POST_GAME":
            so = ref.shootout
            out["result"] = {
                "score": {"us": ref.score[team], "them": ref.score[other(team)]},
                "winner": "us" if ref.winner == team else "them",
                "how": self.end_how(),
                "shootout": None if not so else {"us": so["goals"][team], "them": so["goals"][other(team)]},
            }
        return out

    def cameras(self, seat, query=None):
        return CAM.camera_defs()

    def render_state(self):
        return {"qpos": [float(x) for x in self.w.vision_frame()[1]]}

    def broadcast_frame(self):
        ref = self.w.referee
        return {
            "q": [round(float(x), 5) for x in self.w.data.qpos],
            "score": dict(ref.score),
            "half": ref.half,
            "play_time": round(ref.play_time, 2),
            "command": ref.state,
            "stage": ref.stage,
        }

    def final_fields(self):
        ref = self.w.referee
        out = {
            "level": self.level,
            "first_kickoff": self.first_team,
            "score": dict(ref.score),
            "end_how": self.end_how(),
            "winner_team": ref.winner,
            "fouls": dict(ref.fouls),
            "cards": {t: dict(v) for t, v in ref.cards_given.items()},
            "shootout": None if ref.shootout is None else dict(ref.shootout["goals"]),
            "goals": [
                {k: e.get(k) for k in ("t", "half", "play_time", "team", "robot", "penalty")}
                for e in self.w.events
                if e.get("type") == "GOAL"
            ],
            "world_revision": W.REVISION,
            "stops": len(self.stops),
            "forfeit": None if not self.forfeited else {"seat": self.forfeited[0], "why": self.forfeited[1]},
        }
        if self.opp is not None:
            out["opponent"] = {"class": type(self.opp).__name__, "refused": self.opp_refused}
        return out


class SkillLayer:
    """The action layer of both levels: the act body (a command or a batch) checked against the level's schema (and
    the robots' state: a robot off the field is refused with 409); the command takes effect at the next boundary."""

    worker = None
    delay_steps = 0

    def __init__(self, level):
        self.level = level

    def schema(self, match, seat):
        return SCHEMA if self.level != "low" else LOW_SCHEMA

    def parse(self, seat, body, match, ctx):
        return match.parse(seat, body, self.schema(match, seat))

    def snapshot(self, seat, cmd, match, ordinal):
        return None

    def prepare(self, job):
        return None

    def lower(self, seat, cmd, prepared, match):
        return cmd, {}

    def reply(self, seat, cmd, info, match):
        return info


# ---------------------------------------------------------------------------------------------- onboard mode
class SSLOnboardMatch(SSLMatch):
    """The second perception mode (formats *_onboard; line "onboard", the Embodied Olympics screening notes): no overhead cameras; every robot sees through its own front camera (sim/onboard.py:
    0.13 m high, 15 deg down, 90 deg wide, 640 x 480, a frame every ONBOARD_PERIOD control steps, 40 ms late), and
    knows its wheel odometry and gyro (sim/odometry.py) and the poses the robot handlers told it, not its global pose.
    The images are the sport's own (camera_job): a camera definition holds the robot's world pose, so /spec, which
    lists the camera definitions it is given, must not get them (it gets the mount and the intrinsics instead)."""

    cameras = MatchBase.cameras  # no camera definitions for /spec (they would tell the robots' true poses)

    def onboard_cams(self, seat):
        """The front cameras of the seat's robots on the field, posed from the frame the cameras show (render_state):
        renderers/base CameraDef dicts, one tile per robot in robot order."""
        k, q = self.w.vision_frame()
        team = self.team_of_seat(seat)
        out = []
        P = SPEC["onboard"]
        pitch = math.radians(P["pitch_down_deg"])
        K = ONB.intrinsics(tuple(P["tile_px"]), P["hfov_deg"])
        zero = np.zeros(self.w.model.nv)
        for n in robots_of(seat):
            rid = (team, n)
            if not self.w.on_field[rid]:
                continue
            (x, y, yaw), _ = self.w.base[rid].pose_vel(q, zero)
            c, s_ = math.cos(yaw), math.sin(yaw)
            pos = [x + P["forward_m"] * c, y + P["forward_m"] * s_, P["height_m"]]
            d = [math.cos(pitch) * c, math.cos(pitch) * s_, -math.sin(pitch)]
            up = [math.sin(pitch) * c, math.sin(pitch) * s_, math.cos(pitch)]
            out.append(
                {
                    "name": f"robot{n}",
                    "pos": [float(v) for v in pos],
                    "lookat": [float(pos[i] + d[i]) for i in range(3)],
                    "up": [float(v) for v in up],
                    "fovy_deg": round(K["fovy_deg"], 6),
                    "width": K["w"],
                    "height": K["h"],
                }
            )
        return out

    def camera_job(self, seat):
        cams = self.onboard_cams(seat)
        if not cams:
            return None, {}
        return {"state": self.render_state(), "cams": cams, "columns": ONBOARD_COLUMNS}, {}


def is_onboard(fmt: str) -> bool:
    return str(fmt).endswith("_onboard")


ONBOARD_PERIOD = int(SPEC["onboard"]["frame_every_steps"])
ONBOARD_COLUMNS = 3
_ONB_DRAW: dict = {}


def onboard_scene_xml() -> str:
    """The onboard formats' scene: the match scene with sim/onboard.py's visual settings (near clip plane for a lens
    13 cm above the carpet, a plain grey hall as the background, no MSAA; the team colour bands are line A's,
    bodies/ssl_robot S12, so onboard's own bands are off)."""
    if "onboard" not in _SCENE:
        spec, handles = F.build_scene(N, 0)
        ONB.add_onboard_cameras(spec, handles["robots"], team_band=False)
        _SCENE["onboard"] = spec.to_xml()
    return _SCENE["onboard"]


# ---------------------------------------------------------------------------------------------- the scene
_SCENE: dict = {}


def scene_xml() -> str:
    """The match scene for the renderers: the field, the ball and the ten robots (sim/field.py build_scene, the same
    model the world compiles) with the overhead cameras' visual settings (sim/camera.py add_cameras: no MSAA, even
    light)."""
    if "xml" not in _SCENE:
        spec, handles = F.build_scene(N, 0)
        CAM.add_cameras(spec, handles["field"])
        _SCENE["xml"] = spec.to_xml()
    return _SCENE["xml"]


# ---------------------------------------------------------------------------------------------- built-in players
class Stand:
    """Never acts."""

    def __init__(self, spec, seat, seed):
        pass

    def act(self, view):
        return None


class Random:
    """Random moves of random robots (a check policy; own state only)."""

    def __init__(self, spec, seat, seed):
        self.rng = np.random.default_rng(int(seed) * 7919 + sum(map(ord, seat)))
        self.ents = [str(n) for n in robots_of(seat)]

    def act(self, view):
        st = view["state"]
        if st.get("world") not in (None, "running"):
            return None
        e = self.ents[int(self.rng.integers(len(self.ents)))]
        if not ((st.get("robots") or {}).get(e) or {}).get("on_field", True):
            return None
        return {
            "type": "move",
            "entity": e,
            "x": float(self.rng.uniform(-4.0, 4.0)),
            "y": float(self.rng.uniform(-2.8, 2.8)),
            "theta": float(self.rng.uniform(-3.1, 3.1)),
        }


class KickOff:
    """A simple camera-free player (own state and the referee only; NOT the reference player): at its own kick-off
    the kicker (robot 1, on its spot behind the ball) drives through the ball with an armed flat kick; every robot
    otherwise stays where it is. Used for the golden recordings until line D's players exist."""

    def __init__(self, spec, seat, seed):
        self.mine = robots_of(seat)
        self.done_at = None

    def act(self, view):
        st = view["state"]
        ref = st.get("referee") or {}
        if st.get("world") not in (None, "running") or 1 not in self.mine:
            return None
        if ref.get("command") == "KICKOFF" and ref.get("for_team") == "us" and self.done_at != ref.get("play_time"):
            self.done_at = ref.get("play_time")
            return {
                "type": "batch",
                "commands": [
                    {"type": "kick", "entity": "1", "speed": 3.0, "armed_for": 2.0},
                    {"type": "move", "entity": "1", "x": 0.2, "y": 0.0, "theta": 0.0},
                ],
            }
        return None


class SSLSport:
    name, protocol, revision, source_dirs, workers = "soccer_ssl", "realtime", REVISION, [HERE], ("render",)

    def build(self, cfg):
        return SSLOnboardMatch(cfg) if is_onboard(cfg.format) else SSLMatch(cfg)

    def action_layer(self, level):
        if level not in ("high", "low"):
            raise ValueError("soccer_ssl has the action levels high (the skill API) and low (the servo interface)")
        return SkillLayer(level)

    def scene(self, cfg):
        from renderers.base import Scene

        return Scene(xml=onboard_scene_xml() if is_onboard(cfg.format) else scene_xml())

    def worker_init(self, kind, seat, cfg):
        """The onboard formats draw their own images (SSLOnboardMatch.camera_job) with the core's MuJoCo renderer on
        the onboard scene."""
        from core.observe import CameraWorker
        from renderers.base import Scene

        return CameraWorker(Scene(xml=onboard_scene_xml()), None)

    def worker_call(self, obj, kind, job):
        import time

        if obj is None:  # in-process (core/local.py)
            obj = _ONB_DRAW.get("w") or _ONB_DRAW.setdefault("w", self.worker_init(kind, None, None))
        t = time.monotonic()
        out = obj.draw(job["state"], job["cams"], job.get("columns", ONBOARD_COLUMNS))
        out["worker_s"] = time.monotonic() - t
        return out

    def spec(self, cfg, seat, m):
        team = m.team_of_seat(seat)
        return {
            "team": team,
            "team_color": team,
            "your_robots": list(robots_of(seat)),
            "skill_contract": K.describe(),
            "act": "one command per robot: {'type': 'move' | 'kick' | 'dribble' | 'substitute', 'entity': 'N', ...} "
            "or {'type': 'batch', 'commands': [...]} (several robots at one boundary); N = your robot's number "
            + str(list(robots_of(seat))),
            "match": {
                "format": cfg.format,
                "robots_per_team": N,
                "half_s": m.w.referee.half_s,
                "first_kickoff": "us" if m.first_team == team else "them",
                "opponent": "scripted team" if m.single else "another player",
                "opponent_level": m.level if m.single else None,
            },
            "vision_pattern": {
                **CAM.PATTERN,
                "note": "robot frame x forward, y left (metres); ids by the colours of "
                "the dots front-left, front-right, back-left, back-right (P pink, G green)",
            },
            "cameras_note": "four overhead cameras 4.0 m above the carpet, straight down; image right = world +x, "
            "image up = world +y; tiles in reading order: top-left (x < 0, y > 0), top-right, bottom-left, "
            "bottom-right; the images show the world vision.latency_s ago (vision.t_capture)",
            "robot_top_height_m": 0.148,
            **(
                {
                    "perception": "onboard",
                    "onboard_camera": {
                        **ONB.camera_defs(tuple(SPEC["onboard"]["tile_px"]), SPEC["onboard"]["hfov_deg"]),
                        "tiles": "one per robot of yours on the field, named robotN, in robot order, "
                        f"{ONBOARD_COLUMNS} per row; a frame every {ONBOARD_PERIOD} control steps",
                    },
                    "cameras_note": "no overhead cameras: each robot's front camera (onboard_camera: mount in the "
                    "robot frame, x forward, y left, z up; pinhole). Your robots' poses: wheel odometry and gyro "
                    "(robots[N].odom, in your team frame, drifting) and the last pose the handlers told "
                    "(robots[N].told); move targets are taken in the robot's odometry frame",
                }
                if is_onboard(cfg.format)
                else {}
            ),
        }

    def players(self):
        out = {"stand": Stand, "random": Random, "kickoff": KickOff, "reference": KickOff}
        try:
            import builtin_players as bp  # line D: the reference player and the check policies

            out.update(bp.PLAYERS if hasattr(bp, "PLAYERS") else {"reference": bp.Reference})
        except ModuleNotFoundError as e:
            if e.name != "builtin_players":
                raise
        return out


def reference_match(format="match", level=None, seed=1, perception="truth", render=None, max_steps=None):
    """tools/check stage 5 ([reference] match): one match of the sport's reference player (sport.toml [players]
    reference, line D's builtin_players) against the scripted team, through the platform's skills only, played as
    core/local.py plays a realtime match (every 5 control steps the seat acts on its view; reviews end at once).
    perception "camera": the player sees what a seat sees (the whitelisted observation and the camera images);
    "truth": the same player with World.truth_view of its team in its view's state (`truth`, which its perception
    then uses instead of the images; never part of an agent's observation) and no images drawn.
    -> {"won", "scores": [ours, theirs], "report": {"goals": [ours, all], "fouls": [ours, all], "cards": [ours, all],
    "refused": [refused acts, acts]}}."""
    from core.local import make_players
    from core.sport import MatchConfig, parse_action

    f = DECL["formats"][format]
    cfg = MatchConfig(
        sport="soccer_ssl",
        format=format,
        seats=tuple(f["seats"]),
        seed=int(seed),
        first="A",
        level=level,
        action_level="high",
        sides=f.get("sides"),
    )
    plugin = os.path.join(HERE, "plugin.py")
    seat = cfg.seats[0]
    player = make_players(SPORT, cfg, {seat: DECL["players"]["reference"]}, plugin=plugin)[seat]
    m, layer = SPORT.build(cfg), SPORT.action_layer("high")
    draw = (perception == "camera") if render is None else bool(render)
    views = None
    if draw:
        from core.local import Views

        views = Views(SPORT, cfg, m, DECL, True, plugin)
    acts = refused = 0
    limit = int(max_steps or 10**7)
    while m.phase().state != FINISHED and m.k < limit:
        if m.phase().state == UNIT_OVER:
            m.resume()
        if m.k % 5 == 0:
            extra = {"phase": "running", "world": "running", "step": m.k, "t_sim": m.k * m.dt, "done": False}
            if views is not None:
                v = views.view(seat, extra)
            else:
                v = {"state": {"seat": seat, **extra, **m.observe(seat)}, "observation": {}}
            if perception == "truth":
                v["state"]["truth"] = m.w.truth_view(m.team_of_seat(seat))
            body = player.act(v)
            if body is not None:
                acts += 1
                try:
                    cmd = parse_action(layer, seat, body, m, {})
                    low, _ = layer.lower(seat, cmd, None, m)
                    if "rejected" in (m.apply(seat, low) or {}):
                        refused += 1
                except Refused:
                    refused += 1
        m.step()
    ref, team = m.w.referee, m.team_of_seat(seat)
    them = other(team)
    winner = ref.winner if m.phase().state == FINISHED else None
    cards = {t: sum(ref.cards_given[t].values()) for t in TEAMS}
    return {
        "won": winner == team,
        "scores": [ref.score[team], ref.score[them]],
        "report": {
            "goals": [ref.score[team], ref.score[team] + ref.score[them]],
            "fouls": [ref.fouls[team], ref.fouls[team] + ref.fouls[them]],
            "cards": [cards[team], cards[team] + cards[them]],
            "refused": [refused, acts],
        },
    }


SPORT = SSLSport()
