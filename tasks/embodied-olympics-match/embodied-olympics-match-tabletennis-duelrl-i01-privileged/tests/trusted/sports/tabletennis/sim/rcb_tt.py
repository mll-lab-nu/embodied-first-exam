"""
rcb_tt.py — task-local tooling for the robot table tennis tasks (MuJoCo, Franka Panda with a paddle).

World frame (metres): table top is z = 0, the table's long axis is y, the net is the plane y = 0.
The robot stands behind the y < 0 end (base at home (0, -1.75, 0), facing +y); the opponent half is y > 0.

Robot (revision wallclock-7): the Franka arm on a pedestal carried by an x-y rail base behind the end line. Its
joint vector has NQ = 9 entries [base_x, base_y, q1..q7]: base_x / base_y are prismatic joints whose values are the
base's position (metres, |x| <= 1.0, -2.40 <= y <= -1.50, home (0, -1.75)), q1..q7 the arm's joints (rad).

Control: one action = 9 absolute joint-position targets, held for CONTROL_DT = 10 ms (100 Hz). Inside a control step
the target is interpolated linearly over the 10 physics steps (1 ms each), its velocity = the step's difference. The
robot's servo (TTServo, revision wallclock-10: the real robot's limits, fencing-3's servo) follows that reference with a
jerk-limited setpoint (arm: the Franka Panda's velocity, acceleration and jerk limits, the jerk also capped by the
torque rate; base: 2 m/s, 8 m/s^2, 200 m/s^3 per axis) and turns it into joint torques (inertia feed-forward + PD +
gravity/Coriolis, limited to 87 / 12 Nm and 1000 Nm/s) and base forces (PD + bias, clipped at BASE_FORCE). Target
limits (checked, a violation raises ValueError / fails the verifier):
  * every target inside the joint range (JOINT_LOW..JOINT_HIGH; the base's travel for base_x / base_y),
  * |target_k - target_{k-1}| <= VEL_LIMIT * CONTROL_DT per joint (Franka joint speed limits; BASE_VMAX per base
    axis); target_{-1} is the ready configuration Q0 = [home, q0].
The acceleration limits of a player's rows are checked where the rows come in (action_low, rows_problem); whatever the
targets, the servo's setpoints stay within the velocity, acceleration and jerk limits.
An episode lasts HORIZON_S = 2.5 s (250 control steps). A trajectory with fewer than 250 rows holds its last
target for the rest of the episode.

Python
------
  from rcb_tt import Session
  s = Session()                        # loads /app/instance.npz (or Session(instance=...))
  s.reset(); s.step(q_target); s.state(); s.status(); s.actions()
  s.predict_ball(duration=1.5)         # ball-only rollout (no robot) from the current (or a given) ball state
  s.fk(q9) / s.jacobian(q9) / s.ik(pos, normal, q_init, base)   # paddle kinematics helpers
  s.replay(actions) -> status; s.save_trajectory(actions, path)

CLI
---
  python rcb_tt.py info
  python rcb_tt.py replay --traj /app/output/trajectory.npz [--repeat 2]
  python rcb_tt.py render --traj /app/output/trajectory.npz --out replay.mp4
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import mujoco as mj  # rendering backend: MUJOCO_GL (the image sets osmesa = CPU offscreen)

HERE = Path(__file__).resolve().parent
for _root in (HERE.parent.parent, HERE.parent.parent.parent):   # sim/ in a task (bodies/ next to sport/); the repo
    if (_root / "bodies" / "limits.py").is_file():
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        break
from bodies import limits as AL  # noqa: E402
from bodies import selfcollision as SC  # noqa: E402  (the arm's self-collision record, bodies/README.md; recorded only)

SCENE_XML = Path(os.environ.get("RCB_TT_SCENE", HERE / "scene" / "tt_scene.xml"))
DEFAULT_INSTANCE = os.environ.get("RCB_TT_INSTANCE", "/app/instance.npz")

CONTROL_DT = 0.01
SUBSTEPS = 10                      # physics steps per control step (timestep 1 ms)
PHYS_DT = CONTROL_DT / SUBSTEPS
HORIZON_S = 2.5
HORIZON = int(round(HORIZON_S / CONTROL_DT))   # 250 control steps
# The arm is held to the real Franka Panda's limits (revision wallclock-10; bodies/franka_panda/body.toml, enforced by
# bodies/limits.py as in fencing-3): joint velocity, acceleration, jerk, torque and torque rate.
ARM_LIM = AL.load("franka_panda")
ARM_VEL = ARM_LIM.vel.copy()       # rad/s: 2.175 x4, 2.61 x3
# The joint-velocity rule (revision wallclock-15 / duel-wallclock-12, the user's decision of 2026-10-12, option A;
# the Embodied Olympics screening notes): the physical joints of a real Franka overshoot a setpoint that runs at the
# velocity limit (the tracking error and the blade hitting the table: 37 % of B9 strokes up to 2.2 x for ~60 ms), and the
# real robot answers with its velocity reflex. So (1) the setpoint generator and the stroke planner (rally.ARM_LIM) run
# at VMARGIN of the velocity limits, and (2) a physical arm joint faster than REFLEX x its limit triggers the reflex:
# the robot stops (the targets are ignored, the setpoints brake to rest at the pose of the trigger) for REFLEX_RECOVER_S,
# then resumes from rest (the controller's error recovery and restart).
VMARGIN = 0.9
REFLEX = 1.05
REFLEX_RECOVER_S = 1.0
ARM_LIM_OP = __import__("dataclasses").replace(ARM_LIM, vel=ARM_LIM.vel * VMARGIN)   # what the setpoint generator runs at
# The collision reflex (revision 15/12, the re-screen's choice for paddle-table contact): the robot's links or paddle
# pressing on the table with more than COLLISION_REFLEX_N (the Franka's default collision threshold, 20 N) stops the
# robot exactly as the velocity reflex does (hold the pose for REFLEX_RECOVER_S, then resume from rest). Touching the
# table stays legal by the rules (D4); this is the robot's own protection. A planning clearance was measured and did
# not help (the contacts come from the swing's real path, not its targets): the Embodied Olympics screening notes.
COLLISION_REFLEX_N = 20.0
COLLISION_REARM_STEPS = 100        # physics steps (0.1 s) off the table before the collision reflex re-arms
ARM_ACC = ARM_LIM.acc.copy()       # rad/s^2: 15, 7.5, 10, 12.5, 15, 20, 20
ARM_JERK = ARM_LIM.jerk.copy()     # rad/s^3: 7500, 3750, 5000, 6250, 7500, 10000, 10000
# the rail base (revision wallclock-7; limits revision wallclock-10): speed, acceleration and jerk of the two axes
BASE_VMAX = 2.0                    # m/s per axis (DeepMind's table-tennis robot: a Festo linear gantry at 2 m/s)
BASE_AMAX = 8.0                    # m/s^2: the drives' force limit / the moving mass (base 60 kg + arm and paddle)
BASE_JMAX = 200.0                  # m/s^3: ESTIMATED (no manufacturer value; 25 x the acceleration: 0 to 8 m/s^2 in
                                   # 40 ms, a belt-driven gantry's usual setting; the receive study used the same)
BASE_FORCE = 620.0                 # N per axis (= 8.07 m/s^2 for the 76.8 kg the base axes move)
BASE_LO = np.array([-1.0, -2.40])  # travel: |x| <= 1.0 (the table is 1.525 m wide), the column's front stays 1 cm
BASE_HI = np.array([1.0, -1.50])   # behind the end line (y = -1.37) at y = -1.50; 0.9 m of depth back to y = -2.40
HOME = np.array([0.0, -1.75])      # the base's home (the fixed robot's position until revision wallclock-6)
BASE_LIM = AL.ArmLimits(body="tt_rail", model="x-y rail base (belt-driven linear gantry; jerk estimated)",
                        range_lo=BASE_LO.copy(), range_hi=BASE_HI.copy(), vel=np.full(2, BASE_VMAX),
                        acc=np.full(2, BASE_AMAX), jerk=np.full(2, BASE_JMAX), tau=np.full(2, BASE_FORCE), dtau=None,
                        sources={"vel": "DeepMind table-tennis robot (Festo gantry, 2 m/s)",
                                 "acc": "drive force 620 N / 76.8 kg moving mass", "jerk": "estimate, 25 x acc"})
OPP_LIM = AL.ArmLimits(body="tt_opponent", model="the scripted opponent's paddle along its end line (our rail's limits)",
                       range_lo=np.array([-1.0]), range_hi=np.array([1.0]), vel=np.array([BASE_VMAX]),
                       acc=np.array([BASE_AMAX]), jerk=np.array([BASE_JMAX]), tau=np.array([BASE_FORCE]), dtau=None)
NQ = 9
VEL_LIMIT = np.r_[BASE_VMAX, BASE_VMAX, ARM_VEL]                                   # per joint (m/s, rad/s)
ACC_LIMIT = np.r_[BASE_AMAX, BASE_AMAX, ARM_ACC]                                   # per joint (m/s^2, rad/s^2)
JERK_LIMIT = np.r_[BASE_JMAX, BASE_JMAX, ARM_JERK]                                 # per joint (m/s^3, rad/s^3)
TORQUE_LIMIT = np.r_[BASE_FORCE, BASE_FORCE, ARM_LIM.tau]                          # N (base), Nm (arm)
TORQUE_RATE = ARM_LIM.dtau.copy()  # N m/s (arm; 1000)
KP = np.array([6e4, 6e4, 2400.0, 2400.0, 2400.0, 2400.0, 1000.0, 600.0, 200.0])
KD = np.array([4e3, 4e3, 100.0, 100.0, 100.0, 100.0, 30.0, 20.0, 6.0])
RESYNC = 0.02                      # rad: an arm joint pushed farther than this from its setpoint (a ball, the table)
                                   # makes the setpoint follow it (fencing-3): the torque-rate-limited servo does not
                                   # wind up


class RailLimiter(AL.JerkLimiter):
    """The rail base's jerk-limited setpoint generator (per axis: velocity, acceleration, jerk). The arm's cascade
    (bodies/limits.JerkLimiter) assumed until 2026-10-11 that the acceleration follows its command at once (the Panda
    reaches its acceleration limit in 2 ms; since then it brakes within the jerk in force too, revision 12/10); a gantry
    at 200 m/s^3 needs 40 ms, so here the position loop brakes on the jerk-limited stopping distance
    (d = v^2 / (2 a_b) + v a_b / (2 J), a_b = BRAKE x the acceleration limit) with slower loops; the velocity bound V is
    JerkLimiter's (one step of jerk and one of acceleration below the limit). Stable at
    1 ms (the servo) and at 10 ms (the go-to generator, base_goto): a rest-to-rest move of 0.1 / 0.3 / 0.5 / 1.0 m
    settles within 1 mm in 0.36 / 0.44 / 0.57 / 0.83 s with < 3 mm overshoot."""

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
        a_cmd = np.clip(AL._sqrt_ctrl(v_cmd - self.qd, self.KV, J), -A, A)
        room_up, room_dn = np.maximum(0.0, V - self.qd), np.maximum(0.0, V + self.qd)
        a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * room_dn), np.sqrt(2.0 * J * room_up))
        j = np.clip((a_cmd - self.qdd) / dt, -J, J)
        self.q = self.q + self.qd * dt + 0.5 * self.qdd * dt * dt + j * dt ** 3 / 6.0
        self.qd = self.qd + self.qdd * dt + 0.5 * j * dt * dt
        self.qdd = self.qdd + j * dt
        return self.q, self.qd, self.qdd


class TTServo:
    """One robot's 1 kHz servo under the real limits (fencing-3's, bodies/limits.py), from the control step's target
    (interpolated linearly over the 10 physics steps, its velocity = the step's difference / 10 ms):

      arm   a JerkLimiter setpoint (velocity, acceleration, jerk at 100 % of the Panda's; the jerk also capped by the
            torque-rate share at the current pose, limits.jerk_caps), torque = M_arm qdd_setpoint + KP e + KD de +
            gravity/Coriolis, then the TorqueRateLimiter (87 / 12 N m, 1000 N m/s); a joint pushed more than RESYNC
            from its setpoint makes the setpoint follow it;
      base  a JerkLimiter setpoint per axis (2 m/s, 8 m/s^2, 200 m/s^3), force = KP e + KD de + bias, clipped at the
            drives' 620 N.

    The setpoints never exceed the limits whatever the targets (a reference beyond them is followed late). A
    teleported robot (reset, the duel's ready pose, a planner's rehearsal start) re-syncs: the setpoint starts from
    the actual state, the torque from gravity compensation. Deterministic (float64 numpy)."""

    def __init__(self, qadr, vadr, aadr):
        self.qadr, self.vadr, self.aadr = np.asarray(qadr), np.asarray(vadr), np.asarray(aadr)
        self.jl = AL.JerkLimiter(ARM_LIM_OP, PHYS_DT)
        self.trl = AL.TorqueRateLimiter(ARM_LIM, PHYS_DT)
        self.reflex_at = None          # (time, q) of a reflex (velocity or collision), until the recovery
        self.n_reflex = 0              # reflexes of either kind
        self.n_collision_reflex = 0    # of which collision reflexes (the robot pressing on the table)
        self._tbl = None               # (table geom, this robot's link and paddle geoms), resolved on first use
        self._coll_armed = True        # False after a collision reflex until the robot has left the table
        self._clear_steps = 0          # physics steps without table contact since the last collision reflex
        self.reflex_coll = False       # the reflex in progress is a collision reflex
        self.jb = RailLimiter(BASE_LIM, PHYS_DT)
        self.q_end = None              # the robot's joints after the last physics step it drove (teleport detection)
        self.n_resync = 0

    def sync(self, d):
        """Start from the robot's actual state (at rest unless it moves): setpoints = joints, torque = gravity."""
        q, qd = d.qpos[self.qadr], d.qvel[self.vadr]
        self.jl.reset(q[2:], np.clip(qd[2:], -ARM_LIM.vel, ARM_LIM.vel))
        self.jb.reset(q[:2], np.clip(qd[:2], -BASE_VMAX, BASE_VMAX))
        self.trl.reset(d.qfrc_bias[self.vadr[2:]])
        self.q_end = q.copy()
        self.reflex_at = None
        self.reflex_coll = False
        self._coll_armed = True

    def copy_from(self, o: "TTServo"):
        """The same servo state as `o` (a robot-only rehearsal of the live robot)."""
        for a, b in ((self.jl, o.jl), (self.jb, o.jb)):
            a.reset(b.q, b.qd, b.qdd)
        self.trl.reset(o.trl.tau)
        self.q_end = None if o.q_end is None else o.q_end.copy()
        self.reflex_at = None if o.reflex_at is None else (o.reflex_at[0], o.reflex_at[1].copy())
        self.reflex_coll, self._coll_armed, self._clear_steps = o.reflex_coll, o._coll_armed, o._clear_steps

    def _table_force(self, m, d) -> float:
        """The normal force (N) of this robot's links and paddle on the table at this physics step."""
        if self._tbl is None:
            own = set(int(x) for x in self.qadr)

            def moves(b):
                while b > 0:
                    j = m.body_jntadr[b]
                    if j >= 0 and int(m.jnt_qposadr[j]) in own:
                        return True
                    b = m.body_parentid[b]
                return False
            names = [mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, g) or "" for g in range(m.ngeom)]
            self._tbl = (mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_table"),
                         {g for g in range(m.ngeom) if (names[g].startswith("link") or names[g].startswith("paddle"))
                          and moves(int(m.geom_bodyid[g]))}, np.zeros(6))
        table, geoms, f6 = self._tbl
        if table < 0:
            return 0.0
        tot = 0.0
        for i in range(d.ncon):
            g1, g2 = int(d.contact.geom1[i]), int(d.contact.geom2[i])
            if (g1 == table and g2 in geoms) or (g2 == table and g1 in geoms):
                mj.mj_contactForce(m, d, i, f6)
                tot += abs(float(f6[0]))
        return tot

    def state(self):
        return np.r_[self.jl.q, self.jl.qd, self.jl.qdd, self.jb.q, self.jb.qd, self.jb.qdd, self.trl.tau]

    def ctrl(self, m, d, M, j, prev, new, lo, hi):
        """Physics step j (1..SUBSTEPS) of the control step from target `prev` to target `new`: the actuator commands
        (9: base forces, arm torques). M: the full joint-space inertia (of the last forward pass)."""
        qa, va = self.qadr, self.vadr
        q, qd = d.qpos[qa], d.qvel[va]
        if j == 1 and (self.q_end is None or np.max(np.abs(q - self.q_end)) > 1e-12):
            self.sync(d)                                               # teleported since the last step
        r = prev + (new - prev) * (j / SUBSTEPS)
        rd = (new - prev) / CONTROL_DT
        if self.reflex_at is None and (d.ncon or not self._coll_armed):
            f_tbl = self._table_force(m, d) if d.ncon else 0.0
            if not self._coll_armed:                                   # after a collision reflex: re-armed once the
                self._clear_steps = self._clear_steps + 1 if f_tbl == 0.0 else 0     # robot has been off the table
                self._coll_armed = self._clear_steps >= COLLISION_REARM_STEPS         # for 0.1 s (contacts flicker)
            elif f_tbl > COLLISION_REFLEX_N:
                self.reflex_at = (float(d.time), q.copy())            # the collision reflex: stop the robot
                self.reflex_coll = True
                self.n_reflex += 1
                self.n_collision_reflex += 1
        if self.reflex_at is None and np.any(np.abs(qd[2:]) > REFLEX * ARM_VEL):
            self.reflex_at = (float(d.time), q.copy())                # the joint-velocity reflex: stop the robot
            self.n_reflex += 1
        if self.reflex_at is not None and d.time - self.reflex_at[0] >= REFLEX_RECOVER_S:
            coll = self.reflex_coll
            self.sync(d)                                               # recovered: restart from the actual state
            self._coll_armed, self._clear_steps = not coll, 0          # a collision reflex re-arms when the contact
                                                                       # is relieved, not while the arm still rests on
                                                                       # the table (else it would stop again at once)
        if self.reflex_at is not None:                                 # stopped: hold the pose of the trigger
            r, rd = self.reflex_at[1].copy(), np.zeros_like(rd)
        Ma = M[np.ix_(va[2:], va[2:])]
        q_sp, qd_sp, qdd_sp = self.jl.step(r[2:], rd[2:], AL.jerk_caps(Ma, ARM_LIM))
        b_sp, bd_sp, _ = self.jb.step(r[:2], rd[:2])
        e = q_sp - q[2:]
        tau = Ma @ qdd_sp + KP[2:] * e + KD[2:] * (qd_sp - qd[2:]) + d.qfrc_bias[va[2:]]
        f = KP[:2] * (b_sp - q[:2]) + KD[:2] * (bd_sp - qd[:2]) + d.qfrc_bias[va[:2]]
        out = np.r_[np.clip(f, lo[:2], hi[:2]), self.trl(tau)]
        if np.max(np.abs(e)) > RESYNC:                                 # the arm cannot hold the setpoint: follow it
            big = np.abs(e) > RESYNC
            jl = self.jl
            jl.q[big] = q[2:][big] + np.sign(e[big]) * RESYNC
            jl.qd[big] = np.clip(qd[2:], -jl.V, jl.V)[big]
            jl.qdd[big] = 0.0
            self.n_resync += 1
        return out

    def after_step(self, d):
        self.q_end = d.qpos[self.qadr].copy()
