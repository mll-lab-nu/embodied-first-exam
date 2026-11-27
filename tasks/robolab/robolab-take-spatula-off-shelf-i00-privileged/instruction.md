# RoboLab · take_spatula_off_shelf (privileged)

## Task
Take the spatula off the wire shelf and put it on the table.

## Goal
Success: the spatula is off the wire shelf and lies on the table, and neither gripper finger touches it. The replay of
your trajectory ends as soon as the task is done (later rows are never executed).

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, "/app/output/trajectory.npz")`. It
holds `task` and `actions`, a (T, 8) float array of at most 100,000 rows (one per control step, 1.9 h of robot time).
Anything else (another shape, NaN, more rows, a file that is not such an npz) scores 0. It is replayed open-loop from
the fixed start, the same way `s.replay(actions)` and the replay CLI do it. A replay can end slightly differently from
your run, so leave a margin. Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and
overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A Franka Panda arm with a Robotiq 2F-85 gripper at a table (NVIDIA RoboLab's DROID setup, Isaac Sim / PhysX). The scene
is one fixed instance: the objects and the robot start the same way after every reset. You have the full simulator to
develop with; you hand in one replayable trajectory of robot actions, not a general policy.

### Session
`/opt/tools/rcb_robolab.py`, importable as `rcb_robolab` (run `python` from any directory):
```python
from rcb_robolab import Session
s = Session("take_spatula_off_shelf", instance="/app/instance.json")   # ~1-2 min: launches Isaac Sim, builds the scene, restores the frozen state
s.reset()                          # back to the frozen initial state, as often as you like (not every PhysX internal: see Others)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, bounds, size, velocity (env-local frame)
p["move_ee"](pos, quat_wxyz, speed=0.2)   # straight-line fingertip move, one differential-IK update per control step
p["move_joints"](q7); p["set_gripper"](True); p["open_gripper"](); p["hold"](10)
s.ee_pose(); s.joint_positions(); s.ik_step(pos, quat_wxyz)      # kinematics helpers (differential IK, one update per call)
s.render_frame("egocentric_mirrored_camera")   # RGB uint8 of one camera, current state (s.VIDEO_CAMERAS); s.render_grid()
s.step(action)                     # one low-level action (7 joint targets + gripper command) = one control step (1/15 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 8) actions, one row per control step
s.status()                         # {'success': bool, 'progress': float, 'sim_steps': int, 'resets': int, 'state_sha': str, 'terminated': bool}
s.replay(actions)                  # resets, replays open-loop, returns status (the first replay in a process is exact)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state, writes a tiled camera video
s.render_depth("wrist_cam")        # with Session(..., depth=True) (steps ~13 % slower): float32 (H,W) z-depth in metres (0 = no reading), pixel-aligned with render_frame(cam)
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world->camera, OpenCV axes), cam2world_gl, mount, moves
s.robot_spec(); s.proprio()        # joints + limits, gripper, gains, tool frames; measured joint pos/vel, tcp pose, opening, efforts
s.kinematics({"op": "fk", "q": q7}); s.kinematics({"op": "ik", "targets": {"tcp": pose7}, "seed": q7})   # stateless FK / IK (s.kinematics_spec())
s.gripper_angle(); s.eef_frame_pose(); s.body_pose("base_link")   # finger_joint (rad); the flange frame; any robot link's pose
p["get_object_points"](name); p["get_object_pose"](name)          # an object's surface points (N,3) / (pos, quat wxyz)
p["set_joint_targets"](a8, steps=1); p["get_joint_targets"]()     # raw 8-D targets for `steps` control steps; the targets in force
s.start_video("/app/output/try.mp4"); ...; s.stop_video()          # film the steps in between; s.state_sha(): the state's hash
```
- The scene's objects (`s.objects()`, the names the primitives take): `wireshelving_a01`, `spatula_01`, `plate_small`,
  `fork_big`, `fork_small`, `ceramic_mug`, `mug`, `mug_01`, `table`.
- The primitives are deliberately thin: IK moves, joint moves, gripper, hold. You build grasping, placing and every
  other skill from them.
- The replay CLI does what the grader does; run it to check yourself:
  `python /opt/tools/rcb_robolab.py replay --task take_spatula_off_shelf --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Frame: env-local = the robot's root frame (the Franka base at the origin, x forward towards the table, z up).
  Quaternions are WXYZ. `s.objects()["table"]["bounds"][1][2]` is the table-top height.
- An action has 8 entries: panda_joint1..7 absolute joint-position targets (rad, PD-tracked) and the gripper command (0
  = open, 1 = close; the Robotiq action is binary). `s.hold_action()` is the no-op. Control runs at 15 Hz (sim dt 1/120
  s, decimation 8). An episode ends after at most 100,000 control steps, which is also the most a trajectory may hold.
- `s.ee_pose()` and every primitive use the fingertip-centre tool frame. It is RoboLab's `eef_frame` (the gripper
  flange, `s.eef_frame_pose()`) moved 0.162 m along the approach axis, to the ends of the closed fingertips. The pads
  extend ~5.7 cm back from there, so for a low object the frame goes almost down to the table. `p["top_down_quat"](yaw)`
  gives its orientation for a vertical approach, with the finger-closing direction rotated by `yaw` (rad, about z) from
  the reset pose. At yaw 0 the fingers close along `p["get_finger_closing_dir"]()` (world y at the reset pose).
  `p["yaw_for_closing_dir"]([dx, dy])` gives the yaw for any horizontal closing direction. The Robotiq opens to 8.5 cm.
- One `Session` per process (Isaac Sim launches once, ~70 s; the scene ~30 s more). Physics is PhysX on the CPU,
  rendering on the GPU; ~15 control steps/s.

After your last row, its command is held for about two seconds more, so a release in the last rows completes. A
trajectory that ends with an object in the gripper goes on holding it.

## Others
- The episode ends by itself the moment the task is done: after that `s.step` raises and the primitives become no-ops,
  so stop recording there.
- Do not call `s.close()` before you have written every output.
- The first episode of a process (a live run before any `s.reset()`, or the first `s.replay()`) ends in the same state
  as the grader's replay of the same actions. After `s.reset()` the state is restored, but not every PhysX internal. So
  a live run recorded after a reset, and later replays in the same process, can end differently: a success after a few
  resets has failed the grader's replay. Record the final trajectory from the first episode of a new process, and check
  it with the replay CLI, which runs in a new process.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 29 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (22 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
