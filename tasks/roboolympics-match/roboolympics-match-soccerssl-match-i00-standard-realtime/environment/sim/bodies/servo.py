"""The robot library's one trusted limit / servo path (bodies/README.md "限位与伺服").

Every robot of the library sends its commands through this module, and nothing else writes a library robot's
actuators: a robot's `body.py` builds its servo here (`Servo`, `Actuators`, `PlanarBase`, `WalkCommand`) from its
`body.toml`, and a sport drives the robot through the robot's rig (`rig.apply`, `rig.begin_step`) or, for the
fixed-base arms of the library (bodies/franka_panda, franka_fr3, kuka_iiwa14), through `bodies/limits.py`'s
`JerkLimiter` and `TorqueRateLimiter` (the primitives this module composes). `ci_checks/check-robot-limits.py` fails a
sport that references a library robot without going through these (or that defines or patches its own limiter).

The real limits are binding (user decision 2026-10-08, "B0"): the values the manufacturer's controller enforces (SDK)
over the URDF's, never unlimited; an unpublished value is a labelled estimate in body.toml ([limits.<group>.source]
says which). What this module enforces, per layer:

  command     `Servo.check` / the rigs' `check`: a 10 ms target row inside the ranges, within the speed limits from
              the row before, and (given the row before that) within the acceleration limits; walking commands
              clipped to the real joystick range and rate-limited (`WalkCommand`)
  setpoint    every 1 ms physics step the reference (the 10 ms targets, interpolated) passes a jerk-limited setpoint
              generator (`SetpointGenerator`, limits.JerkLimiter's cascade and braking law, which holds for any ratio
              of acceleration to jerk, for joints and joint-like coordinates; `PlanarBase` for a planar base,
              per axis in the robot's own frame like the vendors' chassis SDKs, or on the norm): the setpoint never
              exceeds the velocity, acceleration and jerk limits that body.toml declares
  output      `Actuators.write`: the servo torque through the torque-rate limit (where published), the motor's
              torque-speed curve (where published: Unitree's actuator model) and the torque limit; only then
              `d.ctrl`

What it does not change: contacts, collisions and external forces (a joint pushed by a hit moves as physics says;
D9 of the audit: recorded, not prevented), the joint ranges of the MJCF.

Deterministic: plain float64 numpy, no randomness, no threads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import limits as AL

from .sources import QUANTITIES, REQUIRED, SOURCE_RE, TRUSTED, source_problems  # noqa: F401  (stdlib only)


# ------------------------------------------------------------------------------------------------ declarations
def _arr(v, n=None):
    if v is None:
        return None
    a = np.atleast_1d(np.asarray(v, float))
    if n is not None and a.size == 1 and n > 1:
        a = np.full(n, float(a[0]))
    return a


def joint_limits(decl: dict, group: str, n: int | None = None, name: str | None = None) -> AL.ArmLimits:
    """The limits of one joint group of a body.toml ([limits.<group>]) as bodies/limits.py's ArmLimits (scalars
    broadcast to n joints). Missing acceleration / jerk / torque rate stay None (body.toml's source table says why)."""
    L = decl["limits"][group]
    vel = _arr(L["speed_rad_s"], n)
    n = len(vel)
    rng = L.get("range_rad")
    if rng is not None and np.ndim(rng) == 1:
        lo, hi = np.full(n, float(rng[0])), np.full(n, float(rng[1]))
    elif rng is not None:
        lo, hi = np.array([r[0] for r in rng], float), np.array([r[1] for r in rng], float)
    else:
        lo = _arr(L.get("range_lo_rad"), n) if L.get("range_lo_rad") is not None else np.full(n, -np.inf)
        hi = _arr(L.get("range_hi_rad"), n) if L.get("range_hi_rad") is not None else np.full(n, np.inf)
    return AL.ArmLimits(
        body=decl["body"]["name"] if name is None else name, model=decl["body"]["title"] + f" [{group}]",
        range_lo=lo, range_hi=hi, vel=vel, acc=_arr(L.get("accel_rad_s2"), n), jerk=_arr(L.get("jerk_rad_s3"), n),
        tau=_arr(L.get("torque_nm"), n) if L.get("torque_nm") is not None else np.full(n, np.inf),
        dtau=_arr(L.get("torque_rate_nm_s"), n), sources=dict(decl.get("sources", {})))


def stack(parts: list[AL.ArmLimits], body: str, model: str) -> AL.ArmLimits:
    """Several limit groups as one (the order of `parts`); a quantity one part lacks becomes None for all, unless
    every part has it."""
    cat = lambda k: None if any(getattr(p, k) is None for p in parts) else np.concatenate([getattr(p, k) for p in parts])
    return AL.ArmLimits(body, model, cat("range_lo"), cat("range_hi"), cat("vel"), cat("acc"), cat("jerk"),
                        cat("tau"), cat("dtau"), parts[0].sources if parts else {})


# ------------------------------------------------------------------------------------------------ output stage
class Actuators:
    """The output stage of a group of motors: servo torques -> torque-rate limit (where declared) -> the motors'
    torque-speed curve (where declared) -> the torque limit -> d.ctrl. The only writer of a library robot's motors.

    envelope: per joint (X1, X2, Y1, Y2) of Unitree's actuator model (unitree_rl_lab unitree_actuators.py): a torque
    along the motion is limited to Y1 below X1 rad/s, falling linearly to 0 at X2 (the motor cannot drive faster); a
    torque against the motion (braking) to Y2 at any speed, as the curve's drawing in unitree_actuators.py shows it
    (its code also fades the braking torque beyond X1, which lets a joint pushed past X2 run away unbraked).

    thermal (optional; motor_model() builds it from body.toml [motors.thermal]): (rated, T, derate_from) per motor:
    an I^2 t state h per motor, dh/dt = ((tau / rated)^2 - h) / T (h = 1: the winding at its limit after a long
    time at the rated torque); the torque limit falls linearly from tau_max at h = derate_from to the rated torque at
    h = 1 (a drive's I^2 t foldback). h starts at 0 (a cold motor) and is never reset by reset(): heat stays with the
    motor (cool_down() for a new match).
    power (optional; [motors.bus]): (groups, watts): per group of motors (one robot's), the summed positive
    mechanical power tau * qd is capped at watts; above it the torques doing positive work are scaled down together
    (the battery and the drives cannot deliver more).
    """

    def __init__(self, model, aid, vadr, tau_max, dt, dtau=None, envelope=None, thermal=None, power=None):
        self.aid, self.vadr = np.asarray(aid, int), np.asarray(vadr, int)
        n = len(self.aid)
        self.dt = float(dt)
        self.tau_max = np.minimum(np.asarray(tau_max, float), model.actuator_ctrlrange[self.aid, 1])
        self.step_max = None if dtau is None else np.asarray(dtau, float) * float(dt)
        self.env = None if envelope is None else tuple(np.asarray(e, float) for e in envelope)
        self.thermal = None
        if thermal is not None:
            rated, T, frm = (np.broadcast_to(np.asarray(x, float), (n,)).copy() for x in thermal)
            self.thermal = (np.minimum(rated, self.tau_max), T, frm)
        self.power = None
        if power is not None:
            groups, watts = power
            self.power = ([np.asarray(g, int) for g in groups], float(watts))
        self.h = np.zeros(n)
        self.tau = np.zeros(n)
        self.stats = dict(steps=0, torque_clipped=0, rate_clipped=0, envelope_clipped=0, thermal_derated=0,
                          power_capped=0)

    def reset(self, tau=None):
        self.tau = np.zeros(len(self.aid)) if tau is None else np.clip(np.asarray(tau, float), -self.tau_max,
                                                                        self.tau_max)

    def cool_down(self):
        """The thermal state of cold motors (a new match)."""
        self.h = np.zeros(len(self.aid))

    def thermal_limit(self):
        """The torque limit per motor now (the I^2 t foldback; tau_max without a thermal model)."""
        if self.thermal is None:
            return self.tau_max
        rated, _, frm = self.thermal
        x = np.clip((self.h - frm) / np.maximum(1.0 - frm, 1e-9), 0.0, 1.0)
        return self.tau_max - (self.tau_max - rated) * x

    def limit(self, qd):
        """The torque limit per motor at joint speeds qd for torques along (+) the motion: (along, against)."""
        if self.env is None:
            return self.tau_max, self.tau_max
        X1, X2, Y1, Y2 = self.env
        a = np.abs(qd)
        with np.errstate(invalid="ignore"):                 # X1 = X2 = inf: no curve for that joint
            fall = np.clip(1.0 - (a - X1) / np.maximum(X2 - X1, 1e-9), 0.0, 1.0)
        k = np.where(a < X1, 1.0, fall)
        return np.minimum(Y1 * k, self.tau_max), np.minimum(Y2, self.tau_max)

    def write(self, d, tau):
        t = np.asarray(tau, float)
        st = self.stats
        st["steps"] += 1
        if self.step_max is not None:
            c = np.clip(t, self.tau - self.step_max, self.tau + self.step_max)
            st["rate_clipped"] += int(np.any(c != t))
            t = c
        if self.env is not None:
            qd = d.qvel[self.vadr]
            along, against = self.limit(qd)
            lim = np.where(t * qd > 0, along, against)
            c = np.clip(t, -lim, lim)
            st["envelope_clipped"] += int(np.any((np.abs(c) < np.abs(t) - 1e-12) & (lim < self.tau_max)))
            t = c
        c = np.clip(t, -self.tau_max, self.tau_max)
        st["torque_clipped"] += int(np.any(c != t))
        t = c
        if self.thermal is not None:
            th = self.thermal_limit()
            c = np.clip(t, -th, th)
            st["thermal_derated"] += int(np.any(c != t))
            t = c
        if self.power is not None:
            qd = d.qvel[self.vadr]
            groups, watts = self.power
            p = np.maximum(t * qd, 0.0)
            capped = False
            for g in groups:
                ps = float(p[g].sum())
                if ps > watts:
                    pos = g[p[g] > 0]
                    t[pos] = t[pos] * (watts / ps)
                    capped = True
            st["power_capped"] += int(capped)
        if self.thermal is not None:
            rated, T, _ = self.thermal
            self.h = self.h + self.dt * ((t / rated) ** 2 - self.h) / T
        self.tau = t
        d.ctrl[self.aid] = t
        return t


def unitree_envelope(decl: dict, joint_keys: list):
    """(X1, X2, Y1, Y2) arrays for joints named by their body.toml [motors.assign] keys (None: a joint without a
    motor curve, e.g. a planar copy's base), or None when the body declares no [motors]."""
    mot = decl.get("motors")
    if not mot:
        return None
    inf = dict(X1=np.inf, X2=np.inf, Y1=np.inf, Y2=np.inf)
    curves = [inf if k is None else mot[mot["assign"][k]] for k in joint_keys]
    return tuple(np.array([c[x] for c in curves], float) for x in ("X1", "X2", "Y1", "Y2"))


def motor_model(decl: dict, joint_keys: list, groups=None) -> dict:
    """Actuators keyword arguments of a body's motor model from body.toml [motors]: the torque-speed envelope
    (unitree_envelope), the thermal derating ([motors.thermal]: rated_frac of the torque limit is the continuous
    torque, the peak torque from cold lasts peak_s before the foldback ends at the rated torque, the foldback starts
    at derate_from) and the bus power cap per group of motors ([motors.bus] power_w; groups: index arrays into
    joint_keys, one per robot; default all one group). Only the parts the body declares."""
    mot = decl.get("motors") or {}
    kw = dict(envelope=unitree_envelope(decl, joint_keys))
    th = mot.get("thermal")
    if th:
        tau = np.array([np.nan if k is None else _leg_torque(decl, k) for k in joint_keys], float)
        rf = float(th["rated_frac"])
        T = float(th["peak_s"]) / -math.log(1.0 - rf ** 2)    # h(peak_s) = 1 at the peak torque from cold
        kw["thermal"] = (rf * tau, T, float(th["derate_from"]))
    bus = mot.get("bus")
    if bus:
        kw["power"] = ([np.arange(len(joint_keys))] if groups is None else groups, float(bus["power_w"]))
    return kw


def _leg_torque(decl: dict, key: str) -> float:
    """The torque limit of a motor by its [motors.assign] key (the [motors] curve's Y1, the URDF torque)."""
    mot = decl["motors"]
    return float(mot[mot["assign"][key]]["Y1"])


# ------------------------------------------------------------------------------------------------ setpoints
brake_speed = AL.brake_speed     # the jerk-limited stopping speed (bodies/limits.py; the same law, one copy)


class SetpointGenerator:
    """The library's setpoint generator at the physics rate: per coordinate a third-order state (q, qd, qdd) that
    follows a reference (position r, velocity rd) and never exceeds |qd| <= vel, |qdd| <= acc, |dqdd/dt| <= jerk.

    limits.JerkLimiter's law (velocity loop: the sqrt law at the jerk limit; the velocity guard; the jerk clipped;
    the reference velocity as feed-forward; a position loop that brakes within both the acceleration and the jerk
    limit, brake_speed), with the body's own jerk limit at every step (no per-step jerk_cap). A plain sqrt law on the
    position, which assumes the deceleration is there at once, overshoots and rings wherever the jerk needs long to
    build the acceleration: an SDK's slow jerk (the R1 Pro's arm: 4.5 rad/s^2 at 4.5 rad/s^3) and equally the
    Franka's when its jerk is capped by the torque rate at the pose (limits.jerk_caps(): a few hundred rad/s^3 on
    the shoulder), which is why limits.JerkLimiter uses this law too since 2026-10-11 (since 2026-10-12 both take
    the coast distance relative to the reference's velocity, qd - rd). The velocity bound runs one step of
    acceleration and jerk below the limit (the discrete steps' overshoot). Without declared acceleration /
    jerk (Unitree: none published) it is a velocity limiter with a 17 ms lag. Deterministic (float64 numpy)."""

    KP, KV, BRAKE = AL.JerkLimiter.KP, AL.JerkLimiter.KV, AL.JerkLimiter.BRAKE

    def __init__(self, lim: AL.ArmLimits, dt: float, q0=None):
        self.lim, self.dt = lim, float(dt)
        n = lim.n
        self.A = lim.acc if lim.acc is not None else np.full(n, 1e6)
        self.J = lim.jerk if lim.jerk is not None else np.full(n, 1e9)
        margin = (lim.jerk * self.dt ** 2 if lim.jerk is not None else 0.0) + \
            (lim.acc * self.dt if lim.acc is not None else 0.0)
        self.V = np.maximum(lim.vel - margin, 0.5 * lim.vel)
        self.reset(np.zeros(n) if q0 is None else q0)

    def reset(self, q, qd=None, qdd=None):
        n = self.lim.n
        self.q = np.asarray(q, float).copy()
        self.qd = np.zeros(n) if qd is None else np.clip(np.asarray(qd, float), -self.V, self.V)
        self.qdd = np.zeros(n) if qdd is None else np.asarray(qdd, float).copy()

    def step(self, r, rd=None):
        dt, V, A, J = self.dt, self.V, self.A, self.J
        r = np.asarray(r, float)
        rd = np.zeros_like(r) if rd is None else np.asarray(rd, float)
        e = r - self.q
        # the position loop sees the error left once the present acceleration has ramped to zero at the jerk limit
        # (the distance it still covers, relative to the reference moving at rd): with a slow jerk that distance is
        # what makes a plain sqrt law overshoot; taken with qd alone a moving reference looked overshot and the
        # setpoint braked early (limits.JerkLimiter, 2026-10-12)
        t = np.abs(self.qdd) / J
        e = e - ((self.qd - rd) * t + 0.5 * self.qdd * t * t - np.sign(self.qdd) * J * t ** 3 / 6.0)
        v_pos = np.sign(e) * np.minimum(self.KP * np.abs(e), brake_speed(np.abs(e), self.BRAKE * A, J))
        v_cmd = np.clip(rd + v_pos, -V, V)
        a_cmd = np.clip(AL._sqrt_ctrl(v_cmd - self.qd, self.KV, J), -A, A)
        room_up, room_dn = np.maximum(0.0, V - self.qd), np.maximum(0.0, V + self.qd)
        a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * room_dn), np.sqrt(2.0 * J * room_up))
        j = np.clip((a_cmd - self.qdd) / dt, -J, J)
        self.q = self.q + self.qd * dt + 0.5 * self.qdd * dt * dt + j * dt ** 3 / 6.0
        self.qd = self.qd + self.qdd * dt + 0.5 * j * dt * dt
        self.qdd = self.qdd + j * dt
        return self.q, self.qd, self.qdd


