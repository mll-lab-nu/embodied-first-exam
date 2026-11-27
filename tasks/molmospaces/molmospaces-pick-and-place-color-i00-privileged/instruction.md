# MolmoSpaces · pick-and-place-color (privileged)

## Task
Put the small dark bird in the red bowl.

## Goal
Success: the small dark bird rests in or on the red bowl, the robot has let go of it, and the red bowl has not been
pushed far or tipped over. Your trajectory is replayed from the fixed start. What counts is the state after its last
action. Rows past the step limit (Limits) are never run. To stop there once the task holds, end your trajectory.

Deliverable: `/app/output/trajectory.npz` with `actions`, float64 (T, 8), one row per control step (the layout is under
Actions); at most 100,000 rows (a longer file scores 0). `s.save_trajectory(rows, "/app/output/trajectory.npz")` writes
it. It is replayed open-loop from the fixed start. Leave the script that produced it at `/app/output/gen.py`. Also leave
`/app/output/rcb_session_log.jsonl` where it is: the tooling writes it with your sessions, resets and simulated steps,
reported as cost. That log is not graded. Save a valid trajectory early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) in a simulated house (Ai2's MolmoSpaces,
MuJoCo). The episode is one fixed instance: the house, every object and the robot start the same way after every reset.
You have the full simulator to develop with; you hand in one open-loop trajectory of robot actions, not a general
policy.

### Session
`/opt/tools/rcb_molmospaces.py`, importable as `rcb_molmospaces` (run `python` from any directory):
```python
from rcb_molmospaces import Session
s = Session("/app/instance.json")    # builds the episode (10-40 s: the Franka scenes ~10 s, the RB-Y1 houses up to ~40 s)
s.layout; row = s.hold_row()         # the row layout; the row that keeps every controller at its current target
s.step(row)                          # one control step = one simulator Task.step; False once the episode is over
s.done; s.status()                   # the simulator's is_done(); {"success", "done", "steps", "horizon", "state_sha", "resets"}
s.state()                            # {"bodies": {name: [x y z qw qx qy qz]}, "joints": {name: [qpos]}, "task", "time", "mujoco"}
s.model, s.data                      # the live MuJoCo model and data (read them; changing them is not part of the replay)
s.render(cam); s.render_depth(cam)   # uint8 (H, W, 3); float32 (H, W) depth in m. Cameras: s.cameras
s.camera_info(cam)                   # intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.proprio(); s.robot_spec()          # joint pos / vel / effort, gripper openings, tcp poses; joints, limits, commands
s.kinematics({"op": "fk", "q": q})   # the robot's kinematic model, no physics: tcp poses for joint positions q
s.kinematics({"op": "ik", "targets": {"gripper": pose7}})   # joint positions for a tcp pose (x y z qw qx qy qz)
s.reset()                            # back to the fixed start (as often as you like)
s.replay(rows)                       # reset, run the rows, return the status
s.save_trajectory(rows, "/app/output/trajectory.npz")
```
- `q` follows `s.kinematics_spec()["joint_names"]`; poses are x y z qw qx qy qz.
- The simulator's package `molmo_spaces` is installed (without its scripted experts); the episode is
  `/app/instance.json`.
- The replay CLI does what the grader does; run it to check yourself:
  `python /opt/tools/rcb_molmospaces.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- The house's world frame, z up, metres; quaternions wxyz.
- A row (`s.layout`) has 8 entries, the targets of the robot's joint-position controllers, in this order: `fr3_joint1`,
  `fr3_joint2`, `fr3_joint3`, `fr3_joint4`, `fr3_joint5`, `fr3_joint6`, `fr3_joint7`, `gripper` (fr3_joint1..7 in rad;
  gripper: the Robotiq command, 0 = open .. 255 = closed). At t = 0 the gripper is open and its target is 0.
- One control step is 0.066 s of simulated time (MuJoCo steps of 2 ms). A row holds until the next one. `s.hold_row()`
  keeps every controller at its current target.

## Others
- `s.state()["task"]`: `pickup_obj_name` is the small dark bird, `place_receptacle_name` the red bowl.
- Physics is MuJoCo on the CPU: the same rows from the same start give the same result every time.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 7 CPUs, 20 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (7 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
- Steps: at most 606 control steps (the benchmark's 40 s horizon), then the replay stops.
