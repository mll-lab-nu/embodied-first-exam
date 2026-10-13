"""pole-vault (TR 28: the sunken box, the 4.5 m bar at 2.00 m on its pegs, the 5 x 5 x 0.8 m mat, a rigid 4 m pole,
the H1-2): the referee says no to standing still, to walking on to the mat with the pole, to a jump over the bar
without the pole, to going round the uprights and under the bar, to letting go too early (down on the mat before the
bar), to a vault after which the pole falls onto the bar, to moving the hand up the pole in the air, and to a hand
that rests on the bar.

The positive is an INJECTION for the run-up, the plant and the swing up, and real from there: the robot is held in
the air by hand while its own motors stretch its right arm up and draw its legs up; the pole is put through its
right palm by hand, 3.9 m from the tip, with the tip on the bottom of the box and the pole 20 degrees short of
vertical, and gripped (World.grab; the palm is within the grip's reach); robot and pole are given the velocity of a
turn about the tip (the hand at 3.0 m/s). Everything after that is physics and the action interface: the robot
really hangs on the planted pole (its weight presses the tip into the box), the pole really turns over the vertical,
the robot passes over the bar without touching it, opens its grip (the grip action) and lands on the mat. At the
release the pole is pushed back by hand (1.5 rad/s about its tip), as a vaulter's arm does; without that push the
rigid pole falls onto the bar, which is a failure (shown below)."""
import math

import mujoco
import numpy as np
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

ARM_UP = {"shoulder_pitch_joint": -3.14, "shoulder_roll_joint": 0.0, "shoulder_yaw_joint": 0.0, "elbow_pitch_joint": 1.51,
          "elbow_roll_joint": 0.0, "wrist_pitch_joint": 0.0, "wrist_yaw_joint": 0.0}
TIP = np.array([-0.125, 0.0, -0.175])        # the pole's tip at the plant: on the box's bottom, just before the stop board


def targets(w, tuck):
    """Joint targets: the right arm stretched up, the legs drawn up (tuck) or in the stance."""
    q = np.r_[w.robot.stance, w.robot.rest[12:]].copy()
    for j, v in ARM_UP.items():
        q[w.L.JOINTS.index("right_" + j)] = v
    if tuck:
        for s in (0, 6):
            q[s + 1], q[s + 3] = tuck
    return q


def set_pole(w, tip, top, omega_y=0.0):
    """The pole through `top` with its tip at `tip`, turning about its tip at omega_y (rad/s, forwards)."""
    u = (tip - top) / np.linalg.norm(tip - top)
    v = np.cross([1.0, 0.0, 0.0], u)
    quat = np.zeros(4)
    mujoco.mju_axisAngle2Quat(quat, v / np.linalg.norm(v), np.arctan2(np.linalg.norm(v), u[0]))
    L = w.task.p["pole_length_m"]
    com = tip - (L / 2) * u
    R = np.zeros(9); mujoco.mju_quat2Mat(R, quat); R = R.reshape(3, 3)
    om = np.array([0.0, omega_y, 0.0])
    w.put("pole", com, quat, vel=np.cross(om, com - tip), angvel=R.T @ om)
    return u


def on_the_pole(w, A, grip=3.9, before_deg=20.0, speed=2.5, tuck=(-2.8, 2.05), y=0.0, with_pole=True, centred=True):
    """Injected: the robot held in the air by hand (its base pose reset at every step) while its own motors bring the
    right arm up and draw the legs up; then the pole put through its right palm, `grip` m from the tip, the tip in
    the box and the pole `before_deg` short of vertical, and gripped; robot and pole turning about the tip so that the
    hand moves forwards at `speed`."""
    hold(w, A, 0.1, grips=[0, 0]); w.pin("pole", (-8.0, 3.0, 0.05))
    a = np.radians(before_deg)
    top = TIP + grip * np.array([-np.sin(a), 0.0, np.cos(a)]) + np.array([0.0, y, 0.0])
    q = targets(w, tuck)
    base = None
    for k in range(120):
        if base is None or k % 20 == 0:                      # where the pelvis must be for the palm to be at `top`
            rel = w.d.site_xpos[w.robot.palm["right"]] - w.d.qpos[w.robot.fq:w.robot.fq + 3]
            if centred:                                      # ... with the robot's centre of mass in the pole's plane
                top[1] = y + float(w.d.site_xpos[w.robot.palm["right"]][1] - w.com()[1])
            base = top - rel
        move_robot(w, x=base[0], y=base[1], z=base[2], yaw=0.0)
        w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
        act(w, A, "joints", np.r_[q, 0, 0])
    rel = w.d.site_xpos[w.robot.palm["right"]] - w.d.qpos[w.robot.fq:w.robot.fq + 3]
    move_robot(w, *(top - rel), yaw=0.0); w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
    mujoco.mj_forward(w.m, w.d)
    if with_pole:
        w.unpin("pole")
        set_pole(w, TIP + np.array([0.0, y, 0.0]), w.d.site_xpos[w.robot.palm["right"]].copy(), omega_y=speed / grip)
        mujoco.mj_forward(w.m, w.d)
        gap, _ = w._grip_gap("right", "pole")
        assert gap <= 0.035, gap                             # within the grip's reach: a legal grip
        w.grab("right", "pole")
    kick_robot(w, speed * np.array([np.cos(a), 0.0, np.sin(a)]))
    return q


