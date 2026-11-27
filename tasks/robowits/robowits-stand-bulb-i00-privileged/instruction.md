# RoboWits · stand_bulb (privileged)

## Task
Stand the tall object with the curved bottom upright on the green target area, so that it stays standing.

## Goal
Success: the tall object with the curved bottom stands upright on the green target area, both clear of the table's
edges, and stays standing still; the robot has let go of it and moved its grippers away from it. Your trajectory is
replayed from the fixed start. What counts is the state after its last action. After your last row the grader holds its
command for about three seconds (a second, then two seconds in which all of this must keep holding, with nothing
moving).

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`: the (T, 16) actions, one row
per control step (1/30 s), at most 200,000 rows (more score 0). It is replayed once from the fixed start, settle check
included. Leave the script that produced it at `/app/output/gen.py`. Save a trajectory as soon as one replays
successfully, and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A simulated bimanual Marvin robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis 0.4.7 physics). The
scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of robot actions.

### Session
`/opt/tools/rcb_robowits.py`, importable as `rcb_robowits`:
```python
from rcb_robowits import Session
s = Session("stand_bulb", instance="/app/instance.json")   # ~60 s: builds the frozen scene (object poses in instance.json)
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("left", pos, quat_wxyz, linear=3)   # IK (RoboWits' own) to a gripper-tip pose, then joint interpolation
p["move_joints"]("left", q7); p["set_gripper"]("left", 0.0); p["open_gripper"]("left"); p["hold"](10)
s.ee_pose("left"); s.joint_positions(); s.ik("left", pos, quat_wxyz)    # kinematics helpers
s.render_frame("ego")              # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS)
s.render_depth("ego")              # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame("ego")
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (position / velocity / effort limits), grippers, PD gains, tool frames Gripper_Tip_R/L
s.kinematics({"op": "fk", "q": q14})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"Gripper_Tip_R": pose7}, "seed": q14}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("left")   # measured state: 16-vectors in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["set_joint_targets"](q16, steps=1); p["close_gripper"]("left"); p["gripper_quat"](yaw, approach)   # more thin wrappers: help(p[...])
s.step(action)                     # one low-level action (16 joint targets, below) = one control step (1/30 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 16) actions, one row per control step
s.status()                         # {'success': the conditions hold now, 'predicate', 'touching', 'progress', 'sim_steps', 'resets', 'state_sha'}
s.replay(actions)                  # resets, replays open-loop, then the settle window: the verdict  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```

The primitives are deliberately thin: IK moves, joint moves, gripper, hold. You build grasping, placing and every other
skill from them. `s.replay(actions)` runs exactly what the grader runs, settle check included, and returns the verdict
as `success` (why it failed in `settle`); `s.status()["success"]` is the same conditions at one instant, without the
settle check. One `Session` per process (Genesis initialises once). The physics runs on Genesis' bit-deterministic CPU
backend at ~700 control steps/s; the GPU only renders camera images. Do not call `s.close()` before writing every
output. The grader replays with this command; run it to self-check:
`python /opt/tools/rcb_robowits.py replay --task stand_bulb --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Action (16): right arm 7 joint targets (rad), right gripper width (m, 0 closed .. 0.1 open), left arm 7 joint targets,
  left gripper width; absolute position targets tracked by PD controllers. `s.hold_action()` is the no-op.
- Control runs at 30 Hz (4 physics substeps). A `Session` between two resets has at most 200,000 control steps. `s.step`
  returns `True` on the step that reaches it and raises after it until `s.reset()`.
- Grippers open to 10 cm. The gripper tip frame's +z axis is the approach direction and +x the finger-closing direction;
  `p["top_down_quat"](yaw)` builds a vertical-approach orientation whose fingers close along `yaw`.
- World frame: robot base at (0, 0, 1.08), table top at z = 0.76, x points away from the robot, y to its left (the left
  arm works at y > 0). Quaternions are **WXYZ**.

## Others
- Labels in `s.objects()`: `tall object with curved bottom`, `target patch` (the green target area), `stabilizing ring`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 13 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (5 GiB of its memory); `blenderkit` runs in its own container (1 CPU, 4 GiB memory). Over a cap a process can
  be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`, an exact snapshot restore).
