"""backflip: the referee says no to standing still, to a jump without the turn, to a forward flip, to two thirds
of a turn, to a spin about the vertical with the pelvis rolled on its side, to a backward roll on the ground, to a flip that comes down on the head, to a flip whose landing falls, to
a flip that does not start from the feet (thrown up from lying on the ground).

The positive is an INJECTION (no controller of this robot flips yet): the standing robot is given a velocity
(rfo.testing.kick_robot: 3.4 m/s up and 8.97 rad/s backwards about the pelvis' left-right axis), so it really leaves
the ground, turns 360 degrees in 0.70 s of flight and comes down feet first; at touchdown the test removes its
rotation and horizontal speed (a ghost: the `stand` action cannot stop a 9 rad/s rotation), and the platform's stance
takes the vertical impact and stands."""
import math

from rfo.testing import hold, kick_robot, make, verdict

VZ = 3.4
SPIN = 2 * math.pi / (2 * VZ / 9.81)          # one turn in the flight time


def ghost_flip(w, A, f=0.99, vz=VZ, stop=True, seconds=None):
    hold(w, A, 0.3)
    kick_robot(w, vel=(0.0, 0.0, vz), angvel=(0.0, -f * SPIN, 0.0))
    stopped = False
    t_end = None if seconds is None else w.t + seconds
    while not w.done and (t_end is None or w.t < t_end):
        hold(w, A, 0.01)
        if stop and not stopped and w.task.trackers["landed"]:
            fv = w.robot.fv
            w.d.qvel[fv:fv + 2] = 0.0
            w.d.qvel[fv + 3:fv + 6] = 0.0
            stopped = True


def main():
    w, A = make("backflip")
    p = w.task.p
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    w.reset(); ghost_flip(w, A)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["take-off", "full turn", "landing", "stand"], v   # positive (injection)
    assert v["metrics"]["turn_deg"] >= p["turn_deg"] and v["metrics"]["air_s"] > 0.6, v
    sha = w.state_sha()
    w.reset(); ghost_flip(w, A)
    assert w.state_sha() == sha                                                               # deterministic
    w.reset(); ghost_flip(w, A, f=0.0)                                                        # a jump, no turn
    assert verdict(w)["failed"] == "not a full backward turn" and verdict(w)["stages"] == ["take-off"], verdict(w)
    w.reset(); ghost_flip(w, A, f=-0.99)                                                      # a forward flip
    v = verdict(w)
    assert v["failed"] == "not a full backward turn" and v["metrics"]["turn_deg"] < -300, v
    w.reset(); ghost_flip(w, A, f=0.66)                                                       # two thirds of a turn
    assert verdict(w)["failed"] == "not a full backward turn", verdict(w)
    w.reset(); ghost_flip(w, A, f=0.86)                                  # a salto that comes down on its feet 36 degrees
    v = verdict(w)                                                       # short of upright: the turn and the landing
    assert v["stages"] == ["take-off", "full turn", "landing"], v        # count (the ghost's stance then falls: the
    assert 300 < v["metrics"]["turn_deg"] < 330 and v["failed"] == "fell", v   # rest of the turn is the landing's work)
    w.reset(); hold(w, A, 0.3)                                           # the pelvis on its side in the air, spinning
    r = w.robot                                                          # about the vertical: a rotation about its own
    w.d.qpos[r.fq + 2] += 1.5                                            # left-right axis that is no backward turn
    w.d.qpos[r.fq + 3:r.fq + 7] = [math.cos(math.pi / 4), math.sin(math.pi / 4), 0, 0]
    kick_robot(w, vel=(0.0, 0.0, 2.0), angvel=(0.0, -3 * SPIN, 0.0)); hold(w, A, 1.5)
    v = verdict(w)
    assert "full turn" not in v["stages"] and abs(w.task.trackers["turn_rad"]) < 0.5, (v, w.task.trackers["turn_rad"])
    w.reset(); ghost_flip(w, A, f=1.10)                                                       # over-rotated: head first
    assert verdict(w)["failed"] == "did not land on the feet" and "full turn" in verdict(w)["stages"], verdict(w)
    w.reset(); ghost_flip(w, A, vz=0.0, f=0.5)                                                # a backward roll on the ground
    assert verdict(w)["failed"] == "fell" and "full turn" not in verdict(w)["stages"], verdict(w)
    w.reset(); ghost_flip(w, A, f=0.94, stop=False)                                           # lands on the feet, falls
    assert verdict(w)["failed"] == "fell" and verdict(w)["stages"] == ["take-off", "full turn", "landing"], verdict(w)
    w.reset(); ghost_flip(w, A, vz=0.6, f=0.0)                                                # a hop shorter than min_air
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)
    w2, A2 = make("backflip", fall_pelvis_m=-1.0)                                             # with the pelvis rule
    w2.task.fall_rule = False                                                                 # and the fall rule off:
    hold(w2, A2, 0.2)                                                                         # the robot on its back,
    w2.d.qpos[w2.robot.fq + 2] = 0.25                                                         # thrown up with the same
    w2.d.qpos[w2.robot.fq + 3:w2.robot.fq + 7] = [math.cos(-math.pi / 4), 0, math.sin(-math.pi / 4), 0]
    hold(w2, A2, 1.0)                                                                         # spin: not from the feet
    assert not w2.ref.parts_touching(w2.ref.ground) <= {"left_foot", "right_foot"}
    kick_robot(w2, vel=(0.0, 0.0, VZ), angvel=(0.0, -SPIN, 0.0)); hold(w2, A2, 2.0)
    assert verdict(w2)["failed"] == "did not take off from the feet", verdict(w2)
    assert p["turn_deg"] == 300.0 and p["stand_s"] == 2.0
    print("PASS backflip")


if __name__ == "__main__":
    main()
