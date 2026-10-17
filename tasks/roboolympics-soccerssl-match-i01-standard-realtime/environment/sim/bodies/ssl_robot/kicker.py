"""The SSL robot's kicker (body.toml [limits.kicker]): a capacitor, a break beam and an impulse model.

Real robots (S1 2.2-2.3, 3.2): a charger fills the capacitors (0 -> 250 V in 2 s; after a strong kick 0.5 s); a kick
discharges them through a coil whose plunger hits the ball (flat) or a shovel under it (chip, 45 deg); an infrared
break beam across the dribbler's sides fires an armed kick the moment the ball arrives ("Relying on vision data for
this purpose is not precise enough", S1 2.3).

Here:
  * the capacitor is a stored-energy fraction c in [0, 1] that fills at 1 / charge_full_s per second; the kick speed
    grows with the coil current, i.e. with the voltage (S1 3.2: "The kick strength is directly proportional to the
    current"), so a kick at speed v needs c >= (v / v_max)^2 (the voltage v / v_max of the full one) and uses
    0.25 (v / v_max)^2 of the full energy (a kick at the maximum speed takes recharge_after_max_s = 0.5 s to refill,
    and the next maximum kick waits for it; a 6 m/s kick right after one is possible);
  * the break beam is a ray between two sites on the dribbler's sides (mujoco.mj_ray): anything that crosses it
    blocks it, as on the real robot;
  * a discharge whose beam is blocked by a free body lighter than 0.1 kg (the ball) sets that body's velocity to the
    robot's velocity at that point plus the kick speed along the robot's heading (rotated by the direction error),
    elevated by the chip angle for a chip; the speed error is Gaussian, sigma = speed_sigma_rel x the speed; the
    ball leaves without spin. A discharge with nothing in the beam (an immediate kick, armed_for = 0, with no ball)
    still uses the energy, as the real plunger does.
numpy + mujoco.
"""
from __future__ import annotations

import math

import numpy as np

BALL_MAX_KG = 0.1


class Kicker:
    def __init__(self, L: dict, rng: np.random.Generator):
        self.L = L
        self.flat_max = float(L["flat_speed_max_m_s"])
        self.chip_max = float(L["chip_speed_max_m_s"])
        self.chip_angle = math.radians(float(L["chip_angle_deg"]))
        self.sigma_rel = float(L["speed_sigma_rel"])
        self.sigma_dir = math.radians(float(L["direction_sigma_deg"]))
        self.rate = 1.0 / float(L["charge_full_s"])
        self.use_max = float(L["recharge_after_max_s"]) * self.rate        # 0.25
        self.rng = rng
        self.charge = 1.0
        self.armed = None            # dict(speed, mode, until) while armed
        self.pending = None          # an immediate kick to fire at the next physics step

    def need(self, speed, mode):
        """the stored-energy fraction a kick at this speed needs (the voltage threshold)"""
        vmax = self.flat_max if mode == "flat" else self.chip_max
        return (speed / vmax) ** 2

    def use(self, speed, mode):
        """the stored-energy fraction a kick at this speed uses"""
        return self.use_max * self.need(speed, mode)

    def wait_s(self, need):
        return max(0.0, (need - self.charge) / self.rate)

    def command(self, speed, mode, armed_for, now):
        """the kick skill: 'ok', 'clipped' (speed beyond the machine's maximum: clipped to it), 'kicker_not_ready',
        'disarmed' (speed 0); raises ValueError on a bad mode"""
        if mode not in ("flat", "chip"):
            raise ValueError(f"mode must be 'flat' or 'chip', not {mode!r}")
        speed = float(speed)
        if not math.isfinite(speed) or speed < 0:
            raise ValueError("speed must be a finite number >= 0")
        vmax = self.flat_max if mode == "flat" else self.chip_max
        status = "ok"
        if speed > vmax:
            speed, status = vmax, "clipped"
        if speed == 0.0:
            self.armed, self.pending = None, None
            return "disarmed", dict(speed=0.0)
        need = self.need(speed, mode)
        if self.charge + 1e-12 < need:
            return "kicker_not_ready", dict(wait_s=round(self.wait_s(need), 3), charge=round(self.charge, 4))
        armed_for = float(armed_for or 0.0)
        if armed_for > 0.0:
            self.armed, self.pending = dict(speed=speed, mode=mode, until=now + armed_for), None
        else:
            self.armed, self.pending = None, dict(speed=speed, mode=mode)
        return status, dict(speed=speed)

    def charge_step(self, dt):
        self.charge = min(1.0, self.charge + self.rate * dt)

    def fire(self, model, data, robot_body, blocker_body, heading, speed, mode):
        """discharge: use the energy; kick the blocking body if it is a ball. Returns the event's fields."""
        self.charge = max(0.0, self.charge - self.use(speed, mode))
        out = dict(mode=mode, speed_cmd=round(speed, 4), ball=False)
        b = int(blocker_body)
        if b < 0 or model.body_mass[b] > BALL_MAX_KG or model.body_jntnum[b] != 1:
            return out
        j = model.body_jntadr[b]
        import mujoco as mj
        if model.jnt_type[j] != mj.mjtJoint.mjJNT_FREE:
            return out
        s = speed * (1.0 + self.sigma_rel * float(self.rng.standard_normal()))
        s = max(0.0, s)
        yaw = heading + self.sigma_dir * float(self.rng.standard_normal())
        elev = self.chip_angle if mode == "chip" else 0.0
        v_rel = s * np.array([math.cos(elev) * math.cos(yaw), math.cos(elev) * math.sin(yaw), math.sin(elev)])
        # the robot's velocity at the ball (its planar joints: x, y, yaw; the ball's centre relative to the robot)
        dof = model.jnt_dofadr[j]
        bp = data.xpos[b]
        rp = data.xpos[robot_body]
        res = np.zeros(6)
        import mujoco as mj2
        mj2.mj_objectVelocity(model, data, mj2.mjtObj.mjOBJ_BODY, robot_body, res, 0)   # world frame: [w, v]
        w, v = res[0:3], res[3:6]
        v_at = v + np.cross(w, bp - rp)
        v_at[2] = 0.0
        data.qvel[dof:dof + 3] = v_at + v_rel
        data.qvel[dof + 3:dof + 6] = 0.0
        out.update(ball=True, speed=round(s, 4), dir_err_deg=round(math.degrees(yaw - heading), 3),
                   ball_body=b, v_ball=np.round(data.qvel[dof:dof + 3], 4).tolist())
        return out
