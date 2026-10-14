# MolmoSpaces · navigate-to — frozen episode

**Task:** Navigate to any tablelamp (2 available).

You control a Rainbow Robotics RB-Y1 mobile manipulator: holonomic base, 6-joint torso, two 7-joint arms with parallel grippers, head camera in one episode of Ai2's MolmoSpaces benchmark (upstream package `holodeck-objaverse/NavToObjDataGenConfig/NavToObjHolodeckBench_20260115_json_benchmark`,
episode 237: several objects of the target type (the nearest counts)), simulated by upstream's own code (molmo-spaces 0.2.9, MuJoCo 3.5.0) via Python.
The episode is frozen: the house, every object and the robot start the same way after every reset, and you may reset as
often as you like. Your deliverable is **one open-loop trajectory**, not a general policy.

## Success (upstream's rule, judged by upstream's code)
The episode ends after the last row of your trajectory, or after **500 control steps** (the benchmark's
100 s horizon at 5 Hz), whichever comes first. Success is upstream's `judge_success()` on the state
at that moment: for the one of the 2 target objects nearest to the robot base (horizontal distance), the horizontal distance from the base to its position (the origin of its body, not its nearest surface) is less than 1.5 m and at least one of its pixels shows in head_camera. The task has to hold at the end: met earlier and undone by then does not count, and ending
your trajectory right after the task is met is how you stop there.

## Deliverable
`/app/output/trajectory.npz` with `actions`: float64 (T, 25), one row per control step, the targets of upstream's
joint-position controllers in this order: `base_x`, `base_y`, `base_theta`, `torso_0`, `torso_1`, `torso_2`, `torso_3`, `torso_4`, `torso_5`, `left_arm_0`, `left_arm_1`, `left_arm_2`, `left_arm_3`, `left_arm_4`, `left_arm_5`, `left_arm_6`, `right_arm_0`, `right_arm_1`, `right_arm_2`, `right_arm_3`, `right_arm_4`, `right_arm_5`, `right_arm_6`, `left_gripper`, `right_gripper` (base_x, base_y in m and base_theta in rad (world frame); torso, arm joints in rad; grippers: the finger motor's force, -100 .. 100 (positive closes, negative opens, 0 exerts none)). `s.save_trajectory(rows)` writes it. Also leave the
script that produced it at `/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as
you improve it: whatever is in `/app/output/` when your time is up is graded. The tooling also writes
`/app/output/rcb_session_log.jsonl` (your sessions, resets and simulated steps, reported as cost; not graded): leave it
there.

## Tooling (installed; `python` from any directory)
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
s.reset()                            # rebuild the frozen episode
s.replay(rows)                       # reset, run the rows, return the status
s.save_trajectory(rows, "/app/output/trajectory.npz")
```
`q` follows `s.kinematics_spec()["joint_names"]`. The upstream package `molmo_spaces` is installed (without its scripted
experts); the frozen episode is `/app/instance.json`. The grader runs exactly this CLI in two fresh processes, so run it
to check yourself:
`python /opt/tools/rcb_molmospaces.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame of the house, z up, metres; quaternions **wxyz**.
- One control step is 0.2 s of simulated time (MuJoCo steps of 2 ms); a row holds until the next one.
- Physics is MuJoCo on the CPU: the same rows from the same start give the same result in every fresh process.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **7 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
