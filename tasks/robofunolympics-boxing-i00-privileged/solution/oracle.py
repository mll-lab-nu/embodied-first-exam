"""boxing (v2): a straight punch from the guard with the trunk's turn behind it, then the walking policy for the
balance. In `stand` mode the fist of the named side goes to the guard (the elbow folded, the fist at the shoulder) and
the trunk turns that shoulder back; the punch drives the arm straight out while the trunk turns the shoulder forwards
(the trunk's motor is the robot's strongest above the hips); as soon as the bag moves (privileged: its angular speed)
the arm is pulled back to the guard and the legs go to the walking policy at zero command, which absorbs the turn.
Measured: 14 to 17 N s over the twelve variations tried (trunk angles, timing, the bag 1.5 cm nearer or farther)."""
import numpy as np

GUARD_ELBOW = -0.94          # the elbow folded as far as it goes: the fist beside the shoulder
OUT_SHOULDER, OUT_ELBOW = -1.45, 1.45      # the arm straight out in front, at shoulder height
WIND, TURN = -0.40, 1.10     # the trunk's angle before the punch and where the punch turns it to (for the right fist)
N_PUNCH = 10                 # control steps over which the targets go from the guard to the punch
SETTLE = 80                  # control steps to take the guard and let the body come to rest


def solve(s, wind=WIND, turn=TURN, n=N_PUNCH, settle=SETTLE, fist=None, recover="walk"):
    w = s.world
    side = fist or w.task.p["fist"]
    sgn = 1.0 if side == "right" else -1.0
    names = [j[:-6] for j in w.L.JOINTS[12:]]
    i_sp, i_ep = names.index(f"{side}_shoulder_pitch"), names.index(f"{side}_elbow_pitch")
    rest = w.robot.rest[12:].copy()

    def upper(torso, shoulder, elbow):
        r = rest.copy()
        r[0], r[i_sp], r[i_ep] = sgn * torso, shoulder, elbow
        return r

    for i in range(settle):                                 # the guard, the trunk wound back
        f = min(1.0, (i + 1) / 50)
        if s.step("stand", np.r_[upper(wind * f, 0.0, GUARD_ELBOW * f), 0.0, 0.0]):
            return
    for i in range(60):                                     # the punch, until the bag moves
        if w.task.meter.speed(w) > 0.01:
            break
        f = min(1.0, (i + 1) / n)
        if s.step("stand", np.r_[upper(wind + (turn - wind) * f, OUT_SHOULDER * f,
                                       GUARD_ELBOW + (OUT_ELBOW - GUARD_ELBOW) * f), 0.0, 0.0]):
            return
    while not s.done:                                       # back to the guard; the walking policy keeps the balance
        if recover == "walk":
            s.step("walk", np.r_[0.0, 0.0, 0.0, upper(0.0, 0.0, GUARD_ELBOW), 0.0, 0.0])
        else:
            s.step("stand", np.r_[upper(0.0, 0.0, GUARD_ELBOW), 0.0, 0.0])
