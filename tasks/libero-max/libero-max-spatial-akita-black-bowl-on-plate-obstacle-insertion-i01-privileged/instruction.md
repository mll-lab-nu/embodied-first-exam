# LIBERO-MAX · libero_spatial · obstacle insertion (privileged)

## Task
Pick up the black bowl on the table, not the one on the stove, and put it on the plate.

## Goal
Success: that bowl sits on the plate, near its middle. Your trajectory is replayed from the fixed start. The episode
ends as soon as the task is done, and the trajectory must end on that step: any action after it makes the trajectory
invalid.

Deliverable: `/app/output/trajectory.npz` with key `actions`, shape `(T, 7)`, 1 ≤ T ≤ 220 (LIBERO's step limit for this
task). Each row is one of LIBERO's native control steps (1/20 s). The rows start after LIBERO's 10 warm-up steps, which
are no-ops with the gripper open and already part of the fixed start. Write it with `s.save_trajectory()` so the format
is right. Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when you
have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A Franka Panda arm at a table (LIBERO on robosuite / MuJoCo). The scene is one fixed instance, and it changes once while
you work (see Others). You have the full simulator to develop with; you hand in a trajectory of robot actions.

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

One simulator per process: a second `Session` in the same process raises an error, because some scenes do not rebuild
exactly the same way a second time. To start over, start a new Python process (as often as you like); `replay_fresh`
does this for you.

### Actions
- Action `[dx, dy, dz, drx, dry, drz, grip]`, each clipped to [-1, 1], for LIBERO's operational-space controller
  (OSC_POSE). Per control step it moves the hand's target by `[dx, dy, dz]` × 0.05 m and rotates it by `[drx, dry, drz]`
  × 0.5 rad (axis-angle, world frame). `grip` +1 closes the gripper, -1 opens it.
- World frame: metres, x forward (across the table), y to the robot's left, z up; quaternions are w x y z. The robot's
  base is at (-0.66, 0, 0.912), facing +x.
- Everything in `s.env` (robosuite's LIBERO environment) and `s.sim` is readable (privileged mode).

## Others
- Labels in `s.state()`: `akita_black_bowl_1` (the bowl to move), `plate_1` (the plate).
- The scene changes once, the first time the gripper comes within about a hand's length of the bowl: a cookie box
  (`cookies_1`) appears as an obstacle next to the bowl, on its far side from the robot. `s.state()["event_fired"]` and
  `event_step` show when it happened. The same change happens in the grader's replay.

## Limits
- Time: 1800 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like: start a new Python process (one `Session` per process).
