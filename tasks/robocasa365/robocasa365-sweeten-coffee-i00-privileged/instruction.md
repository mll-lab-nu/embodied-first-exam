# RoboCasa365 · SweetenCoffee (privileged)

## Task
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa365, robosuite / MuJoCo).
Take a sugar cube from the saucer and place it inside the coffee. Then, grab milk from the fridge and place it next to
the coffee on the counter to sweeten the coffee. The scene is one fixed instance. You have the full simulator to develop
with; you hand in a trajectory of robot actions.

## Goal
Success: the sugar cube is in the coffee, the milk stands on the counter right next to the coffee, and the hand has let
go and moved away from the milk and the sugar cube. What counts is how things stand after the last action of your
trajectory, replayed from the fixed start: a success reached earlier and lost by the end does not count.

Deliverable: `/app/output/trajectory.npz` with key `actions`: the robot's native controller commands, shape `(T, 13)`
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
- An action has 13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the
  joint limits in `s.action_spec`); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's
  velocities in its own frame (normalised, [-1, 1]); `torso` -- the torso lift's velocity; `hybrid_mode` (> 0: base
  mode; <= 0: arm mode, the default -1). Values are clipped to the limits.
- World frame: metres, z up; `s.state()["bodies"]` gives every body's position and orientation (quaternions w x y z).
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
