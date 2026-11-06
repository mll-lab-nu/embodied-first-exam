"""The table-tennis robot's servo model: the low-level toolkit's servo library (agent side, seat/toolkit.toml).

The robot's own 1 kHz servo law exactly as `game spec` limits.controller documents it (the simulator's rcb_tt.TTServo:
a jerk-limited setpoint for the arm within the Panda's velocity, acceleration and jerk limits, the jerk also capped
by the torque-rate share at the pose; torque = M qdd_sp + kp e + kd de + gravity/Coriolis, limited to 87 / 12 N m and
1000 N m/s; the rail's jerk-limited setpoint and PD force within 620 N; a joint pushed more than resync_rad from its
setpoint makes the setpoint follow it), on the robot-only model (/opt/robot/robot_only.xml). It lets a player roll
its own joint-target rows out on its own robot, as a robotics engineer does with a robot's model and controller
before running a motion on the real machine. It reads nothing of the world: no ball, no table, no opponent (the
robot-only model holds none of them; contacts with the table are therefore not simulated here).

    import sys; sys.path.insert(0, "/opt/robot/lib")
    from tt_servo import RobotSim
    S = RobotSim()                                   # /opt/robot/robot_only.xml
    S.reset(q, qd, q_target, servo)                  # the robot's observed state (9 each) and its servo's state
                                                     # (observation `servo`): the rollout continues exactly
    out = S.rollout(rows)                            # follow one 9-joint target per 10 ms row: per row the blade's
                                                     # (pos, normal, vel) and the joints (q, qd) after it

Deterministic (float64 numpy, MuJoCo's own integrator). Version 1.0.3 (revision 15/12: the setpoint generator at 0.9 of the velocity limits and the joint-velocity reflex; 1.0.2, revision 14/11: the setpoint law of bodies/limits.JerkLimiter).
"""
from __future__ import annotations

import os

import numpy as np

