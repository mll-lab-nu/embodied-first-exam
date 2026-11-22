# MuJoCo Playground · Go1JoystickRoughTerrain (standard)

## Task
The Unitree Go1 quadruped (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no
walking or balance controller. It starts at its `home` pose, its base moved to (-0.096, 0.049) m and turned to a yaw of
118.2 deg, with a random base velocity. The ground is Playground's rough terrain: a 20 x 20 m heightfield (`hfield.png`,
up to 5 cm high) centred on the world origin, with nothing beyond its edge. Make it follow the joystick's command
schedule for the whole 20 s episode without falling over. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: for the whole schedule the robot never falls, and in every command's stretch, after a short settling time at
its start, its velocity over the ground (in its own frame) and its turning rate follow the command closely on average.
The episode lasts the whole schedule (20 s, 1000 control steps); a fall (the trunk tipping over) ends it at once, as a
failure, and so does ending it yourself (`done`) or running out of time before the schedule's end.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the targets and watch for 1 s (max 30)
r.fk(q); r.ik({"FR": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["track"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the current targets). A reset
(`POST /reset`, the `_post` line above) puts the robot back on the same frozen starting state and starts a new episode,
either abandoning the running one or after one has ended; it takes no simulated time and returns the start's images and
proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock is the run's
and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes (`meta["control_steps"]` is the
current episode's). If the service crashes, a call fails with a connection error: it restarts and resumes the same
episode (never a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check
`r.status()`. One call returns at most 3000 images.

### Actions
Action type `joint_position` (12): FR, FL, RR, RL legs, each hip (abduction), thigh (hip pitch), calf (knee): absolute
targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5 N m s/rad). Rows are `dt` apart (a
whole multiple of the 0.02 s control period, at most 0.5 s), `interpolate="linear"` (default) or `"hold"` between rows;
a chunk covers at most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped
and listed in `res.meta["clipped"]`. Feedback control means short chunks: each response tells you where the robot is
now.

### Observations
Cameras: `track`, `side`, `back`, `top` (they follow the robot); `spec["cameras"]` gives each one's mounting and
intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`,
`joint_effort` (12 each, action order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame:
x forward, y left, z up), `foot_contact` (FR, FL, RR, RL).

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. The schedule is `spec["command_schedule"]` (each segment's start and command); every response's
`meta["command_now"]` is the current command.

### This run: privileged state queries
This run lets you query the simulator's state.

- `GET /state/entities` (on the same base URL as your other calls) lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}}}}`. The kinds are
  `robot` (the robot's base or root), `robot_link` (a hand, a foot, an end effector), `object`, `articulation` (a door,
  a drawer, a faucet: its joints) and `scene_feature` (a zone, a line, a hazard, a canvas region). The list is fixed for
  the run.
- `POST /state/query` with `{"names": ["robot", ...], "fields": ["pos", "quat"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the current
  values. `fields` is optional: without it you get every field of each name. In Python:
  `requests.post(base + "/state/query", json={"names": ["robot"]}).json()["state"]`.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s,
    `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents), and `bbox` [[min x,
    y, z], [max x, y, z]] m. A task may add its own; each field's unit is in the list.
  - All values are in the world frame that `frame` describes.
  - A field that an entity does not have is left out of its entry.
  - An unknown name or field is a 400 that lists the valid ones.
- A query only reads. It takes no control step, and it does not advance or pause the clock. In standard-realtime it
  answers at the current simulation time while the robot keeps moving. It is served while the episode runs (409 after
  the episode ended). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: the goal, the success rule and its thresholds are not given, and no answer says whether the task
  is done.

### This run: unlimited resets, save and load
This run changes the reset budget and adds two calls.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON
  body such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state. The
  answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`, `loads`
  and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets. Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a load
  until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved state
  followed by what you did after the load. The success rule is checked again from your next command on. A success still
  ends the run: no reset, save or load after it.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
