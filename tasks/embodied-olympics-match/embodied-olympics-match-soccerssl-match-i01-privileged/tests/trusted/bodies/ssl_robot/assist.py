"""The dribbler's capped grip (body.toml [dribbler_assist]; README "Dribbler"): what the rigid contact model misses.

Why: the bar-ball contact (body.py: a 14 mm TPU bar spun by its motor, on a damped hinge) reproduces the real
dribbler's forward and backward ball handling, but not its lateral and turning grip. A spinning bar slides on the
ball, so its kinetic friction points along the spin and almost nothing is left sideways; the real soft TPU bar
grips the ball over a contact patch ("the ball dips into the dribble bar", KIKS 2023) that a rigid MuJoCo contact
cannot have. Measured (tools/dribble_lab.py, README): with the contact alone the ball is lost sideways at
0.5-0.6 m/s and turning at 1.5-2.7 rad/s whatever the friction, bar speed or torque, while real robots carry it
sideways to 2.6 m/s and turn to 9.3 rad/s (ZJUNlict 2024, S6).

What: while the dribbler turns and a ball sits at the bar, a horizontal spring-damper pulls the ball towards its
held point (the bar's rest point), with
  * a force cap (hold_force_n): an opponent or a fast turn pulls the ball out; the force never lifts the ball (the
    rules forbid lifting, S7 3.2.4) and the robot feels the opposite force;
  * engagement only when the ball reaches the bar (the break beam blocked by it) at a relative speed up to
    catch_speed_m_s (a faster ball just bounces off the contact model);
  * release when the robot moves beyond the measured limits of real dribbling (back_speed_m_s, side_speed_m_s,
    turn_rate_rad_s: the speeds at which ZJUNlict's robot lost the ball at 3 m/s^2, S6), when the ball leaves the
    zone (zone_m in front of the held point), when the dribbler is off, or at a kick.
It is a bounded physical force, not a weld: the ball still rolls, collides and is stolen by contact.
The force is written into data.qfrc_applied every physics step (the ball's free-joint translation; the opposite
force and its moment on the robot's planar joints) as a change of this rig's own previous contribution, so other
writers' forces are kept. A world must not clear qfrc_applied (it may clear xfrc_applied).
"""
from __future__ import annotations

import math

import numpy as np


class Assist:
    def __init__(self, P: dict, held_point, ball_r):
        self.P = P
        self.hold = np.asarray(held_point, float)              # robot frame (x, y)
        self.ball_r = float(ball_r)
        self.k = float(P["stiffness_n_m"])
        self.c = float(P["damping_n_s_m"])
        self.cap = float(P["hold_force_n"])
        self.ball = -1                                          # the engaged ball body
        self.m, self.rdofs = None, None                         # set by the rig: the model, the robot's x, y, yaw dofs
        self.f_prev = None                                      # (ball body, robot body, force) last written
        self.stats = dict(engaged=0, released=dict())

    def release(self, why):
        if self.ball >= 0:
            self.stats["released"][why] = self.stats["released"].get(why, 0) + 1
        self.ball = -1

    def step(self, m, d, robot_body, pose, vel, beam, dribbling, on=True):
        """one physics step: decide engagement, write the force (or clear it). pose / vel: the robot's (x, y, yaw)
        and its time derivative (world frame); beam: (blocked, body)."""
        if self.ball < 0 and not beam[0]:                      # nothing engaged, nothing at the bar: no force
            if self.f_prev is not None:
                self._write(d, robot_body, np.zeros(3))
            return None
        P = self.P
        F = np.zeros(3)
        c, s = math.cos(pose[2]), math.sin(pose[2])
        vb = np.array([c * vel[0] + s * vel[1], -s * vel[0] + c * vel[1]])
        if not on or not dribbling:
            self.release("dribbler off")
        elif self.ball < 0 and beam[0] and beam[1] >= 0 and m.body_mass[beam[1]] <= 0.1 \
                and m.body_jntnum[beam[1]] == 1:
            rel_v = self._rel(m, d, beam[1], pose, vel)[1]
            if float(np.linalg.norm(rel_v)) <= float(P["catch_speed_m_s"]):
                self.ball = int(beam[1])
                self.stats["engaged"] += 1
        if self.ball >= 0:
            if vb[0] < -float(P["back_speed_m_s"]):
                self.release("back speed")
            elif abs(vb[1]) > float(P["side_speed_m_s"]):
                self.release("side speed")
            elif abs(vel[2]) > float(P["turn_rate_rad_s"]):
                self.release("turn rate")
        if self.ball >= 0:
            (rp, rv), z = self._rel(m, d, self.ball, pose, vel), self._z(d, self.ball)
            e = rp - self.hold
            if e[0] > float(P["zone_m"]) or abs(e[1]) > float(P["zone_m"]) or z > self.ball_r + 0.01:
                self.release("left the zone")
            else:
                f = -self.k * e - self.c * rv                      # robot frame
                n = float(np.linalg.norm(f))
                if n > self.cap:
                    f *= self.cap / n
                F[0:2] = (c * f[0] - s * f[1], s * f[0] + c * f[1])
        self._write(d, robot_body, F)
        return F

    def _rel(self, m, d, b, pose, vel):
        """the ball's centre and velocity relative to the robot, in the robot frame (x, y)"""
        j = m.body_jntadr[b]
        qa, va = m.jnt_qposadr[j], m.jnt_dofadr[j]
        p = d.qpos[qa:qa + 3]
        v = d.qvel[va:va + 3]
        dx, dy = p[0] - pose[0], p[1] - pose[1]
        c, s = math.cos(pose[2]), math.sin(pose[2])
        rp = np.array([c * dx + s * dy, -s * dx + c * dy])
        vr = np.array([v[0] - (vel[0] - vel[2] * dy), v[1] - (vel[1] + vel[2] * dx)])   # minus the robot's point
        return rp, np.array([c * vr[0] + s * vr[1], -s * vr[0] + c * vr[1]])

    def _z(self, d, b):
        return float(d.xpos[b][2])

    def _write(self, d, robot_body, F, m=None, rdofs=None):
        """qfrc_applied: + F on the ball's translation, - F (and its moment about the robot's centre) on the robot"""
        if self.f_prev is not None:
            bd, rd, f0 = self.f_prev
            d.qfrc_applied[bd:bd + 3] -= f0[0]
            d.qfrc_applied[rd] -= f0[1]
            self.f_prev = None
        if self.ball >= 0 and np.any(F) and self.m is not None:
            m = self.m
            bd = int(m.jnt_dofadr[m.body_jntadr[self.ball]])
            r = d.xpos[self.ball][0:2] - d.xpos[robot_body][0:2]
            fr = np.array([-F[0], -F[1], -(r[0] * F[1] - r[1] * F[0])])
            d.qfrc_applied[bd:bd + 3] += F
            d.qfrc_applied[self.rdofs] += fr
            self.f_prev = (bd, self.rdofs.copy(), (F.copy(), fr))
