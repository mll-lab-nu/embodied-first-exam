# DexToolBench · mallet hammer · swing_down (privileged)

## Task
A KUKA iiwa 14 arm with a 22-joint Sharpa HA4 dexterous hand stands next to a table with a mallet hammer on it
(DexToolBench, MuJoCo). Pick up the mallet hammer and move it through the demonstrated motion (a downward hammer swing):
bring it to each of the 36 goal poses in order (the green ghost tool shows the current goal). The scene is one fixed
instance.
You have the full simulator to develop with; you hand in a trajectory of joint targets.

## Goal
Success: the mallet hammer has been brought to each of its 36 goal poses in turn, in order; a goal counts once the whole
tool matches the ghost's pose closely (position and orientation), and the next one then appears. A replay ends as soon
as the task is done; later rows are not run. Each goal has 30 s (1,800 control steps): if it is not reached in time, the
attempt ends there. There is no partial credit (goals reached / 36 is only reported, as `progress`).

Deliverable: `/app/output/trajectory.npz`: joint position targets, shape `(T, 29)`, one row per control step (1/60 s,
each held for 10 physics steps), at most 360,000 rows; record it with the tooling (`s.record_start()`,
`s.record_stop()`, `s.save_trajectory(A)`) so the layout is right. It is replayed from the fixed start. Leave the script
that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the joint targets count: editing `s.data` (e.g. moving the tool by hand) while you develop changes nothing in the
replay.

## Robot Interface
### Session
`/opt/tools/rcb_dtb.py`, importable as `rcb_dtb`:
```python
import numpy as np, rcb_dtb
s = rcb_dtb.Session("/app/instance.json")      # builds the scene at the start state; s.model / s.data are MuJoCo objects
st = s.state()      # q, qd (29), targets, object_pos, object_quat_wxyz, goal_index, goal (x y z qx qy qz qw), palm_pos, time_s
s.goals             # all 36 goal poses (x y z qx qy qz qw, world frame, metres)
s.record_start()
p = s.step(targets) # (29,) joint position targets for one control step; returns progress
                    #   {reached, n_goals, progress, done, failed, steps_left_on_goal, goal_distance_m}
A = s.record_stop(); s.save_trajectory(A)       # -> /app/output/trajectory.npz
s.replay(A)         # replay from the start state, as the grader does -> progress + state hash
s.reset()           # back to the start state (as often as you like)
img = s.render("front")                          # RGB (240, 320, 3); cameras: front, side, top, oblique
s.render_video(A, "/app/output/debug.mp4")
```

### Actions
Joint order `rcb_dtb.JOINT_NAMES`: `joint1..joint7` (iiwa), then the hand: thumb (`CMC_FE, CMC_AA, MCP_FE, MCP_AA, IP`),
index / middle / ring (`MCP_FE, MCP_AA, PIP, DIP` each), pinky (`CMC, MCP_FE, MCP_AA, PIP, DIP`), all prefixed
`palmleft_`. Limits: `s.lower`, `s.upper` (targets are clipped). Start: `rcb_dtb.INIT_Q`.

### Scene
World frame: metres, z up; goal poses are x y z qx qy qz qw. Hand bodies are named `palmworld`,
`palmleft_<finger>_{PP,MP,DP}` (DP = fingertip); the tool body is `object`. The table top is at z = 0.53 m; the robot
base is at (0, 0.8, 0). Everything in `s.model` / `s.data` is readable, e.g. for inverse kinematics with
`mujoco.mj_jacBody`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 20 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (5 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
