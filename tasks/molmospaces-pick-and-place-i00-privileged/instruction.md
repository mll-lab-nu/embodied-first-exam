# MolmoSpaces · pick-and-place — frozen episode

**Task:** Pick up the realistic small white bird with feathers and place it in or on the black bowl with colorful grid.

You control a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) in one episode of Ai2's MolmoSpaces benchmark (upstream package `procthor-objaverse/FrankaPickandPlaceHardBench/FrankaPickandPlaceHardBench_20260206_json_benchmark`,
episode 134: an Objaverse object), simulated by upstream's own code (molmo-spaces 0.2.9, MuJoCo 3.5.0) via Python.
The episode is frozen: the house, every object and the robot start the same way after every reset, and you may reset as
often as you like. Your deliverable is **one open-loop trajectory**, not a general policy.

## Success (upstream's rule, judged by upstream's code)
The episode ends after the last row of your trajectory, or after **606 control steps** (the benchmark's
40 s horizon at 15.152 Hz), whichever comes first. Success is upstream's `judge_success()` on the state
at that moment: the robot does not touch the object; the receptacle supports the object (it carries at least 50% of the object's weight through contact, or the object lies on it by upstream's on-receptacle test, or the object is within 5 mm and 10 degrees, relative to the receptacle, of a pose in which it was supported at an earlier control step); and the receptacle has moved at most 15 cm and tilted at most 60 degrees from its start pose. The task has to hold at the end: met earlier and undone by then does not count, and ending
your trajectory right after the task is met is how you stop there.

## Deliverable
`/app/output/trajectory.npz` with `actions`: float64 (T, 8), one row per control step, the targets of upstream's
joint-position controllers in this order: `fr3_joint1`, `fr3_joint2`, `fr3_joint3`, `fr3_joint4`, `fr3_joint5`, `fr3_joint6`, `fr3_joint7`, `gripper` (fr3_joint1..7 in rad; gripper: the Robotiq command, 0 = open .. 255 = closed). At t = 0 the gripper is open and its target is 0. `s.save_trajectory(rows)` writes it. Also leave the
script that produced it at `/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as
you improve it: whatever is in `/app/output/` when your 3600 s are up is graded. The tooling also writes
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
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **7 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.