MERGE_GAP_S = 0.005                # contacts with the same object closer than this in time count as one
NET_TOP_Z = 0.1525
TABLE_HALF_X, TABLE_HALF_Y = 0.7625, 1.37

ARM_JOINTS = [f"joint{i}" for i in range(1, 8)]
JOINTS = ["base_x", "base_y"] + ARM_JOINTS
ROBOT_ROOT = "base"


def _brake(d, a):
    """The fastest speed (per joint) from which a target stepped every 10 ms can stop within the distance d >= 0 at the
    deceleration a (the discrete-time braking law)."""
    d = np.maximum(0.0, np.asarray(d, float))
    return np.sqrt(a * a * CONTROL_DT ** 2 / 4.0 + 2.0 * a * d) - a * CONTROL_DT / 2.0


def seek(q, v, goal, vmax, amax, lo=None, hi=None):
    """One control step of a per-joint go-to under velocity and acceleration limits (the slews and the return to the
    ready pose): from the target q moving at v towards goal -> (new target, its velocity). The braking velocity is the
    discrete-time one (exact for 10 ms steps at 90 % of amax), so it stops on the goal without overshoot; with lo / hi
    (the joint ranges) a joint moving towards its range limit brakes as hard as it may and stops at the limit."""
    q = np.asarray(q, float); v = np.asarray(v, float); goal = np.asarray(goal, float)
    vmax = np.broadcast_to(np.asarray(vmax, float), q.shape); amax = np.broadcast_to(np.asarray(amax, float), q.shape)
    a = 0.9 * amax
    e = goal - q
    vb = np.sqrt(a * a * CONTROL_DT ** 2 / 4.0 + 2.0 * a * np.abs(e)) - a * CONTROL_DT / 2.0
    v_des = np.sign(e) * np.minimum(vb, vmax)
    v_new = np.clip(v + np.clip(v_des - v, -amax * CONTROL_DT, amax * CONTROL_DT), -vmax, vmax)
    if lo is not None:                               # brake for the range limit (as hard as the acceleration allows)
        up, dn = _brake(hi - q, a), _brake(q - lo, a)
        v_new = np.clip(v_new, np.maximum(-dn, v - amax * CONTROL_DT), np.minimum(up, v + amax * CONTROL_DT))
    q_new = q + v_new * CONTROL_DT
    done = (np.abs(goal - q_new) < 1e-7) & (np.abs(v_new) <= a * CONTROL_DT)
    q_new = np.where(done, goal, q_new)
    if lo is not None:
        q_new = np.clip(q_new, lo, hi)
    return q_new, (q_new - q) / CONTROL_DT


