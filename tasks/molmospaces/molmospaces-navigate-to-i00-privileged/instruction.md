# MolmoSpaces · navigate-to (privileged)

## Task
A Rainbow Robotics RB-Y1 mobile manipulator (holonomic base, 6-joint torso, two 7-joint arms with parallel grippers,
head camera) in a simulated house (Ai2's MolmoSpaces, MuJoCo). Navigate to any tablelamp (2 available). The episode is
one fixed instance: the house, every object and the robot start the same way after every reset. You have the full
simulator to develop with; you hand in one open-loop trajectory of robot actions, not a general policy.

## Goal
Success: the robot stands within about 1.5 m of a table lamp, and that lamp shows in its head camera; of the two lamps,
the one nearest the robot counts. What counts is how things stand after the last action of your trajectory, replayed
from the fixed start: a success reached earlier and lost by the end does not count. Rows past the step limit (Limits)
are never run: ending your trajectory once the task holds is how you stop there.

Deliverable: `/app/output/trajectory.npz` with `actions`, float64 (T, 25), one row per control step (the layout is under
Actions); at most 100,000 rows (a longer file scores 0). `s.save_trajectory(rows, "/app/output/trajectory.npz")` writes
it. It is replayed open-loop from the fixed start. Leave the script that produced it at `/app/output/gen.py`, and leave
`/app/output/rcb_session_log.jsonl` where it is (the tooling writes it: your sessions, resets and simulated steps,
reported as cost; not graded). Save a valid trajectory early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the trajectory counts: changing the live MuJoCo model or data while you develop is not part of the replay.

## Robot Interface
### Session
`/opt/tools/rcb_molmospaces.py`, importable as `rcb_molmospaces` (run `python` from any directory):
```python
from rcb_molmospaces import Session
s = Session("/app/instance.json")    # builds the episode (10-40 s: the Franka scenes ~10 s, the RB-Y1 houses up to ~40 s)
s.layout; row = s.hold_row()         # the row layout; the row that keeps every controller at its current target
s.step(row)                          # one control step = one upstream Task.step; False once the episode is over
s.done; s.status()                   # upstream's is_done(); {"success", "done", "steps", "horizon", "state_sha", "resets"}
s.state()                            # {"bodies": {name: [x y z qw qx qy qz]}, "joints": {name: [qpos]}, "task", "time", "mujoco"}
s.model, s.data                      # the live MuJoCo model and data (read them; changing them is not part of the replay)
s.render(cam); s.render_depth(cam)   # uint8 (H, W, 3); float32 (H, W) depth in m. Cameras: s.cameras
s.camera_info(cam)                   # intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.proprio(); s.robot_spec()          # joint pos / vel / effort, gripper openings, tcp poses; joints, limits, commands
s.kinematics({"op": "fk", "q": q})   # upstream's kinematic model, no physics: tcp poses for joint positions q
s.kinematics({"op": "ik", "targets": {"left_gripper": pose7}})   # joint positions for a tcp pose (x y z qw qx qy qz)
s.reset()                            # back to the fixed start (as often as you like)
s.replay(rows)                       # reset, run the rows, return the status
s.save_trajectory(rows, "/app/output/trajectory.npz")
```
- `q` follows `s.kinematics_spec()["joint_names"]`; poses are x y z qw qx qy qz.
- Upstream's package `molmo_spaces` is installed (without its scripted experts); the episode is `/app/instance.json`.
- The replay CLI does what the grader does; run it to check yourself:
  `python /opt/tools/rcb_molmospaces.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

### Actions
- The house's world frame, z up, metres; quaternions wxyz.
- A row (`s.layout`) has 25 entries, the targets of upstream's joint-position controllers, in this order: `base_x`,
  `base_y`, `base_theta`, `torso_0`, `torso_1`, `torso_2`, `torso_3`, `torso_4`, `torso_5`, `left_arm_0`, `left_arm_1`,
  `left_arm_2`, `left_arm_3`, `left_arm_4`, `left_arm_5`, `left_arm_6`, `right_arm_0`, `right_arm_1`, `right_arm_2`,
  `right_arm_3`, `right_arm_4`, `right_arm_5`, `right_arm_6`, `left_gripper`, `right_gripper` (base_x, base_y in m and
  base_theta in rad (world frame); torso, arm joints in rad; grippers: the finger motor's force, -100 .. 100 (positive
  closes, negative opens, 0 exerts none)).
- One control step is 0.2 s of simulated time (MuJoCo steps of 2 ms); a row holds until the next one, and `s.hold_row()`
  keeps every controller at its current target.

## Others
Physics is MuJoCo on the CPU: the same rows from the same start give the same result every time.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 7 CPUs, 20 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (7 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
- Steps: at most 500 control steps (the benchmark's 100 s horizon); the replay stops there.
