# MetaWorld+ · box-close

A **Sawyer** arm stands at a table: Meta-World's `box-close-v3` environment (MuJoCo). **Task: Move the lid onto the box to close it.**
The scene is one frozen instance of Meta-World's own randomization (object and goal positions; seed 0).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: Meta-World's native actions, shape `(T, 4)` with 1 ≤ T ≤ 500
(Meta-World's episode length), one row per control step (1/80 s). Write it with `s.save_trajectory()` so the format
is right: the verifier reads a plain `.npz` of at most 2 MB that holds arrays only (no pickled objects, at most 64
members), and grades anything else as an invalid trajectory. Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies Meta-World's own success check for `box-close-v3` (`evaluate_state`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` computes exactly this check on the current state.

For `box-close-v3` the check is: The lid (measured at its handle) is less than 8 cm from the target point. ("The target point" is `s.state()["target_pos"]`.)

## Tooling (`/opt/tools/mw_tool.py`, importable as `mw_tool`)
```python
import numpy as np, mw_tool
s = mw_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the Meta-World env, s.model / s.data MuJoCo
st = s.state()        # tcp, gripper_opening, mocap_pos, target_pos, object_pos / object_quat_wxyz, object2_*,
                      #   observation (Meta-World's 39-d), qpos, qvel, bodies {name: pos, quat_wxyz}, success
r = s.step([dx, dy, dz, grip])   # one control step -> {"success": ..., "control_steps": ..., ...}
s.check()             # Meta-World's success check on the current state
s.save_trajectory()   # the actions since the last reset -> /app/output/trajectory.npz
s.replay(A)           # reset, then replay A (what the verifier does) -> {"success": ..., "state_sha": ...}
s.reset()             # back to the frozen start, as often as you like
img = s.render("front")   # RGB (240, 320, 3); views front, left, right, topview; s.render_grid() shows all four
```
- Action `[dx, dy, dz, grip]`, each clipped to [-1, 1]. The hand's target (a mocap body) moves by `[dx, dy, dz]` × 1 cm
  per control step and stays inside x ∈ [-0.5, 0.5], y ∈ [0.4, 1], z ∈ [0.05, 0.5]; the hand follows it through a weld constraint. `grip` drives the two
  fingers (+1 closes, -1 opens). The wrist does not rotate.
- World frame: metres; x to the robot's right, y forward (away from the robot's base), z up; the table top is at z = 0. Quaternions are w x y z.
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode), including Meta-World's source.

## Rules
- Write your own controller. Do not use Meta-World's scripted policies or any published solution for this benchmark.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Save a working trajectory early, then improve it; do not stop early.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