def limit_rows(rows, q_prev, v_prev, vmax=None, amax=None, lo=None, hi=None):
    """Rows of targets made to respect the per-step velocity and acceleration limits from the target in force q_prev
    moving at v_prev: each row as close to the wanted one as the limits allow (the velocity change per step bounded
    by amax x 10 ms, the velocity by vmax), in order. A row list already within the limits is returned unchanged
    (up to rounding); the high level's planners use it as the last guard of what the low level's validator checks."""
    vmax = VEL_LIMIT if vmax is None else np.asarray(vmax, float)
    amax = ACC_LIMIT if amax is None else np.asarray(amax, float)
    q, v = np.asarray(q_prev, float).copy(), np.asarray(v_prev, float).copy()
    out = []
    for r in rows:
        r = np.asarray(r, float)
        v_new = np.clip(np.clip((r - q) / CONTROL_DT, v - amax * CONTROL_DT * 0.999, v + amax * CONTROL_DT * 0.999),
                        -vmax * 0.999, vmax * 0.999)
        if lo is not None:                       # brake in time for the joint ranges (within the acceleration limit)
            up, dn = _brake(hi - q, 0.9 * amax), _brake(q - lo, 0.9 * amax)
            v_new = np.clip(v_new, np.maximum(-dn, v - amax * CONTROL_DT * 0.999),
                            np.minimum(up, v + amax * CONTROL_DT * 0.999))
        qn = q + v_new * CONTROL_DT
        if lo is not None:
            qn = np.clip(qn, lo, hi)
        v, q = (qn - q) / CONTROL_DT, qn
        out.append(q.copy())
    return out