# ------------------------------------------------------------------------------------------------ planar base
@dataclass
class BaseLimits:
    """A planar base: speed / acceleration / jerk of the translation (per axis of the robot's own frame, `axes`, or
    on the norm, `norm`) and of the yaw. From body.toml [limits.base]."""

    speed: np.ndarray       # (2,) or scalar for norm
    accel: np.ndarray
    jerk: np.ndarray
    yaw_rate: float
    yaw_accel: float
    yaw_jerk: float
    mode: str = "axes"

    @classmethod
    def of(cls, L: dict) -> "BaseLimits":
        mode = L.get("mode", "norm")
        f = (lambda k: np.asarray(L[k], float)) if mode == "axes" else (lambda k: float(np.max(L[k])))
        return cls(f("speed_m_s"), f("accel_m_s2"), f("jerk_m_s3"), float(L["yaw_rate_rad_s"]),
                   float(L["yaw_accel_rad_s2"]), float(L["yaw_jerk_rad_s3"]), mode)

    def table(self) -> dict:
        r = lambda x: np.round(np.asarray(x, float), 4).tolist()
        return dict(mode=self.mode, speed_m_s=r(self.speed), accel_m_s2=r(self.accel), jerk_m_s3=r(self.jerk),
                    yaw_rate_rad_s=self.yaw_rate, yaw_accel_rad_s2=self.yaw_accel, yaw_jerk_rad_s3=self.yaw_jerk)


