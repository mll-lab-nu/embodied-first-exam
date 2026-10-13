"""box-jump (the H1-2, a free 0.61 m box): the referee says no to standing still, to walking into the box, to being put
on it without a flight, to a jump in place, to a leg tuck without a take-off, to a one-foot take-off, to a jump that is
too short (the feet meet the box's front), to one that comes down on the hands, to one with a foot beside the box, to
an overshoot, to a landing that is not absorbed (tumbles off), to stepping off after the landing, to sitting down on the
box, to standing on it lower than the line (the rule alone, with the line raised), to a fall on the floor.

The positive is an INJECTION (no controller of this robot jumps 0.61 m: its best open-loop squat jump found here leaves
the floor at 1.8 m/s and lifts its centre of mass 0.16 m): the standing robot is given a velocity
(rfo.testing.kick_robot: 1.6 m/s forward, 3.7 m/s up), so it really leaves the floor from both feet, flies 0.50 s with
its pelvis rising 0.69 m, and comes down with both feet on the box's top face; at touchdown the test removes its
horizontal speed (a ghost: the `stand` action does not absorb a 1.6 m/s landing), and the platform's stance takes the
vertical impact and stands on the free box."""
import numpy as np

from rfo.testing import act, hold, kick_robot, make, move_robot, verdict


def ghost_jump(w, A, vx=1.6, vz=3.7, wy=0.0, stop=True, until=None, y=None):
    hold(w, A, 0.3)
    if y is not None:
        move_robot(w, y=y)
        hold(w, A, 0.1)
    kick_robot(w, vel=(vx, 0.0, vz), angvel=(0.0, wy, 0.0))
    stopped = False
    while not w.done and (until is None or w.t < until):
        hold(w, A, 0.01)
        if stop and not stopped and w.ref.has("take-off"):
            w.d.qvel[w.robot.fv:w.robot.fv + 2] = 0.0
            stopped = True