def rows_problem(Q, prev=None, prev_vel=None, tol=1.001):
    """Rows of 9 targets one control step apart against the per-step speed and acceleration limits (VEL_LIMIT,
    ACC_LIMIT; prev / prev_vel: the target in force and its velocity, joined to the first row if given): None or the
    reason. Jerk is not checked here: the servo smooths it to the jerk limits at 1 kHz."""
    a = np.asarray(Q, float).reshape(-1, NQ)
    if prev is not None:
        a = np.vstack([np.asarray(prev, float)[None], a])
    if len(a) >= 2:
        v = np.diff(a, axis=0) / CONTROL_DT
        bad = np.abs(v) > VEL_LIMIT * tol + 1e-9
        if bad.any():
            i, j = np.argwhere(bad)[0]
            return (f"rows {int(i)}->{int(i) + 1}: joint {JOINTS[j]} at {abs(v[i, j]):.4f} per s exceeds its speed "
                    f"limit {VEL_LIMIT[j]}")
        if prev is not None and prev_vel is not None:
            v = np.vstack([np.asarray(prev_vel, float)[None], v])
        if len(v) >= 2:
            acc = np.diff(v, axis=0) / CONTROL_DT
            bad = np.abs(acc) > ACC_LIMIT * tol + 1e-9
            if bad.any():
                i, j = np.argwhere(bad)[0]
                return (f"joint {JOINTS[j]}: {abs(acc[i, j]):.2f} per s^2 between rows exceeds its acceleration "
                        f"limit {ACC_LIMIT[j]} (second difference of rows / (10 ms)^2)")
    return None


def base_goto(b, v, goal, vmax=BASE_VMAX, amax=BASE_AMAX, a=None):
    """One control step of the base's go-to generator (jerk-limited since revision wallclock-10): per axis the
    RailLimiter law at 98 % of the speed, 85 % of the acceleration and 85 % of the jerk limit (headroom for the servo),
    as a difference equation on the targets (v, a = the targets' first and second differences / 10 ms, so a caller can
    resume it from its rows): from the target b moving at v with acceleration a (default 0) towards goal -> (new target,
    its velocity, its acceleration). Within 0.5 mm of the goal and nearly at rest it snaps onto the goal. A rest-to-
    rest move of 0.1 / 0.23 / 0.5 / 1.0 m arrives in 0.33 / 0.47 / 0.67 / 0.94 s. Deterministic."""
    V, A, J = 0.98 * vmax, 0.85 * amax, 0.85 * BASE_JMAX
    b = np.asarray(b, float); v = np.clip(np.asarray(v, float), -V, V)
    a = np.zeros(2) if a is None else np.clip(np.asarray(a, float), -A, A)
    goal = np.clip(np.asarray(goal, float), BASE_LO, BASE_HI)
    e = goal - b
    ab = RailLimiter.BRAKE * A
    d = np.abs(e)
    v_stop = 0.5 * (-ab * ab / J + np.sqrt((ab * ab / J) ** 2 + 8.0 * ab * d))
    v_cmd = np.clip(np.sign(e) * np.minimum(v_stop, RailLimiter.KP * d), -V, V)
    a_cmd = np.clip(AL._sqrt_ctrl(v_cmd - v, RailLimiter.KV, J), -A, A)
    a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * np.maximum(0.0, V + v)), np.sqrt(2.0 * J * np.maximum(0.0, V - v)))
    an = a + np.clip(a_cmd - a, -J * CONTROL_DT, J * CONTROL_DT)
    vn = np.clip(v + an * CONTROL_DT, -V, V)
    nb = np.clip(b + vn * CONTROL_DT, BASE_LO, BASE_HI)
    if np.max(np.abs(goal - nb)) < 5e-4 and np.max(np.abs(vn)) < 0.02:
        nb = goal.copy()
    vn = (nb - b) / CONTROL_DT
    an = (vn - v) / CONTROL_DT
    if np.array_equal(nb, goal) and np.max(np.abs(vn)) < 0.06:
        return nb, np.zeros(2), np.zeros(2)
    return nb, vn, an