def _clipn(v, lim, norm):
    if not norm:
        return np.clip(v, -lim, lim)
    n = float(np.linalg.norm(v))
    return v if n <= lim or n == 0.0 else v * (lim / n)


def _sqrtn(err, k, dlim, norm):
    """the sqrt law (limits._sqrt_ctrl) per component, or on the vector's length along its direction"""
    if not norm:
        return AL._sqrt_ctrl(err, k, dlim)
    n = float(np.linalg.norm(err))
    if n == 0.0:
        return np.zeros_like(err)
    return err / n * float(AL._sqrt_ctrl(np.array([n]), k, dlim)[0])


class PlanarBase:
    """The jerk-limited setpoint generator of a planar base (x, y in the mount frame; yaw). The translation is limited
    in the robot's own frame (rotated by the setpoint's yaw), per axis ("axes": the vendors' chassis SDKs limit the
    commanded vx, vy, wz separately) or on the norm ("norm"); the yaw as one joint. The same cascade as
    limits.JerkLimiter (position -> velocity -> acceleration -> jerk, sqrt laws, the velocity guard)."""

    KP, KV, BRAKE = AL.JerkLimiter.KP, AL.JerkLimiter.KV, AL.JerkLimiter.BRAKE

    def __init__(self, lim: BaseLimits, dt: float):
        self.lim, self.dt = lim, float(dt)
        self.norm = lim.mode != "axes"
        self.reset(np.zeros(3))

    def reset(self, q, qd=None):
        """q: (x, y, yaw) in the mount frame; qd: their time derivatives (mount frame)."""
        q = np.asarray(q, float)
        qd = np.zeros(3) if qd is None else np.asarray(qd, float)
        self.p, self.yaw = q[:2].copy(), float(q[2])
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        self.v = np.array([c * qd[0] + s * qd[1], -s * qd[0] + c * qd[1]])      # body frame
        self.a = np.zeros(2)
        self.w, self.wd = float(qd[2]), 0.0

    def state(self):
        """(q, qd, qdd) in the mount frame: x, y, yaw."""
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        R = np.array([[c, -s], [s, c]])
        v, a = R @ self.v, R @ self.a
        return np.r_[self.p, self.yaw], np.r_[v, self.w], np.r_[a, self.wd]

    def _axis(self, e, rd, v, a, V, A, J, norm):
        dt = self.dt
        Vg = V - J * dt * dt - A * dt                # one step of jerk and of acceleration (discrete overshoot)
        if norm:                                   # the error left once the acceleration has ramped to zero
            na = float(np.linalg.norm(a))          # (relative to the reference moving at rd)
            if na > 0.0:
                t = na / J
                e = e - ((v - rd) * t + 0.5 * a * t * t - a / na * J * t ** 3 / 6.0)
        else:
            t = np.abs(a) / J
            e = e - ((v - rd) * t + 0.5 * a * t * t - np.sign(a) * J * t ** 3 / 6.0)
        if norm:
            n_e = float(np.linalg.norm(e))
            sp = min(self.KP * n_e, float(brake_speed(n_e, self.BRAKE * A, J)))
            v_pos = e / n_e * sp if n_e > 0 else np.zeros_like(e)
        else:
            v_pos = np.sign(e) * np.minimum(self.KP * np.abs(e), brake_speed(np.abs(e), self.BRAKE * A, J))
        v_cmd = _clipn(rd + v_pos, Vg, norm)
        a_cmd = _clipn(_sqrtn(v_cmd - v, self.KV, J, norm), A, norm)
        if norm:                                   # the velocity guard along the motion
            sp = float(np.linalg.norm(v))
            if sp > 0.0:
                u = v / sp
                ap = float(a_cmd @ u)
                cap = math.sqrt(2.0 * J * max(0.0, Vg - sp))
                if ap > cap:
                    a_cmd = a_cmd - (ap - cap) * u
        else:
            room_up, room_dn = np.maximum(0.0, Vg - v), np.maximum(0.0, Vg + v)
            a_cmd = np.clip(a_cmd, -np.sqrt(2.0 * J * room_dn), np.sqrt(2.0 * J * room_up))
        j = _clipn((a_cmd - a) / dt, J, norm)
        return j

    def step(self, r, rd=None):
        """advance one step towards the reference r = (x, y, yaw) moving at rd; returns (q, qd, qdd) (mount frame)"""
        L, dt = self.lim, self.dt
        r = np.asarray(r, float)
        rd = np.zeros(3) if rd is None else np.asarray(rd, float)
        jw = self._axis(np.array([r[2] - self.yaw]), np.array([rd[2]]), np.array([self.w]), np.array([self.wd]),
                        L.yaw_rate, L.yaw_accel, L.yaw_jerk, False)[0]
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        Rt = np.array([[c, s], [-s, c]])                        # mount -> body frame
        e_b, rd_b = Rt @ (r[:2] - self.p), Rt @ rd[:2]
        j = self._axis(e_b, rd_b, self.v, self.a, L.speed, L.accel, L.jerk, self.norm)
        v_new = self.v + self.a * dt + 0.5 * j * dt * dt
        dp_b = self.v * dt + 0.5 * self.a * dt * dt + j * dt ** 3 / 6.0
        self.a = self.a + j * dt
        yaw_mid = self.yaw + 0.5 * self.w * dt
        cm, sm = math.cos(yaw_mid), math.sin(yaw_mid)
        self.p = self.p + np.array([cm * dp_b[0] - sm * dp_b[1], sm * dp_b[0] + cm * dp_b[1]])
        self.v = v_new
        self.yaw += self.w * dt + 0.5 * self.wd * dt * dt + jw * dt ** 3 / 6.0
        self.w += self.wd * dt + 0.5 * jw * dt * dt
        self.wd += jw * dt
        return self.state()


