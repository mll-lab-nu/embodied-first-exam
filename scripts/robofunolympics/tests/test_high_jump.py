"""high-jump (TR 26-27: the 4 m bar at 1.00 m, the 6 x 4 x 0.7 m mat, the H1-2): the referee says no to standing
still, to walking on under the bar, to walking round the uprights, to passing under the bar, to a jump from both feet, to
a jump that takes the bar along, to getting onto the mat without a flight, and to a bar that falls after a clean jump.

The positive is an INJECTION, not a solution: the robot is put 0.8 m before the bar by hand, really lifts its left
foot with its own motors (`joints` rows) and stands on the right one; then it is given a velocity by hand
(rfo.testing.kick_robot: 1.5 m/s forward, 5.0 m/s up) so that it really leaves the ground from one foot, really passes
over the bar without touching it (its lowest point 1.28 m up as the pelvis passes the 1.00 m bar) and really comes
down on the mat (where it falls over, which the rules allow)."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict

LEG = {"left": 0, "right": 6}    # the first joint of each leg (hip yaw; the hip pitch is 1, the knee 3 further)


def one_leg(w, lifted):
    q = np.r_[w.robot.stance, w.robot.rest[12:]].copy()
    if lifted:
        q[LEG[lifted] + 1], q[LEG[lifted] + 3] = -1.3, 1.6
    return q


def jump(w, A, vel, back=0.8, lifted="left", seconds=None, y=0.0):
    """Injected jump: put before the bar, one foot lifted by the robot's motors, the velocity given, the pose held."""
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-back, y=y); hold(w, A, 0.5)
    q0, q = w.robot.arb.target().copy(), one_leg(w, lifted)
    for k in range(40):
        act(w, A, "joints", np.r_[q0 + min(1.0, (k + 1) / 30) * (q - q0), 0, 0])
    kick_robot(w, vel)
    low, n = 9.0, None if seconds is None else int(seconds / w.CONTROL_DT)
    while not w.done and (n is None or n > 0):
        act(w, A, "joints", np.r_[q, 0, 0])
        if abs(w.pelvis()[0]) < 0.15:
            low = min(low, float(w.ref.robot_extent()[0][2]))
        n = None if n is None else n - 1
    return low


def main():
    w, A = make("high-jump")
    T, p = w.task, w.task.p
    assert (p["bar_height_m"], p["bar_length_m"], p["upright_gap_m"], p["bar_mass_kg"]) == (1.0, 4.0, 4.02, 2.0)
    assert (p["mat_width_m"], p["mat_length_m"], p["mat_height_m"]) == (6.0, 4.0, 0.7)
    bar = w.m.geom("bar").id
    assert abs(w.d.geom_xpos[bar][2] + w.m.geom_size[bar][0] - 1.0) < 1e-6                    # the bar's upper side
    assert abs(w.m.body_subtreemass[w.m.body("bar").id] - 2.0) < 1e-6
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    assert abs(w.pos("bar")[2] - T.bar["rest_z"]) < 0.002 and abs(w.pos("bar")[0]) < 0.002    # ... the bar rests for 60 s
    low = jump(w, A, (1.5, 0.0, 5.0))                                                         # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == T.stages and low > 1.2 and v["metrics"]["rise_m"] > 1.0, (v, low)
    assert abs(w.pos("bar")[2] - T.bar["rest_z"]) < 0.002 and abs(w.pos("bar")[0]) < 0.002    # the bar was not touched
    land = next(e for e in w.ref.events if e["ev"] == "landing")
    assert land["on_the_mat"] and next(e for e in w.ref.events if e["ev"] == "stage")["foot"] == "right", w.ref.events
    print("  injected jump:", v["metrics"], "lowest point over the bar %.2f m" % low, land)
    sha = w.state_sha()
    jump(w, A, (1.5, 0.0, 5.0))
    assert w.state_sha() == sha                                                               # determinism
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-1.5); hold(w, A, 0.5)   # walking on into the bar
    up = w.robot.rest[12:]
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.7, np.clip(-2 * y, -0.3, 0.3), np.clip(-2 * yaw, -1, 1), up, 0, 0])
    v = verdict(w)                                                       # ... a foot comes down under the bar first
    assert v["failed"] == "touched the ground or the mat beyond the bar's plane without a jump" and v["stages"] == [], v
    assert "foot" in w.ref.events[-1]["parts"][0], w.ref.events[-1]
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-1.0, y=2.6); hold(w, A, 0.5)                 # round the upright
    while not w.done:
        _, y, _, yaw = w.pelvis()
        act(w, A, "walk", np.r_[0.7, np.clip(2 * (2.6 - y), -0.3, 0.3), np.clip(-2 * yaw, -1, 1), up, 0, 0])
    v = verdict(w)                                                       # (TR 27.2: "either between or outside the uprights")
    assert v["failed"] == "touched the ground or the mat beyond the bar's plane without a jump" and v["stages"] == [], v
    jump(w, A, (1.5, 0.0, 5.0), y=2.6)                                   # the same good jump, outside the uprights
    assert verdict(w)["failed"] == "went round the bar" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-0.5, z=0.62); hold(w, A, 0.01)               # ducked under the bar
    move_robot(w, x=0.04, z=0.62); hold(w, A, 0.05)
    assert verdict(w)["failed"] == "passed under the bar" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, (1.5, 0.0, 5.0), lifted=None)                             # the same jump from both feet
    assert verdict(w)["failed"] == "the take-off was not from one foot" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, (1.5, 0.0, 4.42), back=0.65)                              # a little too low: the sole takes the bar along
    v = verdict(w)
    assert v["failed"] == "the bar did not stay on its supports" and v["stages"] == ["take-off", "clearance"], v
    jump(w, A, (1.5, 0.0, 4.1), back=0.65)                               # lower: the foot goes through below the bar's height
    v = verdict(w)
    assert v["failed"] == "passed under the bar" and "foot" in w.ref.events[-1]["what"], (v, w.ref.events[-1])
    # put onto the mat by hand (up, across, down in three steps: 0.03 s off the ground is no flight)
    w.reset(); hold(w, A, 0.1); move_robot(w, x=-0.5, z=2.4); hold(w, A, 0.01); move_robot(w, x=1.5, z=2.4); hold(w, A, 0.01)
    move_robot(w, x=1.5, z=0.7 + w.robot.stand_z - 0.015); w.d.qvel[w.robot.fv:w.robot.fv + 6] = 0.0; hold(w, A, 0.3)
    v = verdict(w)
    assert v["failed"] == "touched the ground or the mat beyond the bar's plane without a jump" and v["stages"] == [], v
    jump(w, A, (1.5, 0.0, 5.0), seconds=1.6)                             # a clean jump, then the bar falls
    assert verdict(w)["stages"] == ["take-off", "clearance"] and not w.done, verdict(w)
    w.put("bar", (0.3, 0.0, 0.75)); hold(w, A)
    assert verdict(w)["failed"] == "the bar did not stay on its supports", verdict(w)
    for push, falls in ((0.015, False), (0.03, True)):                   # the bar on its 4 cm supports
        w.reset(); w.put("bar", (push, 0.0, T.bar["rest_z"])); hold(w, A, 1.5)
        assert (w.pos("bar")[2] < T.bar["rest_z"] - 0.05) == falls and (verdict(w)["failed"] is not None) == falls, (push, w.pos("bar"))
    print("PASS high-jump")


if __name__ == "__main__":
    main()