def base_plan(b, v, goal, n, a=None):
    """n targets of the go-to generator from (b, v, a); (rows (n, 2), index of the first row at rest at the goal or
    None)."""
    out, arrived = np.zeros((n, 2)), None
    goal = np.clip(np.asarray(goal, float), BASE_LO, BASE_HI)
    for i in range(n):
        b, v, a = base_goto(b, v, goal, a=a)
        out[i] = b
        if arrived is None and np.array_equal(b, goal) and not v.any():
            arrived = i
    return out, arrived


def base_reach(b, v, goal, n_avail, margin=5, a=None):
    """The goal the base can reach (and stop at) `margin` steps before step n_avail, on the line from b to goal: goal
    itself if it can, else the farthest such point (bisection). (goal used, metres short of the wanted goal)."""
    b = np.asarray(b, float); goal = np.clip(np.asarray(goal, float), BASE_LO, BASE_HI)
    _, arr = base_plan(b, v, goal, max(1, n_avail), a)
    if arr is not None and arr <= n_avail - margin:
        return goal, 0.0
    lo, hi = 0.0, 1.0
    for _ in range(10):
        mid = 0.5 * (lo + hi)
        _, a2 = base_plan(b, v, b + mid * (goal - b), max(1, n_avail), a)
        if a2 is not None and a2 <= n_avail - margin:
            lo = mid
        else:
            hi = mid
    g = b + lo * (goal - b)
    return g, float(np.linalg.norm(goal - g))


STANCE_BOX = np.array([0.25, 0.10])   # the contact may lie this far (x, y) from base + STANCE_PREF without a base move
STANCE_PREF = np.array([0.0, 0.45])   # the arm's comfortable contact: 0.45 m in front of the base (the fixed robot's)


def stance(p_c, b_now):
    """The high level's default base position for a contact (blade centre) at p_c: the base moves only as much as
    needed to bring the contact within STANCE_BOX of base + STANCE_PREF (the prototype's rule), clipped to the travel."""
    b_now = np.asarray(b_now, float)
    rel = np.asarray(p_c[:2], float) - (b_now + STANCE_PREF)
    shift = rel - np.clip(rel, -STANCE_BOX, STANCE_BOX)
    return np.clip(b_now + shift, BASE_LO, BASE_HI)


def _world_spin(d) -> np.ndarray:
    R = np.zeros(9)
    mj.mju_quat2Mat(R, d.qpos[3:7])
    return R.reshape(3, 3) @ d.qvel[3:6]


def _robot_geom_ids(m: mj.MjModel) -> set[int]:
    root = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, "link0")   # the arm and paddle (the base is drawn only)
    ids = set()
    for g in range(m.ngeom):
        b = m.geom_bodyid[g]
        while b not in (0, root):
            b = m.body_parentid[b]
        if b == root:
            ids.add(g)
    return ids


def _ball_only_xml(path: Path) -> str:
    """The same scene with the robot removed: used by predict_ball (identical ball/table/net physics)."""
    tree = ET.parse(path)
    root = tree.getroot()
    wb = root.find("worldbody")
    for b in list(wb):
        if b.tag == "body" and b.get("name") == ROBOT_ROOT:
            wb.remove(b)
    for tag in ("actuator",):
        for el in root.findall(tag):
            root.remove(el)
    con = root.find("contact")
    for el in list(con):
        if el.tag == "exclude" or (el.tag == "pair" and (el.get("geom2") == "paddle_blade" or
                                                        (el.get("name") or "").startswith("selfcol"))):
            con.remove(el)
    root.find("compiler").set("meshdir", str((path.parent / "assets").resolve()))
    return ET.tostring(root, encoding="unicode")


def load_instance(path: str | Path) -> dict:
    d = np.load(path, allow_pickle=False)
    return {k: d[k].copy() for k in d.files}


