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
(privileged tier), e.g. for inverse kinematics with `mujoco.mj_jacSite`.

## Rules
- Write your own controller; do not use trained policies from MuJoCo Playground or elsewhere.
- Only the actuator targets count: editing `s.data` while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time.