VERSION = "1.0.3"
DEFAULT_XML = os.environ.get("RO_ROBOT_XML", "/opt/robot/robot_only.xml")
JOINTS = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
CONTROL_DT, SUBSTEPS = 0.01, 10
PHYS_DT = CONTROL_DT / SUBSTEPS
# /spec limits (the Franka Panda's: bodies/franka_panda/body.toml; the rail's)
ARM_VEL = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])
ARM_ACC = np.array([15.0, 7.5, 10.0, 12.5, 15.0, 20.0, 20.0])
ARM_JERK = np.array([7500.0, 3750.0, 5000.0, 6250.0, 7500.0, 10000.0, 10000.0])
ARM_TAU = np.array([87.0, 87.0, 87.0, 87.0, 12.0, 12.0, 12.0])
ARM_DTAU = np.full(7, 1000.0)
BASE_V, BASE_A, BASE_J, BASE_F = 2.0, 8.0, 200.0, 620.0
KP = np.array([6e4, 6e4, 2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
KD = np.array([4e3, 4e3, 100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
RESYNC = 0.02
# the joint-velocity rule (/spec limits.controller, revision 15/12): the arm's setpoint generator runs at VMARGIN of the
# velocity limits; a physical arm joint faster than REFLEX x its limit triggers the velocity reflex: the robot holds the
# pose of the trigger (targets ignored) for REFLEX_RECOVER_S, then resumes from rest
VMARGIN, REFLEX, REFLEX_RECOVER_S = 0.9, 1.05, 1.0


def _sqrt_ctrl(err, k, d):
    lin = d / (k * k)
    a = np.abs(err)
    return np.where(a <= lin, k * err, np.sign(err) * np.sqrt(np.maximum(0.0, 2.0 * d * (a - 0.5 * lin))))


def _brake_speed(dist, A, J):
    """The largest speed from which a jerk-limited stop (acceleration from 0, at most A, jerk J) ends within dist
    (bodies/limits.brake_speed)."""
    dist = np.maximum(np.asarray(dist, float), 0.0)
    A, J = np.asarray(A, float), np.asarray(J, float)
    small = dist <= A**3 / J**2
    v_small = np.cbrt(dist * dist * J)
    v_big = 0.5 * (-A * A / J + np.sqrt(A**4 / J**2 + 8.0 * A * dist))
    return np.where(small, v_small, v_big)


def jerk_caps(M, jerk=ARM_JERK, dtau=ARM_DTAU, share=0.7):
    """The arm joints' jerk the torque-rate limit allows at the inertia M: share x dtau / row sums of |M|."""
    cap = share * dtau / np.maximum(np.sum(np.abs(np.asarray(M, float)), axis=1), 1e-9)
    return np.minimum(jerk, cap)


class SetpointModel:
    """Setpoint generator (q, qd, qdd) within |qd| <= vel, |qdd| <= acc, |jerk| <= jerk (the documented law)."""

    KP, KV, BRAKE = 60.0, 300.0, 0.6

    def __init__(self, vel, acc, jerk, dt):
        self.dt = float(dt)
        vel = np.asarray(vel, float)    # one step of jerk and one of acceleration below the limit (discrete overshoot)
        self.V = np.maximum(vel - (np.asarray(jerk, float) * self.dt ** 2 + np.asarray(acc, float) * self.dt), 0.5 * vel)
        self.A, self.J = np.asarray(acc, float), np.asarray(jerk, float)
        self.reset(np.zeros(len(self.A)))

    def reset(self, q, qd=None, qdd=None):
        n = len(self.A)
        self.q = np.asarray(q, float).copy()
        self.qd = np.zeros(n) if qd is None else np.asarray(qd, float).copy()
        self.qdd = np.zeros(n) if qdd is None else np.asarray(qdd, float).copy()

    def step(self, r, rd=None, jerk_cap=None):
        dt, V, A, Jh = self.dt, self.V, self.A, self.J
        J = Jh if jerk_cap is None else np.minimum(Jh, jerk_cap)
        r = np.asarray(r, float)
        rd = np.zeros_like(r) if rd is None else np.asarray(rd, float)
        # the position loop brakes within the acceleration and the jerk in force (bodies/limits.JerkLimiter, revision
        # 14/11): the error left once the present acceleration has ramped to zero at this step's jerk, relative to the
        # reference's velocity (qd - rd), and the jerk-limited stopping speed
        e = r - self.q
        t = np.abs(self.qdd) / J
        e = e - ((self.qd - rd) * t + 0.5 * self.qdd * t * t - np.sign(self.qdd) * J * t**3 / 6.0)
        v_pos = np.sign(e) * np.minimum(self.KP * np.abs(e), _brake_speed(np.abs(e), self.BRAKE * A, J))
        v_cmd = np.clip(rd + v_pos, -V, V)
        a_cmd = np.clip(_sqrt_ctrl(v_cmd - self.qd, self.KV, J), -A, A)
        room_up, room_dn = np.maximum(0.0, V - self.qd), np.maximum(0.0, V + self.qd)
        a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * room_dn), np.sqrt(2.0 * J * room_up))
        hard = (self.qdd > np.sqrt(2.0 * Jh * room_up)) | (self.qdd < -np.sqrt(2.0 * Jh * room_dn))
        a_cmd = np.where(hard, np.clip(a_cmd, -np.sqrt(2.0 * Jh * room_dn), np.sqrt(2.0 * Jh * room_up)), a_cmd)
        jl = np.where(hard, Jh, J)
        j = np.clip((a_cmd - self.qdd) / dt, -jl, jl)
        self.q = self.q + self.qd * dt + 0.5 * self.qdd * dt * dt + j * dt ** 3 / 6.0
        self.qd = self.qd + self.qdd * dt + 0.5 * j * dt * dt
        self.qdd = self.qdd + j * dt
        return self.q, self.qd, self.qdd


class RailLimiter(SetpointModel):
    """The rail's setpoint generator (braking on the jerk-limited stopping distance)."""

    KP, KV, BRAKE = 12.0, 30.0, 0.55

    def step(self, r, rd=None, jerk_cap=None):
        dt, V, A, J = self.dt, self.V, self.A, self.J
        r = np.asarray(r, float)
        rd = np.zeros_like(r) if rd is None else np.asarray(rd, float)
        e = r - self.q
        ab = self.BRAKE * A
        d = np.abs(e)
        v_stop = 0.5 * (-ab * ab / J + np.sqrt((ab * ab / J) ** 2 + 8.0 * ab * d))
        v_cmd = np.clip(rd + np.sign(e) * np.minimum(v_stop, self.KP * d), -V, V)
        a_cmd = np.clip(_sqrt_ctrl(v_cmd - self.qd, self.KV, J), -A, A)
        room_up, room_dn = np.maximum(0.0, V - self.qd), np.maximum(0.0, V + self.qd)
        a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * room_dn), np.sqrt(2.0 * J * room_up))
        j = np.clip((a_cmd - self.qdd) / dt, -J, J)
        self.q = self.q + self.qd * dt + 0.5 * self.qdd * dt * dt + j * dt ** 3 / 6.0
        self.qd = self.qd + self.qdd * dt + 0.5 * j * dt * dt
        self.qdd = self.qdd + j * dt
        return self.q, self.qd, self.qdd


