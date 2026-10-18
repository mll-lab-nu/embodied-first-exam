"""practice.py: a CPU practice simulator for the joint level of robot soccer (your toolkit, /opt/robot).

The match's own physics for robots under joint control: the same MuJoCo scene (pitch, boards, goals, ball, four Booster
T1 lower bodies: /opt/robot/lib/soccer_scene.py), the same 2 ms physics step and 20 ms control step, the same row
limiter (at most the URDF speed x 20 ms from the row before, inside the joint ranges, a non-finite value keeps the
previous one), the same PD law with Booster's deployment gains, the same motors (/opt/robot/lib/bodies/servo.py
Actuators with booster_t1's torque-speed envelope, I^2 t foldback and 1 kW bus per robot), the same ball rolling
resistance, the same placement (Booster's default stance, upright, soles on the floor) and the referee's 1 s hold after a
placement. What it does NOT have: the referee's rules (goals, penalties, stand-ups), the opponents' controller (there is
none here: robots you do not drive can be parked off the pitch or held still as obstacles), the cameras.

    import sys; sys.path.insert(0, "/opt/robot"); import practice as PR
    sim = PR.Practice()                                 # all four robots parked off the pitch, ball at the centre
    sim.place("A1", x=-2.0, y=0.0, yaw=0.0)             # Booster's default stance; held 1 s (hold=False: not held)
    sim.place("B1", 1.0, 0.5, 3.14, statue=True)         # an obstacle: held still for good
    sim.place_ball(-1.0, 0.0)
    for k in range(500):
        o = sim.observe("A1")                            # the match's low-level robot state + "truth" (team A frame)
        sim.step({"A1": my_row(o)})                     # 12 joint targets per driven robot; others hold their row
        if o["fallen"]: ...
    sim.push("A1", fx=150.0, fy=0.0, dur_s=0.1)         # a shove on the trunk (N)

Frames: world = team A's frame (A attacks +x). Joint order: left hip pitch, roll, yaw, knee, ankle pitch, roll, then
the right leg (sim.JOINTS). Deterministic (float64 MuJoCo). About 1-2 ms of CPU per control step for one robot.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)
os.environ.setdefault("RCB_T1_ASSETS", os.path.join(HERE, "t1"))
import mujoco  # noqa: E402
import tomllib  # noqa: E402
import soccer_scene as SC  # noqa: E402
from bodies import servo as SV  # noqa: E402

T1 = tomllib.loads(open(os.path.join(LIB, "bodies", "booster_t1", "body.toml"), "rb").read().decode())
PHYS_DT, SUB = 0.002, 10
CTRL_DT = PHYS_DT * SUB
JOINTS = ["Left_Hip_Pitch", "Left_Hip_Roll", "Left_Hip_Yaw", "Left_Knee_Pitch", "Left_Ankle_Pitch", "Left_Ankle_Roll",
          "Right_Hip_Pitch", "Right_Hip_Roll", "Right_Hip_Yaw", "Right_Knee_Pitch", "Right_Ankle_Pitch",
          "Right_Ankle_Roll"]
LEG_KEYS = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"] * 2
KP = np.array([200.0, 200.0, 200.0, 200.0, 50.0, 50.0] * 2)
KD = np.array([5.0, 5.0, 5.0, 5.0, 1.0, 1.0] * 2)
DEFAULT_Q = np.array([-0.2, 0.0, 0.0, 0.4, -0.25, 0.0] * 2)       # Booster's default joint angles (the stance)
ROW_STEP = np.tile(np.asarray(T1["limits"]["leg"]["speed_rad_s"], float), 2) * CTRL_DT
TORQUE = np.tile(np.asarray(T1["limits"]["leg"]["torque_nm"], float), 2)
FALL_Z = 0.40                    # the referee: trunk (IMU) below this = fallen
HOLD_S = 1.0
ROLL_DECEL = 0.52


def _yaw_quat(yaw):
    return np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])


class _Robot:
    def __init__(self, m, name, idx):
        p = name + ":"
        self.name, self.idx = name, idx
        self.jq = np.array([m.jnt_qposadr[m.joint(p + n).id] for n in JOINTS])
        self.jv = np.array([m.jnt_dofadr[m.joint(p + n).id] for n in JOINTS])
        self.act = np.array([m.actuator(p + n).id for n in JOINTS])
        root = m.joint(p + "root")
        self.rq, self.rv = int(m.jnt_qposadr[root.id]), int(m.jnt_dofadr[root.id])
        s = lambda n: int(m.sensor_adr[m.sensor(p + n).id])  # noqa: E731
        self.s_quat, self.s_gyro, self.s_acc = s("torso_quat"), s("torso_gyro"), s("accelerometer")
        self.imu = m.site(p + "imu").id
        self.lo = m.jnt_range[[m.joint(p + n).id for n in JOINTS], 0].copy()
        self.hi = m.jnt_range[[m.joint(p + n).id for n in JOINTS], 1].copy()
        self.trunk = m.body(p + "Trunk").id


class Practice:
    def __init__(self):
        self.m = SC.build_model()
        self.d = mujoco.MjData(self.m)
        m = self.m
        self.names = list(SC.ROBOTS)
        self.rob = {n: _Robot(m, n, i) for i, n in enumerate(self.names)}
        rs = list(self.rob.values())
        self.motors = SV.Actuators(m, np.concatenate([r.act for r in rs]), np.concatenate([r.jv for r in rs]),
                                   np.concatenate([TORQUE for _ in rs]), PHYS_DT,
                                   **SV.motor_model(T1, LEG_KEYS * len(rs),
                                                    groups=[np.arange(12) + 12 * i for i in range(len(rs))]))
        bj = m.joint("ball")
        self._bq, self._bv = int(m.jnt_qposadr[bj.id]), int(m.jnt_dofadr[bj.id])
        self._bb = int(m.geom_bodyid[m.geom("ball").id])
        bm = float(m.body_mass[self._bb])
        self._rr = bm * ROLL_DECEL * (1.0 + float(m.body_inertia[self._bb][0]) / (bm * SC.BALL_R ** 2))
        self.stance_z = self._stance_z()
        self.reset()

    def _stance_z(self):
        m, d = self.m, mujoco.MjData(self.m)
        r = self.rob[self.names[0]]
        d.qpos[r.rq:r.rq + 7] = [0, 0, 0, 1, 0, 0, 0]
        d.qpos[r.jq] = DEFAULT_Q
        mujoco.mj_kinematics(m, d)
        low = 0.0
        for g in range(m.ngeom):
            b = m.body(int(m.geom_bodyid[g])).name
            if not b.startswith(r.name + ":") or not b.endswith("foot_link") or not m.geom_contype[g]:
                continue
            if int(m.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_BOX):
                R, c, h = d.geom_xmat[g].reshape(3, 3), d.geom_xpos[g], m.geom_size[g]
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        for sz in (-1, 1):
                            low = min(low, float((c + R @ (h * np.array([sx, sy, sz])))[2]))
            else:
                low = min(low, float(d.geom_xpos[g][2] - m.geom_rbound[g]))
        return -low + 0.0005

    def reset(self):
        """Every robot parked off the pitch (held), the ball at the centre, cold motors, time 0."""
        mujoco.mj_resetData(self.m, self.d)
        self.motors.cool_down()
        self.k = 0
        self.row, self.held, self.held_pose, self.parked = {}, {}, {}, set()
        for i, n in enumerate(self.names):
            self.place(n, -20.0 + 3.0 * i, 20.0, 0.0, statue=True)
            self.parked.add(n)
        self.place_ball(0.0, 0.0)
        self.pushes = []
        mujoco.mj_forward(self.m, self.d)

    def place(self, name, x, y, yaw, hold=True, statue=False):
        """Put a robot in Booster's default stance, upright at (x, y, yaw); held 1 s (as the referee does after every
        placement), or held for good (statue=True: an obstacle)."""
        r, d = self.rob[name], self.d
        d.qpos[r.rq:r.rq + 3] = [x, y, self.stance_z]
        d.qpos[r.rq + 3:r.rq + 7] = _yaw_quat(yaw)
        d.qpos[r.jq] = DEFAULT_Q
        d.qvel[r.rv:r.rv + 6] = 0.0
        d.qvel[r.jv] = 0.0
        self.row[name] = DEFAULT_Q.copy()
        self.held[name] = 10 ** 12 if statue else (self.k + int(round(HOLD_S / CTRL_DT)) if hold else self.k)
        self.held_pose[name] = d.qpos[r.rq:r.rq + 7].copy()
        self.parked.discard(name)
        mujoco.mj_forward(self.m, self.d)

    def place_ball(self, x, y, vx=0.0, vy=0.0):
        d = self.d
        d.qpos[self._bq:self._bq + 7] = [x, y, SC.BALL_R, 1, 0, 0, 0]
        d.qvel[self._bv:self._bv + 6] = 0.0
        d.qvel[self._bv:self._bv + 2] = [vx, vy]
        mujoco.mj_forward(self.m, self.d)

    def push(self, name, fx, fy, dur_s=0.1):
        """A horizontal force (N) on the trunk for dur_s (from the next physics step)."""
        g0 = self.k * SUB
        self.pushes.append((name, g0, g0 + int(round(dur_s / PHYS_DT)), float(fx), float(fy)))

    def step(self, rows: dict):
        """One 20 ms control step; rows: {robot: 12 joint targets} (robots not given keep their row)."""
        m, d = self.m, self.d
        for n, t in rows.items():
            prev = self.row[n]
            t = np.asarray(t, float).reshape(12)
            t = np.where(np.isfinite(t), t, prev)
            t = np.clip(t, prev - ROW_STEP, prev + ROW_STEP)
            self.row[n] = np.clip(t, self.rob[n].lo, self.rob[n].hi)
        rs = list(self.rob.values())
        tg = np.array([self.row[r.name] for r in rs])
        held = [r for r in rs if self.k < self.held[r.name]]
        for s in range(SUB):
            d.xfrc_applied[:] = 0.0
            if d.xipos[self._bb][2] <= SC.BALL_R + 0.02:
                v = d.cvel[self._bb][3:5]
                sp = float(np.hypot(v[0], v[1]))
                if sp > 1e-6:
                    d.xfrc_applied[self._bb, :2] = -self._rr * min(1.0, sp / 0.05) * v / sp
            g = self.k * SUB + s
            for n, a, b, fx, fy in self.pushes:
                if a <= g < b:
                    d.xfrc_applied[self.rob[n].trunk, 0] += fx
                    d.xfrc_applied[self.rob[n].trunk, 1] += fy
            q = np.array([d.qpos[r.jq] for r in rs])
            qd = np.array([d.qvel[r.jv] for r in rs])
            tau = KP * (tg - q) - KD * qd
            self.motors.write(d, tau.reshape(-1))
            mujoco.mj_step(m, d)
            for r in held:
                d.qpos[r.rq:r.rq + 7] = self.held_pose[r.name]
                d.qvel[r.rv:r.rv + 6] = 0.0
        self.k += 1

    def observe(self, name) -> dict:
        """The match's low-level state of one robot (team A frame) plus "truth": the ball and every robot."""
        d, r = self.d, self.rob[name]
        q = d.sensordata[r.s_quat:r.s_quat + 4]
        w, x, y, z = q
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
        pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
        h = float(d.site_xpos[r.imu][2])
        out = dict(pose=dict(x=float(d.qpos[r.rq]), y=float(d.qpos[r.rq + 1]), yaw=yaw),
                   velocity=dict(vx=float(d.qvel[r.rv]), vy=float(d.qvel[r.rv + 1])),
                   imu=dict(roll=roll, pitch=pitch, yaw=yaw), trunk_height=h, fallen=h < FALL_Z,
                   joint_pos=d.qpos[r.jq].tolist(), joint_vel=d.qvel[r.jv].tolist(),
                   trunk_quat=d.qpos[r.rq + 3:r.rq + 7].tolist(), gyro=d.sensordata[r.s_gyro:r.s_gyro + 3].tolist(),
                   accelerometer=d.sensordata[r.s_acc:r.s_acc + 3].tolist(), trunk_pos_z=float(d.qpos[r.rq + 2]),
                   trunk_vel=d.qvel[r.rv:r.rv + 3].tolist(), row=self.row[name].tolist(),
                   held_s=max(0, min(self.held[name], 10 ** 6) - self.k) * CTRL_DT, step=self.k,
                   motor_heat=self.motors.h[12 * r.idx:12 * r.idx + 12].tolist())
        bp = d.qpos[self._bq:self._bq + 3]
        out["truth"] = dict(ball=bp.tolist(), ball_v=d.qvel[self._bv:self._bv + 2].tolist(),
                            robots={n: dict(x=float(d.qpos[o.rq]), y=float(d.qpos[o.rq + 1]),
                                            yaw=float(math.atan2(2 * (d.qpos[o.rq + 3] * d.qpos[o.rq + 6] + d.qpos[o.rq + 4] * d.qpos[o.rq + 5]),
                                                                 1 - 2 * (d.qpos[o.rq + 5] ** 2 + d.qpos[o.rq + 6] ** 2))),
                                            parked=n in self.parked)
                                    for n, o in self.rob.items()})
        return out
