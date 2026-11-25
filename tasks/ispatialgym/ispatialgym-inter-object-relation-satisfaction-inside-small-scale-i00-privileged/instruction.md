# iSpatialGym · make the scene look like a picture (privileged)

## Task
Make the scene look like the goal image /app/goal.png, the head camera's view once the task is done; the robot itself
does not have to match it.

## Goal
Success: the objects that matter stand as the picture shows them (what is on, in, under, next to or touching what, what
is open, what the robot holds and what it has let go of); one object stands roughly where the picture shows it, turned
roughly as there, and a second one roughly where the picture shows it; then the robot and those objects stay still for
at least a second and a half.

A replay ends as soon as the task is done, and also at your last row: end the trajectory with at least a second and a
half of the robot standing still.

Deliverable: `/app/output/trajectory.npz`: an array `actions` of shape `(T, 23)`, finite float32 numbers, at most 2370
rows, one action per 30 Hz control step (79.0 s of simulated time); write it with `s.save_trajectory(path)`, which saves
`s.rows`. The grader replays it open-loop from the frozen start and scores 1 if the replay succeeds; a file of another
shape or with more than 2370 rows scores 0. Leave the script that made it at `/app/output/gen.py`. Save a valid one
early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
An R1Pro mobile robot with two arms, in a simulated house (iSpatialGym on BEHAVIOR-1K's OmniGibson). You have the full
simulator to develop with; you hand in a trajectory of robot actions.

### Session
`/opt/tools/rcb_ispatialgym.py`, on `PYTHONPATH`:
```python
from rcb_ispatialgym import Session
s = Session("/app")                     # one per process: Isaac Sim starts and the scene loads
                                        # (7 min; the first start in a container is the slowest)
a = s.hold_action()                     # 23 floats: the current targets with the base at rest (the no-op)
s.step(a)                               # one control step; s.rows holds every row since the start or the last reset
s.reset()                               # back to the start in this process (approximate); clears s.rows
s.cameras(); s.frames(cams)             # the three RGB cameras, 1080x1080, after the last step: {camera: uint8 (H, W, 3)}
s.extrinsics(cams)                      # per camera, odometry frame -> camera (3x4, OpenCV axes) of its last frame
s.robot_spec(); s.proprio_layout(); s.proprio_row()   # joints and limits, the gripper rule, the TCP; named proprioception
s.kinematics_spec(); s.kinematics({"op": "fk", "q": q}); s.kinematics({"op": "ik", "targets": {"left_tcp": pose}, "seed": q})
s.env, s.robot                          # OmniGibson's environment and robot: every object's pose and state
s.state_sha(); s.save_trajectory("/app/output/trajectory.npz")
```
Check a trajectory the way the grader replays it, from the frozen start in a process of its own (it prints the final
state's hash, not a verdict):
```
python /opt/tools/rcb_ispatialgym.py replay --instance /app --traj /app/output/trajectory.npz [--video V.mp4]
```
The simulator runs at about 7 control steps per second of wall time. Each simulator process uses about 13 GiB of memory
and 4-5 GiB of GPU memory: run at most two at once.

### Actions
Layout (`s.robot.controller_action_idx`): base (3), trunk (4), left arm (7), left gripper (1), right arm (7), right
gripper (1).
- Base: a velocity command in [-1, 1] in the robot's own frame (forward, left, yaw rate), scaled to 0.75 m/s, 0.75 m/s
  and 1 rad/s. Zeros stop the base.
- Trunk and arms: absolute joint targets in rad.
- Grippers: one command each in [-1, 1]: -1 closed, 1 fully open, values in between set the fingers' target as a
  fraction of their travel. Grasping is assisted: closing on an object holds whatever the finger pads touch, and the
  hand lets go only at 1.

### Observations
- Frames and units: the odometry frame is the robot's `base_link` at the start (x forward, y left, z up); `s.env` also
  gives the world frame. Quaternions are XYZW, lengths in m, angles in rad.
- Cameras: `s.cameras()` names the three RGB cameras (head `robot_r1:zed_link:Camera:0`, the goal image's camera, and
  the two wrists), 1080 × 1080; `s.frames(cams)` gives their images after the last step and `s.extrinsics(cams)` their
  poses (odometry frame to camera, OpenCV axes). While the robot moves, a camera frame shows the scene 2 control steps
  earlier.
- `s.env` and `s.robot` are OmniGibson's environment and robot: every object's pose and state. OmniGibson and
  iSpatialGym's simulator code are installed; this tooling gives you no motion primitives or planners (only what the
  installed packages themselves ship): moving the robot is up to you.

### Goal image
`/app/goal.png` is what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the
same camera, resolution and intrinsics as the robot's own head camera.

## Others
- Nothing installed here knows the goal: `/app/instance.json` is only the start, and your simulator never reports
  success.
- `s.reset()` returns to the start in the same process, close to but not exactly the frozen state; a new process starts
  exactly from it, as the grader's replay does: check the trajectory you hand in with the replay command above.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 12 CPUs, 38 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (22 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`, approximate; a new process starts exactly from the frozen start).
