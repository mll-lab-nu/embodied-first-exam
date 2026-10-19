"""The badminton robot's servo model: the low-level toolkit's servo library (agent side, seat/toolkit.toml).

The robot's own 1 kHz servo law exactly as `game spec` limits.controller documents it (the simulator's bm.Phys.servo),
on the robot-only model (/opt/robot/robot_only.xml):
  * the 10 ms joint targets are interpolated linearly over the 10 physics steps of a control step, with the step's
    velocity (target - previous target) / 10 ms as the reference velocity;
  * the arm: a jerk-limited setpoint generator (0.9 of the Franka Panda's velocity limits: VMARGIN; its
    acceleration and jerk limits, the jerk also capped at 0.7 x the torque-rate limit over the row sums of the arm's
    inertia), torque = M_arm qdd_sp + kp e + kd de + gravity/Coriolis + the base's commanded acceleration fed forward
    through the arm-base inertia, limited to 87 / 12 N m and changing by at most 1000 N m/s; a joint more than
    0.02 rad from its setpoint pulls the setpoint along (no wind-up);
  * the base: PD to the interpolated target + bias compensation within the drive force (the model's ctrlrange);
  * the joint-velocity reflex (game spec velocity_rule): a physical arm joint faster than REFLEX = 1.05 x its
    velocity limit stops the robot for REFLEX_RECOVER_S = 1 s: the targets are ignored, the arm's setpoints brake to
    rest at the pose of the trigger, and the gantry's targets pass from then on through a setpoint generator at the
    gantry's limits (BaseLimits: speed, per-axis acceleration, jerk 25 x the acceleration; started from the targets'
    state) whose reference is its stop point during the reflex and the targets after it, until the referee next
    puts the robot at its spot (a new point: the observed servo state then has no base_sp). After the second the robot
    follows its targets again from rest (the arm through its setpoint generator). `reflexes` counts them in a
    rollout; reset(..., servo) continues a reflex in progress from the observed state (servo.reflex, servo.base_sp).
It lets a player roll its own joint-target rows out on its own robot, as a robotics engineer does with a robot's
model and controller before running a motion on the real machine. It reads nothing of the world: no shuttle, no
court, no opponent (the robot-only model holds none of them; the robot's self-collision pairs are in it, so a rollout
shows the arm stopped by its own pedestal or links: `contact_steps`).

    import sys; sys.path.insert(0, "/opt/robot/lib")
    from bm_servo import RobotSim
    S = RobotSim()                                   # /opt/robot/robot_only.xml
    S.reset(state["q"], state["qd"], state["q_target"], state["servo"])   # the low level's observed state: the
                                                     # rollout continues where the robot's servo is
    out = S.rollout(rows)                            # one 9-joint target per 10 ms row: per row the racket's
                                                     # (pos, normal, vel) and the joints (q, qd) after it

Deterministic (float64 numpy, MuJoCo's own integrator). Version 1.2.0 (1.2.0, sport revision wallclock-12 /
duel-14: the joint-velocity rule, the arm's setpoints at 0.9 of the velocity limits and the velocity reflex with the
gantry braking; 1.1.0: the setpoint generator as bodies/limits.py since #94: braking within the jerk in force,
relative to the reference's velocity). The base's constants (BASE_KP, BASE_KD, BASE_V, BASE_A, BASE_RANGE; the drive
force: base_force=spec['limits']['base']['max_force_n'], else the model's ctrlrange) are the gantry's defaults;
RobotSim(gains=spec['limits']['gains'], base_limits=spec['limits']['base']) takes the match's own (a sport revision
that changes the base changes game spec, not this file).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

VERSION = "1.2.0"
DEFAULT_XML = os.environ.get("RO_ROBOT_XML", "/opt/robot/robot_only.xml")
JOINTS = ["base_x", "base_y"] + [f"joint{i}" for i in range(1, 8)]
SITE = "racket_center"
CONTROL_DT, SUBSTEPS = 0.01, 10
PHYS_DT = CONTROL_DT / SUBSTEPS
# /spec limits.controller (the Franka Panda's limits: bodies/franka_panda/body.toml)
ARM_VEL = np.array([2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61])
ARM_ACC = np.array([15.0, 7.5, 10.0, 12.5, 15.0, 20.0, 20.0])
ARM_JERK = np.array([7500.0, 3750.0, 5000.0, 6250.0, 7500.0, 10000.0, 10000.0])
ARM_TAU = np.array([87.0, 87.0, 87.0, 87.0, 12.0, 12.0, 12.0])
ARM_DTAU = np.full(7, 1000.0)
ARM_KP = np.array([2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
ARM_KD = np.array([100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
JERK_SHARE = 0.7
RESYNC = 0.02
# the base (the gantry): PD gains; its drive force = the model's ctrlrange of motor_bx / motor_by; its limits (game
# spec limits.base: speed, per-axis acceleration; jerk 25 x the acceleration) and travel, for the reflex's braking
BASE_KP, BASE_KD = 4e4, 3e3
BASE_V, BASE_A = 2.0, np.array([15.0, 15.0])
BASE_JERK_PER_ACC = 25.0
BASE_RANGE = (np.array([-1.5, -(2.68 + 0.85)]), np.array([1.5, -0.5]))   # x: the stroke; y: the court's back + 0.85 m to -0.5 m
# the joint-velocity rule (game spec velocity_rule, sport revision wallclock-12 / duel-14): the arm's setpoint generator
# runs at VMARGIN of the velocity limits; a physical arm joint faster than REFLEX x its limit stops the robot for
# REFLEX_RECOVER_S
VMARGIN, REFLEX, REFLEX_RECOVER_S = 0.9, 1.05, 1.0


def _sqrt_ctrl(err, k, d):
    lin = d / (k * k)
    a = np.abs(err)
    return np.where(a <= lin, k * err, np.sign(err) * np.sqrt(np.maximum(0.0, 2.0 * d * (a - 0.5 * lin))))


def brake_speed(dist, A, J):
    """The largest speed from which a jerk-limited stop (acceleration from 0, at most A, jerk J) ends within dist."""
    dist = np.maximum(np.asarray(dist, float), 0.0)
    A, J = np.asarray(A, float), np.asarray(J, float)
    small = dist <= A ** 3 / J ** 2
    v_small = np.cbrt(dist * dist * J)
    v_big = 0.5 * (-A * A / J + np.sqrt(A ** 4 / J ** 2 + 8.0 * A * dist))
    return np.where(small, v_small, v_big)


def jerk_caps(M):
    """The arm joints' jerk the torque-rate limit allows at the inertia M: JERK_SHARE x dtau / row sums of |M|."""
    cap = JERK_SHARE * ARM_DTAU / np.maximum(np.sum(np.abs(np.asarray(M, float)), axis=1), 1e-9)
    return np.minimum(ARM_JERK, cap)


