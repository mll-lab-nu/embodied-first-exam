# RoboARC · slotted_post_ring (privileged)

## Task
Two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base, at a table (RoboARC, MuJoCo). Separate and
place the entire removable metal ring inside the green dashed goal region. Keep the post, cord, beads and end discs on
the puzzle/system side. The scene is one fixed instance. You have the full simulator to develop with; you hand in a
trajectory of robot actions.

## Goal
Success: the removable metal ring lies entirely inside the green dashed goal square, every part of it within the line;
it may be held there, above the square, but must be still. The post, cord, beads and end discs stay on the puzzle's
side: the cord, beads and discs may move, but no part of them may pass an invisible, fixed wall that stands parallel to
the goal square's near edge, just beyond the puzzle's nearest point to the square at the start; moving the whole puzzle
into the goal does not count. A replay ends, as a success, as soon as all of this has held for half a second; later rows
are not run.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`: the (T, 14) actions, one row
per control step (1/40 s), at most 189000 rows (a longer trajectory is invalid). Leave the script that produced it at
`/app/output/gen.py`. It is replayed once from the fixed start and passes if the task gets done within your rows. Save a
valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actions count: changing the simulator's state while you develop changes nothing in the replay.

## Robot Interface
### Session
`/opt/tools/rcb_topogym.py`, importable as `rcb_topogym`:
```python
from rcb_topogym import Session
s = Session("slotted_post_ring", instance="/app/instance.json")   # builds the frozen scene (instance.json) and compiles kernels
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

- The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
  are yours to build from them.
- One `Session` per process (one simulator per process). Building the scene and compiling its kernels can take minutes;
  every `Session`, including the one a replay or render CLI command starts, holds its own scene in GPU memory, so keep
  one alive at a time. Do not call `s.close()` before writing every output.
- Once the episode has ended, later steps do not change the execution record or move the scene
  (`s.status()["episode_end"]`), and `s.reset()` starts over.
- A failure is reported in `s.status()["episode_end"]` as "connection_or_volume_invalid: <what>" or "forced_breakdown:
  <what>" (<what>: the readable reason); `s.safety()` reports forcing, contact depths, volume ratios and table-guard
  stops, each next to its limit.
- The grader replays with this command (run it to self-check):
  `python /opt/tools/rcb_topogym.py replay --task slotted_post_ring --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Action (14): arm `left`: 6 joint targets (rad), then `left_native_gripper` = native drive target (m, limits 0.002 ..
  0.037; open/closed targets in robot_spec); arm `right`: 6 joint targets (rad), then `right_native_gripper` = native
  drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); absolute position targets tracked by PD
  controllers, out-of-limit values clipped. `s.hold_action()` is the no-op.
- Control runs at 40 Hz (10 physics step(s) per control step). One control step takes about 0.076 s of wall clock here:
  budget your experiments.
- World frame: +z up. Quaternions are **WXYZ**. The ee_pose action and the proprio TCP pose are given in this world
  frame.
- Tool frame (TCP, the ee pose and IK frame): a fixed point near the closed finger pads; approach axis (hand ->
  fingertips) = local [1.0, 0.0, -0.023], finger-closing axis = local [0.0, 1.0, 0.008]. The ee_pose action, the proprio
  tcp pose and the IK use this frame. `p["top_down_quat"](yaw)` builds a vertical approach whose fingers close along
  `yaw`; `p["gripper_quat"](yaw, approach)` any other.

### Grasping
- Assisted grasping: a gripper whose command moves towards closed takes hold of a graspable part (slotted_chain) once
  both fingers touch the same part inside its grasp region, the tool frame within 9 cm of it and the penetration at most
  2 mm, for 0.02 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of
  its travel) lets it go. A hold that breaks (the fingers open more than 15 %, the part drifts 1 cm / 0.15 rad from its
  held pose, or the hold has to push or pull its part with more than 60 N averaged over 20 ms) is lost, and the gripper
  must open before it can take hold again; that force is reached when, for example, two held parts that hook into each
  other are pulled apart, or a held part is pressed into another object. Two grippers never hold the same part; other
  objects are grasped physically (friction).
- Grasp regions (one sphere per graspable part): slotted_chain: radius 76 mm. Both finger contacts must lie inside the
  part's sphere; a part touched elsewhere is grasped physically. Each region's centre (in its link's frame) is in
  `/app/instance.json` under `simulator.grasp_assist.targets`.

## Others
- The scene's objects (`s.objects()`: `goal_region` (fixed), `slotted_chain`).
- A replay's confirmation can end a few physics ticks later than in your own run, which stops at your success: append a
  few copies of the last row (holding still) before saving. `s.replay(actions, grading=True)` replays as the grader does
  and reports whether the goal was reached within your rows (`["grading"]["strict_success"]`).
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
- The goal square measures about 23 cm on a side inside its dashed line (the line's inner edge is the limit), and the
  goal region reaches about 22 cm above the table.
- The cord is about 1.4 m long and 7 mm thick: a chain of short rigid links whose joints bend only so far.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 7 CPUs, 23 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (4 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
