# DexToolBench · spoon spatula · flip_over (MuJoCo)

A KUKA iiwa 14 arm with a 22-joint **Sharpa HA4** dexterous hand stands next to a table with a **spoon spatula** on it.
**Task:** pick up the spoon spatula and move it through the demonstrated motion (flipping something over): bring it to each
of the **40 goal poses in order** (the green ghost tool shows the current goal). This is task `spatula / spoon_spatula /
flip_over` of DexToolBench (SimToolReal), run here in plain MuJoCo.

## What you hand in
`/app/output/trajectory.npz` — joint position targets, shape `(T, 29)`, one row per control step (1/60 s), each held
for 10 physics steps. Record it with the tooling (below) so the layout is right. The verifier replays it from the
frozen start state in a separate sandbox (MuJoCo on CPU is bit-exact) and scores it. Leave the script that produced it
at `/app/output/gen.py`.

## Scoring (the benchmark's own rule)
The current goal counts as reached when all 8 corners of the tool's grasp box (0.141 × 0.030 × 0.027 m, scaled by
1.5, in the tool's frame) are within **1.5 cm** of the same corners at the goal pose; then the next goal becomes
current. Each goal has **30 s (1,800 control steps)**; if it is not reached in time the attempt ends there (DexToolBench's own rule is 10 s; relaxed here because your trajectory is replayed offline and you can reset as often as you like). The trajectory may be at most 360,000 control steps.
**Score: 1 if all 40 goals are reached (and the replay is deterministic), else 0.** Goals reached / 40 is reported as `progress`; there is no partial credit.

## Tooling (`/opt/tools/rcb_dtb.py`, importable as `rcb_dtb`)
```python
import numpy as np, rcb_dtb
s = rcb_dtb.Session("/app/instance.json")      # builds the scene at the start state; s.model / s.data are MuJoCo objects
st = s.state()      # q, qd (29), targets, object_pos, object_quat_wxyz, goal_index, goal (x y z qx qy qz qw), palm_pos, time_s
s.goals             # all 40 goal poses (x y z qx qy qz qw, world frame, metres)
s.record_start()
p = s.step(targets) # (29,) joint position targets for one control step; returns progress
                    #   {reached, n_goals, progress, done, failed, steps_left_on_goal, goal_distance_m}
A = s.record_stop(); s.save_trajectory(A)       # -> /app/output/trajectory.npz
s.replay(A)         # fresh replay from the start state -> progress + state hash (what the verifier does)
s.reset()           # back to the start state (as often as you like)
img = s.render("front")                          # RGB (240, 320, 3); cameras: front, side, top, oblique
s.render_video(A, "/app/output/debug.mp4")
```
Joint order `rcb_dtb.JOINT_NAMES`: `joint1..joint7` (iiwa), then the hand: thumb (`CMC_FE, CMC_AA, MCP_FE, MCP_AA, IP`),
index / middle / ring (`MCP_FE, MCP_AA, PIP, DIP` each), pinky (`CMC, MCP_FE, MCP_AA, PIP, DIP`), all prefixed
`palmleft_`. Limits: `s.lower`, `s.upper` (targets are clipped). Start: `rcb_dtb.INIT_Q`. Hand bodies are named
`palmworld`, `palmleft_<finger>_{PP,MP,DP}` (DP = fingertip); the tool body is `object`. The table top is at
z = 0.53 m; the robot base is at (0, 0.8, 0). Everything in `s.model` / `s.data` is readable (this is the privileged
tier), e.g. for inverse kinematics with `mujoco.mj_jacBody`.

## Rules
- The network reaches only the model API and the package registries (PyPI, Debian / Ubuntu archives). Do not use pretrained manipulation policies or any
  DexToolBench / SimToolReal solution; write your own controller.
- Only the joint targets count: editing `s.data` (e.g. moving the tool by hand) while debugging changes nothing in
  the replay.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **7 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