class SetpointModel:
    """Setpoint generator (q, qd, qdd) within |qd| <= vel, |qdd| <= acc, |jerk| <= jerk (the documented law; a copy of
    the robot's own generator, bodies/limits.py JerkLimiter, which the seat does not have). Default: the arm's, at
    VMARGIN of the velocity limits (what the robot's servo runs); vel, acc, jerk: another axis set (the gantry's in a
    reflex: base_setpoints())."""

    KP, KV, BRAKE = 60.0, 300.0, 0.6

    def __init__(self, dt=PHYS_DT, vel=None, acc=None, jerk=None):
        self.dt = float(dt)
        vel = ARM_VEL * VMARGIN if vel is None else np.asarray(vel, float)
        acc = ARM_ACC if acc is None else np.asarray(acc, float)
        jerk = ARM_JERK if jerk is None else np.asarray(jerk, float)
        # the velocity bound one step of jerk and one of acceleration below the limit (the discrete steps' overshoot)
        self.V = np.maximum(vel - (jerk * self.dt ** 2 + acc * self.dt), 0.5 * vel)
        self.A, self.J = acc.copy(), jerk.copy()
        self.n = len(vel)
        self.reset(np.zeros(self.n))

    def reset(self, q, qd=None, qdd=None):
        self.q = np.asarray(q, float).copy()
        self.qd = np.zeros(self.n) if qd is None else np.asarray(qd, float).copy()
        self.qdd = np.zeros(self.n) if qdd is None else np.asarray(qdd, float).copy()

    def step(self, r, rd=None, jerk_cap=None):
        dt, V, A, Jh = self.dt, self.V, self.A, self.J
        J = Jh if jerk_cap is None else np.minimum(Jh, jerk_cap)
        r = np.asarray(r, float)
        rd = np.zeros_like(r) if rd is None else np.asarray(rd, float)
        # the position loop sees the error left once the present acceleration has ramped to zero at this step's jerk
        # (relative to the reference moving at rd) and brakes within the acceleration and that jerk (brake_speed)
        e = r - self.q
        t = np.abs(self.qdd) / J
        e = e - ((self.qd - rd) * t + 0.5 * self.qdd * t * t - np.sign(self.qdd) * J * t ** 3 / 6.0)
        v_pos = np.sign(e) * np.minimum(self.KP * np.abs(e), brake_speed(np.abs(e), self.BRAKE * A, J))
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