def main():
    w, A = make("box-jump")
    p = w.task.p
    r = w.robot
    up = r.rest[12:]
    assert w.robot_name == "unitree_h1" and abs(w.task.top_z(w) - 0.61) < 1e-6 and "box" in w.free   # official, free
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    w.reset(); ghost_jump(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["take-off", "landing", "stand"], v                # positive (injection)
    assert v["metrics"]["air_s"] >= 0.4 and v["metrics"]["pelvis_rise_m"] >= 0.6, v
    assert v["metrics"]["pelvis_above_box_m"] >= p["upright_pelvis_m"], v
    assert abs(w.task.top_z(w) - 0.61) < 0.005 and abs(w.pos("box")[0] - w.task.box0[0]) < 0.02   # the box stayed
    sha = w.state_sha()
    w.reset(); ghost_jump(w, A)
    assert w.state_sha() == sha                                                               # deterministic
    w.reset()                                                                                 # walking into the box
    while not w.done:
        act(w, A, "walk", np.r_[0.5, 0, 0, up, 0, 0])
    assert verdict(w)["failed"] == "touched the box before the jump", verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # put on the box, no flight
    move_robot(w, x=p["box_distance_m"] + 0.22, z=r.stand_z + p["box_height_m"] - 0.004); hold(w, A, 0.5)
    assert verdict(w)["failed"] == "touched the box before the jump", verdict(w)
    w.reset(); ghost_jump(w, A, vx=0.0)                                                       # a jump in place
    assert verdict(w)["failed"] == "the jump landed on the floor", verdict(w)
    w.reset(); hold(w, A, 0.2)                                                                # a leg tuck: both feet
    q = w.d.qpos[r.qadr].copy()                                                               # pulled up, the body falls
    for o in (0, 6):
        q[o + 1], q[o + 3], q[o + 4] = -1.6, 2.0, -0.4
    act(w, A, "lowcmd", np.r_[q, np.zeros(2 * w.L.NJ), r.kp_max, r.kd0, 0, 0], 80)
    v = verdict(w)
    assert v["failed"] == "not a real take-off" and v["metrics"]["air_s"] >= p["min_air_s"], v
    assert v["metrics"]["pelvis_rise_m"] < 0.02, v
    w.reset(); hold(w, A, 0.2)                                                                # a one-foot take-off
    q = w.d.qpos[r.qadr].copy()
    q[1], q[3] = -1.0, 1.5                                                                    # the left foot lifted
    act(w, A, "joints", np.r_[q, 0, 0], 25)
    assert not w.ref.touching(w.task.foot["left"], w.task.floor) and not w.done, verdict(w)
    kick_robot(w, vel=(1.6, 0.0, 3.9)); hold(w, A, 2.0)
    assert verdict(w)["failed"] == "not a two-foot take-off", verdict(w)
    w.reset(); ghost_jump(w, A, vx=1.0, vz=3.55)                                              # too short: the toes
    assert verdict(w)["failed"] == "landed on the side of the box", verdict(w)                # meet the front face
    w.reset(); ghost_jump(w, A, wy=2.5)                                                       # pitched forward: the
    v = verdict(w)                                                                            # hands come down first
    assert v["failed"] == "did not land on the feet" and v["stages"] == ["take-off"], v
    w.reset(); ghost_jump(w, A, y=0.30)                                                       # the left foot beside
    v = verdict(w)                                                                            # the box: it drops along
    assert v["failed"] == "landed on the side of the box" and v["stages"] == ["take-off"], v  # the side face
    assert w.ref.events[-1]["feet"] == ["left"], w.ref.events[-1]
    w.reset(); ghost_jump(w, A, vx=2.4, vz=4.5, stop=False)                                   # an overshoot: over the
    v = verdict(w)                                                                            # box, down beyond it
    assert v["failed"] == "the jump landed on the floor" and v["stages"] == ["take-off"], v
    w.reset(); ghost_jump(w, A, stop=False)                                                   # a real 1.6 m/s landing
    v = verdict(w)                                                                            # is not absorbed
    assert v["failed"] == "touched the floor after the landing" and v["stages"] == ["take-off", "landing"], v
    w.reset(); ghost_jump(w, A, until=1.6)                                                    # lands, then steps off
    assert verdict(w)["stages"] == ["take-off", "landing"] and not w.done, verdict(w)
    move_robot(w, x=p["box_distance_m"] + p["box_length_m"] + 0.5, z=r.stand_z + 0.01); hold(w, A, 1.0)
    assert verdict(w)["failed"] == "touched the floor after the landing", verdict(w)
    w.reset(); ghost_jump(w, A, until=1.6)                                                    # lands, then sits down
    q = w.d.qpos[r.qadr].copy()                                                               # on the box
    for o in (0, 6):
        q[o + 1], q[o + 3], q[o + 4] = -1.9, 1.2, 0.0
    act(w, A, "joints", np.r_[q, 0, 0], 300)
    v = verdict(w)
    assert v["failed"] == "touched the box with something other than the feet" and v["stages"] == ["take-off", "landing"], v
    w.reset(); hold(w, A, 0.2); move_robot(w, x=-1.0, z=0.30)                                 # a fall on the floor
    w.d.qpos[r.fq + 3:r.fq + 7] = [np.cos(np.pi / 4), 0, np.sin(np.pi / 4), 0]; hold(w, A, 1.0)
    assert verdict(w)["failed"] == "fell", verdict(w)
    w.close()
    w, A = make("box-jump", upright_pelvis_m=1.10)                                            # the upright rule alone: a
    ghost_jump(w, A)                                                                          # line above this robot's
    v = verdict(w)                                                                            # straight-leg height is
    assert v["failed"] == "time" and v["stages"] == ["take-off", "landing"], v                # never reached: it
    assert 1.00 < v["metrics"]["pelvis_above_box_m"] < 1.10, v                                # stands there to the end
    print("PASS box-jump")


if __name__ == "__main__":
    main()
