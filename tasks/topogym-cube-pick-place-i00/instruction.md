# TopoGym · cube_pick_place — frozen instance

You control a simulated robot (**a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base**; TopoGym on Genesis 1.2.1 physics, Nyx rendering) via Python.
**Task:** Pick up the cube, hold it at least 5 cm above the table for at least 0.2 s, place it back at its original position, open the gripper, withdraw at least 5 cm and let it settle. Merely reaching or closing the gripper is not completion.

The scene objects are the task's entities (`s.objects()`: `cube`, `target_marker` (fixed)). The success predicate is
`CubePickPlaceTask.evaluate_state` (module `rcb_topogym`); the task succeeds once it holds continuously for
0.5 s:
```python
        def evaluate_state(self, state):
            _, failure, metrics = super().evaluate_state(state)
            reached = (self.lifted and self.held_once and metrics["gripper_open"] and metrics["withdrawn"]
                       and metrics["target_error_m"] <= .02 and abs(metrics["clearance_m"]) <= .003
                       and metrics["linear_speed_m_s"] <= .01 and metrics["angular_speed_rad_s"] <= .1)
            return bool(reached), failure, metrics
```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_topogym import Session
s = Session("cube_pick_place", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
s.reset()                          # back to the frozen initial state (unlimited; a restore of the first recorded state)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("arm", pos, quat_wxyz, linear=3)   # IK on the robot's model to a TCP pose, then joint interpolation
p["move_joints"]("arm", q_arm); p["set_gripper"]("arm", 0.0); p["open_gripper"]("arm"); p["hold"](10)
s.ee_pose("arm"); s.joint_positions(); s.ik("arm", pos, quat_wxyz)    # kinematics helpers (arms: ['arm'])
s.render_frame("agentview")         # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS); s.render_grid()
s.render_depth("agentview")         # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (limits), grippers (the grasping rule), PD gains, tool frames ['arm_tcp']
s.kinematics({"op": "fk", "q": q})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"arm_tcp": pose7}, "seed": q}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("arm")   # measured state in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["object_in_hand"]("arm"); p["set_joint_targets"](row, steps=1); p["gripper_quat"](yaw, approach)   # help(p[...])
s.step(action)                     # one low-level action (8 entries, below) = one control step (1/40 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 8) actions, one row per control step
s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end'}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_topogym.py replay --task cube_pick_place --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (-0.570, 0.000, 0.920), table top at z = 0.920, +z up. Quaternions are **WXYZ**.
- Action (8): arm `arm`: 7 joint targets (rad), then `arm_gripper` = opening width (m, 0 closed .. 0.0854 open); absolute position targets tracked by PD controllers, out-of-limit
  values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (1 physics step(s) per control step). There is no step budget; your
  wall-clock budget is 90 min (5400 s). One control step takes about 0.3 s of wall clock here (the
  simulator keeps a full checkpoint of every physics step), so budget your experiments.
- Grippers: assisted grasping (contact_weld_v1): a gripper whose command moves towards closed takes hold of a graspable part (cube) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the penetration at most 2 mm, for 0.02 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, or the part drifts 1 cm / 0.15 rad from its held pose) is lost, and the gripper must open before it can take hold again. Two grippers never hold the same part; other objects are grasped physically (friction).
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand -> fingertips) = local [0.0, 0.0, 1.0], finger-closing axis = local [-0.0, -1.0, 0.0]. The ee_pose action, the proprio tcp pose and the IK use this frame.
  `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along `yaw`; `p["gripper_quat"](yaw, approach)` any other.
- The task succeeds once its predicate has held continuously for 0.5 s; that, or one of its failure predicates,
  ends the simulated episode: later steps are recorded but no longer move the scene (`s.status()["episode_end"]`), and
  `s.reset()` starts over.
- One `Session` per process (Genesis initialises once). Do not call `s.close()` before writing every output.
