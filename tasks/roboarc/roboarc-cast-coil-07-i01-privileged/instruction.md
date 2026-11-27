# RoboARC · cast_coil (privileged)

## Task
Fit the gold and silver pieces fully together, interlocked the way they are made to fit, resting on the table. Then let
go of them and move both arms clear of them.

## Goal
Success: the gold and silver pieces are fitted together exactly the way they are made to fit, resting on the table, with
both arms clear of them and both pieces still. Do not force pieces into each other: a success with pieces pushed into
each other is reviewed instead of credited automatically. Dropping a piece off the table ends the episode as a failure.
A replay ends, as a success, as soon as all of this has held for 0.5 s; later rows are not run.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`: the (T, 14) actions, one row
per control step (1/40 s), at most 200000 rows (a longer trajectory is invalid). Leave the script that produced it at
`/app/output/gen.py`. It is replayed once from the fixed start and passes if the task gets done within your rows. Save a
valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
Two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base, at a table (RoboARC, MuJoCo). The scene is one
fixed instance. You have the full simulator to develop with; you hand in a trajectory of robot actions.

### Session
`/opt/tools/rcb_topogym.py`, importable as `rcb_topogym`:
```python
from rcb_topogym import Session
s = Session("cast_coil", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
s.reset()                          # back to the frozen initial state (unlimited; a restore of the first recorded state)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("left", pos, quat_wxyz, linear=3)   # IK on the robot's model to a TCP pose, then joint interpolation
p["move_joints"]("left", q_arm); p["set_gripper"]("left", 0.0); p["open_gripper"]("left"); p["hold"](10)
s.ee_pose("left"); s.joint_positions(); s.ik("left", pos, quat_wxyz)    # kinematics helpers (arms: ['left', 'right'])
s.render_frame("cam_high")         # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS)
s.render_depth("cam_high")         # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (limits), grippers (the grasping rule), PD gains, tool frames ['left_tcp', 'right_tcp']
s.kinematics({"op": "fk", "q": q})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"left_tcp": pose7}, "seed": q}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("left")   # measured state in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["object_in_hand"]("left"); p["set_joint_targets"](row, steps=1); p["gripper_quat"](yaw, approach)   # help(p[...])
s.step(action)                     # one low-level action = one control step (1/40 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 14) actions, one row per control step
s.status()                         # {'success', 'progress', 'sim_steps', 'resets', 'state_sha', 'episode_end', 'review', 'forcing'}
s.safety()                         # since the last call: forcing / deepest contacts / rope volume / table-guard stops vs the limits
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```

- The primitives are deliberately thin: IK moves, joint moves, gripper, hold. You build grasping, placing and every
  other skill from them.
- One `Session` per process (one simulator per process). Building the scene and compiling its kernels can take minutes;
  every `Session`, including the one a replay or render CLI command starts, holds its own scene in GPU memory, so keep
  one alive at a time. Do not call `s.close()` before writing every output.
- Once the episode has ended, later steps do not change the execution record or move the scene
  (`s.status()["episode_end"]`), and `s.reset()` starts over.
- A failure is reported in `s.status()["episode_end"]` as "A task body fell below the table" or "forced_breakdown:
  <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard
  stops, each next to its limit, and `s.status()["review"]` the deep task contacts that would hold a success for review.
- The grader replays with this command (run it to self-check):
  `python /opt/tools/rcb_topogym.py replay --task cast_coil --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Action (14): arm `left`: 6 joint targets (rad), then `left_native_gripper` = native drive target (m, limits 0.002 ..
  0.037; open/closed targets in robot_spec); arm `right`: 6 joint targets (rad), then `right_native_gripper` = native
  drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); absolute position targets tracked by PD
  controllers, out-of-limit values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). One control step takes about 0.039 s of wall clock here:
  budget your experiments.
- World frame: +z up. Quaternions are **WXYZ**. The ee_pose action and the proprio TCP pose are given in this world
  frame.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand ->
  fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.008]. The ee_pose action, the proprio
  tcp pose and the IK use this frame. `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along
  `yaw`; `p["gripper_quat"](yaw, approach)` any other.

### Grasping
- Assisted grasping: a gripper whose command moves towards closed takes hold of a graspable part (coil_gold,
  coil_silver) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the
  penetration at most 2 mm, for 0.02 s; the part then follows the gripper rigidly. Any command that opens the gripper
  (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, the part drifts 1
  cm / 0.15 rad from its held pose, or the hold has to push or pull its part with more than 60 N averaged over 20 ms) is
  lost, and the gripper must open before it can take hold again; that force is reached when, for example, two held parts
  that hook into each other are pulled apart, or a held part is pressed into another object. Two grippers never hold the
  same part; other objects are grasped physically (friction).
- Grasp regions (one sphere per graspable part): coil_silver: radius 25 mm; coil_gold: radius 25 mm. Both finger
  contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in
  its link's frame) is in `/app/instance.json` under `simulator.grasp_assist.targets`.

### Safety
- Robot safety: no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part
  of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame
  (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an
  arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a
  fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it
  stops pushing (the safety readings report these stops as static_guard).
- Forcing (an arm drive near its torque cap while its gripper, or a part it holds, presses hard on something) is
  recorded as evidence (`s.safety()`, `s.status()["forcing"]`) and shown to the reviewer when a success is reviewed; it
  does not end the episode or change the grade by itself. A simulator breakdown ends the episode: as an infrastructure
  error, or as your failure if an arm was forcing just before it.

## Others
- The scene's objects (`s.objects()`: `coil_gold`, `coil_silver`).

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 16 CPUs, 30 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (12 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
