"""high-bar-swing: pump the swing up from the dead hang until the extended body goes right round the bar (privileged
swing angle).

Two pumps, both with the arms held at the hanging pose:
  1. up to 60 degrees: the playground-swing pump (legs flexed forwards while the centre of mass swings forwards,
     extended behind while it swings back; a tanh of the swing's angular velocity whose width follows its recent peak);
  2. from there: the length pump: the legs are tucked (hips and knees flexed, the waist bent) on the way up as far as
     `open_deg` from the bottom, and straight everywhere else: short through the bottom, long over the top. That adds
     energy every half swing and, once the body goes over the bar, keeps it extended there, which is what the referee's
     giant swing asks for.
Measured: the full circle with the body extended after 24 to 35 s (flex 1.6 to 2.5, open_deg 80 to 180, waist 0 or
0.5); the first passes over the bar are tucked and do not count."""
import math

import numpy as np


def solve(s, flex=2.2, knee=2.2, waist=0.5, open_deg=100.0, start_deg=60.0):
    base = np.array(s.state()["q_target"])            # the hanging pose (legs in the stance, arms up)
    dt = s.world.CONTROL_DT
    prev, peak, amp = math.radians(s.state()["task"]["swing_deg"]), 0.0, 0.0
    first = True
    while not s.done:
        th = math.radians(s.state()["task"]["swing_deg"])
        v = ((th - prev + math.pi) % (2 * math.pi) - math.pi) / dt
        prev = th
        peak = max(abs(v), peak * 0.995)
        amp = max(amp, abs(math.degrees(th)))
        x = 1.0 if first else math.tanh(v / min(max(0.6 * peak, 0.05), 1.0))
        first = False
        q = base.copy()
        q[3] = q[9] = 0.0                                   # knees straight
        q[4] = q[10] = 0.0
        if amp < start_deg:
            q[0] = q[6] = -1.4 * x                          # hip pitch: negative is forwards
        elif th * v > 0 and abs(math.degrees(th)) < open_deg:
            q[0] = q[6] = -flex                             # going up, below open_deg: tucked
            q[3] = q[9] = knee
            q[14] = waist
        s.step("joints", np.r_[q, 1.0, 1.0])
