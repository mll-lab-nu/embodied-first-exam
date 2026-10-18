"""juggling-feet (keepie-uppie with the feet only, a size-5 ball from the hand, ten foot strikes in a row): the referee
says no to holding the ball, to dropping it on the ground, to a ball that only bounces off a still foot, to strikes that
do not send it a ball's diameter up (or above the knee), to the shin, the thigh, the trunk, the head and the hands, to
a ball trapped between the feet, to a ball resting on a foot, to a re-grip, to leaving the grid and to a fall; yes to
ten real strikes of the right foot.

The positive is an INJECTION, because the G1 has no single-leg balance (no built-in gait stands on one leg). Real: the
right hand lets go of the ball (the drop); every touch is a real contact of the ball with the right foot, and the ball's
speed comes from the foot: the robot's own motors (a `lowcmd` row, hip and knee on an inverse-kinematics stroke that
moves the toe straight up at 0.8 m/s through the contact, the ankle pointed) strike it, and the referee measures in
and out speeds of about 3 m/s. Injected: (1) the support: the pelvis is put back where it stands, at rest, after every
control step (a "ghost" standing leg); (2) the aim: after the drop the ball is put 0.25 m above the toe, falling, and
each time a touch is over and the ball is off the foot it is put back over the toe at its height, its vertical
speed kept, its horizontal speed (about 0.1 m/s) and spin cleared. On the G1 a falling ball meets the top of the foot
clear of the lower leg's collision hull only on its front 2-3 cm, and there the way it leaves is very sensitive to where
it lands (5 mm farther forward, over the toe's edge, sends it off at 0.4 m/s): a closed-loop strike that follows the
ball with the foot and chooses the strike point from the ball's drift was tried and lost the ball after two touches.
"""
import numpy as np

import mujoco

from rfo.testing import act, hold, make, move_robot, verdict

FAMILY = "juggling-feet"
R = 0.11
G = 9.81
POSE = (-1.5, 1.0, 0.5)          # the right hip pitch, knee and ankle pitch at the contact: thigh up, shin forward,
#                                  the foot pointed (the ankle at its 0.52 rad limit), its top level
TOE = 0.137                      # m: the point struck, ahead of the ankle along the foot (the top, 3 mm from the toe)


def minjerk(u):
    u = min(max(u, 0.0), 1.0)
    return 10 * u ** 3 - 15 * u ** 4 + 6 * u ** 5


class Leg:
    """The right leg's stroke: hip and knee for the toe point moved straight up by delta (x kept, ankle fixed)."""

    def __init__(self, w, toe=TOE, pose=POSE, D=0.06):
        self.w, self.D, self.pose = w, D, pose
        m, r = w.m, w.robot
        J = {n: i for i, n in enumerate(w.L.JOINTS)}
        self.iH, self.iK, self.iA = J["right_hip_pitch_joint"], J["right_knee_joint"], J["right_ankle_pitch_joint"]
        self.foot = m.body("right_ankle_roll_link").id
        self.p_toe = np.array([toe, 0.0, 0.002])
        self.dd = mujoco.MjData(m)
        self.base = w.d.qpos.copy()
        self.p0 = self.toe(pose[0], pose[1])
        dzs = np.linspace(-0.08, 0.08, 33)
        sol = {}
        for order in (range(16, 33), range(16, -1, -1)):          # continuation from the pose, both ways
            h, k = pose[0], pose[1]
            for i in order:
                for _ in range(60):
                    p = self.toe(h, k)
                    e = np.array([p[0] - self.p0[0], p[2] - self.p0[2] - dzs[i]])
                    if np.abs(e).max() < 1e-7:
                        break
                    Jm = np.zeros((2, 2))
                    for j, (dh, dk) in enumerate(((1e-6, 0.0), (0.0, 1e-6))):
                        p2 = self.toe(h + dh, k + dk)
                        Jm[:, j] = [(p2[0] - p[0]) / 1e-6, (p2[2] - p[2]) / 1e-6]
                    s = np.clip(np.linalg.lstsq(Jm, -e, rcond=None)[0], -0.05, 0.05)
                    h, k = h + s[0], k + s[1]
                assert np.abs(e).max() < 1e-4, (dzs[i], e)
                sol[i] = (dzs[i], h, k)
        self.tab = np.array([sol[i] for i in range(33)])
        self.dh = np.gradient(self.tab[:, 1], self.tab[:, 0])
        self.dk = np.gradient(self.tab[:, 2], self.tab[:, 0])

    def toe(self, h, k):
        r, dd = self.w.robot, self.dd
        dd.qpos[:] = self.base
        dd.qpos[r.qadr[[self.iH, self.iK, self.iA]]] = h, k, self.pose[2]
        mujoco.mj_kinematics(self.w.m, dd)
        return dd.xpos[self.foot] + dd.xmat[self.foot].reshape(3, 3) @ self.p_toe

    def q(self, delta, rate=0.0):
        r = self.w.robot
        q, dq = r.rest.copy(), np.zeros(len(r.rest))
        t = self.tab
        q[self.iH], q[self.iK], q[self.iA] = np.interp(delta, t[:, 0], t[:, 1]), np.interp(delta, t[:, 0], t[:, 2]), \
            self.pose[2]
        dq[self.iH], dq[self.iK] = np.interp(delta, t[:, 0], self.dh) * rate, np.interp(delta, t[:, 0], self.dk) * rate
        return q, dq


