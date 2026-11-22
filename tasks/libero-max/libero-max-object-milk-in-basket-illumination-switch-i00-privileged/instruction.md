# LIBERO-MAX · libero_object · illumination switch (privileged)

## Task
A Franka Panda arm at a table (LIBERO on robosuite / MuJoCo). Pick the milk and place it in the basket. The scene is one
fixed instance, and it changes once while you work (Others). You have the full simulator to develop with; you hand in a
trajectory of robot actions.

## Goal
Success: the milk is in the basket. Your trajectory is replayed from the fixed start, and the episode ends as soon as
the task is done: the trajectory must end on that step (actions after it make it invalid).

Deliverable: `/app/output/trajectory.npz` with key `actions`: LIBERO's native control steps, shape `(T, 7)`, 1 ≤ T ≤ 280
(LIBERO's step limit for this task), one row per control step (1/20 s), starting after LIBERO's 10 warm-up steps (no-ops
with the gripper open, already part of the fixed start). Write it with `s.save_trajectory()` so the format is right.
Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when you have a
better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actions count: changing the simulator state while you develop changes nothing in the replay.

## Robot Interface
### Session
`/opt/tools/lmx_tool.py`, importable as `lmx_tool`:
```python
import numpy as np, lmx_tool
s = lmx_tool.Session("/app/instance.json")  # builds the frozen scene; ONE Session per Python process
st = s.state()        # eef {pos, quat_wxyz}, gripper_qpos, joint_pos/vel, objects / fixtures {name: pos, quat_wxyz},
                      #   articulations {joint: position} (drawer slides in m, door and knob hinges in rad),
                      #   goal, instruction, success, done, event_fired, event_step, control_steps, steps_left
r = s.step([dx, dy, dz, drx, dry, drz, grip])   # one control step -> {"success", "done", "event_fired", ...}
s.check()             # LIBERO's success check on the current state
s.save_trajectory()   # the actions so far -> /app/output/trajectory.npz
lmx_tool.replay_fresh(A)   # replay A in a new process (as the grader does) -> {"success", "state_sha", ...}
img = s.render("agentview", 256)   # RGB, upright; cameras "agentview" and "wrist"; depth=True adds metric depth
```

One simulator per process: some scenes do not rebuild exactly the same a second time in one process, so a second
`Session` in a process raises an error. To start over, start a new Python process (as often as you like); `replay_fresh`
does this for you.

### Actions
- Action `[dx, dy, dz, drx, dry, drz, grip]`, each clipped to [-1, 1]: LIBERO's operational-space controller (OSC_POSE)
  moves the hand's target by `[dx, dy, dz]` × 0.05 m and rotates it by `[drx, dry, drz]` × 0.5 rad (axis-angle, world
  frame) per control step; `grip` +1 closes, -1 opens the gripper.
- World frame: metres; the robot's base is at (-0.6, 0, 0) facing +x: x forward (across the table), y to the robot's
  left, z up; quaternions are w x y z.
- Everything in `s.env` (robosuite's LIBERO environment) and `s.sim` is readable (privileged mode).

## Others
- The scene changes once: the first time the gripper comes within 0.18 m of `milk_1`, the lighting is scaled by 0.2.
  `s.state()["event_fired"]` and `event_step` show when it happened; the grader's replay applies it by the same trigger.

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
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like: start a new Python process (one `Session` per process).
