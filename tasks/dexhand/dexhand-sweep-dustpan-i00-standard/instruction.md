# DexHand · Sweep debris into a held dustpan (standard)

## Task
Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan.

## Goal
Success: every one of the six pieces has been touched by the broom's bristles; all six lie on the pan floor, touching
the pan; the pan is held up off the floor; and everything is still for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- A piece leaves the floor work area.
- Any part of the robot touches a piece (sweep with the broom only).
- After the short settling period at the start, a tool slips in its hand or falls out of it.
- A tool is pressed by any robot part other than its own hand.
- The arms, the torso or the two hands collide with each other.
- The physics becomes unstable.

The steps before the last count as they happen.

When you are done, send `/finish` to end the episode and get it graded. Everything else is judged on the state at that
point.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded. No reset is possible after
  `/finish`.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no score, no success
  signal.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, over a floor (DexHand, MuJoCo).
The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"], spec["action_types"]["joint_position"]["layout"]
obs = r.get_obs(cameras=["work"], depth=True)
obs.last["work"]               # RGB uint8 (480, 640, 3)
obs.last_depth["work"]         # z-depth in metres
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.0005, interpolate="hold", video="none")
r.fk(q)                        # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
The client sends rows as float32. Requests return at most 1,000 camera images; ask for fewer cameras or a lower
`video_fps` for long chunks. `hold(s)` holds the current targets and records those steps; `get_obs()` only observes.
Forward kinematics covers the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in
  `fields`) and returns the service's reply `meta` unchanged; images, arrays and video are written as files under
  `/app/obs/` (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file
  (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `dt` must be a multiple of
`1 / spec["control_hz"]` (0.0005 s), at most 0.5 s; a chunk covers at most `spec["max_chunk_s"]` seconds. `hold` keeps
each row for `dt`; `linear` interpolates from the previous target. Targets are clipped to the published joint limits and
clipping is reported.

Every row holds both arms' joint targets and both hands' finger targets (layout below). Sharpa rows (58 targets): the 7
left-arm joints `SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand Sharpa
Wave finger targets (radians). Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20
right-hand Wuji Hand 2.2 finger targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC
flexion, CMC abduction, MCP, IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both palm poses (`l_hand_palm`, `r_hand_palm`) and current targets. Object poses, contacts are not published. Cameras
are overview, work (the floor area and the pan), pan and side, 640 x 480, fixed in the world. Measured poses use WXYZ
quaternions; world z is up, metres, the robot base at the origin, the floor the plane z = -0.10 m.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order. This task uses two hands of one model on the two arms of a fixed robot: Sharpa Wave (default) or
Wuji Hand 2.2. With Wuji the start differs only in the finger joints and their targets: both Wuji hands start closed on
the same broom and dustpan (the arm, tool, debris and bristle coordinates and the arm targets are those of the Sharpa
start), and the targets at the start keep them.

### Robot
The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its handle;
the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force bounds; the
broom, the dustpan and the debris move only through contact and gravity. At the start the current targets keep both
tools in the hands; the first 1.2 s are a settling period in which the grip is not yet judged. The simulator integrates
at 0.5 ms and every action row is one physics step, so rows are a 2000 Hz control. The service simulates slower than
real time (several seconds of CPU per simulated second).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 160,000 rows (one per 0.5 ms physics step) (80 s of simulated time) per episode; an episode that
  reaches them ends there.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