class ServoModel:
    """The robot's servo at 1 kHz (the arm cascade and the rail's), the documented law."""

    def __init__(self):
        self.jl = SetpointModel(ARM_VEL * VMARGIN, ARM_ACC, ARM_JERK, PHYS_DT)
        self.jb = RailLimiter(np.full(2, BASE_V), np.full(2, BASE_A), np.full(2, BASE_J), PHYS_DT)
        self.tau = np.zeros(7)
        self.reflex_at = None          # (time s, q 9) of a joint-velocity reflex, until the recovery

    def sync(self, q, qd, bias_arm):
        self.jl.reset(q[2:], np.clip(qd[2:], -ARM_VEL, ARM_VEL))
        self.jb.reset(q[:2], np.clip(qd[:2], -BASE_V, BASE_V))
        self.tau = np.clip(np.asarray(bias_arm, float), -ARM_TAU, ARM_TAU)
        self.reflex_at = None

    def ctrl(self, q, qd, M_arm, bias, j, prev, new, lo, hi, t=0.0):
        r = prev + (new - prev) * (j / SUBSTEPS)
        rd = (new - prev) / CONTROL_DT
        if self.reflex_at is None and np.any(np.abs(qd[2:]) > REFLEX * ARM_VEL):
            self.reflex_at = (float(t), np.asarray(q, float).copy())     # the joint-velocity reflex: stop the robot
        if self.reflex_at is not None and t - self.reflex_at[0] >= REFLEX_RECOVER_S:
            self.sync(q, qd, bias[2:])                                  # recovered: restart from the actual state
        if self.reflex_at is not None:                                  # stopped: hold the pose of the trigger
            r, rd = self.reflex_at[1].copy(), np.zeros_like(rd)
        q_sp, qd_sp, qdd_sp = self.jl.step(r[2:], rd[2:], jerk_caps(M_arm))
        b_sp, bd_sp, _ = self.jb.step(r[:2], rd[:2])
        e = q_sp - q[2:]
        tau = M_arm @ qdd_sp + KP[2:] * e + KD[2:] * (qd_sp - qd[2:]) + bias[2:]
        f = KP[:2] * (b_sp - q[:2]) + KD[:2] * (bd_sp - qd[:2]) + bias[:2]
        t = np.clip(tau, self.tau - ARM_DTAU * PHYS_DT, self.tau + ARM_DTAU * PHYS_DT)
        self.tau = np.clip(t, -ARM_TAU, ARM_TAU)
        out = np.r_[np.clip(f, lo[:2], hi[:2]), self.tau]
        if np.max(np.abs(e)) > RESYNC:
            big = np.abs(e) > RESYNC
            jl = self.jl
            jl.q[big] = q[2:][big] + np.sign(e[big]) * RESYNC
            jl.qd[big] = np.clip(qd[2:], -jl.V, jl.V)[big]
            jl.qdd[big] = 0.0
        return out


