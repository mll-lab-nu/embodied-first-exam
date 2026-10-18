# Reference solution for dominos (RoboWits task 06), evaluation scene 00. Runs with the rcb_robowits primitives in scope
# (only the thin ones: move_ee, close_gripper, hold, top_down_quat).
# White blocks 3, 2, 1 and the red block stand as a domino chain ending just short of the green target; toppling white
# block 3 along the chain knocks the red block over onto the target. Push white block 3 near its top with the closed
# right gripper, along the chain direction, then retreat and let the chain fall.
import math
import numpy as np

ARM = "right"
o = objects()
p3 = np.array(o["white block 3"]["position"], dtype=float)
p2 = np.array(o["white block 2"]["position"], dtype=float)
d = (p2 - p3)[:2]
d = d / np.linalg.norm(d)                                  # chain direction, towards the red block
top = float(o["white block 3"]["bounds"][1][2])
yaw = math.atan2(d[1], d[0]) + math.pi / 2                  # fingers close across the push direction
close_gripper(ARM, 10)
q, reached = None, False
for tilt in (0.9, 0.7, 1.1, 0.5, 1.3):
    try:
        q = top_down_quat(yaw, tilt=tilt)
        start = np.array([p3[0] - 0.05 * d[0], p3[1] - 0.05 * d[1], top - 0.015])
        move_ee(ARM, start + np.array([0.0, 0.0, 0.08]), q, settle=5)
        move_ee(ARM, start, q, linear=4, settle=3)
        reached = True
        print(f"[oracle] pre-push pose reached with tilt {tilt}")
        break
    except PrimitiveError as e:
        print(f"[oracle] tilt {tilt}: {e}")
if not reached:
    raise PrimitiveError("white block 3 is out of reach for a direct push")
push_to = np.array([p3[0] + 0.03 * d[0], p3[1] + 0.03 * d[1], top - 0.015])
move_ee(ARM, push_to, q, linear=6, max_dq=0.02)
move_ee(ARM, push_to + np.array([-0.06 * d[0], -0.06 * d[1], 0.08]), q, linear=3)
hold(90)
print("[oracle] red block now at", objects()["red block"]["position"])
print("[oracle] status:", session.status())
