# MuJoCo Playground · Panda pick cube with orientation (privileged)

## Task
Pick up the green box and hold it at the see-through red box, tilted the same way.

## Goal
Success: the green box is at the see-through red box, tilted the same way as it. What counts is how things stand after
the last action of your trajectory, replayed from the fixed start.

Deliverable: `/app/output/trajectory.npz`: actuator targets, shape `(T, 8)` (T at most 3000), one row per control step
(1/50 s), each held for 4 physics steps; record it with the tooling so the layout is right. It is replayed from the
frozen start. Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when
you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A Franka Panda arm (MuJoCo Playground's scene, in MuJoCo). The scene is one fixed instance. You have the full simulator
to develop with; you hand in a trajectory of actuator targets.

### Session
`/opt/tools/rcb_panda.py` (importable as `rcb_panda`):
```python
import numpy as np, rcb_panda as rp
s = rp.Session("/app/instance.json")    # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # qpos, qvel, targets, gripper_pos, gripper_mat, object_pos, object_quat_wxyz, target_pos,
                    #   target_quat_wxyz, plus the success check fields
s.record_start()
r = s.step(targets) # (8,) actuator targets for one control step -> the success check fields
A = s.record_stop(); s.save_trajectory(A)          # -> /app/output/trajectory.npz
s.replay(A)         # replay from the start, as graded
s.reset()           # back to the start (as often as you like)
img = s.render()                                    # RGB (240, 320, 3); s.render_grid() gives four views
```

Everything in `s.model` / `s.data` is readable (privileged mode), e.g. for inverse kinematics with `mujoco.mj_jacSite`.
`s.check()` checks success on the current state.

### Actions
Actuators: `actuator1..7` = joint position targets (rad) for `joint1..joint7`, `actuator8` = finger opening (0 = closed
… 0.04 m = open). Limits: `s.lower`, `s.upper`. The site `gripper` sits between the fingertips; the hand approaches
along the site's z axis and the fingers close along its y axis.

### Observations
`s.state()`: qpos, qvel, targets, gripper_pos, gripper_mat, object_pos, object_quat_wxyz, target_pos, target_quat_wxyz,
plus the success check fields.

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
