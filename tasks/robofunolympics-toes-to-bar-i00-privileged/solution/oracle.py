"""toes-to-bar: five kipped toes-to-bar from the dead hang (privileged swing angle and the referee's rep state).

The snap: hips and waist fully flexed, the knees tucked, elbows bent (a short pull on the bar), ankles flexed. From
a still hang it throws both feet onto the bar in about 0.3 s. As soon as the referee has seen both feet on the bar the
robot goes back to the hanging pose: the legs come down, the referee sees the full hang about 0.9 s later, and the
body is left swinging 25 to 45 degrees each way. On a swing the snap only reaches the bar from the right part of it
(measured on free swings of 7 to 45 degrees: always when the body is behind the bar and still going back), so the next
snap is timed as a kip is: it starts when the body, going back, is `phase` of its swing amplitude behind the bar (the
amplitude from the swing angle and its rate), or at once when the hang is nearly still. A snap that misses is given up
after `give_up_s`.
Measured: 5 repetitions in about 10 s."""
import math

import numpy as np

OMEGA = 3.12                  # rad/s: the hanging robot's small-swing angular frequency (measured)


def solve(s, phase=0.7, hip=-2.53, waist=0.52, elbow=2.09, ankle=0.4, knee=1.2, give_up_s=0.8, still_deg=3.0):
    base = np.array(s.state()["q_target"])            # the hanging pose (legs in the stance, arms up)
    dt = s.world.CONTROL_DT
    prev = s.state()["task"]["swing_deg"]
    mode, t0, t = "snap", 0.0, 0.0                    # the first snap: from the dead hang
    while not s.done:
        task = s.state()["task"]
        th = task["swing_deg"]
        v = math.radians(th - prev) / dt
        prev = th
        amp = math.hypot(th, math.degrees(v) / OMEGA)     # the swing's amplitude (degrees)
        q = base.copy()
        if mode == "hang" and not task["touched"] and (amp < still_deg or (v < 0.0 and th <= -phase * amp)):
            mode, t0 = "snap", t
        if mode == "snap":
            q[0] = q[6] = hip
            q[14] = waist
            q[18] = q[25] = elbow
            q[4] = q[10] = ankle
            q[3] = q[9] = knee
            if task["touched"] or t - t0 > give_up_s:
                mode, t0 = "hang", t
                q = base.copy()
        s.step("joints", np.r_[q, 1.0, 1.0])
        t += dt