def juggle(w, A, vf=0.8, first=0.25, toe=TOE, strike=True, reaim=True, drop_at=1.0, after_drop=None, hook=None):
    """Raise the right leg (pelvis held: the injected support) holding the ball, drop it at drop_at, put it `first`
    above the toe, then strike it each time it falls (a min-jerk stroke of 2D peaking at vf at the contact), re-aiming
    it after each counted touch (see the docstring). strike=False: the foot stays still (the passive case)."""
    w.reset()
    r, d = w.robot, w.d
    leg = Leg(w, toe=toe)
    D = leg.D
    T = 2 * D * 1.875 / vf
    kp, kd = r.kp_max.copy(), np.minimum(2 * r.kd0, r.kd_max)
    kp[:12], kd[:12] = np.minimum(kp[:12], 900.0), np.minimum(r.kd_max[:12], 20.0)
    pin = d.qpos[r.fq:r.fq + 7].copy()
    q_start = d.qpos[r.qadr].copy()
    q_low, _ = leg.q(-D)
    t0, k, spot, placed = None, 0, None, False
    n_set = int(round(drop_at / w.CONTROL_DT))
    while not w.done:
        grip = 1.0 if w.k < n_set else 0.0
        if w.k < n_set:                                     # the leg up, the ball held
            q, dq = q_start + minjerk(w.k / (0.9 * n_set)) * (q_low - q_start), np.zeros(len(q_start))
        else:
            delta, rate = -D, 0.0
            if t0 is not None:
                u = (w.t - t0) / T
                if u <= 1:
                    delta = -D + 2 * D * minjerk(u)
                    rate = 2 * D / T * (30 * u ** 2 - 60 * u ** 3 + 30 * u ** 4)
                else:                                       # back down in 0.25 s
                    u2 = min(1.0, (u - 1) * T / 0.25)
                    delta = D - 2 * D * minjerk(u2)
                    if u2 >= 1:
                        t0 = None
            q, dq = leg.q(delta, rate)
        act(w, A, "lowcmd", np.r_[q, dq, np.zeros(len(q)), kp, kd, 0.0, grip])
        d.qpos[r.fq:r.fq + 7] = pin                         # the injected support
        d.qvel[r.fv:r.fv + 6] = 0.0
        if w.done:
            break
        tr = w.task.trackers
        if tr["dropped"] is None:
            continue
        if not placed:
            placed = True
            spot = leg.toe(*leg.tab[16, 1:])
            if after_drop is not None:                      # a negative's own placement instead
                after_drop(w, spot)
                strike = reaim = False
                continue
            w.launch("ball", (spot[0], spot[1], spot[2] + R + first), (0.0, 0.0, 0.0))
            continue
        if hook is not None:                                # a negative's own action after the placement
            hook(w)
            continue
        bz, bv = float(w.pos("ball")[2]), float(w.vel("ball")[2])
        zc = spot[2] + R
        if strike and t0 is None and bv < 0:                # time the stroke's middle to the ball's arrival
            tc = (bv + np.sqrt(max(bv * bv + 2 * G * (bz - zc), 0.0))) / G
            if tc <= T / 2:
                t0 = w.t + tc - T / 2
        if reaim and tr["touch"].count > k and not w.ref.touching(w.task.ball, w.ref.robot_mask):
            k = tr["touch"].count                           # a touch is over and the ball is off the foot
            w.put("ball", (spot[0], spot[1], bz), vel=(0.0, 0.0, bv))


