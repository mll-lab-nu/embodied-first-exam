"""badminton-serve (v2): a forehand low serve played as `stand` rows (the waist's and both arms' joint targets), the
grippers' closures in the rows' grip columns. Found offline by CMA-ES (RoboOlympics' key-pose method, like
search_technique.py) over two key poses: the ready pose (the waist turned, the left arm holding the shuttle out over
the racket's path, the right arm back) and the swing's end pose (the waist and the right arm), and the swing's
duration. Each trial was timed by a dry run of the same rows without the release: where the racket's strings cross
the vertical through the hanging shuttle's cork, and how long the shuttle (drag included) takes to fall that far, give
the control step at which the left gripper opens. The left arm then moves out of the way, the swing meets the falling
shuttle base first, and the robot goes to the walking policy at zero command to stay up.

Rows in order: 1.0 s from the start pose to the ready pose, 0.6 s still (the stand's sway dies down), then the swing
(the targets go from the ready pose to the end pose over `dur_s`) with the release `release_step` control steps after
the swing's first row (negative: before it, the swing waiting for it), then `walk` at zero command from 0.3 s after the
swing's end. Open loop on the frozen start; deterministic.

Measured: the shuttle falls 0.50 m from the left gripper and is hit base first 0.48 m above the floor (the whole
shuttle); it leaves at 13.9 m/s, 47 degrees up, and lands 4.0 m beyond the net, 1.36 m left of the centre line (the
service court's middle is at 4.34 m and 1.29 m); success at 3.45 s. Robust: 10 of 10 with the start shifted by up to
2 cm, 10 of 10 with N(0, 0.02 rad) noise on every key-pose joint, the release 1 or 2 control steps earlier or later
succeeds too, and the search's last mean succeeded 20 of 20 times with N(0, 0.05) noise on its search variables."""
import numpy as np

# shuttle and racket closures of the start (the task's RACKET_CLOSURE / SHUTTLE_CLOSURE)
GRIP_SHUTTLE, GRIP_RACKET = 0.365, 1.0
LEFT_AWAY = [-0.3, 1.2, 0.0, 0.3, 1.5708, 0.0, 0.0]      # the left arm after the release (out to the side)
# The CMA-ES mean after 60 + 60 generations of 24 (scratch tools search2.py / search3.py; score: the referee's stages,
# then the landing's margin inside the service court and the clearance over the net). Ready: the waist turned 50
# degrees to the right and leaning forward, the left arm reaching forward-right over the racket's path; the swing
# (0.16 s) turns the waist back a little and drives the right arm forward and up through the falling shuttle.
TECHNIQUE = {"k1": [-0.8663, 0.0944, 0.353, -0.8634, 0.7821, 0.5078, 0.6818, 0.9999, -0.4613, -0.4385, 0.1385, 0.0554,
                    0.4125, -0.1013, 0.0711, 1.8486, -1.1388],
             "k2": [-0.7463, 0.1818, -0.0332, -0.6926, 0.1483, 0.8254, -0.3678, 0.9649, 1.4419, -0.5072],
             "dur_s": 0.157, "release_step": -17}


def play(s, tech=None):
    """The technique from the start. Returns True if the episode ended."""
    tech = tech or TECHNIQUE
    w = s.world
    up0 = w.robot.arb.target()[12:].copy()
    k1 = np.asarray(tech["k1"], float)                     # waist 3, left arm 7, right arm 7
    k2 = np.asarray(tech["k2"], float)                     # waist 3, right arm 7
    away = np.asarray(LEFT_AWAY, float)
    dt = w.CONTROL_DT
    n1, n2 = int(round(1.0 / dt)), int(round(0.6 / dt))
    nsw = max(1, int(round(tech["dur_s"] / dt)))
    rel = int(tech["release_step"])
    k0 = n1 + n2 + max(0, -rel)
    gl, gr = GRIP_SHUTTLE, GRIP_RACKET
    k = 0
    while not s.done:
        cur = up0 + (k1 - up0) * min(1.0, (k + 1) / n1)
        j = k - k0
        if j >= rel:
            gl = 0.0
            f = min(1.0, max(0.0, (j - rel - 8) / 15))     # the left arm leaves 0.08 s after the release
            cur[3:10] = k1[3:10] + (away - k1[3:10]) * f
        if j >= 0:
            f = min(1.0, (j + 1) / nsw)
            cur[0:3] = k1[0:3] + (k2[0:3] - k1[0:3]) * f
            cur[10:17] = k1[10:17] + (k2[3:10] - k1[10:17]) * f
        if j >= nsw + 30:
            s.step("walk", np.r_[0.0, 0.0, 0.0, cur, gl, gr])
        else:
            s.step("stand", np.r_[cur, gl, gr])
        k += 1
    return True


def solve(s, tech=None):
    play(s, tech)