JerkLimiter = SetpointModel   # the name under which the seat's first copy published it (players' code imports it)


def base_setpoints(vmax=BASE_V, amax=BASE_A, dt=PHYS_DT):
    """The gantry's setpoint generator that the velocity reflex engages (speed vmax per axis, per-axis acceleration
    amax, jerk BASE_JERK_PER_ACC x amax): sim/bm.py base_limits()."""
    a = np.broadcast_to(np.asarray(amax, float), (2,)).copy()
    return SetpointModel(dt, np.full(2, float(vmax)), a, BASE_JERK_PER_ACC * a)


class RobotSim:
    """The robot-only model under its servo: roll joint-target rows out from an observed state."""

    def __init__(self, xml_path=DEFAULT_XML, meshdir=None, gains=None, base_force=None, base_limits=None):
        """gains: game spec limits.gains ({kp, kd}: 9 each, base first); default the constants above. base_force: the
        base drives' force limit (N; game spec limits.base.max_force_n), which the match sets on its model; default the
        robot-only model's own ctrlrange. base_limits: game spec limits.base (max_speed_mps, max_accel_per_axis_mps2,
        range): the gantry's limits the velocity reflex brakes within; default BASE_V, BASE_A, BASE_RANGE."""
        import mujoco as mj
        self.mj = mj
        if meshdir is None:
            self.m = mj.MjModel.from_xml_path(str(xml_path))
        else:
            xml = Path(xml_path).read_text()
            xml = re.sub(r'meshdir="[^"]*"', f'meshdir="{Path(meshdir).resolve()}"', xml, count=1)
            self.m = mj.MjModel.from_xml_string(xml)
        m = self.m
        jid = [mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS]
        if min(jid) < 0:
            raise ValueError("not the 9-joint badminton robot (base_x, base_y, joint1..joint7)")
        self.qadr = np.array([m.jnt_qposadr[i] for i in jid])
        self.vadr = np.array([m.jnt_dofadr[i] for i in jid])
        self.site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, SITE)
        if base_force is None and base_limits and base_limits.get("max_force_n"):
            base_force = base_limits["max_force_n"]
        if base_force is not None:
            m.actuator_ctrlrange[:2] = [[-float(base_force), float(base_force)]] * 2
        bl = base_limits or {}
        self.base_v = float(bl.get("max_speed_mps", BASE_V))
        self.base_a = np.asarray(bl.get("max_accel_per_axis_mps2", BASE_A), float)
        rg = bl.get("range")
        self.base_lo, self.base_hi = ((BASE_RANGE[0].copy(), BASE_RANGE[1].copy()) if not rg else
                                      (np.array([rg["x"][0], rg["y"][0]], float), np.array([rg["x"][1], rg["y"][1]], float)))
        self.d = mj.MjData(m)
        self.M = np.zeros((m.nv, m.nv))
        self.jl = SetpointModel()
        self.bl = None                 # the gantry's setpoint generator, engaged by a reflex (until the next point)
        self.reflex_at = None          # (time s, q 9 at the trigger, the gantry's stop point) of a reflex in force
        self.tau = np.zeros(7)
        self.target = np.zeros(9)
        self.target_prev = np.zeros(9)
        self.steady = 0
        self.contact_steps = 0
        self.reflexes = 0
        kp = np.r_[BASE_KP, BASE_KP, ARM_KP] if not gains else np.asarray(gains["kp"], float)
        kd = np.r_[BASE_KD, BASE_KD, ARM_KD] if not gains else np.asarray(gains["kd"], float)
        self.kp, self.kd = kp, kd
        self._jp, self._jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))

    def reset(self, q, qd=None, q_target=None, servo=None):
        """The robot at joints q moving at qd (9 each, base first), the target in force q_target (default q).
        servo: the servo's own state as the low level's observation reports it (state['servo']: the arm setpoint
        generator's q, qd, qdd (7 each), the arm's last torque tau (7), the target before q_target (q_target_prev, 9),
        steady (control steps since the robot was last put at rest, capped at 2: below 2 the base's acceleration
        is not fed forward), and the velocity reflex: reflex (None, or {s_left: seconds of the stop left, q: the 9
        joints at the trigger, stop: the gantry's stop point}) and base_sp (None, or the gantry's setpoint generator
        {q, qd, qdd} (2 each), engaged since a reflex of this point)); then the rollout continues exactly where the
        robot's servo is. Without it the setpoint starts at the actual joints at rest and the torque at gravity
        compensation (a teleported robot)."""
        mj, m, d = self.mj, self.m, self.d
        mj.mj_resetData(m, d)
        d.qpos[self.qadr] = np.asarray(q, float)
        d.qvel[self.vadr] = 0.0 if qd is None else np.asarray(qd, float)
        mj.mj_forward(m, d)
        self.target = np.asarray(q if q_target is None else q_target, float).copy()
        self.bl, self.reflex_at = None, None
        if servo:
            self.jl.reset(servo["q"], servo["qd"], servo["qdd"])
            self.tau = np.asarray(servo["tau"], float).copy()
            self.target_prev = np.asarray(servo.get("q_target_prev", self.target), float).copy()
            self.steady = int(servo.get("steady", 2))
            bs = servo.get("base_sp")
            if bs:
                self.bl = base_setpoints(self.base_v, self.base_a)
                self.bl.reset(bs["q"], bs["qd"], bs["qdd"])
            rf = servo.get("reflex")
            if rf:                       # a reflex in progress: s_left of its stop remain
                self.reflex_at = (float(d.time) - (REFLEX_RECOVER_S - float(rf["s_left"])),
                                  np.asarray(rf["q"], float).copy(), np.asarray(rf["stop"], float).copy())
        else:
            self.jl.reset(d.qpos[self.qadr[2:]])
            self.tau = np.clip(d.qfrc_bias[self.vadr[2:]], -ARM_TAU, ARM_TAU)
            self.target_prev = self.target.copy()
            self.steady = 0
        self.contact_steps = 0
        self.reflexes = 0

    def racket(self):
        """The racket head centre, its string-face normal (the racket body's +x) and its linear velocity now."""
        d = self.d
        R = d.site_xmat[self.site].reshape(3, 3)
        self.mj.mj_jacSite(self.m, d, self._jp, self._jr, self.site)
        return d.site_xpos[self.site].copy(), R[:, 0].copy(), self._jp[:, self.vadr] @ d.qvel[self.vadr]

    def step(self, q_new):
        """One 10 ms control step towards the target q_new (9)."""
        mj, m, d = self.mj, self.m, self.d
        qa, va = self.qadr, self.vadr
        q_new = np.asarray(q_new, float)
        prev = self.target
        rd0 = (q_new - prev) / CONTROL_DT
        b_acc0 = (np.zeros(2) if self.steady < 2 else
                  (q_new[:2] - 2.0 * prev[:2] + self.target_prev[:2]) / CONTROL_DT ** 2)
        lo, hi = m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1]
        for j in range(1, SUBSTEPS + 1):
            r = prev + (q_new - prev) * (j / SUBSTEPS)
            rd, b_acc = rd0, b_acc0
            mj.mj_fullM(m, self.M, d.qM)
            M = self.M
            if self.reflex_at is None and np.any(np.abs(d.qvel[va[2:]]) > REFLEX * ARM_VEL):
                # the velocity reflex: the gantry's setpoints from its targets' state, braking to its stop point
                if self.bl is None:
                    bl = self.bl = base_setpoints(self.base_v, self.base_a)
                    bl.reset(r[:2], np.clip(rd[:2], -bl.V, bl.V), np.clip(b_acc, -bl.A, bl.A))
                bl = self.bl
                stop = bl.q + bl.qd * np.abs(bl.qd) / (2.0 * bl.A) + bl.qd * (bl.A / bl.J)
                self.reflex_at = (float(d.time), d.qpos[qa].copy(), np.clip(stop, self.base_lo, self.base_hi))
                self.reflexes += 1
            if self.reflex_at is not None and d.time - self.reflex_at[0] >= REFLEX_RECOVER_S - 1e-9:
                self.reflex_at = None    # recovered: the targets again, through the setpoint generators
            if self.reflex_at is not None:
                r = np.r_[self.reflex_at[2], self.reflex_at[1][2:]]
                rd = np.zeros(9)
            if self.bl is not None:
                b_sp, bd_sp, b_acc = self.bl.step(r[:2], rd[:2])
            else:
                b_sp, bd_sp = r[:2], rd[:2]
            fb = (self.kp[:2] * (b_sp - d.qpos[qa[:2]]) + self.kd[:2] * (bd_sp - d.qvel[va[:2]])
                  + d.qfrc_bias[va[:2]])
            d.ctrl[:2] = np.clip(fb, lo[:2], hi[:2])
            Ma = M[np.ix_(va[2:], va[2:])]
            q_sp, qd_sp, qdd_sp = self.jl.step(r[2:], rd[2:], jerk_caps(Ma))
            e = q_sp - d.qpos[qa[2:]]
            tau = Ma @ qdd_sp + self.kp[2:] * e + self.kd[2:] * (qd_sp - d.qvel[va[2:]]) + d.qfrc_bias[va[2:]]
            tau = tau + M[np.ix_(va[2:], va[:2])] @ b_acc
            t = np.clip(tau, self.tau - ARM_DTAU * PHYS_DT, self.tau + ARM_DTAU * PHYS_DT)
            self.tau = np.clip(t, -ARM_TAU, ARM_TAU)
            d.ctrl[2:] = self.tau
            if np.max(np.abs(e)) > RESYNC:
                big = np.abs(e) > RESYNC
                jl = self.jl
                jl.q[big] = d.qpos[qa[2:]][big] + np.sign(e[big]) * RESYNC
                jl.qd[big] = np.clip(d.qvel[va[2:]], -jl.V, jl.V)[big]
                jl.qdd[big] = 0.0
            mj.mj_step(m, d)
            if d.ncon:
                self.contact_steps += 1
        self.target_prev, self.target = prev.copy(), q_new.copy()
        self.steady += 1

    def rollout(self, rows):
        """Follow the rows (one per 10 ms); per row (pos, normal, vel of the racket head, q, qd) after it."""
        out = []
        for r in rows:
            self.step(r)
            p, n, v = self.racket()
            out.append((p, n, v, self.d.qpos[self.qadr].copy(), self.d.qvel[self.vadr].copy()))
        return out
