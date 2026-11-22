# RoboCasa-GR1 · PosttrainPnPNovelFromCuttingboardToPotSplitA (privileged)

## Task
A Fourier GR1 humanoid (arms, waist and two dexterous six-command Fourier hands, on a fixed base), at a simulated
kitchen counter (RoboCasa GR1 tabletop, robosuite / MuJoCo). Pick the bell pepper from the cutting board and place it in
the pot. The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of robot
actions.

## Goal
Success: the bell pepper rests in the pot, not touching the counter, the pot still upright, and both hands have let go
and moved away from the bell pepper and the pot. What counts is how things stand after the last action of your
trajectory, replayed from the fixed start: a success reached earlier and lost by the end does not count.

Deliverable: `/app/output/trajectory.npz` with key `actions`: the robot's native controller commands, shape `(T, 24)`
with 1 ≤ T ≤ 3000, one row per control step (1/20 s). Write it with `s.save_trajectory()` so the format is right. Leave
the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actions count: changing `s.data` or the environment while you develop changes nothing in the replay.

## Robot Interface
### Session
`/opt/tools/casa_tool.py`, importable as `casa_tool`:
```python
import numpy as np, casa_tool
s = casa_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the robosuite env, s.model / s.data MuJoCo
s.action_spec        # every channel: name, unit, kind (delta | absolute | grip | mode), lower / upper; frames
st = s.state()       # qpos, qvel, joint_names, bodies {name: pos, quat_wxyz}, objects, proprio, success
r = s.step(action)   # one control step -> {"success": ..., "control_steps": ..., ...}
s.check()            # the success check's latest result
s.save_trajectory()  # the actions since the last reset -> /app/output/trajectory.npz
s.replay(A)          # reset, then replay A (as the grader does) -> {"success": ..., "state_sha": ...}
s.reset()            # back to the frozen start, as often as you like (it takes a few seconds)
img = s.render("robot0_agentview_center")   # RGB (240, 320, 3); views in s.camera_views
```

### Actions
- An action has 24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` --
  absolute, in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics
  controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order
  `little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not a
  binary grip. The GR1 has no mobile base. Values are clipped to the limits.
- World frame: metres, z up; `s.state()["bodies"]` gives every body's position and orientation (quaternions w x y z).
  The action's pose targets are in the robot's base frame. The robot's base frame (body `robot0_base`, fixed in the
  world) has its origin at world (2.66899, -2.16906, 0.89825) m and is turned +90.0 deg about z (quaternion w x y z
  (0.70711, 0, 0, 0.70711)): `p_world = R @ p_base + t` with R = [[0, -1, 0], [1, 0, 0], [0, 0, 1]].
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode).

## Others
- Read success with `s.check()`: the check runs after every step in your session as it does in the grader, and calling
  the environment's own check yourself changes the run you are recording.

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
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
