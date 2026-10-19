"""The world of wheeled 5 v 5 soccer (SSL Division B): field + ball + 2 x n robots in one MuJoCo model, the skills'
entry point, and the automatic referee (referee.py).

Time (interfaces v1 §2): 1 ms physics steps; one control step = 10 ms = 10 physics steps. `apply()` queues a skill
command; it takes effect at the start of the next control step. `step()` advances one control step:
  1. the queued commands go to the robots' rigs (world -> rig: set_base_target / kick / dribble);
  2. every robot's rig.step() writes its actuators (and fires its kicker);
  3. 10 physics steps; after each one the world records which robots touch the ball, which robot pairs touch (with
     the velocities just before a new contact) and the ball's state;
  4. the referee judges the control step and returns its actions (placing the ball, moving / removing robots), which
     the world carries out.

Random numbers come only from core.rng streams named by the seed (kick errors per robot, the kick-off formation's
jitter, the shoot-out coin toss), so a match replays bit-exactly from (seed, commands).

Robots: `field.default_body()` (bodies.ssl_robot once line A has delivered it, else sim/stub_robot.py); both have
mount(spec, name, team, number, pose, lod) -> handles and rig(model, data, handles, limits) -> Rig (interfaces v1 §3).
The world additionally uses Rig.reset(pose, data) when the referee moves a robot (an extension requested from A).
"""

from __future__ import annotations

import inspect
import math
import os
import sys
from types import SimpleNamespace

import numpy as np

from . import ball as BALL
from . import field as F
from .frames import TEAMS, attack_sign, other, to_team, to_world, vec_to_team, wrap
from .referee import KEEPER, Referee

_here = os.path.dirname(os.path.abspath(__file__))
for _d in (os.path.dirname(os.path.dirname(os.path.dirname(_here))), os.path.dirname(os.path.dirname(_here))):
    if os.path.isdir(os.path.join(_d, "core")) and _d not in sys.path:
        sys.path.insert(0, _d)
from core import rng as RNG  # noqa: E402

SPORT = "soccer_ssl"
REVISION = "soccer_ssl-world-1"  # world-1: World.execute (feedback at once), substitute, vision delay, truth views
CONTROL_DT, SUBSTEPS = 0.01, 10
SKILLS = ("move", "kick", "dribble")
COMMANDS = SKILLS + ("substitute",)
VISION_DELAY_STEPS = 4  # 40 ms of game time: the camera images show the world 4 control steps ago (SSL vision about
# 45 ms: ER-Force RC2021 preset 35 + 10 ms, MCT 2017 53 +- 16 ms, ZJUNlict 2020 40-60 ms; proposal §3.1, §5.3)
# own robot events a player may see (bodies/ssl_robot Rig events) and the fields of each (the rest is truth: the
# kick's real speed and direction error, the ball's velocity)
OWN_EVENT_FIELDS = {
    "kicked": ("t", "mode", "speed_cmd", "ball"),  # ball: whether the ball blocked the beam (own sensor)
    "kick_expired": ("t", "mode"),
    "kicker_not_ready": ("t", "wait_s", "charge"),
    "kick_clipped": ("t", "mode", "speed"),
    "base_resync": ("t", "err_m"),
}
PARK_Y = -(F.WALL_Y + F.WALL_T + 0.17)  # removed robots wait outside the walls (the walking area, §2.1.2)
SUB_Y = -(F.HALF_W + F.MARGIN / 2)  # a robot put in enters in the field margin (§9.1.2)


# ----------------------------------------------------------------------------------------------- formations
def _team_spots(n, kicking: bool):
    """team-frame spots for a kick-off (§5.3.2: own half, outside the centre circle; the kicker inside it)."""
    if kicking:
        spots = [(-4.2, 0.0), (-0.25, 0.0), (-1.2, 1.5), (-1.2, -1.5), (-2.8, 0.0), (-2.2, 2.4)]
    else:
        spots = [(-4.2, 0.0), (-0.9, 0.0), (-1.2, 1.5), (-1.2, -1.5), (-2.8, 0.0), (-2.2, -2.4)]
    return spots[:n]


def kickoff_formation(n, seed, half=1, kicking="blue"):
    """{(team, number): world pose} for a kick-off; seed = None gives the nominal spots, else up to 0.1 m of seeded
    jitter on the field robots other than the kicker (proposal §2.4)."""
    rng = (
        RNG.stream(SimpleNamespace(sport=SPORT, seed=seed), f"formation:{half}:{kicking}") if seed is not None else None
    )
    out = {}
    for team in TEAMS:
        s = attack_sign(team, half)
        for k, (x, y) in enumerate(_team_spots(n, team == kicking)):
            if rng is not None and k >= 1 and not (team == kicking and k == 1):
                x, y = x + float(rng.uniform(-0.1, 0.1)), y + float(rng.uniform(-0.1, 0.1))
            out[(team, k)] = to_world(s, x, y, 0.0)
    return out


