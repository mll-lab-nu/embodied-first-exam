# MuJoCo Playground · Panda pick cube with orientation

A **Franka Panda** arm stands in front of a **green box** (4 × 4 × 6 cm) on the floor. A **translucent red target box**
floats above, tilted.
**Task:** pick up the green box and hold it **at the target, in the target's orientation**. This is MuJoCo Playground's
`PandaPickCubeOrientation`, run here in plain MuJoCo; the box and target poses are randomized as in Playground, with
a fixed seed.

## What you hand in
`/app/output/trajectory.npz` — actuator targets, shape `(T, 8)` (T ≤ 3000), one row per control step (1/50 s), each held
for 4 physics steps. Record it with the tooling so the layout is right. The verifier replays it from the frozen start
in a separate sandbox (MuJoCo on CPU is bit-exact). Leave the script that produced it at `/app/output/gen.py`.

## Success
At the **end of the trajectory** the box's centre is within **2 cm** of the target's centre (`s.target_pos`) and its
orientation within **15°** of the target's (`s.target_quat_wxyz`, w x y z). `s.check()` computes exactly this.

## Tooling (`/opt/tools/rcb_panda.py`, importable as `rcb_panda`)
```python
import numpy as np, rcb_panda as rp
s = rp.Session("/app/instance.json")    # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # qpos, qvel, targets, gripper_pos, gripper_mat, object_pos, object_quat_wxyz, target_pos,
                    #   target_quat_wxyz, plus the success check fields
s.record_start()
r = s.step(targets) # (8,) actuator targets for one control step -> the success check fields
A = s.record_stop(); s.save_trajectory(A)          # -> /app/output/trajectory.npz
s.replay(A)         # fresh replay from the start (what the verifier does)
s.reset()           # back to the start (as often as you like)
img = s.render()                                    # RGB (240, 320, 3); s.render_grid() gives four views
```
Actuators: `actuator1..7` = joint position targets (rad) for `joint1..joint7`, `actuator8` = finger opening (0 = closed
… 0.04 m = open). Limits: `s.lower`, `s.upper`. The site `gripper` sits between the fingertips; the hand approaches
along the site's z axis and the fingers close along its y axis. Everything in `s.model` / `s.data` is readable
(privileged mode), e.g. for inverse kinematics with `mujoco.mj_jacSite`.

## Rules
- Write your own controller; do not use trained policies from MuJoCo Playground or elsewhere.
- Only the actuator targets count: editing `s.data` while debugging changes nothing in the replay.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of GPU memory**, **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
