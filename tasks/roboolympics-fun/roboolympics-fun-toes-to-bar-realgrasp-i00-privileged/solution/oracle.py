"""toes-to-bar-realgrasp: five slow (strict, not kipped) toes-to-bar from the dead hang, gentle enough for a friction
grip (privileged: the feet's height under the bar, the swing angle and the referee's rep state).

The base family's kipped snap throws the feet onto the bar in 0.3 s; its hand loads (up to about 2000 N per hand over
50 ms, with the weld) tear the bar out of the Dex1-1's jaws, which hold about 238 N per hand. Here the joint targets
move along one path, a progress s from the hanging pose (0) to the fold (1: hips at `hip`, knees `knee`, ankles
`ankle`, waist pitch `waist`, shoulders pulled down to `shoulder`, elbows bent to `elbow`: the body rolls back under the
bar and the feet come up to it): s rises at 1/up_s while the higher foot is more than `near_m` below the bar, then
creeps at 1/creep_s (the feet must touch the bar, not press on it: what the feet push the bar with, the grippers carry
on top of the body's weight), and as soon as the referee has seen the touch it comes back down at 1/down_s with an
ease-out, and waits in the hang until the rep has counted and the swing has calmed below `still_deg`."""
import math

import numpy as np

OMEGA = 3.0                   # rad/s: the hanging robot's small-swing angular frequency (about)


def fold_pose(base, shoulder, elbow, knee, ankle, waist, hip):
    q = base.copy()
    q[0] = q[6] = hip
    q[3] = q[9] = knee
    q[4] = q[10] = ankle
    q[14] = waist
    q[15] = q[22] = shoulder
    q[18] = q[25] = elbow
    return q


def solve(s, shoulder=-1.5, elbow=2.09, knee=0.6, ankle=0.4, waist=0.52, hip=-2.53, up_s=3.0, creep_s=15.0,
          near_m=0.5, down_s=5.5, still_deg=5.0, damp=0.4, damp_max=0.3, give_up_s=8.0):
    base = np.array(s.state()["q_target"])            # the hanging pose (legs in the stance, arms up)
    fold = fold_pose(base, shoulder, elbow, knee, ankle, waist, hip)
    dt = s.world.CONTROL_DT
    prev = s.state()["task"]["swing_deg"]
    mode, x, t, t0, reps = "up", 0.0, 0.0, 0.0, 0
    while not s.done:
        task = s.state()["task"]
        th = task["swing_deg"]
        v = math.radians(th - prev) / dt
        prev = th
        amp = math.hypot(th, math.degrees(v) / OMEGA)
        extra = np.zeros_like(base)
        if mode == "up":
            if task["touched"] or t - t0 > give_up_s:
                mode, t0 = "down", t
            else:
                high = min(task["feet_below_bar_m"].values())
                x = min(1.0, x + dt / (up_s if high > near_m else creep_s))
        if mode == "down":
            x = max(0.0, x - dt / down_s)
            if x == 0.0:
                mode = "hang"
        if mode == "hang":
            if task["reps"] > reps and amp < still_deg:
                reps, mode, t0 = task["reps"], "up", t
            else:                                     # damp the swing: the legs a little back while it swings forwards
                extra[0] = extra[6] = float(np.clip(damp * v, -damp_max, damp_max))
        k = x * x * (3 - 2 * x)
        s.step("joints", np.r_[base + k * (fold - base) + extra, 1.0, 1.0])
        t += dt