# ------------------------------------------------------------------------------------------------ the servo
class Servo:
    """The servo of one robot's commanded coordinates x (a rig's controlled vector u, or the part of it that is
    positions) in a compiled model: joint targets q = M x + c.

    Every physics step (`track`): the reference (r, rd) passes the setpoint generator (SetpointGenerator on the joint
    coordinates `jix`, PlanarBase on the base coordinates `bix` = (x, y, yaw)); the joint setpoint (q_sp, qd_sp,
    qdd_sp) = M (x_sp, xd_sp, xdd_sp) + c; the torque tau = kp (q_sp - q) + kd (qd_sp - qd) + bias (gravity, Coriolis)
    + M(q) qdd_sp (inertia feed-forward); then the output stage (Actuators.write). Coordinates of x that map to no
    joint (all-zero columns of M, e.g. a legged robot's walking command) are not servoed here."""

    def __init__(self, model, qadr, vadr, act: Actuators, M, c, kp, kd, dt, joint_lim: AL.ArmLimits | None,
                 jix=(), base: BaseLimits | None = None, bix=(), feedforward=True):
        self.m = model
        self.qadr, self.vadr = np.asarray(qadr, int), np.asarray(vadr, int)
        self.act = act
        self.M, self.c = np.asarray(M, float), np.asarray(c, float)
        self.kp, self.kd = np.asarray(kp, float), np.asarray(kd, float)
        self.dt = float(dt)
        self.jix, self.bix = np.asarray(jix, int), np.asarray(bix, int)
        self.n = self.M.shape[1]
        self.lim = joint_lim
        self.jl = SetpointGenerator(joint_lim, dt) if len(self.jix) else None
        self.base = PlanarBase(base, dt) if len(self.bix) else None
        self.ff = feedforward
        self.ready = False
        self._acc = np.zeros(model.nv)
        self._f = np.zeros(model.nv)
        self.x = np.zeros(self.n)
        self.xd = np.zeros(self.n)
        self.xdd = np.zeros(self.n)
        self.peak = dict(vel=np.zeros(self.n), acc=np.zeros(self.n))    # |setpoint| peaks (conformance)

    def reset(self, x, xd=None):
        """The setpoint generator at x (moving at xd), at rest in acceleration: after a teleport, at the start."""
        x = np.asarray(x, float)
        xd = np.zeros(self.n) if xd is None else np.asarray(xd, float)
        if self.jl is not None:
            self.jl.reset(x[self.jix], xd[self.jix])
        if self.base is not None:
            self.base.reset(x[self.bix], xd[self.bix])
        self.x, self.xd, self.xdd = x.copy(), xd.copy(), np.zeros(self.n)
        self.act.reset()
        self.ready = True

    def setpoint(self, r, rd):
        """one step of the setpoint generator towards (r, rd): (x_sp, xd_sp, xdd_sp)"""
        r, rd = np.asarray(r, float), np.asarray(rd, float)
        x, xd, xdd = r.copy(), rd.copy(), np.zeros(self.n)
        if self.jl is not None:
            q, qd, qdd = self.jl.step(r[self.jix], rd[self.jix])
            x[self.jix], xd[self.jix], xdd[self.jix] = q, qd, qdd
        if self.base is not None:
            q, qd, qdd = self.base.step(r[self.bix], rd[self.bix])
            x[self.bix], xd[self.bix], xdd[self.bix] = q, qd, qdd
        self.x, self.xd, self.xdd = x, xd, xdd
        np.maximum(self.peak["vel"], np.abs(xd), out=self.peak["vel"])
        np.maximum(self.peak["acc"], np.abs(xdd), out=self.peak["acc"])
        return x, xd, xdd

    def track(self, d, r, rd, extra_tau=None):
        """one physics step: setpoint, servo torque, output stage (writes d.ctrl of this servo's motors)"""
        if not self.ready:
            raise RuntimeError("servo not reset (rig.place / rig.sync first)")
        x, xd, xdd = self.setpoint(r, rd)
        q_sp, qd_sp, qdd_sp = self.M @ x + self.c, self.M @ xd, self.M @ xdd
        tau = self.kp * (q_sp - d.qpos[self.qadr]) + self.kd * (qd_sp - d.qvel[self.vadr]) + d.qfrc_bias[self.vadr]
        if self.ff:
            import mujoco as mj
            self._acc[:] = 0.0
            self._acc[self.vadr] = qdd_sp
            mj.mj_mulM(self.m, d, self._f, self._acc)
            tau = tau + self._f[self.vadr]
        if extra_tau is not None:
            tau = tau + extra_tau
        return self.act.write(d, tau)