def vault(w, A, release_x=0.95, push_back=1.5, **kw):
    """The injected hang on the planted pole, then the action interface: the pose held, the grip opened when the
    pelvis passes release_x; at that moment the pole is pushed back by hand (push_back rad/s about its tip; None: not)."""
    w.reset()
    q = on_the_pole(w, A, **kw)
    low, released = 9.0, False
    while not w.done:
        x = w.pelvis()[0]
        if not released and release_x is not None and x > release_x:
            released = True
            if push_back is not None and w.holder("pole"):
                R = w.d.xmat[w.task.pole_id].reshape(3, 3)
                tip = w.task.tip(w)
                set_pole(w, tip, tip - R[:, 0], omega_y=-push_back)
        act(w, A, "joints", np.r_[q, 0, 0 if released else 1])
        if abs(w.pelvis()[0] - w.task.bar["x"]) < 0.15:
            low = min(low, float(w.ref.robot_extent()[0][2]))
    return low


def ballistic(w, A, vel, x, y=0.0, z=None, tuck=None):
    """Injected flight without the pole: the pole put down, the robot put at (x, y), standing, and given `vel`."""
    w.reset(); hold(w, A, 0.1, grips=[0, 0]); w.pin("pole", (-8.0, 3.0, 0.05))
    move_robot(w, x=x, y=y, z=w.robot.stand_z if z is None else z); hold(w, A, 0.3, grips=[0, 0])
    kick_robot(w, vel)
    q = targets(w, tuck)
    q[12:] = w.robot.rest[12:]
    while not w.done:
        act(w, A, "joints", np.r_[q, 0, 0])