def drop_and(w, A, place, t=0.5):
    """Stand, drop the ball at t (real), then `place(w)` it (a launch) and stand to the end."""
    w.reset()
    hold(w, A, t, grips=[0, 1])
    hold(w, A, 0.02, grips=[0, 0])
    place(w)
    hold(w, A, grips=[0, 0])
    return verdict(w)


def main():
    w, A = make(FAMILY)
    p, m = w.task.p, w.m
    assert abs(m.geom("ball").size[0] - 0.11) < 1e-9 and abs(m.body("ball").mass[0] - 0.43) < 1e-9
    assert w.held["right"] == "ball" and p["touches"] == 10 and w.task.time_limit_s == 60.0

    hold(w, A, grips=[0, 1])                                               # nop: the ball stays in the hand
    v = verdict(w)
    assert v["failed"] == "time" and v["stages"] == [], v

    juggle(w, A)                                                           # positive (injection, see the docstring)
    v = verdict(w)
    assert v["success"] and v["stages"] == [f"touch {i + 1}" for i in range(10)], v
    st = [e for e in w.ref.events if e["ev"] == "stage"]
    assert all(e["foot"] == "right_foot" and e["speed_out"] >= p["touch_gain"] * e["speed_in"] for e in st), st
    sha, t_ok = w.state_sha(), w.t
    speeds = [(e["speed_in"], e["speed_out"]) for e in st]
    juggle(w, A)
    assert w.state_sha() == sha                                            # the same run again: the same state

    juggle(w, A, strike=False, first=1.2)                                  # a still foot: the ball only bounces
    v = verdict(w)
    bounce = [e for e in w.ref.events if e["ev"] == "bounce"]
    assert v["stages"] == [] and bounce and bounce[0]["speed_out"] < p["touch_gain"] * bounce[0]["speed_in"], (v, bounce)
    assert v["failed"] in ("the ball was touched again before it had risen enough", "the ball touched the ground",
                           "the ball touched a part other than a foot"), v
    passive = bounce[0]["speed_out"] / bounce[0]["speed_in"]

    juggle(w, A, vf=0.5)                                                   # strikes too soft: not a diameter up
    v = verdict(w)
    assert v["failed"] == "the ball was touched again before it had risen enough" and v["stages"] == [], v

    w2, A2 = make(FAMILY, knee_z_m=1.0)                                    # the height rule binds (a knee at 1 m)
    juggle(w2, A2)
    v = verdict(w2)
    assert v["failed"] == "the ball was touched again before it had risen enough" and v["stages"] == [], v

    def on_leg(b0, b1, off):                                               # the ball dropped onto a part of the leg
        return lambda w, spot: w.launch("ball", (w.pos(b0) + w.pos(b1)) / 2 + off, (0.0, 0.0, -1.0))
    for part, b0, b1, off in (("right_shin", "right_knee_link", "right_ankle_pitch_link", (0.10, 0.0, 0.16)),
                              ("right_thigh", "right_hip_pitch_link", "right_knee_link", (0.09, 0.0, 0.20))):
        juggle(w, A, after_drop=on_leg(b0, b1, off))
        v = verdict(w)
        assert v["failed"] == "the ball touched a part other than a foot" and part in w.ref.events[-1]["parts"], \
            (part, v, w.ref.events[-1])
        if part == "right_shin":
            assert w.ref.events[-1].get("at_foot_frame", [0, 0, 0])[2] > p["instep_z_m"], w.ref.events[-1]

    def rest_on_toe(w, spot):                                              # the ball laid on the still toe
        w.launch("ball", (spot[0] - 0.022, spot[1], spot[2] + R + 0.001), (0.0, 0.0, 0.0))
    juggle(w, A, after_drop=rest_on_toe)
    v = verdict(w)
    assert v["failed"] in ("the ball was carried", "the ball was touched again before it had risen enough") \
        and v["stages"] == [], v                                           # resting, or small hops on the foot
    rest_end = v["failed"]

    w3, A3 = make(FAMILY, carry_s=0.002)                                   # below a real strike's contact time
    juggle(w3, A3)
    assert verdict(w3)["failed"] == "the ball was carried", verdict(w3)

    sent = []

    def to_left_hand(w):                                                   # a foot touch, then the left hand while
        tr = w.task.trackers                                               # it is judged (inside the release grace)
        if tr["touch"].count == 1 and tr["pending"] and not w.ref.touching(w.task.ball, w.ref.robot_mask) \
                and not sent:
            sent.append(w.t)
            w.launch("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.0, 0.125, 0.0], (0.0, -3.0, 0.0))
    juggle(w, A, after_drop=lambda w, spot: w.launch("ball", spot + [0.0, 0.0, R + 0.005], (0.0, 0.0, -2.0)),
           hook=to_left_hand)
    v = verdict(w)
    ev = w.ref.events[-1]
    assert v["failed"] == "handball" and ev.get("during_touch") and ev["t"] - w.task.trackers["dropped"] < \
        p["release_grace_s"], (v, ev)

    w.reset()                                                              # the arrival speed is kept up to date
    hold(w, A, 0.3, grips=[0, 1])                                          # before the drop too
    assert abs(w.task.trackers["speed"] - float(np.linalg.norm(w.vel("ball")))) < 0.05, w.task.trackers["speed"]

    w.reset()                                                              # dropped: straight to the ground
    hold(w, A, 0.5, grips=[0, 1]); hold(w, A, grips=[0, 0])
    v = verdict(w)
    assert v["failed"] == "the ball touched the ground" and v["stages"] == [], v

    v = drop_and(w, A, lambda w: w.launch("ball", w.d.site_xpos[w.robot.palm["left"]] + [0.0, 0.60, 0.25],
                                          (0.0, -2.5, 0.0)))               # onto the left hand after the drop
    assert v["failed"] == "handball" and "left_hand" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])

    for part, body, off, vel in (("torso", "torso_link", (0.60, 0.0, 0.12), (-3.5, 0.0, 0.5)),       # the chest
                                 ("head", "torso_link", (0.0, 0.0, 0.95), (0.0, 0.0, -1.0)),         # the head
                                 ("right_thigh", "right_hip_pitch_link", (0.45, 0.0, -0.12), (-3.0, 0.0, 0.3)),
                                 ("left_shin", "left_knee_link", (0.50, 0.0, -0.05), (-3.0, 0.0, 0.3))):
        v = drop_and(w, A, lambda w: w.launch("ball", w.pos(body) + off, vel))
        assert v["failed"] == "the ball touched a part other than a foot" and part in w.ref.events[-1]["parts"], \
            (part, v, w.ref.events[-1])

    v = drop_and(w, A, lambda w: w.launch("ball", (0.05, 0.0, 0.17), (0.0, 0.0, -0.5)))    # between the feet
    assert v["failed"] == "the ball touched a part other than a foot" and \
        w.ref.events[-1]["at_foot_frame"][2] > p["instep_z_m"], (v, w.ref.events[-1])     # (standing: the shins)
    w4, A4 = make(FAMILY, instep_z_m=0.25)                                 # the lower legs counted up to 0.25 m:
    v = drop_and(w4, A4, lambda w: w.launch("ball", (0.05, 0.0, 0.17), (0.0, 0.0, -0.5)))  # both feet at once
    assert v["failed"] == "the ball was trapped between the feet", (v, w4.ref.events[-1])

    w.reset()                                                              # the ball cannot be gripped again
    hold(w, A, 0.5, grips=[0, 1]); hold(w, A, 0.05, grips=[0, 0])
    w.put("ball", w.d.site_xpos[w.robot.palm["right"]] + [0.0, 0.0, 0.0]); hold(w, A, 0.02, grips=[0, 1])
    assert w.held["right"] is None, w.held

    w.reset(); hold(w, A, 0.2, grips=[0, 1]); move_robot(w, x=2.6, held=True); hold(w, A, 0.1, grips=[0, 1])
    assert verdict(w)["failed"] == "stepped out of the grid", verdict(w)                       # out of the grid

    w.reset(); hold(w, A, 0.2, grips=[0, 1]); move_robot(w, z=0.30); hold(w, A, 0.5, grips=[0, 1])   # on the ground
    assert verdict(w)["failed"] == "fell", verdict(w)
    print(f"injection: ten right-foot strikes at t = {t_ok:.2f} s, speed in/out {speeds[0]} ... {speeds[-1]} m/s; "
          f"a still foot returns {passive:.2f} of the speed (not counted); a ball laid on the toe: {rest_end}")
    print(f"PASS {FAMILY}")


if __name__ == "__main__":
    main()
