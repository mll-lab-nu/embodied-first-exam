# MyoSuite · baoding (standard-mcp-shell)

## Task
The MyoHand, a musculoskeletal model of a human forearm and hand (MyoSuite, MuJoCo), driven only through its actuators
(39 muscles): there is no joint-level controller. Two balls rest in the palm of the upturned hand; two small markers
show where each ball should be now. Baoding balls: rotate the two balls around each other in the palm so that each
follows its moving marker (the markers circle the palm once every 5 s). The robot runs as a service you reach through
the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real hardware.

## Goal
Success: both balls keep up closely with their moving markers for one full orbit of the markers (5 s). The episode ends
as soon as the task is done; it ends as a failure when a ball falls out of the palm, and after 25 s without success.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: a success ends the run at once (no reset after it), and when your time is up the episode then running is
  graded.
- No privileged state: you get the camera images (with their calibration) and the body's own proprioception (joint
  positions, velocities and actuator torques, muscle activations and lengths); no object, ball, opponent or goal poses;
  the episode ends when the task is done, and the service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the simulator's world frame (z up): camera poses are given in it; no part here takes an end-effector
pose; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: the robot's own action types only
(`execute_trajectory` space `native`). Cameras: `side_view`, `front_view`, `hand_top`, `hand_bottom`, `hand_side_inter`,
`hand_side_exter`, `plam_lookat`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: A muscle's command a sets its excitation u = 1 / (1 + exp(-5 (a - 0.5))), not clipped (a = -1: about 0.0006,
a = 0.5: 0.5, a = 1: 0.92); activation follows excitation with a short delay (about 10 ms up, 40 ms down); muscles only
pull, one muscle can cross several joints, and its force depends on its length and speed. Before your first command of
an episode every column holds -1 (all muscles relaxed). Every command goes through execute_trajectory space native
(action_type muscle, 39 numbers per row). The robot's own action type takes one row per control step (the control period
is in describe_robot), columns in its layout (describe_robot: action_types_native; spec_file has each actuator, muscle
and joint). The state is proprio_now (layout in spec_file: proprio_layout, proprio_groups): joint positions and
velocities, muscle activations and lengths, joint efforts. There is no joint-level controller: joints move only through
muscle forces. Time passes only inside calls; the service says when the episode ended and why, never the object or goal
state.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: hand_top)
obs = r.get_obs(cameras=["side_view"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("muscle", rows, dt=0.025)          # rows: (T, 39) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["side_view"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). A reset
(`POST /reset`, the `_post` line above) puts the body and the scene back on the same frozen starting state and starts a
new episode, either abandoning the running one or after one has ended; it takes no simulated time and returns the
start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall
clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes
(`meta["control_steps"]` is the current episode's). If the service crashes, a call fails with a connection error: it
restarts and resumes the same episode (never a reset) in the state after the last call it completed. `r.wait_ready()`
waits for it; then check `r.status()`. One call returns at most 1000 images. `r.fk(q)` (`/kinematics`) gives the
fingertip sites and the camera mounts for any joint positions.

### Actions
Action type `muscle` (39): 39 real numbers per control step, one per actuator in order: 39 muscles. A muscle's command a
maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1:
0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only
pull; one muscle can cross several joints; its force also depends on its length and velocity. Columns in
`spec["action_types"]["muscle"]["layout"]` order. Rows are `dt` apart (a whole multiple of the 25 ms control period, at
most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous command) or `"hold"`; the
client sends them as float32. The control rate is 40 Hz (10 physics substeps); there is no step budget.

### Observations
Cameras: `side_view`, `front_view`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat`
(640x480; default `hand_top`). `hand_top` and `hand_side_inter` are close-ups of the hand, mounted on the forearm (the
radius): they move with it (pronation turns them), so use the pose returned with each frame; `spec["cameras"]` gives
each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every
response carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel`
(`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort`
(`effort_<joint>`, the actuators' generalized force on each joint).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
