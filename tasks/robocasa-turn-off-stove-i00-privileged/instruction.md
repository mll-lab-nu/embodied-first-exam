# RoboCasa · TurnOffStove

A **Franka Panda arm on an Omron mobile base** (with a torso lift) works in a kitchen: RoboCasa's `TurnOffStove` kitchen task (robosuite, MuJoCo).
**Task: Turn off the front right burner of the stove.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations (kitchen
layout, style, fixtures, objects and their poses).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: the robot's native controller commands, shape `(T, 12)` with
1 ≤ T ≤ 3000, one row per control step (1/20 s). Write it with `s.save_trajectory()` so the format is right.
Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies the environment's own success check for `TurnOffStove` (`_check_success`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` returns the check's latest result.

What `TurnOffStove`'s check requires (RoboCasa @ 756598a), all on that final state:
- The front right burner's knob is within 0.35 rad (about 20°) of its off position.

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
- Actions: 12 channels, in order: `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz` -- the end effector's motion per control step in the robot's base frame, scaled by the controller (1.0 = 5 cm and 0.5 rad per step); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's target velocities in its own frame (1.0 = 1 m/s for `base_x` / `base_y` and 1.5 rad/s for `base_yaw`; force-limited velocity servos, so the base may lag the target); `torso` -- the torso lift, a joint-position controller with delta input (each step sets the lift's height target to its current height + 0.05 m × the value, so 1.0 = 5 cm per step; lift range 0–0.34 m); `hybrid_mode` (> 0: base mode, the arm's goal moves with the base; <= 0: arm mode, the default -1). Every channel is clipped to [-1, 1].
- The success check runs twice after every control step and once at reset, in your session exactly as in the
  verifier. Some checks count consecutive successful steps, so calling `s.env._check_success()` yourself changes the
  state of the run you are recording; use `s.check()`.
- World frame: metres, z up; `s.state()["bodies"]` gives every body's position and orientation (quaternions w x y z).
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode).

## Rules
- Write your own controller. Do not use the benchmark's demonstrations, trained policies or any published solution.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Save a working trajectory early, then improve it; do not stop early.
