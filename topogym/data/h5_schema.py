"""RoboMME-structural HDF5 layout for TopoGym episode datasets.

Structure (one file = one episode for now; nested under ``episode_0/`` so a
multi-episode file later just adds ``episode_1/`` ...):

    episode_<N>/
    ├── setup/          attrs: stable_id, task_id, seed, preset_id, variant_id,
    │                          difficulty, task_goal, goal_id, status, success,
    │                          plan_id, camera_names, camera_renderers,
    │                          camera_backgrounds, frame_dt_s; datasets:
    │                          subgoals, waypoints, waypoint_labels; group: variant/
    └── timestep_<K>/
        ├── obs/        front_rgb, wrist_rgb (uint8 HxWx3), eef_state(7 xyz+quat),
        │               gripper_state, is_gripper_close, joint_state,
        │               goal_id (int64 scalar)
        ├── action/     ee_pose_action(7, absolute next-step eef pose),
        │               ee_rot6d_action(6, that pose's rotation as the first two
        │               columns of its matrix), gripper_action(1, the COMMANDED
        │               opening at the next step)
        └── info/       attrs: task_goal, simple_subgoal, is_subgoal_boundary,
                               is_completed, status

Field subset vs RoboMME's ``h5_data_format.md`` (documented divergences):
- eef_state stores xyz+quaternion (7), RoboMME uses xyz+rpy (6).
- action stores absolute poses, never deltas. A delta only means something
  divided by the frame interval, so writing one to disk would weld the sampling
  rate into the file; ``scripts/export_h5_lerobot.py`` computes deltas from two
  neighbouring poses instead, and ``frame_dt_s`` says what to divide by. One
  file therefore feeds both conventions: diffusion policies take the absolute
  pose, VLAs take the exporter's delta.
- action stores no joint/waypoint/choice action; RoboMME does. Our sparse
  waypoint plan lives in ``setup``; per-timestep ``waypoint_action`` /
  ``joint_action`` / ``choice_action`` and ``grounded_subgoal`` are RESERVED
  (not written until we produce them).

Version history: 0.2.0 added ``gripper_action``, ``ee_rot6d_action``,
``setup.frame_dt_s`` and the ``setup/variant`` group. 0.3.0 added ``goal_id``
(``setup`` attribute and one ``obs`` entry per timestep). All additive -- a 0.1.0
reader sees the same fields it always did.
"""

from __future__ import annotations

SCHEMA_VERSION = "0.3.0"

OBS_KEYS = (
    "front_rgb",
    "wrist_rgb",
    "eef_state",
    "gripper_state",
    "is_gripper_close",
    "joint_state",
    # Which goal this episode has, as an int: what the instruction sentence
    # names, for a policy that is given no sentence. Constant over the episode
    # and repeated per frame so an obs vector can be assembled from one timestep
    # alone. What the number means is per task -- see the task yaml's
    # ``goal.goal_id_fn`` -- and ``task_goal`` on the same frame spells it out.
    "goal_id",
)
ACTION_KEYS = (
    "ee_pose_action",
    "ee_rot6d_action",
    "gripper_action",
)  # waypoint_action / joint_action / choice_action reserved
INFO_KEYS = (
    "task_goal",
    "simple_subgoal",
    "is_subgoal_boundary",
    "is_completed",
    "status",
)