def penalty_formation(n, half, kicking, ball):
    """legal spots for a penalty kick (§5.3.5): the defending keeper on its goal line, the kicker 0.35 m behind the
    ball, everybody else more than 1 m behind the ball."""
    s = attack_sign(kicking, half)
    bx = ball[0] * s  # the ball in the kicking team's frame
    out = {}
    slots = [(bx - 1.25, y) for y in (-2.6, -1.95, -1.3, -0.65, 0.65, 1.3, 1.95, 2.6)]
    k = 0
    for team in TEAMS:
        for num in range(n):
            if team == kicking and num == 1:
                x, y, yaw = bx - 0.35, 0.0, 0.0
            elif team != kicking and num == KEEPER:
                x, y, yaw = F.HALF_L - 0.05, 0.0, math.pi
            elif team == kicking and num == KEEPER:
                x, y, yaw = -4.2, 0.0, 0.0
            else:
                x, y = slots[k % len(slots)]
                yaw = 0.0 if team == kicking else math.pi
                k += 1
            out[(team, num)] = to_world(s, x, y, yaw)
    return out


def shootout_formation(n, kicking, kicker_number, half=2):
    """§10: only the kicker and the opponent keeper on the field."""
    s = attack_sign(kicking, half)
    mx, _ = F.penalty_mark(s)
    defending = "yellow" if kicking == "blue" else "blue"
    poses = {
        (kicking, kicker_number): to_world(s, mx * s - 0.35, 0.0, 0.0),
        (defending, KEEPER): to_world(s, F.HALF_L - 0.05, 0.0, math.pi),
    }
    parked = [(t, k) for t in TEAMS for k in range(n) if (t, k) not in poses]
    return poses, parked


def park_pose(team, number):
    x = (-4.6 + 0.3 * number) if team == "blue" else (4.6 - 0.3 * number)
    return (x, PARK_Y, math.pi / 2)


def hget(h, key, default=None):
    """a mount handle's field: line A's Handles dataclass or the stub's dict."""
    if isinstance(h, dict):
        return h.get(key, default)
    return getattr(h, key, default)


def base_joints(h):
    return hget(h, "base_joints") or hget(h, "joints")


# ----------------------------------------------------------------------------------------------- base reader
class _Base:
    """position and velocity of a robot's base from its joints: three joints (slide x, slide y, hinge yaw) named in
    handles['base_joints'], or a free joint on the robot's root body."""

    def __init__(self, model, handles):
        import mujoco

        self.kind = None
        names = base_joints(handles)
        if names:
            ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n) for n in names]
            self.q = [int(model.jnt_qposadr[i]) for i in ids]
            self.v = [int(model.jnt_dofadr[i]) for i in ids]
            self.kind = "planar"
        else:
            b = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, hget(handles, "body", hget(handles, "name")))
            j = int(model.body_jntadr[b])
            assert (
                j >= 0 and model.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE
            ), "robot base: no base_joints, no free joint"
            self.qa, self.va = int(model.jnt_qposadr[j]), int(model.jnt_dofadr[j])
            self.kind = "free"

    def pose_vel(self, qpos, qvel):
        if self.kind == "planar":
            return (qpos[self.q[0]], qpos[self.q[1]], qpos[self.q[2]]), (
                qvel[self.v[0]],
                qvel[self.v[1]],
                qvel[self.v[2]],
            )
        w, x, y, z = qpos[self.qa + 3 : self.qa + 7]
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return (qpos[self.qa], qpos[self.qa + 1], yaw), (qvel[self.va], qvel[self.va + 1], qvel[self.va + 5])

    def vel_index(self):
        return (self.v[0], self.v[1]) if self.kind == "planar" else (self.va, self.va + 1)

    def set_pose(self, data, pose):
        x, y, yaw = pose
        if self.kind == "planar":
            data.qpos[self.q[0]], data.qpos[self.q[1]], data.qpos[self.q[2]] = x, y, yaw
            for a in self.v:
                data.qvel[a] = 0.0
        else:
            data.qpos[self.qa : self.qa + 2] = (x, y)
            data.qpos[self.qa + 3 : self.qa + 7] = (math.cos(yaw / 2), 0, 0, math.sin(yaw / 2))
            data.qvel[self.va : self.va + 6] = 0.0


