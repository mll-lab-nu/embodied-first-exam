"""Stand-in for bodies/ssl_robot (line A) until it lands: the same mount / rig / Rig signatures (interfaces v1 §3), a
plain cylinder with an idealized base, an impulse kicker and a capped "adhesion" dribbler. It exists so that the
field, the ball, the world and the referee can be built and tested now; it is NOT the competition robot and none of its
kicker or dribbler numbers is meant to be realistic beyond the limits it shares with the proposal.

- hull: a cylinder 0.18 m wide, 0.148 m high (rulebook §3.2.2 <= 0.18 x 0.15; TIGERs v2020 ETDP table 1), 2.62 kg
  (TIGERs v2020), floating 2 mm above the carpet (the base is a planar joint: slide x, slide y, hinge yaw);
- base: bodies/servo.PlanarBase on the norm with the proposal's limits (3 m/s, 3 m/s^2 accelerating and braking,
  150 m/s^3 ESTIMATE, 20 rad/s, 50 rad/s^2, yaw jerk ESTIMATE), tracked by a PD with velocity feed-forward on each joint;
  the drive force is capped at 40 N (ESTIMATE, stub only);
- kicker: an impulse when the ball is in the kick zone (the "light barrier" in front of the hull): flat <= 8.5 m/s
  (TIGERs v2020 ETDP), chip at 45 deg <= 5.5 m/s (Sumatra config), speed error sd 0.18 m/s (ZJUNlict 2024 TDP), heading
  error sd 1 deg (ESTIMATE), 0.5 s to recharge (TIGERs v2020 ETDP §3.2); the kick adds the robot's own velocity;
- dribbler: while on, a spring-damper force on the ball towards the hull's front point, capped at 0.3 N (stub only;
  line A owns the real dribbler, proposal §4.4).
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

_here = os.path.dirname(os.path.abspath(__file__))
for _d in (os.path.dirname(os.path.dirname(os.path.dirname(_here))), os.path.dirname(os.path.dirname(_here))):
    if os.path.isdir(os.path.join(_d, "bodies")) and _d not in sys.path:
        sys.path.insert(0, _d)
from bodies import servo as SV  # noqa: E402

KIND = "stub"
RADIUS, HEIGHT, MASS = 0.09, 0.148, 2.62
LIFT = 0.002
KP, KV = 4000.0, 200.0  # N/m, N s/m (2.62 kg: about 39 rad/s, damping ratio ~1)
KP_YAW, KV_YAW = 40.0, 2.0
FORCE_MAX, TORQUE_MAX = 40.0, 5.0
LIMITS = dict(
    base=dict(
        mode="norm",
        speed_m_s=3.0,
        accel_m_s2=3.0,
        jerk_m_s3=150.0,
        yaw_rate_rad_s=20.0,
        yaw_accel_rad_s2=50.0,
        yaw_jerk_rad_s3=2500.0,
    ),
    kicker=dict(
        flat_max_m_s=8.5, chip_max_m_s=5.5, chip_angle_deg=45.0, speed_sd_m_s=0.18, dir_sd_deg=1.0, recharge_s=0.5
    ),
    dribbler=dict(max_rpm=17000.0, force_cap_n=0.3, k_n_m=20.0, c_n_s_m=1.0),
)
BALL_R = 0.0215
FRONT = RADIUS + BALL_R  # ball centre against the hull, straight ahead
KICK_ZONE = (FRONT - 0.01, FRONT + 0.015, 0.03)  # forward min, max; |lateral| max
DRIBBLE_ZONE = (FRONT - 0.01, FRONT + 0.035, 0.045)
CONTROL_DT = 0.01
TEAM_RGBA = {"blue": (0.1, 0.3, 0.95, 1.0), "yellow": (0.95, 0.85, 0.1, 1.0)}


def mount(spec, name: str, team: str, number: int, pose=(0.0, 0.0, 0.0), lod: str = "sim") -> dict:
    """Add one stand-in robot to a mujoco.MjSpec; returns its handles (names)."""
    import mujoco

    x, y, yaw = pose
    b = spec.worldbody.add_body(name=name, pos=[0.0, 0.0, LIFT])
    jn = [f"{name}_x", f"{name}_y", f"{name}_yaw"]
    b.add_joint(name=jn[0], type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[1, 0, 0], damping=0.0)
    b.add_joint(name=jn[1], type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[0, 1, 0], damping=0.0)
    b.add_joint(name=jn[2], type=mujoco.mjtJoint.mjJNT_HINGE, axis=[0, 0, 1], damping=0.0)
    hull = f"{name}_hull"
    b.add_geom(
        name=hull,
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[RADIUS, HEIGHT / 2, 0],
        pos=[0, 0, HEIGHT / 2],
        mass=MASS,
        rgba=[0.12, 0.12, 0.12, 1.0],
        condim=3,
        friction=[0.5, 0.005, 0.0001],
    )
    b.add_geom(
        name=f"{name}_team_dot",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[0.025, 0.0005, 0],
        pos=[0, 0, HEIGHT + 0.0005],
        rgba=list(TEAM_RGBA[team]),
        contype=0,
        conaffinity=0,
        mass=0.0,
    )
    b.add_geom(
        name=f"{name}_front_dot",
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        size=[0.012, 0.0005, 0],
        pos=[0.06, 0, HEIGHT + 0.0005],
        rgba=[1, 1, 1, 1],
        contype=0,
        conaffinity=0,
        mass=0.0,
    )
    b.add_site(name=f"{name}_kicker", pos=[FRONT, 0, BALL_R])
    acts = []
    for j, kp, kv, f in ((jn[0], KP, KV, FORCE_MAX), (jn[1], KP, KV, FORCE_MAX), (jn[2], KP_YAW, KV_YAW, TORQUE_MAX)):
        for kind, gain, bias in (("p", kp, [0, -kp, 0]), ("v", kv, [0, 0, -kv])):
            a = spec.add_actuator(name=f"{j}_{kind}", target=j, trntype=mujoco.mjtTrn.mjTRN_JOINT)
            a.gaintype = mujoco.mjtGain.mjGAIN_FIXED
            a.biastype = mujoco.mjtBias.mjBIAS_AFFINE
            gp = np.zeros(10)
            gp[0] = gain
            bp = np.zeros(10)
            bp[:3] = bias
            a.gainprm, a.biasprm = gp, bp
            a.forcelimited = True
            a.forcerange = [-f / 2, f / 2]  # the p and v parts share the cap
            a.ctrllimited = False
            acts.append(f"{j}_{kind}")
    return dict(
        name=name,
        team=team,
        number=number,
        kind=KIND,
        body=name,
        base_joints=jn,
        actuators=acts,
        geoms=[hull],
        kicker_site=f"{name}_kicker",
        init_pose=(float(x), float(y), float(yaw)),
        radius=RADIUS,
    )


class Rig:
    """Commands of one robot (world frame). step() once per 10 ms control step."""

    def __init__(self, model, data, handles, limits=None, rng=None):
        import mujoco

        L = dict(LIMITS)
        if limits:
            L.update(limits)
        self.L = L
        self.h = handles
        self.m = model
        self.jq = [
            int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j)])
            for j in handles["base_joints"]
        ]
        self.jv = [
            int(model.jnt_dofadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j)])
            for j in handles["base_joints"]
        ]
        self.act = {n: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, n) for n in handles["actuators"]}
        jb = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "ball_free")
        self.bq, self.bv = int(model.jnt_qposadr[jb]), int(model.jnt_dofadr[jb])
        self.ball_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "ball")
        self.base = SV.PlanarBase(SV.BaseLimits.of(L["base"]), CONTROL_DT)
        self.rng = rng if rng is not None else np.random.default_rng(0)
        self.events: list = []
        self.t = 0.0
        self.charged_at = 0.0
        self.arm = None  # (speed, mode, until)
        self.rpm = 0.0
        self.target = None
        self.reset(handles["init_pose"], data)

    # ------------------------------------------------------------------------------------------------ commands
    def reset(self, pose, data=None):
        """place the robot at pose (x, y, yaw) at rest (the referee moving a robot, or a substitution)."""
        x, y, yaw = (float(v) for v in pose)
        if data is not None:
            for a, v in zip(self.jq, (x, y, yaw)):
                data.qpos[a] = v
            for a in self.jv:
                data.qvel[a] = 0.0
        self.base.reset(np.array([x, y, yaw]))
        self.target = (np.array([x, y, yaw]), np.zeros(3))
        self.arm = None

    def set_base_target(self, x, y, yaw, t=None, v_end=(0.0, 0.0)):
        _, yaw_now = self.base.p, self.base.yaw
        yaw = yaw_now + (math.atan2(math.sin(yaw - yaw_now), math.cos(yaw - yaw_now)))  # shortest turn
        self.target = (np.array([x, y, yaw], float), np.zeros(3))

    def kick(self, speed, mode="flat", armed_for=0.0) -> str:
        if self.t < self.charged_at:
            return "kicker_not_ready"
        k = self.L["kicker"]
        cap = k["chip_max_m_s"] if mode == "chip" else k["flat_max_m_s"]
        status = "ok"
        if speed > cap:
            speed, status = cap, "clipped"
        self.arm = (float(max(0.0, speed)), mode, self.t + max(0.0, float(armed_for)))
        return status

    def dribble(self, rpm):
        self.rpm = float(np.clip(rpm, 0.0, self.L["dribbler"]["max_rpm"]))

    # ------------------------------------------------------------------------------------------------ stepping
    def _pose(self, data):
        return np.array([data.qpos[a] for a in self.jq]), np.array([data.qvel[a] for a in self.jv])

    def _ball_local(self, data, q):
        bp = data.qpos[self.bq : self.bq + 3]
        dx, dy = bp[0] - q[0], bp[1] - q[1]
        c, s = math.cos(q[2]), math.sin(q[2])
        return c * dx + s * dy, -s * dx + c * dy, bp[2]

    def ball_in_kick_zone(self, data) -> bool:
        q, _ = self._pose(data)
        f, lat, z = self._ball_local(data, q)
        return KICK_ZONE[0] <= f <= KICK_ZONE[1] and abs(lat) <= KICK_ZONE[2] and z < 0.05

    def step(self, model, data):
        self.t = float(data.time)
        q, qd = self._pose(data)
        r, rd = self.target
        sq, sqd, _ = self.base.step(r, rd)
        for (j, kind), val in zip(
            ((0, "p"), (0, "v"), (1, "p"), (1, "v"), (2, "p"), (2, "v")), (sq[0], sqd[0], sq[1], sqd[1], sq[2], sqd[2])
        ):
            data.ctrl[self.act[f"{self.h['base_joints'][j]}_{kind}"]] = val
        # kicker
        if self.arm is not None:
            speed, mode, until = self.arm
            if self.ball_in_kick_zone(data):
                k = self.L["kicker"]
                v = max(0.0, speed + self.rng.normal(0.0, k["speed_sd_m_s"])) if speed > 0 else 0.0
                h = q[2] + math.radians(self.rng.normal(0.0, k["dir_sd_deg"]))
                if mode == "chip":
                    a = math.radians(k["chip_angle_deg"])
                    vel = np.array([v * math.cos(a) * math.cos(h), v * math.cos(a) * math.sin(h), v * math.sin(a)])
                else:
                    vel = np.array([v * math.cos(h), v * math.sin(h), 0.0])
                vel[:2] += qd[:2]
                data.qvel[self.bv : self.bv + 3] = vel
                data.qvel[self.bv + 3 : self.bv + 6] = 0.0
                self.events.append(dict(type="kicked", speed=float(np.linalg.norm(vel)), mode=mode, t=self.t))
                self.arm = None
                self.charged_at = self.t + self.L["kicker"]["recharge_s"]
            elif self.t >= until:
                self.events.append(dict(type="kick_expired", t=self.t))
                self.arm = None
        # dribbler: capped spring-damper towards the hull's front point (stub)
        if self.rpm > 0.0:
            f, lat, z = self._ball_local(data, q)
            if DRIBBLE_ZONE[0] <= f <= DRIBBLE_ZONE[1] and abs(lat) <= DRIBBLE_ZONE[2] and z < 0.05:
                D = self.L["dribbler"]
                c, s = math.cos(q[2]), math.sin(q[2])
                target = np.array([q[0] + c * FRONT, q[1] + s * FRONT])
                bp = data.qpos[self.bq : self.bq + 2]
                bv = data.qvel[self.bv : self.bv + 2]
                tv = qd[:2] + qd[2] * np.array([-s * FRONT, c * FRONT])
                F = D["k_n_m"] * (target - bp) + D["c_n_s_m"] * (tv - bv)
                n = float(np.linalg.norm(F))
                if n > D["force_cap_n"]:
                    F *= D["force_cap_n"] / n
                data.xfrc_applied[self.ball_body, :2] += F

    def state(self) -> dict:
        return dict(
            kind=KIND,
            t=self.t,
            kicker_ready=self.t >= self.charged_at,
            armed=self.arm is not None,
            dribbler_rpm=self.rpm,
        )

    def sensor(self, data) -> dict:
        q, qd = self._pose(data)
        return dict(pose=q.tolist(), vel=qd.tolist(), ball_detected=self.ball_in_kick_zone(data), **self.state())


def rig(model, data, handles, limits=None, rng=None) -> Rig:
    return Rig(model, data, handles, limits, rng)
