# MuJoCo Playground · Panda open cabinet

A **Franka Panda** arm stands in front of a **green handle** mounted on a slide (it moves only along x, from x = 0.5 m
towards the robot), with a shelf behind a barrier. A **red target sphere** marks where the handle should end up.
**Task:** grasp the handle and **pull it along its slide to the target**. This is MuJoCo Playground's
`PandaOpenCabinet`, run here in plain MuJoCo; the target and the arm's start posture are randomized as in Playground,
with a fixed seed.

## What you hand in
`/app/output/trajectory.npz` — actuator targets, shape `(T, 8)` (T ≤ 3000), one row per control step (1/50 s), each held
for 4 physics steps. Record it with the tooling so the layout is right. The verifier replays it from the frozen start
in a separate sandbox (MuJoCo on CPU is bit-exact). Leave the script that produced it at `/app/output/gen.py`.

## Success
At the **end of the trajectory** the handle is within **1.5 cm** of the target along x (`s.target_pos[0]`).
`s.check()` computes exactly this.

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
- You have 60 minutes of wall-clock time.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of GPU memory**, **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.
