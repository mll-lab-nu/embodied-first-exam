"""vertical-jump (Sargent jump and reach): the referee says no to standing still, to a jump that does not reach the
vane (too low, or the arm not raised), to reaching a (lowered) vane from the ground, to being lifted to the vane
without a take-off, to the head on the vane, to touching the stand's post, to a shuffle and to one foot lifted before
the jump, and to a landing that is not on the feet.

The positive is an INJECTION, not a solution: the robot really raises its right arm with its own motors (`stand`
rows); then it is given a take-off velocity by hand (rfo.testing.kick_robot: 2.8 m/s up), really flies 0.53 s, its hand
really hits the vane 0.30 m above its standing reach, and it really lands on its feet; the stand that follows is the
robot's own.

A REAL push-off is shown too (tests/g1_open_loop_jump.py, `joints` and `lowcmd` rows, the arm raised): the referee
latches "take-off"; the pelvis rises 0.23 m, the hand stays below the vane, and nothing controls the landing."""
import numpy as np

from g1_open_loop_jump import jump as real_jump, upper_pose
from rfo.testing import act, hold, kick_robot, make, move_robot, verdict


def raise_arm(w, A, seconds=1.5):
    """The right arm to its highest pose, slowly (real `stand` rows)."""
    r0, up = w.robot.rest[12:], upper_pose(w, True)
    n = int(seconds / w.CONTROL_DT)
    for k in range(n + 50):
        f = 0.5 - 0.5 * np.cos(np.pi * min(1.0, k / n))
        act(w, A, "stand", np.r_[r0 + f * (up - r0), 0, 0])


def jump(w, A, vz, arm=True, before=None, angvel=(0.0, 0.0, 0.0)):
    w.reset()
    if arm:
        raise_arm(w, A)
    else:
        hold(w, A, 0.3)
    if before:
        before()
        hold(w, A, 0.3)
    if w.done:
        return
    kick_robot(w, (0.0, 0.0, vz), angvel)
    hold(w, A)


def main():
    w, A = make("vertical-jump")
    p = w.task.p
    assert p["vane_above_reach_m"] == 0.30 and abs(w.task.vane_z() - 1.96) < 1e-9
    vane = w.m.geom("vane").id
    assert abs(w.d.geom_xpos[vane][2] - w.m.geom_size[vane][2] - 1.96) < 1e-6 and abs(w.d.geom_xpos[vane][1]) < 1e-6
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # nop
    w.reset(); raise_arm(w, A)                                           # the standing reach: below the vane
    hand = np.flatnonzero(w.ref.part("right_hand"))
    R = w.d.geom_xmat[hand].reshape(-1, 3, 3)
    top = float(np.max(w.d.geom_xpos[hand][:, 2] + np.einsum("gj,gj->g", R[:, 2, :], w.m.geom_aabb[hand, :3])
                       + np.sum(np.abs(R[:, 2, :]) * w.m.geom_aabb[hand, 3:], axis=1)))
    assert 1.63 < top < 1.67 and verdict(w)["failed"] is None, top       # (1.66 with the legs straight; the stance bends them)
    hold(w, A)
    assert verdict(w)["failed"] == "time" and verdict(w)["stages"] == [], verdict(w)          # ... reaching up is not enough
    jump(w, A, 2.8)                                                                           # positive (injection)
    v = verdict(w)
    assert v["success"] and v["stages"] == ["take-off", "touch", "landing", "stand"] and v["metrics"]["rise_m"] > 0.3, v
    assert abs(w.task.privileged(w)["vane_angle_rad"]) < 2.41
    print("  injected jump:", v["metrics"], [e for e in w.ref.events if e["ev"] == "vane"])
    sha = w.state_sha()
    jump(w, A, 2.8)
    assert w.state_sha() == sha                                                               # determinism
    w.reset(); real_jump(w, A, act, knee=1.3, arm_up=True)                                    # a real push-off
    v = verdict(w)
    assert v["stages"] == ["take-off"] and v["failed"] == "landed without touching the vane", v
    assert v["metrics"]["air_s"] > 0.3 and 0.15 < v["metrics"]["rise_m"] < 0.30, v
    print("  real open-loop push-off:", v["metrics"])
    jump(w, A, 2.4)                                                      # 0.29 m: just too low
    v = verdict(w)
    assert v["failed"] == "landed without touching the vane" and v["stages"] == ["take-off"] and v["metrics"]["rise_m"] < 0.30, v
    jump(w, A, 2.8, arm=False)                                           # high enough, the arms down
    assert verdict(w)["failed"] == "landed without touching the vane" and verdict(w)["stages"] == ["take-off"], verdict(w)
    w.reset(); raise_arm(w, A); move_robot(w, z=w.pelvis()[2] + 0.31); hold(w, A)             # lifted to the vane by hand
    v = verdict(w)
    assert v["failed"] == "the flight was not a jump" and v["stages"] == [] and v["metrics"]["rise_m"] < 0.05, v
    jump(w, A, 2.8, before=lambda: move_robot(w, x=w.pelvis()[0] - 0.2))                      # a shuffle before the jump
    assert verdict(w)["failed"] == "a step or shuffle before the take-off" and verdict(w)["stages"] == [], verdict(w)
    w.reset(); hold(w, A, 0.3)                                           # the left foot lifted before the jump
    q = w.robot.arb.target().copy()
    q[0], q[3] = -1.0, 1.6
    while not w.done:
        act(w, A, "joints", np.r_[q, 0, 0])
    assert verdict(w)["failed"] == "a foot left the ground before the take-off" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, 2.8, before=lambda: move_robot(w, y=0.43))                # against the stand's post
    assert verdict(w)["failed"] == "touched the stand" and verdict(w)["stages"] == [], verdict(w)
    jump(w, A, 2.8, angvel=(0.0, 4.0, 0.0))                              # a jump that turns over: the hand misses, down on the head
    assert verdict(w)["failed"] == "landed without touching the vane" and verdict(w)["stages"] == ["take-off"], verdict(w)
    print("  a jump that turns over:", verdict(w)["failed"])
    w.close()
    w, A = make("vertical-jump", vane_above_reach_m=-0.04)               # a vane within the standing reach
    raise_arm(w, A); hold(w, A, 0.5)
    assert verdict(w)["failed"] == "touched the vane without a jump" and verdict(w)["stages"] == [], verdict(w)
    w.close()
    w, A = make("vertical-jump", standing_reach_m=1.0, vane_above_reach_m=0.40)   # a vane just over the head
    jump(w, A, 2.8, arm=False)
    v = verdict(w)
    assert v["failed"] == "touched the vane with another part than a hand" and "head" in w.ref.events[-1]["parts"], (v, w.ref.events[-1])
    print("PASS vertical-jump")


if __name__ == "__main__":
    main()
