# iSpatialGym — privileged mode (the simulator in your container)

You control an **R1Pro** mobile robot with two arms, in a house, through Python. The simulator (iSpatialGym on
BEHAVIOR-1K's OmniGibson, Isaac Sim 5.1) runs in your own container: you can read the state of every object, reset as
often as you like and plan with the full simulator. You hand in one trajectory, and a separate grader replays it.

## Your task: make the scene look like a picture
`/app/goal.png` is what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the same
camera, resolution and intrinsics as the robot's own head camera. Change the scene so that it looks like the picture. No
sentence here names the objects that matter or what to do with them: the picture is the whole task. The robot does not have to
match the picture (its arms, grippers and base may be anywhere), and nothing the picture does not show is judged.

## When a replay succeeds
The grader judges each replay of your trajectory (`## What you hand in`).
After every control step it checks three conditions:
1. **Relations.** The objects the task is about stand in the relations the picture shows: what is on, in, under, next to
   or touching what, what is open, and which objects the robot holds or has let go of.
2. **Poses.** Every pose the task measures is within its tolerance of the pose in the picture:
   - one object's pose: position within 0.09 m, orientation within 0.3 rad (17.2°)
   - one object's pose: position within 0.09 m, orientation within 0.3 rad (17.2°)
3. **At rest.** Conditions 1 and 2 have both held at every one of the last **45 control steps** (1.5 s of
   simulated time), and during those steps the objects the task is about and the robot itself are still:
   - at every step, each of them moves slower than 0.001 m/s and 0.005 rad/s, and each robot joint slower than 0.02 rad/s;
   - over the whole window, none of them drifts more than 0.01 m or 0.05 rad, and no robot joint more than 0.05.

A replay succeeds at the first control step where all three hold, which is the last step of that window. This text does
not say which objects the task is about: the picture shows them.

**Once the scene looks right, stop the robot and keep it still for at least 45 control steps.** A replay stops at
your last row, so end your trajectory with at least 45 rows of the robot standing still (for example
`s.hold_action()` rows once the base has stopped).

## What you hand in
- **One trajectory**: `/app/output/trajectory.npz`, at most **2214 rows**, one 23-number action per 30 Hz control
  step (73.8 s of simulated time). Write it with `s.save_trajectory(path)`, which saves `s.rows`.
- **How it is graded.** The grader replays your rows open-loop from the frozen start, in two fresh processes, each within
  2400 s. It scores 1 if both replays succeed (a replay stops at its first success) and both end in the same
  state. A file that is not a `(T, 23)` array `actions` of finite float32 numbers, or that has more than 2214 rows, scores 0.
- **Save early.** Only what is in `/app/output/` when your time runs out is graded: save a trajectory as soon as you have
  one and overwrite it when you have a better one. Also leave the script that made it at `/app/output/gen.py`.

## What is in your container
- **Nothing here judges the task.** `/app/instance.json` is the frozen start only: the scene, the robot and where
  everything stands. It holds no goal, no target and no success check, and neither does anything else installed here, so
  your own simulator never reports success. The grader has the goal, in its own sandbox.
- **Only the first episode in a process is bit-exact.** `s.reset()` returns to the start in the same process, close to
  but not exactly the frozen state; a fresh process starts exactly from it. Check your trajectory the way the grader runs
  it, in a fresh process (it prints the final state hash, not a verdict):
  `python /opt/tools/rcb_ispatialgym.py replay --instance /app --traj /app/output/trajectory.npz [--video V.mp4]`

## Tooling (`/opt/tools/rcb_ispatialgym.py`, on `PYTHONPATH`)
```python
from rcb_ispatialgym import Session
s = Session("/app")                     # one per process: Isaac Sim starts and the scene loads (8-17 min
                                        # measured; the first start in this container, while Isaac compiles its shaders, is the slow one)
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
Frames and units: the odometry frame is the robot's `base_link` at the start (x forward, y left, z up); `s.env` also gives
the world frame. Quaternions are XYZW, lengths in m, angles in rad. While the robot moves, a camera frame shows the scene
2 control steps earlier. OmniGibson and iSpatialGym's simulator code are installed. This tooling gives you no motion
primitives or planners (only what the installed packages themselves ship): moving the robot is up to you.

### The action (23 numbers per row)
Layout (`s.robot.controller_action_idx`): base (3), trunk (4), left arm (7), left gripper (1), right arm (7), right
gripper (1).
- **Base**: a velocity command in [-1, 1] in the robot's own frame (forward, left, yaw rate), scaled to 0.75 m/s, 0.75 m/s
  and 1 rad/s. Zeros stop the base.
- **Trunk and arms**: absolute joint targets in rad.
- **Grippers**: one command each in [-1, 1]: -1 closed, 1 fully open, values in between set the fingers' target as a
  fraction of their travel. Grasping is assisted: closing on an object holds whatever the finger pads touch, and the hand
  lets go only at 1.

The simulator runs at about 5 control steps per second of wall time. Each simulator process uses about 13 GiB
of memory and 4-5 GiB of GPU memory: run at most two at once.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **22 GiB of GPU memory**, **32 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 12 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
