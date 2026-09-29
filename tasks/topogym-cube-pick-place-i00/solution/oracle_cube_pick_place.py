# Reference solution for cube_pick_place, instance 00. Runs with the rcb_topogym primitives in scope (see
# Session.exec_code). Plan: open, come down on the cube from above with the fingers closing along world y, close (assisted
# grasping takes hold of the cube), lift 9 cm and hold 0.4 s, put it back where it started, open, withdraw, let it settle.
import numpy as np

ARM = TASK["arms"][0]
pos, _ = get_object_pose("cube")
quat = top_down_quat(np.pi / 2, arm=ARM)           # vertical approach, fingers closing along world y (in reach)

open_gripper(ARM, 5)
move_ee(ARM, pos + [0, 0, 0.10], quat, settle=4)
move_ee(ARM, pos, quat, linear=3, settle=12)
close_gripper(ARM, 60)                             # the Robotiq drive needs ~1.5 s to close on 4 cm
print("[oracle] in hand:", object_in_hand(ARM))
move_ee(ARM, pos + [0, 0, 0.09], quat, linear=3)
hold(16)                                            # >= 0.2 s at least 5 cm above the table
move_ee(ARM, pos + [0, 0, 0.002], quat, linear=3, settle=4)
open_gripper(ARM, 40)                               # opening takes as long as closing
move_ee(ARM, pos + [0, 0, 0.10], quat, linear=2)
hold(60)                                            # the task wants the goal state held still for 0.5 s
print("[oracle] status:", session.status())
