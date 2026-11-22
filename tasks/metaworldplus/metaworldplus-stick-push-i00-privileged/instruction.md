# MetaWorld+ · stick-push (privileged)

## Task
A Sawyer arm at a table (Meta-World, MuJoCo). Use the stick to push the target object. The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of robot actions.

## Goal
Success: the thermos is pushed to the target point with the stick still held and lifted off the table (a thermos at the
target after the stick has been let go does not count). What counts is how things stand after the last action of your
trajectory, replayed from the fixed start: a success reached earlier and lost by the end does not count.

Deliverable: `/app/output/trajectory.npz` with key `actions`: Meta-World's native actions, shape `(T, 4)` with 1 ≤ T ≤
500 (Meta-World's episode length), one row per control step (1/80 s). Write it with `s.save_trajectory()` so the format
is right: the grader reads a plain `.npz` of at most 2 MB that holds arrays only (no pickled objects, at most 64
members), and grades anything else as an invalid trajectory. Leave the script that produced it at `/app/output/gen.py`.
Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use Meta-World's scripted policies, trained policies or any published solution.
Only the actions count: changing `s.data` or the environment while you develop changes nothing in the replay.

## Robot Interface
### Session
`/opt/tools/mw_tool.py`, importable as `mw_tool`:
```python
import numpy as np, mw_tool
s = mw_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the Meta-World env, s.model / s.data MuJoCo
st = s.state()        # tcp, gripper_opening, mocap_pos, target_pos, object_pos / object_quat_wxyz, object2_*,
                      #   observation (Meta-World's 39-d), qpos, qvel, bodies {name: pos, quat_wxyz}, success
r = s.step([dx, dy, dz, grip])   # one control step -> {"success": ..., "control_steps": ..., ...}
s.check()             # Meta-World's success check on the current state
s.save_trajectory()   # the actions since the last reset -> /app/output/trajectory.npz
s.replay(A)           # reset, then replay A (as the grader does) -> {"success": ..., "state_sha": ...}
s.reset()             # back to the frozen start, as often as you like
img = s.render("front")   # RGB (240, 320, 3); views front, left, right, topview
```

The target point that Goal names is `s.state()["target_pos"]` (world frame).

### Actions
- Action `[dx, dy, dz, grip]`, each clipped to [-1, 1]. The hand's target (a mocap body) moves by `[dx, dy, dz]` × 1 cm
  per control step and stays inside x ∈ [-0.5, 0.5], y ∈ [0.4, 1], z ∈ [0.05, 0.5]; the hand follows it through a weld
  constraint. `grip` drives the two fingers (+1 closes, -1 opens). The wrist does not rotate.
- World frame: metres; x to the robot's right, y forward (away from the robot's base), z up; the table top is at z = 0.
  Quaternions are w x y z.
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode), including Meta-World's source.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
