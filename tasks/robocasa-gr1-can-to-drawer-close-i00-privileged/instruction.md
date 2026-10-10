# RoboCasa-GR1 · PnPCanToDrawerClose

A **Fourier GR1 humanoid** (arms, waist and two dexterous six-command Fourier hands; fixed base) works at a kitchen counter: RoboCasa's GR1 tabletop `PnPCanToDrawerClose` task (robosuite, MuJoCo).
**Task: pick up the can, place it into the drawer and close the drawer.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations (kitchen
layout, style, fixtures, objects and their poses).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: the robot's native controller commands, shape `(T, 24)` with
1 ≤ T ≤ 3000, one row per control step (1/20 s). Write it with `s.save_trajectory()` so the format is right.
Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies the environment's own success check for `PnPCanToDrawerClose` (`_check_success`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` returns the check's latest result.

Both of these hold on the graded state (upstream `_check_success`, `tabletop_drawer_pnp.py`):
- the can's centre (its body origin) is inside the drawer's interior;
- the drawer is shut: upstream's opening fraction is at most 0.005 (0 = shut, 1 = fully open).

Where the hands end up is not checked.

## Tooling (`/opt/tools/casa_tool.py`, importable as `casa_tool`)
```python
import numpy as np, casa_tool
s = casa_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the robosuite env, s.model / s.data MuJoCo
s.action_spec        # every channel: name, unit, kind (delta | absolute | grip | mode), lower / upper; frames
st = s.state()       # instruction, qpos, qvel, joint_names, bodies {name: pos, quat_wxyz}, objects, proprio, success
r = s.step(action)   # one control step -> {"success": ..., "control_steps": ..., ...}
s.check()            # the success check's latest result
s.save_trajectory()  # the actions since the last reset -> /app/output/trajectory.npz
s.replay(A)          # reset, then replay A (what the verifier does) -> {"success": ..., "state_sha": ...}
s.reset()            # back to the frozen start, as often as you like (it takes a few seconds)
img = s.render("robot0_agentview_center")   # RGB (240, 320, 3); views in s.camera_views; s.render_grid()
```
- Actions: 24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` -- absolute, in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order `little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not a binary grip. The GR1 has no mobile base. Values are clipped to the limits.
- The success check runs twice after every control step and once at reset, in your session exactly as in the
  verifier. Some checks count consecutive successful steps, so calling `s.env._check_success()` yourself changes the
  state of the run you are recording; use `s.check()`.
- World frame: metres, z up; `s.state()["bodies"]` gives every body's position and orientation (quaternions w x y z).
  The action's pose targets are in the robot's base frame. The robot's base frame (body `robot0_base`, fixed in the world) has its origin at world (2.65000, -2.17500, 0.97000) m and is turned +90.0 deg about z (quaternion w x y z (0.70711, 0, 0, 0.70711)): `p_world = R @ p_base + t` with R = [[0, -1, 0], [1, 0, 0], [0, 0, 1]].
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode).

## Rules
- Write your own controller. Do not use the benchmark's demonstrations, trained policies or any published solution.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Save a working trajectory early, then improve it; do not stop early.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
