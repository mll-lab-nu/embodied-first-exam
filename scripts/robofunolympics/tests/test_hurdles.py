"""hurdles (50 m, four official 1.067 m hurdles, the H1-2): the hurdle has the official toppling force (it stands at
3.79 kg on the middle of its top bar and goes over at 3.81 kg); the referee says no to standing still, to walking
into the first hurdle (the forearms and the trunk push it over), to passing a flattened hurdle below its top, to the
feet passing under the bar, to a foot or a leg beside the hurdle, to leaving the lane and to lying on the track; it says yes to a hurdle that the feet knock down on the way over.

The positive is an INJECTION, not a solution: at each hurdle the robot is put 1.1 m before it by hand, stands there on
its own, and is given a velocity by hand (rfo.testing.kick_robot: 2.0 m/s forward, 5.5 m/s up) so that it really
flies over the standing hurdle (pelvis and feet above the bar, nothing touched) and really comes down behind it; just
above the track its velocity is taken away by hand. Between the hurdles it is moved by hand; the last metre to the
finish line it really walks (the walking policy)."""
import mujoco
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict


def ghost_jump(w, A, i, vel=(2.0, 0.0, 5.5), back=1.1, settle=1.0):
    """Injected: put `back` m before hurdle i, stand, fly with `vel`, be stopped just above the track, stand."""
    move_robot(w, x=w.task.hurdle_x()[i] - back, y=0.0, z=w.robot.stand_z, yaw=0.0)
    w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
    hold(w, A, 0.5)
    kick_robot(w, vel)
    while not w.done:
        hold(w, A, 0.01)
        if w.d.qvel[w.robot.fv + 2] < 0 and w.pelvis()[2] < w.robot.stand_z + 0.06:
            w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0
            break
    hold(w, A, settle)


def all_ten(w, A):
    hold(w, A, 0.1)
    for i in range(4):
        ghost_jump(w, A, i)
    D = w.task.p["distance_m"]
    move_robot(w, x=D - 1.2, y=0.0, z=w.robot.stand_z, yaw=0.0); hold(w, A, 0.5)
    up = w.robot.rest[12:]
    while not w.done:                                                    # the last metre: a real walk
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.6, np.clip(-2 * y, -0.3, 0.3), np.clip(-2 * yaw, -1, 1), up, 0, 0])


