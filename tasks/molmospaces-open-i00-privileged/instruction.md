# MolmoSpaces · open — frozen episode

**Task:** Open the cabinet.

You control a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) in one episode of Ai2's MolmoSpaces benchmark (upstream package `ithor/FrankaOpenHardBench/FrankaOpenHardBench_20260206_json_benchmark`,
episode 49: a hinged door (revolute joint)), simulated by upstream's own code (molmo-spaces 0.2.9, MuJoCo 3.5.0) via Python.
The episode is frozen: the house, every object and the robot start the same way after every reset, and you may reset as
often as you like. Your deliverable is **one open-loop trajectory**, not a general policy.

## Success (upstream's rule, judged by upstream's code)
The episode ends after the last row of your trajectory, or after **455 control steps** (the benchmark's
30 s horizon at 15.152 Hz), whichever comes first. Success is upstream's `judge_success()` on the state
at that moment: some joint of any cabinet in the room is open at least 15% of its range (all start closed). The task has to hold at the end: met earlier and undone by then does not count, and ending
your trajectory right after the task is met is how you stop there.

## Deliverable
`/app/output/trajectory.npz` with `actions`: float64 (T, 8), one row per control step, the targets of upstream's
joint-position controllers in this order: `fr3_joint1`, `fr3_joint2`, `fr3_joint3`, `fr3_joint4`, `fr3_joint5`, `fr3_joint6`, `fr3_joint7`, `gripper` (fr3_joint1..7 in rad; gripper: the Robotiq command, 0 = open .. 255 = closed). At t = 0 the gripper is open and its target is 0. `s.save_trajectory(rows)` writes it. Also leave the
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
s.kinematics({"op": "ik", "targets": {"gripper": pose7}})   # joint positions for a tcp pose (x y z qw qx qy qz)
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
- One control step is 0.066 s of simulated time (MuJoCo steps of 2 ms); a row holds until the next one.
- Physics is MuJoCo on the CPU: the same rows from the same start give the same result in every fresh process.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **7 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
