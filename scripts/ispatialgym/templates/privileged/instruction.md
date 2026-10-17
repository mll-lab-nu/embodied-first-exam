# iSpatialGym — privileged mode (the simulator in your container)

You control an **R1Pro** mobile robot with two arms, in a house, through Python. The simulator (iSpatialGym on
BEHAVIOR-1K's OmniGibson, Isaac Sim 5.1) runs in your own container: you can read the state of every object, reset as
often as you like and plan with the full simulator. You hand in one trajectory, and a separate grader replays it.

$goal_rule

## What you hand in
- **One trajectory**: `/app/output/trajectory.npz`, at most **$max_steps rows**, one 23-number action per 30 Hz control
  step ($max_steps_s s of simulated time). Write it with `s.save_trajectory(path)`, which saves `s.rows`.
- **How it is graded.** The grader replays your rows open-loop from the frozen start, in two fresh processes, each within
  $replay_timeout_s s. It scores 1 if both replays succeed (a replay stops at its first success) and both end in the same
  state. A file that is not a `(T, 23)` array `actions` of finite float32 numbers, or that has more than $max_steps rows, scores 0.
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
s = Session("/app")                     # one per process: Isaac Sim starts and the scene loads ($load_mins min
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

The simulator runs at about $steps_per_s control steps per second of wall time. Each simulator process uses about 13 GiB
of memory and 4-5 GiB of GPU memory: run at most two at once.