class Session:
    """One simulator (MuJoCo, single thread) for the frozen instance. Unlimited resets."""

    def __init__(self, instance: str | Path | None = None, scene: str | Path | None = None):
        self.instance_path = str(instance or DEFAULT_INSTANCE)
        self.inst = load_instance(self.instance_path)
        self.scene = Path(scene) if scene else SCENE_XML
        self.m = mj.MjModel.from_xml_path(str(self.scene))
        self.d = mj.MjData(self.m)
        self.selfcol = SC.monitors(self.m, {"A": "selfcol"}, "franka_panda")   # recorded only (sport.toml [self_collision])
        m = self.m
        self._qadr = np.array([m.jnt_qposadr[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j)] for j in JOINTS])
        self._vadr = np.array([m.jnt_dofadr[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j)] for j in JOINTS])
        self.JOINT_LOW = m.jnt_range[[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS], 0].copy()
        self.JOINT_HIGH = m.jnt_range[[mj.mj_name2id(m, mj.mjtObj.mjOBJ_JOINT, j) for j in JOINTS], 1].copy()
        self._ball_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_ball")
        self._table_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_table")
        self._net_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "geom_net")
        self._floor_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "floor")
        self._blade_geom = mj.mj_name2id(m, mj.mjtObj.mjOBJ_GEOM, "paddle_blade")
        self._robot_geoms = _robot_geom_ids(m)
        self._paddle_site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center")
        tz = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "target_zone")
        m.site_pos[tz, :2] = self.inst["target_center"]
        m.site_size[tz, :2] = self.inst["target_half"]
        m.site_rgba[tz, 3] = 0.0  # target-zone visualization is not part of the match
        self._kin = mj.MjData(m)          # scratch data for fk / jacobian / ik (never stepped)
        self._M = np.zeros((m.nv, m.nv))
        self.servo = TTServo(self._qadr, self._vadr, np.arange(NQ))   # the actuators are the 9 joints' motors, in order
        self.Q0 = np.r_[HOME, self.inst["q0"]].astype(np.float64)     # the ready configuration (base at home)
        self.substep_hook = None          # called after every physics step (the serve referee's toss checks)
        self._ball_model = None
        self.sim_steps_total = 0
        self.resets = 0
        self.reset()

    # ------------------------------------------------------------------ episode
    def reset(self) -> dict:
        """Back to the frozen initial state (ball in flight, robot at rest at Q0 = [home, q0], t = 0)."""
        m, d = self.m, self.d
        mj.mj_resetData(m, d)
        d.qpos[0:7] = self.inst["ball_qpos"]
        d.qvel[0:6] = self.inst["ball_qvel"]
        d.qpos[self._qadr] = self.Q0
        d.ctrl[:] = 0.0
        mj.mj_forward(m, d)
        self.servo.sync(d)                    # the servo starts at rest, holding the arm against gravity
        self._target = self.Q0.copy()
        self._actions: list[np.ndarray] = []
        self._k = 0
        self._events: list[dict] = []         # contact onsets involving the ball (merged, see MERGE_GAP_S)
        self._last_touch: dict[str, float] = {}
        self._robot_table = 0                 # the robot touched the table or the floor (allowed, ITTF 2.10.1.9-11)
        self._robot_net = 0                   # the robot touched the net assembly (a fault, ITTF 2.10.1.10)
        self._robot_contact_names: set[str] = set()
        self._v_out = None                    # ball velocity 5 ms after the first paddle contact
        self._w_out = None                    # and its spin (world frame)
        self.resets += 1
        return self.state()

    def _check_target(self, q: np.ndarray) -> None:
        if q.shape != (NQ,) or not np.all(np.isfinite(q)):
            raise ValueError(f"action must be {NQ} finite joint targets [base_x, base_y, q1..q7], got shape {q.shape}")
        lo_bad = q < self.JOINT_LOW - 1e-9
        hi_bad = q > self.JOINT_HIGH + 1e-9
        if lo_bad.any() or hi_bad.any():
            raise ValueError(f"step {self._k}: joint target outside range {np.nonzero(lo_bad | hi_bad)[0].tolist()}: {q}")
        dq = np.abs(q - self._target)
        lim = VEL_LIMIT * CONTROL_DT * (1 + 1e-6) + 1e-12
        if (dq > lim).any():
            j = int(np.argmax(dq / lim))
            raise ValueError(f"step {self._k}: joint {JOINTS[j]} target moved {dq[j]:.5f} in one control step "
                             f"(limit {VEL_LIMIT[j] * CONTROL_DT:.5f} = {VEL_LIMIT[j]} per s x {CONTROL_DT} s)")

    def step(self, q_target) -> dict:
        """Apply one action (9 joint targets [base_x, base_y, q1..q7]) for CONTROL_DT = 10 ms. Returns state()."""
        if self._k >= HORIZON:
            raise RuntimeError(f"episode is over ({HORIZON} control steps = {HORIZON_S} s); call reset()")
        q = np.asarray(q_target, dtype=np.float64).reshape(-1)
        self._check_target(q)
        m, d = self.m, self.d
        q_prev = self._target
        lo, hi = m.actuator_ctrlrange[:, 0], m.actuator_ctrlrange[:, 1]
        for j in range(1, SUBSTEPS + 1):
            mj.mj_fullM(m, self._M, d.qM)        # the joint-space inertia of the last forward pass (the servo's FF)
            d.ctrl[:] = self.servo.ctrl(m, d, self._M, j, q_prev, q, lo, hi)
            self._v_pre = d.qvel[0:3].copy()     # the ball's velocity before this substep (pre-contact)
            mj.mj_step(m, d)
            self.selfcol["A"].update(d)
            self._scan_contacts()
            if self.substep_hook is not None:
                self.substep_hook()
            if self._v_out is None and self._events and any(e["kind"] == "paddle" for e in self._events):
                t_hit = next(e["t"] for e in self._events if e["kind"] == "paddle")
                if d.time >= t_hit + 0.005 - 1e-9:
                    self._v_out = d.qvel[0:3].copy()
                    self._w_out = _world_spin(d)
        self.servo.after_step(d)
        self._target = q.copy()
        self._actions.append(q.copy())
        self._k += 1
        self.sim_steps_total += SUBSTEPS
        return self.state()

    def _scan_contacts(self) -> None:
        d, t = self.d, self.d.time
        bg = self._ball_geom
        for i in range(d.ncon):
            c = d.contact[i]
            g1, g2 = int(c.geom1), int(c.geom2)
            if bg in (g1, g2):
                other = g2 if g1 == bg else g1
                if other == self._table_geom:
                    kind = "table_own" if d.qpos[1] < 0 else "table_opp"
                elif other == self._blade_geom:
                    kind = "paddle"
                elif other == self._net_geom:
                    kind = "net"
                elif other == self._floor_geom:
                    kind = "floor"
                elif other in self._robot_geoms:
                    kind = "robot"
                else:
                    kind = "other"
                last = self._last_touch.get(kind)
                if last is None or t - last > MERGE_GAP_S + 1e-9:
                    # MuJoCo's frame points geom1 -> geom2. Store a stable
                    # surface -> ball convention, independent of geom ordering.
                    normal = c.frame[:3] if g2 == bg else -c.frame[:3]
                    ev = dict(t=round(float(t), 6), kind=kind, pos=d.qpos[0:3].tolist(),
                              vel=d.qvel[0:3].tolist(), vel_pre=self._v_pre.tolist(),
                              contact_pos=c.pos.tolist(), contact_normal=normal.tolist())
                    if kind == "paddle":              # the blade's velocity at the contact (what the arm delivered)
                        jacp = np.zeros((3, self.m.nv))
                        mj.mj_jacSite(self.m, d, jacp, None, self._paddle_site)
                        ev["blade_vel"] = (jacp[:, self._vadr] @ d.qvel[self._vadr]).round(5).tolist()
                    self._events.append(ev)
                self._last_touch[kind] = t
            else:
                rob1, rob2 = g1 in self._robot_geoms, g2 in self._robot_geoms
                if rob1 != rob2:   # robot touches the environment (table, net, floor)
                    if self._net_geom in (g1, g2):
                        self._robot_net = 1
                    else:
                        self._robot_table = 1
                    self._robot_contact_names.add(mj.mj_id2name(self.m, mj.mjtObj.mjOBJ_GEOM, g2 if rob1 else g1) or "?")

    def run_to_end(self) -> dict:
        """Hold the last target until the episode horizon (what the verifier does after the last action)."""
        while self._k < HORIZON:
            self.step(self._target)
        return self.status()

    # ------------------------------------------------------------------ observation
    def state(self) -> dict:
        d = self.d
        R = d.site_xmat[self._paddle_site].reshape(3, 3)
        jacp = np.zeros((3, self.m.nv)); jacr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, d, jacp, jacr, self._paddle_site)
        qd = d.qvel[self._vadr]
        return dict(
            t=float(d.time), k=self._k,
            q=d.qpos[self._qadr].copy(), qd=qd.copy(), q_target=self._target.copy(),
            ball_pos=d.qpos[0:3].copy(), ball_vel=d.qvel[0:3].copy(), ball_spin=d.qvel[3:6].copy(),
            paddle_pos=d.site_xpos[self._paddle_site].copy(), paddle_R=R.copy(), paddle_normal=R[:, 0].copy(),
            paddle_vel=jacp[:, self._vadr] @ qd, paddle_angvel=jacr[:, self._vadr] @ qd,
            events=copy.deepcopy(self._events),
        )

    def actions(self) -> np.ndarray:
        """(N, 9) joint targets applied since the last reset."""
        return np.array(self._actions, dtype=np.float64).reshape(-1, NQ)

    def status(self) -> dict:
        """Judge the episode so far (final only once the ball has landed or the horizon is reached)."""
        st = judge(self._events, self.inst, robot_env_contact=self._robot_net, t=float(self.d.time), k=self._k)
        if self._v_out is not None:
            st["hit_speed_out"] = float(np.linalg.norm(self._v_out))
        return st

    def state_sha(self) -> str:
        d = self.d
        h = hashlib.sha256()
        for a in (d.qpos, d.qvel, d.act, d.qacc_warmstart, d.ctrl, np.array([d.time]), self.servo.state()):
            h.update(np.ascontiguousarray(a, dtype=np.float64).tobytes())
        h.update(json.dumps(self._events, sort_keys=True).encode())
        return h.hexdigest()

    # ------------------------------------------------------------------ replay / io
    def replay(self, actions) -> dict:
        """Reset, apply `actions` open-loop, hold the last target to the 2.5 s horizon, return status()."""
        a = np.asarray(actions, dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != NQ or not (1 <= len(a) <= HORIZON):
            raise ValueError(f"actions must have shape (N, {NQ}) with 1 <= N <= {HORIZON}, got {a.shape}")
        self.reset()
        for q in a:
            self.step(q)
        st = self.run_to_end()
        st["n_actions"] = int(len(a))
        st["state_sha"] = self.state_sha()
        return st

    @staticmethod
    def save_trajectory(actions, path: str = "/app/output/trajectory.npz") -> str:
        a = np.asarray(actions, dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != NQ:
            raise ValueError(f"actions must be (N, {NQ}), got {a.shape}")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(path, actions=a, control_dt=np.float64(CONTROL_DT), task=np.str_("tabletennis_return"))
        return path

    # ------------------------------------------------------------------ helpers (privileged, allowed)
    def predict_ball(self, pos=None, vel=None, spin=None, duration: float = 1.5) -> dict:
        """Roll the ball out WITHOUT the robot (same ball/table/net physics, 1 ms steps) from the current ball
        state or from (pos, vel, spin). Returns t (N,), pos (N,3), vel (N,3), spin (N,3) and the table/net
        contact onsets. Times are relative to the current sim time. Matches the full sim until the ball
        touches the robot (up to floating-point differences)."""
        if self._ball_model is None:
            self._ball_model = mj.MjModel.from_xml_string(_ball_only_xml(self.scene))
            self._ball_data = mj.MjData(self._ball_model)
        bm, bd = self._ball_model, self._ball_data
        mj.mj_resetData(bm, bd)
        bd.qpos[0:7] = self.d.qpos[0:7]
        bd.qvel[0:6] = self.d.qvel[0:6]
        if pos is not None:
            bd.qpos[0:3] = pos
        if vel is not None:
            bd.qvel[0:3] = vel
        if spin is not None:
            bd.qvel[3:6] = spin
        mj.mj_forward(bm, bd)
        n = int(round(duration / bm.opt.timestep))
        P = np.zeros((n, 3)); V = np.zeros((n, 3)); W = np.zeros((n, 3)); T = np.zeros(n)
        tg = mj.mj_name2id(bm, mj.mjtObj.mjOBJ_GEOM, "geom_table")
        ng = mj.mj_name2id(bm, mj.mjtObj.mjOBJ_GEOM, "geom_net")
        fg = mj.mj_name2id(bm, mj.mjtObj.mjOBJ_GEOM, "floor")
        events, prev = [], set()
        for i in range(n):
            mj.mj_step(bm, bd)
            T[i] = (i + 1) * bm.opt.timestep
            P[i], V[i], W[i] = bd.qpos[0:3], bd.qvel[0:3], bd.qvel[3:6]
            cur = set()
            for c in range(bd.ncon):
                g = {int(bd.contact[c].geom1), int(bd.contact[c].geom2)}
                if tg in g:
                    cur.add("table_own" if bd.qpos[1] < 0 else "table_opp")
                if ng in g:
                    cur.add("net")
                if fg in g:
                    cur.add("floor")
            for kind in cur - prev:
                events.append(dict(t=float(T[i]), kind=kind, pos=P[i].tolist()))
            prev = cur
        return dict(t=T, pos=P, vel=V, spin=W, events=events)

    def _kin_set(self, q):
        """Scratch kinematics at the full joint vector q (9: [base_x, base_y, q1..q7])."""
        self._kin.qpos[:] = self.d.qpos
        self._kin.qpos[self._qadr] = q
        mj.mj_kinematics(self.m, self._kin)
        mj.mj_comPos(self.m, self._kin)

    def fk(self, q) -> tuple[np.ndarray, np.ndarray]:
        """Paddle blade centre position (3,) and rotation matrix (3,3) for the joint vector q (9). Column 0 of the
        rotation is the blade face normal, column 2 points along the handle (away from the wrist)."""
        self._kin_set(np.asarray(q, dtype=np.float64))
        return (self._kin.site_xpos[self._paddle_site].copy(),
                self._kin.site_xmat[self._paddle_site].reshape(3, 3).copy())

    def jacobian(self, q) -> np.ndarray:
        """(6, 9) paddle-centre Jacobian [linear; angular] (world frame) at the joint vector q; columns 2: are the arm."""
        self._kin_set(np.asarray(q, dtype=np.float64))
        jacp = np.zeros((3, self.m.nv)); jacr = np.zeros((3, self.m.nv))
        mj.mj_jacSite(self.m, self._kin, jacp, jacr, self._paddle_site)
        return np.vstack([jacp[:, self._vadr], jacr[:, self._vadr]])

    def ik(self, pos, normal, q_init=None, base=None, iters: int = 200, tol: float = 1e-4) -> tuple[np.ndarray, float]:
        """Damped-least-squares IK of the 7 arm joints with the base fixed at `base` (default: its current position):
        blade centre at `pos` with face normal along `normal` (rotation about the normal is free). Joint limits are
        respected by clipping. Returns (q arm (7,), residual) where residual = position error (m) + normal error
        (rad); check it."""
        b = self.d.qpos[self._qadr[:2]].copy() if base is None else np.asarray(base, float)
        q = np.array(self.inst["q0"] if q_init is None else q_init, dtype=np.float64)
        pos = np.asarray(pos, dtype=np.float64)
        n_t = np.asarray(normal, dtype=np.float64); n_t = n_t / np.linalg.norm(n_t)
        err = np.inf
        lo, hi = self.JOINT_LOW[2:] + 1e-4, self.JOINT_HIGH[2:] - 1e-4
        for _ in range(iters):
            p, R = self.fk(np.r_[b, q])
            n = R[:, 0]
            e = np.r_[pos - p, np.cross(n, n_t)]
            err = float(np.linalg.norm(e[:3]) + np.arcsin(min(1.0, np.linalg.norm(e[3:]))))
            if n @ n_t < 0:
                e[3:] = np.cross(n, n_t) + 0.5 * np.cross(n, R[:, 1])  # flip out of the antipodal solution
                err += np.pi / 2
            if err < tol:
                break
            J = self.jacobian(np.r_[b, q])[:, 2:]
            lam = 1e-3
            dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(6), e)
            q = np.clip(q + dq, lo, hi)
        return q, err

    # ------------------------------------------------------------------ rendering
    def render_video(self, actions, out: str, fps: int = 25, every: int = 1, width: int = 640, height: int = 360,
                     slowmo_label: bool = True) -> str:
        """Replay `actions` and write an mp4 (two views side by side). One frame per `every` control steps
        (10 ms): fps=25, every=1 is 4x slow motion."""
        import imageio.v2 as imageio
        a = np.asarray(actions, dtype=np.float64)
        r = mj.Renderer(self.m, height=height, width=width)
        cams = []
        for lookat, dist, az, el in (([0.0, -0.2, 0.1], 3.6, 0.0, -18.0), ([0.0, 0.0, 0.1], 4.2, -90.0, -22.0)):
            c = mj.MjvCamera(); c.lookat[:] = lookat; c.distance = dist; c.azimuth = az; c.elevation = el
            cams.append(c)
        opt = mj.MjvOption()
        writer = imageio.get_writer(out, fps=fps, macro_block_size=8)

        def frame():
            imgs = []
            for c in cams:
                r.update_scene(self.d, camera=c, scene_option=opt)
                imgs.append(r.render())
            writer.append_data(np.concatenate(imgs, axis=1))

        self.reset(); frame()
        for k in range(HORIZON):
            self.step(a[k] if k < len(a) else self._target)
            if (k + 1) % every == 0:
                frame()
        writer.close(); r.close()
        return out


# ---------------------------------------------------------------------- judging
def judge(events: list[dict], inst: dict, robot_env_contact: int = 0, t: float = 0.0, k: int = 0) -> dict:
    """Success iff: the ball bounces exactly once on the robot's half and touches nothing else before the hit;
    exactly one paddle contact; after the hit the ball's first contact other than the net is the table on the
    opponent half inside the target zone; the robot never touches the net assembly (robot_env_contact: a net contact;
    touching the table or the floor is allowed, ITTF 2.10.1.9-2.10.1.11).
    The net is transparent to the judgement (ITTF 2.7.1: a return is good if it touches the opponent's court
    "directly or after touching the net assembly"); `net_touch` reports it. A serve that touches the net is a let:
    the caller decides that before calling judge."""
    center = np.asarray(inst["target_center"], dtype=np.float64)
    half = np.asarray(inst["target_half"], dtype=np.float64)
    def top_contact(e):
        cp, cn = e.get("contact_pos"), e.get("contact_normal")
        # Top edges have an upward component; vertical sides and the underside
        # do not. Contact midpoints may lie well below z=0 at higher impact
        # speeds, so height cannot distinguish top contact from side contact.
        return bool(cp is not None and cn is not None and cn[2] > 1e-6 and
                    abs(cp[0]) <= .7625 + .001 and abs(cp[1]) <= 1.37 + .001)
    kinds = [e["kind"] for e in events]
    out = dict(success=False, hit=0, n_paddle_contacts=kinds.count("paddle"), own_bounces_before_hit=0,
               bad_contact_before_hit=0, landed=0, landed_opponent_half=0, in_zone=0, landing_error_m=-1.0,
               landing_x=0.0, landing_y=0.0, net_touch=int("net" in kinds), robot_env_contact=int(robot_env_contact),
               hit_time=-1.0, hit_speed_out=0.0, t=t, k=k)
    if "paddle" not in kinds:
        return out
    ip = kinds.index("paddle")
    out["hit"] = 1
    out["hit_time"] = float(events[ip]["t"])
    pre = kinds[:ip]
    edge_rules = bool(inst.get("table_edges_valid"))
    out["own_bounces_before_hit"] = sum(e["kind"] == "table_own" and (not edge_rules or top_contact(e))
                                           for e in events[:ip])
    out["bad_contact_before_hit"] = int(any(x in ("robot", "floor", "other") for x in pre) or
        (edge_rules and any(e["kind"] in ("table_own", "table_opp") and not top_contact(e)
                            for e in events[:ip])))
    post = [e for e in events[ip + 1:] if e["kind"] not in ("paddle", "net")]
    if post:
        e = post[0]
        out["landed"] = 1
        out["landing_x"], out["landing_y"] = float(e["pos"][0]), float(e["pos"][1])
        if e["kind"] == "table_opp":
            out["landed_opponent_half"] = 1
            err = np.abs(np.array(e["pos"][:2]) - center)
            if edge_rules:
                cp = e.get("contact_pos")
                out["in_zone"] = int(top_contact(e) and cp[1] >= 0)
            else:
                out["in_zone"] = int(bool(np.all(err <= half)))
            out["landing_error_m"] = float(np.linalg.norm(np.array(e["pos"][:2]) - center))
    out["success"] = bool(out["n_paddle_contacts"] == 1 and out["own_bounces_before_hit"] == 1
                          and not out["bad_contact_before_hit"] and out["landed_opponent_half"] == 1
                          and out["in_zone"] == 1 and not out["robot_env_contact"])
    return out


# ---------------------------------------------------------------------- CLI
def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("--instance", default=DEFAULT_INSTANCE)
    p = sub.add_parser("replay"); p.add_argument("--instance", default=DEFAULT_INSTANCE)
    p.add_argument("--traj", required=True); p.add_argument("--repeat", type=int, default=1)
    p = sub.add_parser("render"); p.add_argument("--instance", default=DEFAULT_INSTANCE)
    p.add_argument("--traj", required=True); p.add_argument("--out", default="replay.mp4")
    a = ap.parse_args(argv)
    s = Session(instance=a.instance)
    if a.cmd == "info":
        inst = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in s.inst.items()}
        print(json.dumps(dict(instance=inst, horizon_s=HORIZON_S, control_dt=CONTROL_DT,
                              joint_low=s.JOINT_LOW.tolist(), joint_high=s.JOINT_HIGH.tolist(),
                              vel_limit=VEL_LIMIT.tolist()), indent=1))
        return 0
    acts = np.load(a.traj, allow_pickle=False)["actions"]
    if a.cmd == "replay":
        for _ in range(a.repeat):
            st = s.replay(acts)
            print(json.dumps({k: v for k, v in st.items()}, default=float))
        return 0
    if a.cmd == "render":
        print(s.render_video(acts, a.out))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_main())
