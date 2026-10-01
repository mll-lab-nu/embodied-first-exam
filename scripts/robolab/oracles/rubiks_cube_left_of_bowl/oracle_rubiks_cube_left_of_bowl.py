# Reference solution for rubiks_cube_left_of_bowl (RoboLab RubiksCubeLeftOfBowlTask), seed-0 instance. Runs with the
# rcb_robolab primitives in scope. RoboLab's success term: in the ROBOT base frame, the horizontal direction from the
# bowl's centre to the cube's centre lies within 45 deg of the robot's +y (left) axis, and the gripper has let go of the
# cube. Plan: top-down grasp of the cube, carry it to a point 10-19 cm along the robot's left of the bowl, set it down
# on the table, release, retreat. The episode ends by itself the moment the term holds. The cube's pose origin lies on
# one of its side faces, not at its centre, so the grasp aims at the centre of its bounds; the success term (and place())
# work with the pose origin.
# The task-level skills (grasp_point, grasp, place, ...) come from solution/ref_primitives.py: the agent's tooling
# has only thin primitives.
import sys

sys.path.insert(0, "/solution")
from ref_primitives import extend  # noqa: E402

globals().update(extend(session))

import math
import numpy as np

objs = objects()
cube, bowl = objs["rubiks_cube"], objs["bowl"]
print(f"[oracle] cube at {np.round(cube['position'], 3).tolist()} size {np.round(cube.get('size'), 3).tolist()}, "
      f"bowl at {np.round(bowl['position'], 3).tolist()}")
w, x, y, z = session.robot.data.root_quat_w[0].detach().cpu().numpy().astype(float)
base_yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
left = np.array([-math.sin(base_yaw), math.cos(base_yaw)])        # the robot's +y axis in the env-local xy plane
print(f"[oracle] robot base yaw {math.degrees(base_yaw):.1f} deg -> robot left = {np.round(left, 3).tolist()}")
table_z = TASK.get("table_top_z") or 0.0
b = np.asarray(cube["bounds"], dtype=float)
centre = (b[0] + b[1]) / 2
print(f"[oracle] cube bounds centre {np.round(centre, 3).tolist()} (pose origin {np.round(cube['position'], 3).tolist()})")
off = None
for k in range(2):
    if session.episode_done:
        break
    try:
        off = grasp("rubiks_cube", point=[centre[0], centre[1], centre[2] + 0.005], hover=0.10, lift=0.10)
        print(f"[oracle] grasped the cube; tip offset {np.round(off, 3).tolist()}")
        break
    except PrimitiveError as e:
        print(f"[oracle] grasp attempt {k}: {e}")
        open_gripper(10); hold(5)
if off is None and not session.episode_done:
    raise PrimitiveError("could not grasp the rubiks cube")
rest_z = float(cube["position"][2]) - float(b[0][2])          # pose origin height above the cube's bottom face
bp = np.asarray(bowl["position"], dtype=float)
for dist in (0.16, 0.13, 0.19, 0.10):
    if session.episode_done:
        break
    tgt = [bp[0] + dist * left[0], bp[1] + dist * left[1], table_z + rest_z + 0.004]
    try:
        err = place(tgt, off, hover=0.10, release_gap=0.004, retreat=0.12)
        print(f"[oracle] set the cube down {dist:.2f} m to the robot's left of the bowl at {np.round(tgt, 3).tolist()} (tip err {err})")
        break
    except PrimitiveError as e:
        print(f"[oracle] place at {dist:.2f} m: {e}")
hold(30)
print("[oracle] status:", session.status())