def main():
    w, A = make("hurdles")
    T, p = w.task, w.task.p
    xs = T.hurdle_x()
    assert xs[0] == 13.72 and xs[3] == 41.14 and abs(p["distance_m"] - xs[3] - 8.86) < 1e-9 and len(xs) == 4
    assert (p["hurdle_height_m"], p["bar_height_m"], p["base_length_m"]) == (1.067, 0.07, 0.70) and 1.18 <= p["hurdle_width_m"] <= 1.20
    bar, body = w.m.geom("hurdle1_bar").id, w.m.body("hurdle1").id
    assert abs(w.d.geom_xpos[bar][2] + p["bar_height_m"] / 2 - 1.067) < 1e-6           # the top edge
    assert w.m.body_subtreemass[body] >= 10.0 and 3.6 <= T.toppling_force_n() / 9.80665 <= 4.0
    for kgf, falls in ((3.6, False), (3.79, False), (3.81, True), (4.0, True)):          # the toppling force, in physics
        w.reset(); tilt = 0.0
        for _ in range(250):
            w.d.qfrc_applied[:] = 0
            top = w.d.geom_xpos[bar] + w.d.geom_xmat[bar].reshape(3, 3) @ np.array([0, 0, p["bar_height_m"] / 2])
            mujoco.mj_applyFT(w.m, w.d, np.array([kgf * 9.80665, 0, 0]), np.zeros(3), top, body, w.d.qfrc_applied)
            hold(w, A, 0.01); tilt = max(tilt, T.tilt_deg(w, 0))
        w.d.qfrc_applied[:] = 0
        assert (tilt > 30.0) == falls and (falls or tilt < 0.5), (kgf, tilt)
    w.reset(); hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [] and w.t == 140.0, (verdict(w), w.t)   # nop
    w.reset(); all_ten(w, A)                                                                  # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == T.stages and "hurdles_down" not in v["metrics"], v
    assert max(T.tilt_deg(w, i) for i in range(4)) < 1.0                                     # no hurdle touched
    print("  ten injected clearances:", v["metrics"])
    sha = w.state_sha()
    w.reset(); all_ten(w, A)
    assert w.state_sha() == sha                                                               # determinism
    w.reset(); hold(w, A, 0.1); ghost_jump(w, A, 0, vel=(2.0, 0.0, 4.6), back=0.93, settle=0.3)   # the feet clip the bar
    v = verdict(w)
    assert v["stages"] == ["hurdle 1"] and v["failed"] is None and v["metrics"]["hurdles_down"] == 1, v
    assert T.tilt_deg(w, 0) > 45.0                                       # knocked down by the feet: allowed
    w.reset(); hold(w, A, 0.1); move_robot(w, x=10.5); hold(w, A, 0.5)   # walking on into the first hurdle
    up = w.robot.rest[12:]
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.8, np.clip(-2 * y, -0.3, 0.3), np.clip(-2 * yaw, -1, 1), up, 0, 0])
    v = verdict(w)
    assert v["failed"] == "knocked the first hurdle with a hand, an arm or the trunk" and v["stages"] == [], v
    print("  walking into the first hurdle:", w.ref.events[-1])
    # a flattened hurdle walked over: the pelvis passes its plane below the height of its top
    w.reset(); hold(w, A, 0.1); w.d.qpos[T.hinge[0]] = np.pi / 2
    move_robot(w, x=xs[0] - 0.4); hold(w, A, 0.05); move_robot(w, x=xs[0] + 0.4); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "went under the top of the first hurdle" and w.ref.events[-1]["what"] == "pelvis", (v, w.ref.events[-1])
    # ... the pelvis high enough (lifted by hand), the feet under the bar
    w.reset(); hold(w, A, 0.1); w.d.qpos[T.hinge[0]] = np.pi / 2
    move_robot(w, x=xs[0] - 0.4, z=1.5); hold(w, A, 0.01); move_robot(w, x=xs[0] + 0.4, z=1.5); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "went under the top of the first hurdle" and "foot" in w.ref.events[-1]["what"], (v, w.ref.events[-1])
    # high enough, but the left foot outside the bar's end
    w.reset(); hold(w, A, 0.1)
    move_robot(w, x=xs[0] - 0.4, y=0.45, z=2.3); hold(w, A, 0.01); move_robot(w, x=xs[0] + 0.4, y=0.45, z=2.3); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "went beside the first hurdle" and w.ref.events[-1]["what"] == "left foot", (v, w.ref.events[-1])
    # a leg beside the hurdle below its top while the body goes over (TR 22.6.1): the robot turned sideways over the bar's end
    w.reset(); hold(w, A, 0.1); ghost_jump(w, A, 0); assert verdict(w)["stages"] == ["hurdle 1"]
    move_robot(w, x=xs[1] - 0.05, y=0.50, z=w.robot.stand_z); hold(w, A, 0.05)
    v = verdict(w)
    assert v["failed"] == "a leg beside the second hurdle below its top" and v["stages"] == ["hurdle 1"], v
    w.reset(); hold(w, A, 0.2); move_robot(w, y=0.7); hold(w, A, 0.05)                        # out of the lane
    assert verdict(w)["failed"] == "left the lane", verdict(w)
    w.reset(); hold(w, A, 0.5); move_robot(w, x=5.0, z=0.30)             # lying on the track, face down along the lane
    w.d.qpos[w.robot.fq + 3:w.robot.fq + 7] = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]
    hold(w, A)
    assert verdict(w)["failed"] == "did not finish: down for too long" and w.t < 20.0, (verdict(w), w.t)
    print("PASS hurdles")


if __name__ == "__main__":
    main()
