# DexHand · Remove and reinstall a vacuum dust bin (standard)

## Task
Remove the dust bin from the handheld vacuum on the counter and reinstall it.

## Goal
Success: in this order, the red release button is pressed nearly all the way down while the bin is still seated, and the
bin is taken clear of its seat; the bin is put back exactly in its seat with the button back up and the bin's catch
behind the latch tooth; then no hand touches the bin, the vacuum or the button, and both are still for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The vacuum body is moved or tilted.
- The bin falls, touches the floor or a table leg, drops below the counter top or leaves the work area.
- The bin and the vacuum are pressed into each other.
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
Two dexterous hands, each on its own six-axis wrist stage (no arm), at a counter (DexHand, MuJoCo). The robot runs as a
service you reach through its client or its MCP tools, as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
`hold(s)` holds the current targets and records those steps; `get_obs()` only observes the current state. Forward
kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. One call returns at most 1000 images.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `D` is 56 for `sharpa`: the right stage
`wrist_x, wrist_y, wrist_z` (metres, offsets of the stage from its origin) and `wrist_rx, wrist_ry, wrist_rz` (radians,
serial XYZ joints), the 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`, the left stage
`left_wrist_x` ... `left_wrist_rz` and the 22 left finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`. `D` is 52
for `wuji`: right stage, left stage, the right Wuji Hand 2.2 fingers `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3` and the
left Wuji fingers `l_wuji_l_...` (the layout list is authoritative). Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s.

Sharpa (56): right stage (6), right fingers (22), left stage (6), left fingers (22). Wuji (52): right stage (6), left
stage (6), right fingers (20), left fingers (20).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.65
m. Cameras are overview and closeup, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`56` for `sharpa`, `52` for `wuji`)
and the exact order.

### Robot
You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin (0.45, 0.0, 0.8) m) and the left hand
(the right hand's mirror image) on `left_wrist_stage` (origin (0.55, 0.3, 0.95) m). Both are needed as in the real task:
one hand steadies the vacuum (or works the button) while the other handles the bin. The stages and the fingers are
position actuated in the physics engine under native force bounds; the vacuum body, the dust bin and the release button
move only through contact and their passive dynamics (the button is a spring-loaded slide). The controller runs at 50
Hz, with twenty 1 ms physics substeps.

Each stage's `x, y, z` targets are offsets (metres, along the world axes) from its origin; the rotations are serial XYZ
joints (radians).

Two hands, each on its own six-axis wrist stage. The left hand is the right Wave mirrored in y; one row is one 50 Hz
control (twenty 1 ms physics substeps).

### Scene
The world frame has z up; lengths are in metres, angles in radians, quaternions WXYZ. A handheld vacuum (free body
`vacuum_body`, 0.752 kg) stands on its base skid on the counter (top at z = 0.65 m); its transparent dust bin (free body
`dust_container`, 0.18 kg) sits in front of the motor housing, with the nozzle overhanging the counter edge. The bin is
held at the bottom by two tabs resting on two ledges inside its mouth and at the top by the latch tooth of the red
release button (`release_button`, spring-loaded slide joint `button_depression`, 0 to 6 mm of travel, 600 N/m). The
tooth's ramp lets the bin's catch push it down while the bin is closed; pressing the button (nearly its full 6 mm)
lowers the tooth below the catch. Latch tooth, catch and bridge have the source's plastic friction 0.55, so pushing the
catch over the raised tooth needs a large closing force. A fixed lip on the housing sits 0.7 mm above the catch's
bridge, so the seated bin cannot be lifted straight out: its top has to tilt out from under the lip, which the raised
tooth prevents. The vacuum-body frame is the body frame of `vacuum_body`; the seated bin pose in that frame is fixed by
the frozen start state (the bin starts seated). Cameras: `overview` (the counter from the front left) and `closeup` (the
latch and the bin).

## Others
- The bin comes out only with its top tilted out from under a lip, and only while the release button is held down.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 3,000 control steps (60 s of simulated time) per episode; an episode that reaches them ends there.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
