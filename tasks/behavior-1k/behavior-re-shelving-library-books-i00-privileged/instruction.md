# BEHAVIOR-1K · re_shelving_library_books (privileged)

## Task
Put the three books into the bookcases.

## Goal
Success: each of the three books is inside a bookcase. It counts only once the scene has settled: nothing the task names
(a tool included) is still in a gripper, and everything has come to rest. The replay of your trajectory ends as soon as
the task is done. After your last row, the robot is held still for a few seconds (as `s.settle()` does). A success that
settles during that time counts, so you need not record that wait. A fall of the robot or a simulator breakdown (a
runaway or non-finite state, e.g. after the robot tumbles) ends the replay as a failure.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, "/app/output/trajectory.npz")`. It
holds `actions` (T, 25), one row per control step, and `task`. It has at most 40,000 rows (22 min of simulated time). A
file that is longer, has another shape or cannot be read scores 0. It is replayed open-loop from the fixed start, the
same way `s.replay(actions)` and the replay CLI do it. A replay can end slightly differently from your run, so leave a
margin. Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when you have
a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
An R1Pro mobile bimanual robot in a simulated house (BEHAVIOR-1K: OmniGibson on Isaac Sim). The scene is one fixed
instance: the objects and the robot start the same way after every reset. You have the full simulator to develop with;
you hand in one replayable trajectory of robot actions, not a general policy.

### Session
`/opt/tools/rcb_behavior.py`, importable as `rcb_behavior` (run `python` from any directory):
```python
from rcb_behavior import Session
s = Session("re_shelving_library_books", instance="/app/instance.json")   # ~3 min: launches Isaac Sim and loads the scene
s.reset()                          # back to the fixed start (as often as you like; approximate within a process, exact in a new one)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # task objects: BDDL name -> category, world position, orientation (xyzw)
p["move_base"](x, y, yaw)          # drive the base straight to a world pose (closed loop; no obstacle avoidance, no planning)
p["move_ee"]("left", pos, quat_xyzw)   # cuRobo IK (trunk + arm, no collision checking), then joint interpolation
p["move_joints"]({"trunk": q4, "left": q7}); p["close_gripper"]("left"); p["open_gripper"]("left"); p["hold"](10)
p["object_in_hand"]("left")        # what assisted grasping attached to that gripper; s.ik({"left": (pos, quat_xyzw)})
s.render_frame("robot_r1:zed_link:Camera:0")   # RGB of a robot camera (s.VIDEO_CAMERAS), 224x224; Session(..., cameras="tiny"): 16x16, cheaper rendering
s.render_depth("robot_r1:zed_link:Camera:0")   # z-depth (H, W) float32 in metres (0 = no reading), pixel-aligned with render_frame
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, image_size, mount
s.robot_spec(); s.robot_state()    # joints with real limits, gripper rule, drive gains, TCP, base limits; measured q/qd/effort, eef/TCP poses
s.kinematics({"op": "fk", "q": q}) # stateless FK / IK ({"op": "ik", "targets": {"left_tcp": pose}, "seed": q}), base frame; s.kinematics_spec()
p["get_robot_pose"](); p["get_eef_pose"]("left"); p["get_object_pose"](name)   # world (position, quaternion xyzw); p["top_down_quat"](yaw)
s.render_grid(); s.start_video(path); s.stop_video(); s.state_sha(); s.episode_done  # camera tiles, mp4 of what follows, state hash
s.robot, s.env, s.get_object(name) # OmniGibson robot / environment / objects (with their object states) for closed-loop control
s.step(action)                     # one low-level action (25 floats, below) = one control step; s.hold_action() holds the targets
s.record_start(); ...; actions = s.record_stop()   # (T, 25) actions, one row per control step (30 Hz)
s.status()                         # {'success', 'goal', 'goal_objects_held', 'goal_objects_moving', 'fallen', 'breakdown', 'q_score', 'sim_steps', 'state_sha', ...}
s.settle()                         # hold still up to 5 s (150 control steps), as the grader does after your last row
s.replay(actions)                  # resets, replays open-loop + settle(), returns status (the first replay in a process is exact)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # tiled robot cameras while replaying (with cameras="tiny": 16x16 tiles, upscaled)
```
- The scene is `house_double_floor_upper`; the task's objects (`s.objects()`, the names the primitives take):
  `book.n.02_1` to `_3`, `table.n.02_1`.
- The primitives are deliberately thin (joint, base, IK and gripper moves): navigation, grasping, placing and every
  other skill are yours to build from them. Primitives that take an `arm` ("left" / "right") default to the left one.
- In `s.status()`, `success` is the success above, and `goal` covers the task's conditions alone. `goal_objects_held` /
  `goal_objects_moving` say what keeps those conditions from counting. `s.goal_objects` lists every object the task
  names, a tool or appliance included. `fallen` and `breakdown` report the failures.
- OmniGibson itself is installed (`/behavior-src/OmniGibson`) with its own libraries; `/behavior-src` and the tooling in
  `/opt/tools` are read-only.
- The replay CLI does what the grader does; run it to check yourself:
  `python /opt/tools/rcb_behavior.py replay --task re_shelving_library_books --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- Coordinates are in the world frame (metres, +z up); quaternions are XYZW (OmniGibson's convention); yaw in radians.
- An action has 25 entries: base (3), trunk (4), left arm (7), left gripper (2), right arm (7), right gripper (2);
  indices per controller: `s.robot.controller_action_idx`. Trunk, arm and gripper entries are absolute joint targets. A
  gripper is 2 finger targets, 0 = closed. Grasping is assisted: a closing gripper holds what it touches and lets go
  only when both fingers are commanded open. The base entries are x, y, yaw position targets in the robot's own frame.
  They are re-applied every control step, so they act as a per-step displacement; 0 = stand still. `s.hold_action()`
  (the last command with the base at 0) is the no-op.
- Control runs at 30 Hz with 120 Hz physics. An episode ends after at most 200,000 control steps (1.85 h of simulated
  time).

### Observations
- While the robot moves, the cameras' frames lag the physics by 2 control steps; `s.camera_info()` gives the pose they
  were rendered with.

## Others
- Do not call `s.close()` until you have written every output: it ends the process.

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 29 GiB memory, 8192 processes and threads, 32 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (22 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
