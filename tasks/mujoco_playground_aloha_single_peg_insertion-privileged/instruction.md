# MuJoCo Playground · ALOHA single peg insertion

An **ALOHA 2** bimanual robot (two ViperX 300s arms facing each other across a table) has a **blue socket** (a square
tube, open on one end, red wall at the back) and a **red peg** in front of it.
**Task:** pick up the socket with one arm and the peg with the other, lift both, and **insert the peg's end into the
socket's open end**. This is MuJoCo Playground's `AlohaSinglePegInsertion`, run here in plain MuJoCo; the peg and socket
positions are randomized as in Playground, with a fixed seed.

## What you hand in
`/app/output/trajectory.npz` — actuator targets, shape `(T, 14)` (T ≤ 3000), one row per control step (1/50 s), each
held for 8 physics steps. Record it with the tooling so the layout is right. The verifier replays it from the frozen
start in a separate sandbox (MuJoCo on CPU is bit-exact). Leave the script that produced it at `/app/output/gen.py`.

## Success
At the **end of the trajectory** the peg's tip (site `peg_end2`) is within **5 mm** of the socket's axis (the line
through sites `socket_rear` and `socket_entrance`) and at least **25 % of the socket's depth inside** it
(axial parameter `t ≤ 0.75`, where t = 0 at the rear wall and 1 at the entrance). `s.check()` computes exactly this.

## Tooling (`/opt/tools/rcb_aloha.py`, importable as `rcb_aloha`)
```python
import numpy as np, rcb_aloha as ra
s = ra.Session("/app/instance.json")    # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # qpos, qvel, targets, peg/socket pos + quat, sites (socket_entrance, socket_rear, peg_end1, peg_end2,
                    #   left/gripper, right/gripper), plus the success check fields
s.record_start()
r = s.step(targets) # (14,) actuator targets for one control step -> {inserted, tip_to_axis_m, axial_t, socket_z, peg_z, time_s}
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
- You have 60 minutes of wall-clock time.
