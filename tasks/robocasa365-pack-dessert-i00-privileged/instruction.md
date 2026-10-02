# RoboCasa365 · PackDessert

A **Franka Panda arm on an Omron mobile base** (with a torso lift) works in a kitchen: RoboCasa365's `PackDessert` kitchen task (robosuite, MuJoCo).
**Task: Add the marshmallow to the tupperware that contains the hot dog.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations (kitchen
layout, style, fixtures, objects and their poses).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: the robot's native controller commands, shape `(T, 13)` with
1 ≤ T ≤ 3000, one row per control step (1/20 s). Write it with `s.save_trajectory()` so the format is right.
Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies the environment's own success check for `PackDessert` (`_check_success`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` returns the check's latest result.

The check for `PackDessert` requires that the hot dog and the marshmallow are both in the tupperware, and the gripper ends more than 0.25 m from the marshmallow.

How RoboCasa365's checks compute these terms (`robocasa/utils/object_utils.py`):
- *the gripper ends more than d m from X*: the distance from the robot's end-effector grip site to X's origin exceeds
  d. Opening the fingers is not enough: release, then move the hand away.
- *X is on / in Y* for an object Y (plate, tray, board, pan, pot, colander, tupperware, glass): X touches Y and their
  centres are within 0.7 × Y's horizontal radius of each other horizontally, unless a distance is given.
- *X touches* a counter, the dining counter or the stove: contact between X and that fixture.
- *X is inside* a fixture (a cabinet, the sink or one of its basins, the microwave): all eight corners of X's bounding
  box are within the fixture's interior region (5 cm tolerance).

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
- Actions: 13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint limits in `s.action_spec`); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` -- the torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the limits.
- The success check runs twice after every control step and once at reset, in your session exactly as in the
  verifier. Some checks count consecutive successful steps, so calling `s.env._check_success()` yourself changes the
  state of the run you are recording; use `s.check()`.
- World frame: metres, z up; `s.state()["bodies"]` gives every body's position and orientation (quaternions w x y z).
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode).

## Rules
- Write your own controller. Do not use the benchmark's demonstrations, trained policies or any published solution.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Save a working trajectory early, then improve it; do not stop early.
