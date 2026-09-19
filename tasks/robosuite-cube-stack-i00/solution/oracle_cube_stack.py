# Human-written reference solution for cube_stack (from cap-x FrankaPickPlaceCodeEnv.ORACLE_CODE, MIT).
# Runs inside Session.exec_code(): primitives are in scope. Never shipped in the agent image.
import numpy as np

_, _, green_ext = get_object_pose("green cube", return_bbox_extent=True)
_, _, red_ext = get_object_pose("red cube", return_bbox_extent=True)

# Sample a grasp pose for the red cube and pick it up
pick_pos, pick_quat = sample_grasp_pose("red cube")
goto_pose(pick_pos, pick_quat, z_approach=0.1)
close_gripper()
# Lift the red cube after grasping
post_pick_pos = pick_pos.copy()
post_pick_pos[2] += 0.2
goto_pose(post_pick_pos, pick_quat)

# Compute placement pose on top of the green cube
green_pos, _, _ = get_object_pose("green cube", return_bbox_extent=False)

place_pos = green_pos.copy()
place_pos[2] = green_pos[2] + green_ext[2]/2 + red_ext[2]/2
# Use down orientation for placement
place_quat = np.array([0.0, 0.0, 1.0, 0.0])

# Approach and place the red cube on the green cube
goto_pose(place_pos, pick_quat, z_approach=0.1)
open_gripper()

# Retract after placing
post_place_pos = place_pos.copy()
post_place_pos[2] += 0.1
goto_pose(post_place_pos, place_quat)
