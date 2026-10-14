# MuJoCo Playground · ALOHA hand-over

An **ALOHA 2** bimanual robot (two ViperX 300s arms facing each other across a table) has a **red box** on the left
arm's side of the table and a **translucent red target box** floating on the right arm's side.
**Task:** pick up the box with the **left** arm, **hand it over** to the **right** arm, and have the right arm hold it
at the target. This is MuJoCo Playground's `AlohaHandOver`, run here in plain MuJoCo; the box and target positions are
randomized as in Playground, with a fixed seed.

## What you hand in
`/app/output/trajectory.npz` — actuator targets, shape `(T, 14)` (T ≤ 3000), one row per control step (1/50 s), each
held for 4 physics steps. Record it with the tooling so the layout is right. The verifier replays it from the frozen
start in a separate sandbox (MuJoCo on CPU is bit-exact). Leave the script that produced it at `/app/output/gen.py`.

## Success
At the **end of the trajectory** the box's centre is within **3 cm** of the target's centre (`s.target_pos`), the box
touches the **right** gripper's fingers and **nothing of the left arm**, and it is off the table (z ≥ 0.05 m).
`s.check()` computes exactly this.

## Tooling (`/opt/tools/rcb_aloha.py`, importable as `rcb_aloha`)
```python
import numpy as np, rcb_aloha as ra
s = ra.Session("/app/instance.json")    # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # qpos, qvel, targets, box_pos, box_quat_wxyz, target_pos, sites (box_top, box_bottom,
                    #   left/gripper, right/gripper), plus the success check fields
s.record_start()
r = s.step(targets) # (14,) actuator targets for one control step -> {success, box_to_target_m, right_holds, left_touches, box_z, time_s}
A = s.record_stop(); s.save_trajectory(A)          # -> /app/output/trajectory.npz
s.replay(A)         # fresh replay from the start (what the verifier does)
s.reset()           # back to the start (as often as you like)
img = s.render("overhead_cam")                      # also teleoperator_pov, collaborator_pov, worms_eye_cam, wrist_cam_left/right
```
Actuators `rcb_aloha.ACTUATOR_NAMES`: per arm (`left/`, `right/`) `waist, shoulder, elbow, forearm_roll, wrist_angle,
wrist_rotate` (joint position targets, rad) and `gripper` (finger position, 0.002 = closed … 0.037 = open). Limits:
`s.lower`, `s.upper`. The arms are position-controlled **without gravity compensation**: a joint settles where the
actuator force kp·(target − q) balances gravity. Everything in `s.model` / `s.data` is readable (privileged mode),
e.g. for inverse kinematics with `mujoco.mj_jacSite` on the `left/gripper` / `right/gripper` sites.

## Rules
- Write your own controller; do not use trained policies from MuJoCo Playground or elsewhere.
- Only the actuator targets count: editing `s.data` while debugging changes nothing in the replay.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of GPU memory**, **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