# ----------------------------------------------------------------------------------------------- the world
class World:
    def __init__(
        self,
        seed: int = 0,
        level=None,
        n_per_team: int = 5,
        body=None,
        first_kickoff: str = "blue",
        half_s: float = 300.0,
        cameras: bool = False,
        lod: str = "sim",
        vision_delay_steps: int = VISION_DELAY_STEPS,
        vision_period: int = 1,
        onboard: bool = False,
    ):
        import mujoco

        self.seed, self.level, self.n = int(seed), level, int(n_per_team)
        cfg = SimpleNamespace(sport=SPORT, seed=self.seed)
        self.cfg = cfg
        poses = kickoff_formation(self.n, self.seed, half=1, kicking=first_kickoff)
        self.spec, self.handles = F.build_scene(self.n, self.seed, body=body, poses=poses, lod=lod)
        self.body = self.handles["body"]
        self.camera_names = []
        if cameras:
            from . import camera  # line C (sim/camera.py)

            self.camera_names = camera.add_cameras(self.spec, self.handles["field"])
        self.model = self.spec.compile()
        self.data = mujoco.MjData(self.model)
        m, d = self.model, self.data
        self.ball = BALL.BallState(m, d)
        self.ids = sorted(self.handles["robots"])
        self.base = {rid: _Base(m, self.handles["robots"][rid]) for rid in self.ids}
        self.rigs = {}
        params = inspect.signature(self.body.rig).parameters
        for rid in self.ids:
            h = self.handles["robots"][rid]
            stream = RNG.stream(cfg, f"kick:{rid[0]}{rid[1]}")
            if "rng" in params:
                kw = dict(rng=stream)
            elif "seed" in params:
                kw = dict(seed=int(stream.integers(2**31)))
            else:
                kw = {}
            self.rigs[rid] = self.body.rig(m, d, h, None, **kw)
        self.rig_list = [self.rigs[rid] for rid in self.ids]
        self.substep_rigs = [r for r in self.rig_list if hasattr(r, "substep")]
        # line A's fast path (bodies/ssl_robot/body.py Group, what SSL.step_world uses): one plan per control step,
        # one vectorised PD per physics step; the world keeps its own physics loop to see every sub-step's contacts
        self.group = self.body.Group(m, self.rig_list) if hasattr(self.body, "Group") else None
        for rid in self.ids:
            self._reset_robot(rid, poses[rid])
        self.ball.place(0.0, 0.0)
        mujoco.mj_forward(m, d)
        # geom -> robot index (-1: not a robot)
        root = m.body_rootid
        robot_root = {}
        for i, rid in enumerate(self.ids):
            h = self.handles["robots"][rid]
            b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, hget(h, "body", hget(h, "name")))
            robot_root[int(root[b])] = i
        self.geom_robot = np.array([robot_root.get(int(root[m.geom_bodyid[g]]), -1) for g in range(m.ngeom)], int)
        self.ball_geom = self.ball.geom
        self.vel_idx = np.array([self.base[rid].vel_index() for rid in self.ids], int)  # (N, 2)
        self.on_field = {rid: True for rid in self.ids}
        self.referee = Referee(
            self.n, first_kickoff=first_kickoff, seed=self.seed, half_s=half_s, rng=RNG.stream(cfg, "coin")
        )
        self.queue: list = []
        self.events: list = []
        self._ev_seen = 0
        self.pair_last = {}
        self.k = 0
        self.mj = mujoco
        # the frames the cameras show (vision latency): qpos after each control step, the newest last
        self.vision_delay = max(0, int(vision_delay_steps))
        self.vision_period = max(1, int(vision_period))  # the cameras take a frame every vision_period control steps
        self.qpos_hist: list = [(self.k, d.qpos.copy())]
        # the onboard perception mode (formats *_onboard): each robot's wheel odometry and gyro (sim/odometry.py) and
        # the poses the robot handlers told it (start of each half, every move by the referee); none otherwise
        self.onboard = bool(onboard)
        self.odo, self.odo_vb, self.told = {}, {}, {}
        # teams whose move targets are true team-frame poses even in the onboard mode: a scripted team reads the
        # truth (World.truth_view) and has no odometry frame of its own (set by the plugin / the screening harness)
        self.truth_frame_teams: set = set()
        if self.onboard:
            from .odometry import Odometry

            for rid in self.ids:
                p, _ = self.robot_pose(rid)
                self.odo[rid] = Odometry(RNG.stream(cfg, f"odometry:{rid[0]}{rid[1]}"), pose0=p)
                self.odo_vb[rid] = (0.0, 0.0, 0.0)
                self.told[rid] = (0, tuple(float(v) for v in p))

    # ------------------------------------------------------------------------------------------------ robots
    def _reset_robot(self, rid, pose):
        rig = self.rigs[rid]
        self.base[rid].set_pose(self.data, pose)
        if getattr(self, "onboard", False) and rid in self.odo:  # the robot handler tells the robot where it stands
            o = self.odo[rid]
            o.pose = np.array(pose, float)
            o.gyro_yaw = float(pose[2])
            self.told[rid] = (self.k, tuple(float(v) for v in pose))
        if hasattr(rig, "place"):  # line A (interfaces v1.1): teleport at rest, hold there
            rig.place(self.data, *pose)
        elif hasattr(rig, "reset"):
            rig.reset(pose, self.data)
        else:
            rig.set_base_target(*pose)

    def robot_pose(self, rid):
        p, v = self.base[rid].pose_vel(self.data.qpos, self.data.qvel)
        return tuple(float(a) for a in p), tuple(float(a) for a in v)

    def kick_point(self, rid):
        """world (x, y) where the ball rests against the robot's kicker (its 'kick' / 'kicker' site)."""
        h = self.handles["robots"][rid]
        sites = hget(h, "sites")
        name = sites["kick"] if isinstance(sites, dict) and "kick" in sites else hget(h, "kicker_site")
        sid = self.mj.mj_name2id(self.model, self.mj.mjtObj.mjOBJ_SITE, name)
        self.mj.mj_forward(self.model, self.data)
        return float(self.data.site_xpos[sid][0]), float(self.data.site_xpos[sid][1])

    def remove_robot(self, rid):
        self.on_field[rid] = False
        self._reset_robot(rid, park_pose(*rid))

    def return_robot(self, rid, pose):
        self.on_field[rid] = True
        self._reset_robot(rid, pose)

    def substitute_out(self, team, number) -> str:
        """§9.2: take a robot off from the substitution area (the agent's robot handler)."""
        rid = (team, int(number))
        self.referee.robots = self._robot_table()
        self.referee.ball = np.r_[self.ball.pos, self.ball.vel].astype(float)
        if not self.referee.can_substitute_out(rid):
            return "not_in_substitution_area"
        self.remove_robot(rid)
        self.referee.on_field[rid] = False
        self.referee.event("ROBOT_SUBSTITUTED_OUT", team, rid)
        self.mj.mj_forward(self.model, self.data)
        return "ok"

    def substitute_in(self, team, number) -> str:
        rid = (team, int(number))
        if self.on_field[rid]:
            return "already_on_field"
        self.referee.on_field = dict(self.on_field)
        if not self.referee.can_substitute_in(team):
            return "too_many_robots"
        s = attack_sign(team, min(self.referee.half, 2))
        others = [self.robot_pose(r)[0] for r in self.ids if self.on_field[r]]
        for k in range(12):
            x = -s * (0.3 + 0.25 * k)
            if all(math.hypot(x - o[0], SUB_Y - o[1]) > 0.2 for o in others):
                break
        self.return_robot(rid, (x, SUB_Y, math.pi / 2))
        self.referee.on_field[rid] = True
        self.referee.event("ROBOT_SUBSTITUTED_IN", team, rid)
        self.mj.mj_forward(self.model, self.data)
        return "ok"

    # ------------------------------------------------------------------------------------------------ skills
    def apply(self, team, number, skill, args=None) -> dict:
        """A skill command for robot (team, number) in the team's frame (interfaces v1 §2; proposal §5.1):
        move(x, y, theta, t=None, v_end=None), kick(speed, mode="flat"|"chip", armed_for=0), dribble(rpm).
        Validated now, carried out at the next control step. t is the world time (s) to arrive by."""
        rid = (team, int(number))
        if rid not in self.rigs:
            return dict(status="refused", reason="no_such_robot")
        if not self.on_field[rid]:
            return dict(status="refused", reason="robot_off_field")
        if skill not in SKILLS:
            return dict(status="refused", reason="unknown_skill")
        args = dict(args or {})
        for k, v in args.items():
            if v is not None and k != "mode" and not np.all(np.isfinite(np.asarray(v, float))):
                return dict(status="refused", reason=f"non_finite_{k}")
        self.queue.append((rid, skill, args))
        return dict(status="queued", effective_step=self.k + 1)

    def execute(self, team, number, skill, args=None) -> dict:
        """A command for robot (team, number) carried out NOW, at the control-step boundary (the plugin calls it when
        the core applies an act, right before step()): the skills move / kick / dribble (team frame, skill_api.py) and
        the robot handler's substitute. Returns the immediate feedback (status, eta, target ...), also kept as a
        "skill" event. Unlike apply() (queue for the next step) the result is known at once; both take effect at the
        same physics step."""
        rid = (team, int(number))
        if rid not in self.rigs:
            return dict(status="refused", reason="no_such_robot")
        if skill not in COMMANDS:
            return dict(status="refused", reason="unknown_skill")
        if skill == "substitute":
            return self._substitute(rid, (args or {}).get("to"))
        if not self.on_field[rid]:
            return dict(status="refused", reason="robot_off_field")
        return self._execute(rid, skill, dict(args or {}))

    def _substitute(self, rid, to) -> dict:
        """the robot handler (§5.5.1, §9.2, S11): off = after a card, while the team has too many robots on the field,
        any robot named is taken off; otherwise from the substitution area only. on = back on the field."""
        team, number = rid
        res = dict(type="skill", robot=f"{team}{number}", skill="substitute", to=to, t=round(float(self.data.time), 4))
        ref = self.referee
        if to == "off":
            if not self.on_field[rid]:
                res["status"] = "already_off_field"
            elif sum(1 for r in self.ids if r[0] == team and self.on_field[r]) > ref.allowed(team):
                self.remove_robot(rid)
                ref.on_field[rid] = False
                ref.card_offender[team] = None
                ref.event("ROBOT_SUBSTITUTED_OUT", team, rid, reason="card")
                self.mj.mj_forward(self.model, self.data)
                res["status"] = "ok"
            else:
                res["status"] = self.substitute_out(team, number)
        elif to == "on":
            if ref.stage == "SHOOTOUT":
                res["status"] = "shootout"
            else:
                res["status"] = self.substitute_in(team, number)
        else:
            res["status"] = "refused"
        self.events.append(res)
        return res

    def _execute(self, rid, skill, a):
        rig = self.rigs[rid]
        s = attack_sign(rid[0], min(self.referee.half, 2))
        res = dict(type="skill", robot=f"{rid[0]}{rid[1]}", skill=skill, t=round(float(self.data.time), 4))
        if skill == "move":
            x, y, yaw = to_world(s, float(a["x"]), float(a["y"]), float(a.get("theta") or 0.0))
            rot = 0.0
            odom_frame = self.onboard and rid[0] not in self.truth_frame_teams
            if odom_frame:  # the target is in the robot's odometry frame (its own estimate of the field)
                x, y, yaw2 = self.odom_to_world(rid, x, y, yaw)
                rot, yaw = yaw2 - yaw, yaw2
            lx, ly = F.WALL_X - F.ROBOT_R, F.WALL_Y - F.ROBOT_R
            cx, cy = float(np.clip(x, -lx, lx)), float(np.clip(y, -ly, ly))
            ve = a.get("v_end") or (0.0, 0.0)
            vex, vey = (ve[0], ve[1]) if s > 0 else (-ve[0], -ve[1])
            if rot:
                vex, vey = math.cos(rot) * vex - math.sin(rot) * vey, math.sin(rot) * vex + math.cos(rot) * vey
            r = rig.set_base_target(cx, cy, wrap(yaw), t=a.get("t"), v_end=(vex, vey))
            res["status"] = "clipped" if (cx, cy) != (x, y) else (r or {}).get("status", "ok")
            if isinstance(r, dict) and "eta" in r:
                res["eta"] = r["eta"]
            if odom_frame:  # the target as commanded (odometry frame): the true one would tell the odometry error
                res["target"] = [
                    round(float(a["x"]), 4),
                    round(float(a["y"]), 4),
                    round(float(a.get("theta") or 0.0), 4),
                ]
            else:
                tx, ty, tyaw = to_team(s, cx, cy, wrap(yaw))
                res["target"] = [round(tx, 4), round(ty, 4), round(tyaw, 4)]
        elif skill == "kick":
            res["status"] = rig.kick(float(a.get("speed", 0.0)), a.get("mode", "flat"), float(a.get("armed_for", 0.0)))
            if res["status"] == "kicker_not_ready":
                k = rig.kicker
                res["wait_s"] = round(k.wait_s(k.need(float(a.get("speed", 0.0)), a.get("mode", "flat"))), 3)
        else:
            res["status"] = rig.dribble(float(a.get("rpm", 0.0))) or "ok"
        self.events.append(res)
        return res

    # ------------------------------------------------------------------------------------------------ stepping
    def _robot_table(self):
        out = {}
        for rid in self.ids:
            p, v = self.robot_pose(rid)
            out[rid] = (p[0], p[1], p[2], v[0], v[1], v[2])
        return out

    def step(self):
        """one 10 ms control step."""
        m, d, mj = self.model, self.data, self.mj
        if self.referee.stage == "POST_GAME":
            return
        for rid, skill, a in self.queue:
            if self.on_field[rid]:
                self._execute(rid, skill, a)
        self.queue = []
        d.xfrc_applied[self.ball.body] = 0.0  # (the stub's dribbler; line A uses qfrc_applied: untouched)
        if self.group is not None:
            self.group.step(d)
        else:
            for rig in self.rig_list:
                rig.step(m, d)
        n = SUBSTEPS
        sub_t = np.empty(n)
        ballk = np.empty((n, 6))
        touches, pairs, crashes = [], [], []
        N = len(self.ids)
        for k in range(n):
            vprev = d.qvel[self.vel_idx]  # (N, 2) base velocities just before the step
            if self.group is not None:  # interfaces v1.1: servo, dribbler, kicker at 1 kHz
                self.group.substep(d)
            else:
                for rig in self.substep_rigs:
                    rig.substep(m, d)
            mj.mj_step(m, d)
            sub_t[k] = d.time
            ballk[k, :3] = self.ball.pos
            ballk[k, 3:] = self.ball.vel
            nc = d.ncon
            tk, pk = set(), set()
            if nc:
                g = d.contact.geom[:nc]
                rr = self.geom_robot[g]
                isb = g == self.ball_geom
                hit = isb[:, 0] & (rr[:, 1] >= 0)
                for i in rr[hit, 1]:
                    tk.add(self.ids[i])
                hit = isb[:, 1] & (rr[:, 0] >= 0)
                for i in rr[hit, 0]:
                    tk.add(self.ids[i])
                both = (rr[:, 0] >= 0) & (rr[:, 1] >= 0) & (rr[:, 0] != rr[:, 1])
                for i, j in rr[both]:
                    a, b = (int(i), int(j)) if i < j else (int(j), int(i))
                    if (a, b) in pk:
                        continue
                    pk.add((a, b))
                    if d.time - self.pair_last.get((a, b), -1e9) > 0.1 + 1e-9:  # a new collision (S1)
                        qa, qb = self.ids[a], self.ids[b]
                        crashes.append(
                            dict(
                                t=float(d.time),
                                a=qa,
                                b=qb,
                                pa=self.robot_pose(qa)[0][:2],
                                pb=self.robot_pose(qb)[0][:2],
                                va=tuple(vprev[a]),
                                vb=tuple(vprev[b]),
                            )
                        )
                for key in pk:
                    self.pair_last[key] = float(d.time)
            touches.append(tk)
            pairs.append({(self.ids[a], self.ids[b]) for a, b in pk})
        self.k += 1
        kicks = self._rig_events(sub_t)
        snap = dict(
            t=float(d.time),
            dt=CONTROL_DT,
            robots=self._robot_table(),
            on_field=dict(self.on_field),
            sub_t=sub_t,
            ball=ballk,
            touches=touches,
            kicks=kicks,
            crashes=crashes,
            pairs=pairs,
        )
        if self.onboard:
            self._odometry_step()
        actions = self.referee.update(snap)
        if actions:
            self._act(actions)
        ev = self.referee.events
        if len(ev) > self._ev_seen:
            self.events.extend(ev[self._ev_seen :])
            self._ev_seen = len(ev)
        assert N == len(self.ids)
        self.qpos_hist.append((self.k, d.qpos.copy()))
        if len(self.qpos_hist) > self.vision_delay + self.vision_period:
            del self.qpos_hist[0]

    def _odometry_step(self):
        """every robot's wheel odometry and gyro over the control step just simulated (sim/odometry.py): the true body
        velocity, and the setpoint's for the wheels that slip while the base is blocked or pushed."""
        from .odometry import body_velocity

        for rid in self.ids:
            if not self.on_field[rid]:
                continue
            p, v = self.robot_pose(rid)
            rig = self.rigs[rid]
            knots = getattr(rig, "knots", None)
            vsp = tuple(float(x) for x in knots[-1][1]) if knots else v
            vb, _ = self.odo[rid].step(body_velocity(v, p[2]), body_velocity(vsp, p[2]), CONTROL_DT)
            self.odo_vb[rid] = tuple(float(x) for x in vb)

    def odom_to_world(self, rid, x, y, yaw):
        """onboard mode: a pose in the robot's odometry frame (its own idea of the field) -> the true world pose the
        base must go to. The robot moves relative to where it is, as a robot without global vision does: the
        odometry error at the moment the command takes effect carries into the target."""
        o = self.odo[rid].pose
        p, _ = self.robot_pose(rid)
        c, s_ = math.cos(-o[2]), math.sin(-o[2])
        dx, dy = c * (x - o[0]) - s_ * (y - o[1]), s_ * (x - o[0]) + c * (y - o[1])
        ct, st = math.cos(p[2]), math.sin(p[2])
        return p[0] + ct * dx - st * dy, p[1] + st * dx + ct * dy, yaw + (p[2] - float(o[2]))

    def _rig_events(self, sub_t):
        """the rigs' events of this control step (dicts with "event" (line A) or "type" (stub)); a kick is a touch of
        the ball at the physics sub-step it fired in."""
        kicks = []
        for rid in self.ids:
            rig = self.rigs[rid]
            evs = rig.take_events() if hasattr(rig, "take_events") else rig.events
            for e in list(evs):
                ev = dict(e) if isinstance(e, dict) else dict(event=str(e))
                typ = ev.pop("type", None) or ev.get("event")
                ev["event"] = typ
                ev["type"] = "robot_event"
                ev["robot"] = f"{rid[0]}{rid[1]}"
                if typ == "kicked":
                    kicks.append((float(ev.get("t", sub_t[0])), rid))
                self.events.append(ev)
            if not hasattr(rig, "take_events"):
                rig.events.clear()
        return kicks

    def _act(self, actions):
        for a in actions:
            if a[0] == "place_ball":
                self.ball.place(a[1], a[2])
            elif a[0] == "move_robot":
                self._reset_robot(a[1], a[2])
            elif a[0] == "remove_robot":
                self.remove_robot(a[1])
            elif a[0] == "return_robot":
                self.return_robot(a[1], a[2])
        self.mj.mj_forward(self.model, self.data)

    def run(self, seconds: float, policy=None):
        """step for `seconds` of world time; policy(world) may issue commands before each step."""
        for _ in range(int(round(seconds / CONTROL_DT))):
            if self.referee.stage == "POST_GAME":
                break
            if policy is not None:
                policy(self)
            self.step()

    # ------------------------------------------------------------------------------------------------ views
    def snapshot(self) -> dict:
        """the truth, for the referee's record and the match log (never for a player)."""
        robots = []
        for rid in self.ids:
            p, v = self.robot_pose(rid)
            st = self.rigs[rid].state() if hasattr(self.rigs[rid], "state") else {}
            robots.append(
                dict(
                    team=rid[0],
                    number=rid[1],
                    on_field=self.on_field[rid],
                    pose=[round(x, 5) for x in p],
                    vel=[round(x, 5) for x in v],
                    rig=st,
                )
            )
        return dict(
            t=round(float(self.data.time), 4),
            step=self.k,
            revision=REVISION,
            ball=dict(pos=[round(float(x), 5) for x in self.ball.pos], vel=[round(float(x), 5) for x in self.ball.vel]),
            robots=robots,
            referee=self.referee.status(),
        )

    def vision_frame(self):
        """(step, qpos) of the frame the cameras show now: the state VISION_DELAY_STEPS control steps ago (the
        oldest kept frame early in a match). Pure."""
        if self.vision_period == 1:
            return self.qpos_hist[0]
        want = (max(0, self.k - self.vision_delay) // self.vision_period) * self.vision_period
        return next((h for h in self.qpos_hist if h[0] == want), self.qpos_hist[0])

    def sign(self, team) -> int:
        """+1 if `team` attacks +x (world) now (the shoot-out keeps the second half's ends)."""
        return attack_sign(team, min(self.referee.half, 2))

    def own_state(self, rid) -> dict:
        """What robot rid's own sensors and controller know (team frame): pose and velocity (onboard estimate:
        exact here, declared), the bar, the capacitor, the armed kick, the break beam, its target and eta. No ball,
        no other robot (the grip's internal state `dribbler_engaged` is not a sensor and is left out)."""
        s = self.sign(rid[0])
        out = dict(number=rid[1], on_field=bool(self.on_field[rid]))
        if not self.on_field[rid]:
            return out
        st = self.rigs[rid].state() if hasattr(self.rigs[rid], "state") else {}
        if self.onboard:  # no global pose: the wheel odometry and gyro, and the last pose the handlers told
            o = self.odo[rid]
            x, y, yaw = to_team(s, float(o.pose[0]), float(o.pose[1]), float(o.pose[2]))
            k0, tp = self.told[rid]
            tx, ty, tyaw = to_team(s, tp[0], tp[1], tp[2])
            out.update(
                odom=[round(x, 5), round(y, 5), round(yaw, 5)],
                odom_vel_body=[round(v, 5) for v in self.odo_vb[rid]],
                told=dict(pose=[round(tx, 4), round(ty, 4), round(tyaw, 4)], t=round(k0 * CONTROL_DT, 3)),
            )
        else:
            p, v = self.robot_pose(rid)
            x, y, yaw = to_team(s, p[0], p[1], p[2])
            vx, vy = vec_to_team(s, v[0], v[1])
            out.update(pose=[round(x, 5), round(y, 5), round(yaw, 5)], vel=[round(vx, 5), round(vy, 5), round(v[2], 5)])
            if "vel_body" in st:
                out["vel_body"] = [round(float(a), 5) for a in st["vel_body"]]
        for k in ("dribbler_rpm", "dribbler_target_rpm", "kicker_charge", "kicker_wait_max_s", "ball_in_beam"):
            if k in st:
                out[k] = round(float(st[k]), 3) if isinstance(st[k], float) else st[k]
        if "kicker_armed" in st:
            out["kicker_armed"] = st["kicker_armed"]
        tg = st.get("target")
        if tg and not self.onboard:  # onboard: the world target would tell the odometry error
            tx, ty, tyaw = to_team(s, tg["x"], tg["y"], tg["yaw"])
            ve = vec_to_team(s, *tg["v_end"]) if tg.get("v_end") is not None else (0.0, 0.0)
            out["target"] = dict(
                x=round(tx, 4),
                y=round(ty, 4),
                theta=round(tyaw, 4),
                t=tg.get("t"),
                v_end=[round(float(ve[0]), 4), round(float(ve[1]), 4)],
            )
        if st.get("eta") is not None:
            out["eta"] = st["eta"]
        return out

    def own_event(self, e: dict, team: str):
        """A rig or skill event of `team`'s own robots as the team sees it (None for anything else): the robot as its
        number, only the fields its own sensors know (OWN_EVENT_FIELDS)."""
        r = e.get("robot") or ""
        if not r.startswith(team):
            return None
        num = int(r[len(team) :])
        if e.get("type") == "skill":
            keep = {k: v for k, v in e.items() if k not in ("type", "robot")}
            return dict(kind="command", robot=num, **keep)
        if e.get("type") == "robot_event":
            name = e.get("event")
            if name not in OWN_EVENT_FIELDS:
                return None
            out = dict(kind=name, robot=num, **{k: e[k] for k in OWN_EVENT_FIELDS[name] if k in e})
            if "ball" in out:
                out["ball_in_beam"] = out.pop("ball")
            return out
        return None

    def truth_view(self, team) -> dict:
        """The truth in `team`'s frame, for the scripted opponents only (never a player's observation): the game
        time, the ball (position, velocity), both teams' robots (pose, velocity, on the field) and the referee's
        status with `us` / `them`."""
        s = self.sign(team)
        bp, bv = self.ball.pos, self.ball.vel
        bx, by = to_team(s, float(bp[0]), float(bp[1]))
        bvx, bvy = vec_to_team(s, float(bv[0]), float(bv[1]))

        def robots(tm):
            out = {}
            for rid in self.ids:
                if rid[0] != tm:
                    continue
                p, v = self.robot_pose(rid)
                x, y, yaw = to_team(s, p[0], p[1], p[2])
                vx, vy = vec_to_team(s, v[0], v[1])
                out[rid[1]] = dict(on_field=bool(self.on_field[rid]), pose=[x, y, yaw], vel=[vx, vy, v[2]])
            return out

        return dict(
            t=float(self.data.time),
            step=self.k,
            team=team,
            ball=dict(pos=[bx, by, float(bp[2])], vel=[bvx, bvy, float(bv[2])]),
            us=robots(team),
            them=robots(other(team)),
            referee=self.referee_view(team),
        )

    def referee_view(self, team) -> dict:
        """The game controller's information as `team` sees it (rulebook §2.3.2; team frame, us / them)."""
        st = self.referee.status()
        s = self.sign(team)
        who = {team: "us", other(team): "them", None: None}
        nc = st.get("next_command")
        px, py = to_team(s, *st["placement"])
        out = dict(
            stage=st["stage"],
            half=st["half"],
            command=st["command"],
            for_team=who.get(st["for_team"]),
            next_command=None if not nc else [nc[0], who.get(nc[1])],
            play_time=st["play_time"],
            time_left=st["time_left"],
            score={"us": st["score"][team], "them": st["score"][other(team)]},
            fouls={"us": st["fouls"][team], "them": st["fouls"][other(team)]},
            yellow_cards_left_s={"us": st["yellow_cards"][team], "them": st["yellow_cards"][other(team)]},
            red_cards={"us": st["red_cards"][team], "them": st["red_cards"][other(team)]},
            allowed_robots={"us": st["allowed_robots"][team], "them": st["allowed_robots"][other(team)]},
            on_field={
                "us": sum(1 for r in self.ids if r[0] == team and self.on_field[r]),
                "them": sum(1 for r in self.ids if r[0] != team and self.on_field[r]),
            },
            placement=[round(px, 4), round(py, 4)],
            keeper=st["keeper"],
            attack_sign=s,
            winner=who.get(st["winner"]),
        )
        rd = self.referee.remove_deadline.get(team)
        if rd is not None:
            out["remove_robot_within_s"] = round(max(0.0, rd - self.referee.t), 2)
        so = st.get("shootout")
        if so:
            out["shootout"] = dict(
                goals={"us": so["goals"][team], "them": so["goals"][other(team)]},
                kicks={"us": list(so["kicks"][team]), "them": list(so["kicks"][other(team)])},
            )
        return out

    def drain_events(self) -> list:
        ev, self.events = self.events, []
        return ev
