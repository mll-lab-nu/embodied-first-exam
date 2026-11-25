# MuJoCo Playground · ALOHA hand-over (privileged)

## Task
Pick up the red box with the left arm, pass it to the right arm, and hold it at the see-through target box. Then take
the left arm off the box.

## Goal
Success: the right gripper holds the box at the target box, off the table, and no part of the left arm touches the box.
What counts is how things stand after the last action of your trajectory, replayed from the fixed start.

Deliverable: `/app/output/trajectory.npz`: actuator targets, shape `(T, 14)` (T at most 3000), one row per control step
(1/50 s), each held for 4 physics steps; record it with the tooling so the layout is right. It is replayed from the
frozen start. Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when
you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
An ALOHA 2 bimanual robot (two ViperX 300s arms facing each other across a table; MuJoCo Playground's scene, in MuJoCo).
The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of actuator
targets.

### Session
`/opt/tools/rcb_aloha.py` (importable as `rcb_aloha`):
```python
import numpy as np, rcb_aloha as ra
s = ra.Session("/app/instance.json")    # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # qpos, qvel, targets, box_pos, box_quat_wxyz, target_pos, sites (box_top, box_bottom,
                    #   left/gripper, right/gripper), plus the success check fields
s.record_start()
r = s.step(targets) # (14,) actuator targets for one control step -> {success, box_to_target_m, right_holds, left_touches, box_z, time_s}
A = s.record_stop(); s.save_trajectory(A)          # -> /app/output/trajectory.npz
s.replay(A)         # replay from the start, as graded
s.reset()           # back to the start (as often as you like)
img = s.render("overhead_cam")                      # also teleoperator_pov, collaborator_pov, worms_eye_cam, wrist_cam_left/right
```

Everything in `s.model` / `s.data` is readable (privileged mode), e.g. for inverse kinematics with `mujoco.mj_jacSite`
on the `left/gripper` / `right/gripper` sites. `s.check()` checks success on the current state.

### Actions
Actuators `rcb_aloha.ACTUATOR_NAMES`: per arm (`left/`, `right/`)
`waist, shoulder, elbow, forearm_roll, wrist_angle, wrist_rotate` (joint position targets, rad) and `gripper` (finger
position, 0.002 = closed … 0.037 = open). Limits: `s.lower`, `s.upper`. The arms are position-controlled without gravity
compensation: a joint settles where the actuator force kp·(target − q) balances gravity.

### Observations
`s.state()`: qpos, qvel, targets, box_pos, box_quat_wxyz, target_pos, sites (box_top, box_bottom, left/gripper,
right/gripper), plus the success check fields. Cameras (`s.render(cam)`): `overhead_cam`, also teleoperator_pov,
collaborator_pov, worms_eye_cam, wrist_cam_left/right.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 5 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (6 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