def check_row(u, u_prev, u_prev2, LO, HI, VEL, ACC, dt, base: BaseLimits | None = None, tol=1e-6):
    """A target row of a controlled vector against the limits: the ranges, the per-step speeds (|du| <= VEL dt) and,
    given u_prev2, the accelerations (|second difference| <= ACC dt^2). base: the limits of a planar base at u[0:3]
    (x, y, yaw): its translation checked on the norm, or per axis in the robot's frame (rotated by u_prev's yaw).
    Returns None or the reason."""
    u, up = np.asarray(u, float), np.asarray(u_prev, float)
    LO, HI, VEL = np.asarray(LO, float), np.asarray(HI, float), np.asarray(VEL, float)
    if u.shape != LO.shape or not np.all(np.isfinite(u)):
        return f"a target must be {len(LO)} finite numbers"
    bad = (u < LO - 1e-9) | (u > HI + 1e-9)
    if bad.any():
        return f"outside the range at {np.nonzero(bad)[0].tolist()}"
    du = u - up
    dd = None if u_prev2 is None else du - (up - np.asarray(u_prev2, float))
    over = np.abs(du) > VEL * dt * (1 + tol) + 1e-12
    if base is not None:
        over[0:2] = False
        why = _base_problem(du[0:2], up[2], base.speed, base.mode, dt, tol)
        if why:
            return "the base speed limit"
    if over.any():
        return f"a per-step speed limit at {np.nonzero(over)[0].tolist()}"
    if dd is not None and ACC is not None:
        over = np.abs(dd) > np.asarray(ACC, float) * dt * dt * (1 + tol) + 1e-12
        if base is not None:
            over[0:2] = False
            if _base_problem(dd[0:2], up[2], base.accel, base.mode, dt * dt, tol):
                return "the base acceleration limit"
        if over.any():
            return f"an acceleration limit at {np.nonzero(over)[0].tolist()}"
    return None


