# MetaWorld+ · disassemble

A **Sawyer** arm stands at a table: Meta-World's `disassemble-v3` environment (MuJoCo). **Task: Lift the nut off the peg.**
The scene is one frozen instance of Meta-World's own randomization (object and goal positions; seed 0).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: Meta-World's native actions, shape `(T, 4)` with 1 ≤ T ≤ 500
(Meta-World's episode length), one row per control step (1/80 s). Write it with `s.save_trajectory()` so the format
is right: the verifier reads a plain `.npz` of at most 2 MB that holds arrays only (no pickled objects, at most 64
members), and grades anything else as an invalid trajectory. Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies Meta-World's own success check for `disassemble-v3` (`evaluate_state`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` computes exactly this check on the current state.

For `disassemble-v3` the check is: The nut is higher than the target point; only the height (z) is compared, measured at the nut's handle. ("The target point" is `s.state()["target_pos"]`.)

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
- Save a working trajectory early, then improve it; do not stop early.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
