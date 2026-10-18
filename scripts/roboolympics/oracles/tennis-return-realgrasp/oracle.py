"""tennis-return-realgrasp: a one-handed backhand with the racket in the right gripper, found offline (a search
over swings on the deterministic serve: an evolutionary search of the torso's and the right arm's backswing and swing
targets, the spot to stand on and the swing's start, each candidate scored on three slightly moved starts).

All on Unitree's walking policy (`walk` rows): the robot walks (privileged pelvis feedback, a braking velocity
profile on the position predicted 0.6 s ahead) 0.67 m to its left and 0.30 m back, to where the bounced serve passes
0.9 m to its left; from 1.8 s it takes the backswing (the torso turned 0.75 rad to the left, the right arm across the
body, the racket's head to its left) while it walks; at 4.02 s, at zero walking command, the torso turns back to
-0.13 rad with the arm slightly changed, and the robot holds that pose on the walking policy to the end. The gripper
stays closed (120 N) throughout. Measured (frozen start): the head meets the 14.7 m/s ball at 7.1 m/s, the ball
leaves at 15.1 m/s, 44 degrees up (a lob), the racket turns 51 degrees in the grip and stays held, and the ball lands
5.0 m past the net. Measured in the simulator image: the frozen start and 9 of 10 starts moved by up to 4 cm and
0.03 rad succeed (the ball lands 2 to 6 m past the net; the miss goes short); on another machine 35 of 40 starts
moved by up to 5 cm and 0.04 rad."""
import math

import numpy as np

TB, TF = 0.7523, -0.1287                                  # the torso's yaw: backswing, swing (rad)
ARM = [-2.3052, -0.0109, -1.2249, 3.18, 1.6553, 0.47, 0.4454]          # right arm: shoulder pitch, roll, yaw, elbow
ARM2 = [-2.2658, -0.1019, -1.1888, 3.18, 2.0186, 0.4415, 0.4925]       # pitch, elbow roll, wrist pitch, wrist yaw
SPOT = (-0.2954, 0.6720)                                  # where the pelvis stands for the swing (m, start frame)
T_SWING = 4.02                                            # the swing's start (s)
T_ARM, RAMP = 1.8, 0.7                                    # the backswing is taken over RAMP s from T_ARM
A_MAX, TAU, STOP = 0.8, 0.6, 0.015                        # the walk's braking profile, look-ahead, stop radius


def upper(torso, arm):
    q = np.zeros(15)
    q[0], q[8:15] = torso, arm
    return q


def solve(s, spot=SPOT, t_swing=T_SWING):
    w = s.world
    r = w.robot
    grips = [0.0, 1.0]                                    # the right gripper closed on the racket (120 N)
    while not s.done and w.t < t_swing - 1e-9:
        f = float(np.clip((w.t - T_ARM) / RAMP, 0.0, 1.0))
        x, y, _, yaw = w.pelvis()
        v = w.d.qvel[r.fv:r.fv + 2]
        ex, ey = spot[0] - (x + v[0] * TAU), spot[1] - (y + v[1] * TAU)
        d = math.hypot(ex, ey)
        if math.hypot(spot[0] - x, spot[1] - y) < STOP and float(np.linalg.norm(v)) < 0.1:
            vx = vy = 0.0
        else:
            sp = min(math.sqrt(2 * A_MAX * d), 1.0)
            vx, vy = (sp * ex / d, sp * ey / d) if d > 1e-6 else (0.0, 0.0)
        c, sn = math.cos(yaw), math.sin(yaw)
        cmd = [float(np.clip(c * vx + sn * vy, -0.8, 0.8)), float(np.clip(-sn * vx + c * vy, -0.5, 0.5)),
               float(np.clip(-2.0 * yaw, -1.0, 1.0))]
        s.step("walk", np.r_[cmd, upper(TB * f, np.array(ARM) * f), grips])
    while not s.done:                                     # the swing, then hold the pose on the walking policy
        s.step("walk", np.r_[0.0, 0.0, 0.0, upper(TF, ARM2), grips])