def main():
    from rfo.tasks import pole_vault as PV
    w, A = make("pole-vault")
    T, p = w.task, w.task.p
    assert (p["bar_height_m"], p["bar_length_m"], p["peg_gap_m"], p["bar_mass_kg"]) == (2.0, 4.5, 4.3, 2.25)
    assert (p["mat_length_m"], p["mat_width_m"], p["mat_height_m"]) == (5.0, 5.0, 0.8) and 0.0 <= p["bar_setback_m"] <= 0.8
    assert abs(PV.BOX_FOOT_X + 0.0999) < 1e-3 and abs(PV.BOX_FRONT_X + 1.0797) < 1e-3 and PV.BOX_DEPTH == 0.20
    assert abs(math.hypot(PV.BOX_FOOT_X - PV.BOX_FRONT_X, PV.BOX_DEPTH) - 1.0) < 1e-9          # the bottom: 1.00 m long
    bar = w.m.geom("bar").id
    assert abs(w.d.geom_xpos[bar][2] + w.m.geom_size[bar][0] - 2.0) < 1e-6                    # the bar's upper side
    assert abs(w.m.body_subtreemass[w.m.body("pole").id] - 2.0) < 1e-3 and abs(w.m.body_subtreemass[w.m.body("bar").id] - 2.25) < 1e-6
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    assert w.holder("pole") == ["right"] and abs(w.pos("bar")[2] - T.bar["rest_z"]) < 0.002   # ... the pole held, the bar up
    # the box is sunk: a pole let go with its tip over the box comes to rest with the tip 0.1 m below the runway
    w.reset(); hold(w, A, 0.1, grips=[0, 0]); set_pole(w, np.array([-0.5, 0.0, 0.05]), np.array([-2.0, 0.0, 1.4]))
    deep, touched = 0.0, False
    for _ in range(40):
        hold(w, A, 0.01, grips=[0, 0])
        deep, touched = min(deep, float(T.tip(w)[2])), touched or w.ref.touching(T.pole_mask, T.box_mask)
    assert deep < -0.08 and touched and not T.planted(w, w.ref), (deep, touched)             # (not gripped: not "planted")
    low = vault(w, A, speed=3.0)                                                              # positive
    v = verdict(w)
    assert v["success"] and v["stages"] == T.stages and v["metrics"]["support_s"] >= 1.0 and low > 2.0, (v, low)
    assert abs(w.pos("bar")[2] - T.bar["rest_z"]) < 0.002 and abs(w.pos("bar")[0] - T.bar["x"]) < 0.002   # the bar untouched
    land = next(e for e in w.ref.events if e["ev"] == "landing")
    assert land["on_the_mat"] and land["pole_in_hand"] == [], land
    print("  vault:", v["metrics"], "lowest point of the body over the bar %.2f m" % low, land)
    sha = w.state_sha()
    vault(w, A, speed=3.0)
    assert w.state_sha() == sha                                                               # determinism
    vault(w, A, speed=3.0, push_back=None)                               # the pole not pushed back: it falls onto the bar
    v = verdict(w)
    assert v["failed"] == "the bar did not stay on its pegs" and v["stages"] == ["plant", "take-off", "clearance"], v
    w.reset(); q = on_the_pole(w, A, speed=3.0)                          # let go before the bar and drop (the forward
    while not w.done and w.pelvis()[0] < 0.3:                            # speed taken away by hand): down on the mat
        act(w, A, "joints", np.r_[q, 0, 1])                              # before the bar
    w.d.qvel[w.robot.fv:w.robot.fv + 2] = 0.0
    while not w.done:
        act(w, A, "joints", np.r_[q, 0, 0])
    v = verdict(w)
    assert v["failed"] == "touched the ground or the mats beyond the zero line before clearing the bar", v
    assert v["stages"] == ["plant", "take-off"] and w.ref.events[-1]["what"] != ["pole"], (v, w.ref.events[-1])
    # climbing: in the hang the robot lets go, is moved 0.2 m up the pole by hand and grips again
    w.reset(); q = on_the_pole(w, A, grip=3.6, speed=3.0)
    act(w, A, "joints", np.r_[q, 0, 1], 40)
    assert verdict(w)["stages"] == ["plant", "take-off"] and not w.done, verdict(w)
    assert abs(T.trackers["grip"]["right"] - 3.6) < 0.02 and abs(T.trackers["grip0"] - 3.6) < 0.02, T.trackers["grip"]
    act(w, A, "joints", np.r_[q, 0, 0])
    mujoco.mj_kinematics(w.m, w.d)
    u = w.d.xmat[T.pole_id].reshape(3, 3)[:, 0]
    higher = T.tip(w) - 3.8 * u                                          # the point of the pole 3.8 m from its tip
    move_robot(w, *(w.d.qpos[w.robot.fq:w.robot.fq + 3] + higher - w.d.site_xpos[w.robot.palm["right"]]))
    w.d.qvel[:] = 0.0                                                    # (robot and pole held still for the new grip)
    act(w, A, "joints", np.r_[q, 0, 1], 5)
    v = verdict(w)
    assert v["failed"] == "moved a hand up the pole after leaving the ground" and w.ref.events[-1]["from_tip_m"] > 3.75, (v, w.ref.events[-1])
    ballistic(w, A, (4.5, 0.0, 6.5), x=-1.9, tuck=(-2.8, 2.05))          # over the bar in a jump, without the pole
    v = verdict(w)
    assert v["failed"] == "cleared the bar without the pole planted in the box" and v["stages"] == [], v
    ballistic(w, A, (4.5, 0.0, 6.5), x=-1.9, y=3.0, tuck=(-2.8, 2.05))   # the same jump outside the uprights
    assert verdict(w)["failed"] == "went round the bar" and verdict(w)["stages"] == [], verdict(w)
    ballistic(w, A, (4.5, 0.0, 3.0), x=-0.4, tuck=(-2.8, 2.05))          # a low jump: through below the bar
    assert verdict(w)["failed"] == "passed under the bar" and verdict(w)["stages"] == [], verdict(w)
    # walking on with the pole, between the front pieces, towards the mat
    w.reset(); hold(w, A, 0.1); dx = -2.6 - w.pelvis()[0]
    move_robot(w, x=-2.6); qa, _ = w.free["pole"]; w.d.qpos[qa] += dx
    up = w.robot.rest[12:]
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.7, np.clip(-2 * y, -0.3, 0.3), np.clip(-2 * yaw, -1, 1), up, 0, 1])
    v = verdict(w)
    assert v["failed"] == "touched the ground or the mats beyond the zero line before clearing the bar" and v["stages"] == [], v
    print("  walking on with the pole:", w.ref.events[-1])
    # a hand resting on the bar (the bar held by hand against the standing robot's raised hand)
    w.reset(); hold(w, A, 0.1, grips=[0, 0]); w.pin("pole", (-8.0, 3.0, 0.05))
    q0, q = w.robot.arb.target().copy(), targets(w, None)
    for k in range(250):
        act(w, A, "stand", np.r_[(q0 + min(1.0, (k + 1) / 200) * (q - q0))[12:], 0, 0])
    hand = np.flatnonzero(w.ref.part("right_hand"))
    R = w.d.geom_xmat[hand].reshape(-1, 3, 3)
    top = float(np.max(w.d.geom_xpos[hand][:, 2] + np.einsum("gj,gj->g", R[:, 2, :], w.m.geom_aabb[hand, :3])
                       + np.sum(np.abs(R[:, 2, :]) * w.m.geom_aabb[hand, 3:], axis=1)))
    palm = w.d.site_xpos[w.robot.palm["right"]]
    assert top > 2.0, top                                               # (above the bar: the pinned bar is not "off its pegs")
    w.pin("bar", (palm[0], 0.0, top + 0.012)); act(w, A, "stand", np.r_[q[12:], 0, 0], 40)
    v = verdict(w)
    assert v["failed"] == "steadied the bar with a hand" and v["stages"] == [], (v, top)
    print("PASS pole-vault")


if __name__ == "__main__":
    main()