def _base_problem(dxy, yaw, lim, mode, scale, tol):
    if mode != "axes":
        return math.hypot(*dxy) > float(np.max(lim)) * scale * (1 + tol) + 1e-12
    c, s = math.cos(yaw), math.sin(yaw)
    b = np.array([c * dxy[0] + s * dxy[1], -s * dxy[0] + c * dxy[1]])
    return bool(np.any(np.abs(b) > np.asarray(lim, float) * scale * (1 + tol) + 1e-12))


# ------------------------------------------------------------------------------------------------ rig layouts
def wheeled_layout(model, rig, decl: dict, phys_dt: float):
    """The servo of a rig with the wheeled humanoid's controlled vector u = [base x, y, yaw, lift, waist, arm 0..6]
    (bodies/wheeled_humanoid, galaxea_r1pro, tianji_marvin_pro): the joint coordinates (lift, waist, arm: those that
    move a joint) through SetpointGenerator with [limits.lift / waist / arm]'s speed, acceleration and jerk, the base
    through PlanarBase ([limits.base]; none when its kind is "absent"). Returns (servo, ACC: the per-coordinate
    acceleration limits for check_row, the base limits or None)."""
    L = decl["limits"]
    moves = np.any(np.abs(rig.M) > 0, axis=0)
    jix = [k for k in range(3, 12) if moves[k]]
    has_base = L["base"].get("kind") != "absent" and moves[0:3].all()
    base = BaseLimits.of(L["base"]) if has_base else None
    group = {3: "lift", 4: "waist"}
    q = lambda k, key: (_arr(L[group.get(k, "arm")].get(key), 7) if group.get(k, "arm") == "arm"
                        else _arr(L[group[k]].get(key)))
    acc = np.full(12, 0.0)
    jerk = np.full(12, 0.0)
    for k in range(3, 12):
        a, j = q(k, "accel_rad_s2"), q(k, "jerk_rad_s3")
        acc[k] = np.inf if a is None else (a[k - 5] if k >= 5 else a[0])
        jerk[k] = np.inf if j is None else (j[k - 5] if k >= 5 else j[0])
    if base is not None:
        acc[0:2] = base.accel if base.mode == "axes" else float(base.accel)
        acc[2] = base.yaw_accel
    ji = np.array(jix, int)
    fin = lambda x: None if not np.all(np.isfinite(x)) else x
    lim = AL.ArmLimits(decl["body"]["name"], decl["body"]["title"] + " [u]", rig.LO[ji], rig.HI[ji], rig.VEL[ji],
                       fin(acc[ji]), fin(jerk[ji]), np.full(len(ji), np.inf), None, dict(decl.get("sources", {})))
    act = Actuators(model, rig.aid, rig.vadr, rig.tau_lim, phys_dt)
    servo = Servo(model, rig.qadr, rig.vadr, act, rig.M, rig.c, rig.kp, rig.kd, phys_dt, lim, jix=jix, base=base,
                  bix=(0, 1, 2) if base is not None else ())
    return servo, acc, base


