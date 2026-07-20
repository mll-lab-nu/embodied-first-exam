"""RoboMME-structural HDF5 layout for TopoGym episode datasets.

Structure (one file = one episode for now; nested under ``episode_0/`` so a
multi-episode file later just adds ``episode_1/`` ...):

    episode_<N>/
    ├── setup/          attrs: stable_id, task_id, seed, preset_id, variant_id,
    │                          difficulty, task_goal, status, success, plan_id,
    │                          camera_names; datasets: subgoals, waypoints,
    │                          waypoint_labels
    └── timestep_<K>/
        ├── obs/        front_rgb, wrist_rgb (uint8 HxWx3), eef_state(7 xyz+quat),
        │               gripper_state, is_gripper_close, joint_state
        ├── action/     ee_pose_action(7, absolute next-step eef pose)
        └── info/       attrs: task_goal, simple_subgoal, is_subgoal_boundary,
                               is_completed, status

Field subset vs RoboMME's ``h5_data_format.md`` (documented divergences):
- eef_state stores xyz+quaternion (7), RoboMME uses xyz+rpy (6).
- action stores only ``ee_pose_action``; RoboMME also stores joint/waypoint/
  choice actions per timestep. Our sparse waypoint plan lives in ``setup``;
  per-timestep ``waypoint_action`` / ``joint_action`` / ``choice_action`` and
  ``grounded_subgoal`` are RESERVED (not written until we produce them).
"""

from __future__ import annotations

SCHEMA_VERSION = "0.1.0"

OBS_KEYS = (
    "front_rgb",
    "wrist_rgb",
    "eef_state",
    "gripper_state",
    "is_gripper_close",
    "joint_state",
)
ACTION_KEYS = ("ee_pose_action",)  # waypoint_action / joint_action reserved
INFO_KEYS = (
    "task_goal",
    "simple_subgoal",
    "is_subgoal_boundary",
    "is_completed",
    "status",
)
