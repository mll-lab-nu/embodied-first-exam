# MolmoSpaces · pick-and-place-next-to (standard)

## Task
Put the black rail mount down right beside the bread, almost touching it.

## Goal
Success: the black rail mount rests on the same surface as the bread, right beside it and almost touching it but not on
it, and the bread has not been pushed far or turned much. The `done` action is the same as `/finish`.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) in a simulated house (Ai2's MolmoSpaces,
MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware: one
live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service builds the episode)
spec = r.spec()                                # action types, limits, cameras (+ calibration), robot_spec, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (H, W, 3); obs.meta["proprio"] {"layout", "now"}
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (H, W) z-depth in m (0 = no reading)
res = r.submit("joint_position", A, dt=0.066)   # A: (T, 8) rows dt apart; res.video[cam], res.proprio, res.meta
obs = r.hold(2.0)                              # hold the current targets for 2 s of robot time (whole control
                                               # steps: obs.meta["duration_s"] is what ran)
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({"gripper": pose7}, seed=q)        # upstream's kinematic model, no physics: tcp poses <-> joint positions
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
- `meta["control_steps"]` counts the episode's control steps; `spec["max_control_steps"]` is the limit.
- One call returns at most 1812 images. Nothing is put into your context automatically: images come back as arrays in
  Python objects.
- If the service crashes, a call fails with a connection error: the service restarts and resumes the same episode (never
  a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- `joint_position` (8): `fr3_joint1`, `fr3_joint2`, `fr3_joint3`, `fr3_joint4`, `fr3_joint5`, `fr3_joint6`,
  `fr3_joint7`, `gripper`: the targets of upstream's joint-position controllers (fr3_joint1..7 in rad; gripper: the
  Robotiq command, 0 = open .. 255 = closed). At t = 0 the gripper is open and its target is 0. Rows are `dt` apart (a
  whole multiple of the 0.066 s control period, at most 0.5 s: up to 0.462 s). Between rows, use `interpolate="linear"`
  (default) or `"hold"`. A chunk covers at most 10 s. Values outside the limits
  (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in `res.meta["clipped"]`.
  `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row order (`["layout"]` names
  every entry). In a row, the gripper entries are commands in the units above, not the measured openings.
- `done` (no rows): `r.submit("done", [])` ends the episode at once.
- `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's world
  frame (z up, metres).

### Observations
- Cameras: `wrist_camera_zed_mini`, `droid_shoulder_light_randomization`, `randomized_zed2_analogue_1`,
  `randomized_zed2_analogue_2`, `randomized_gopro_analogue_1`; RGB, and depth when you ask for it (z-depth in metres, 0
  = no reading). Each camera's intrinsics and mount are in `spec["cameras"]`, and every response carries each camera's
  pose.
- Proprioception, what a real robot reports: joint positions, velocities and efforts, the gripper openings and the tool
  poses.

### Timing
One control step is 0.066 s of simulated time. Simulated time advances only with your commands and with `hold(s)`: while
you think, the robot waits. The service's `time_left_s` counts from your first request to the service, so it never
reaches 0 before your time is up. Plan by it.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 12 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 455 control steps (the benchmark's 30 s horizon), then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