def legged_layout(model, rig, decl: dict, phys_dt: float, upper_keys: list, leg_keys: list, planar: dict | None):
    """The servos of a legged rig (bodies/unitree_g1, unitree_h1): the upper body's commanded coordinates (u[3:]:
    waist and arm joints) through SetpointGenerator at the joints' speed limits (Unitree publishes no acceleration
    or jerk: none declared, the motor curves bound them), the planar copy's base (planar: the [walk.planning] model)
    through PlanarBase; the output stages with the motors' torque-speed curves ([motors]: upper_keys / leg_keys name
    each joint's [motors.assign] entry; None = no curve). Returns (upper servo, legs Actuators or None, ACC)."""
    moves = np.any(np.abs(rig.M) > 0, axis=0)
    jix = [k for k in range(3, 12) if moves[k]]
    ji = np.array(jix, int)
    lim = AL.ArmLimits(decl["body"]["name"], decl["body"]["title"] + " [u]", rig.LO[ji], rig.HI[ji], rig.VEL[ji],
                       None, None, np.full(len(ji), np.inf), None, dict(decl.get("sources", {})))
    base = None
    if planar is not None:
        base = BaseLimits(float(planar["speed_m_s"]), float(planar["accel_m_s2"]), 25.0 * float(planar["accel_m_s2"]),
                          float(planar["yaw_rate_rad_s"]), float(planar["yaw_accel_rad_s2"]),
                          25.0 * float(planar["yaw_accel_rad_s2"]), "norm")
    env = unitree_envelope(decl, upper_keys)
    act = Actuators(model, rig.aid, rig.vadr, rig.tau_lim, phys_dt, envelope=env)
    servo = Servo(model, rig.qadr, rig.vadr, act, rig.M, rig.c, rig.kp, rig.kd, phys_dt, lim, jix=jix, base=base,
                  bix=(0, 1, 2) if base is not None else ())
    legs = None
    if leg_keys:
        legs = Actuators(model, rig.laid, rig.lvadr, rig.ltau, phys_dt, envelope=unitree_envelope(decl, leg_keys))
    acc = np.full(12, np.inf)
    if base is not None:
        acc[0:2], acc[2] = base.accel, base.yaw_accel
    return servo, legs, acc


# ------------------------------------------------------------------------------------------------ walking command
class WalkCommand:
    """A legged robot's walking command (vx, vy, wz in the robot's frame): clipped to the range the real robot's
    deployment accepts ([limits.walk] command_max: Unitree's joystick limits) and changed by at most command_accel
    per second."""

    def __init__(self, L: dict, dt: float):
        self.max = np.asarray(L["command_max"], float)
        self.step_max = np.asarray(L["command_accel"], float) * float(dt)
        self.cmd = np.zeros(3)

    def reset(self):
        self.cmd = np.zeros(3)

    def __call__(self, req):
        req = np.clip(np.asarray(req, float), -self.max, self.max)
        self.cmd = self.cmd + np.clip(req - self.cmd, -self.step_max, self.step_max)
        return self.cmd