class RobotSim:
    """The robot-only model under its servo: roll joint-target rows out from an observed state."""

    def __init__(self, xml_path=DEFAULT_XML):
        import mujoco as mj
        self.mj = mj
        self.m = mj.MjModel.from_xml_path(str(xml_path))
        m = self.m
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS]
        self.qadr = np.array([m.jnt_qposadr[i] for i in jid])
        self.vadr = np.array([m.jnt_dofadr[i] for i in jid])
        self.site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center")
        self.pbody = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, "paddle")
        self.d = mj.MjData(m)
        self.M = np.zeros((m.nv, m.nv))
        self.ctl = ServoModel()
        self.target = None
        self._jp, self._jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))

    def reset(self, q, qd=None, q_target=None, servo=None):
        """The robot at joints q moving at qd (9 each), the target in force q_target (default q). servo: the servo's
        own state as the low level's observation reports it ({q, qd, qdd}: the setpoint generator's, 9 each, base
        first; tau: the arm's last commanded torque) - then the rollout continues exactly where the robot's servo is;
        without it the setpoints start from the actual joints and the torque from gravity compensation (a
        teleported robot)."""
        mj, m, d = self.mj, self.m, self.d
        mj.mj_resetData(m, d)
        d.qpos[self.qadr] = np.asarray(q, float)
        d.qvel[self.vadr] = 0.0 if qd is None else np.asarray(qd, float)
        mj.mj_forward(m, d)
        self.ctl.sync(d.qpos[self.qadr], d.qvel[self.vadr], d.qfrc_bias[self.vadr[2:]])
        if servo:
            sq, sqd, sqdd = (np.asarray(servo[k], float) for k in ("q", "qd", "qdd"))
            self.ctl.jb.reset(sq[:2], sqd[:2], sqdd[:2])
            self.ctl.jl.reset(sq[2:], sqd[2:], sqdd[2:])
            self.ctl.tau = np.asarray(servo["tau"], float).copy()
            rf = servo.get("reflex")
            if rf:                                       # a reflex in progress: s_left of its hold remain
                self.ctl.reflex_at = (float(d.time) - (REFLEX_RECOVER_S - float(rf["s_left"])), np.asarray(rf["q"], float))
        self.target = np.asarray(q if q_target is None else q_target, float).copy()

    def paddle(self):
        d = self.d
        R = d.site_xmat[self.site].reshape(3, 3)
        self.mj.mj_jacSite(self.m, d, self._jp, self._jr, self.site)
        qd = d.qvel[self.vadr]
        return d.site_xpos[self.site].copy(), R[:, 0].copy(), self._jp[:, self.vadr] @ qd

    def step(self, q_new):
        """One 10 ms control step towards the target q_new (9)."""
        mj, m, d = self.mj, self.m, self.d
        lo, hi = m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1]
        q_new = np.asarray(q_new, float)
        va = self.vadr
        for j in range(1, SUBSTEPS + 1):
            mj.mj_fullM(m, self.M, d.qM)
            Ma = self.M[np.ix_(va[2:], va[2:])]
            d.ctrl[:] = self.ctl.ctrl(d.qpos[self.qadr], d.qvel[va], Ma, d.qfrc_bias[va], j, self.target, q_new,
                                        lo, hi, t=float(d.time))
            mj.mj_step(m, d)
        self.target = q_new.copy()

    def rollout(self, rows):
        """Follow the rows (one per 10 ms); per row (pos, normal, vel of the blade, q, qd) after it."""
        out = []
        for r in rows:
            self.step(r)
            p, n, v = self.paddle()
            out.append((p, n, v, self.d.qpos[self.qadr].copy(), self.d.qvel[self.vadr].copy()))
        return out
