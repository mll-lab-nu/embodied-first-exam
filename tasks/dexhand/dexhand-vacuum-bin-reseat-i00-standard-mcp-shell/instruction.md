# DexHand: Remove and reinstall a vacuum dust bin — MCP tools and shell

Remove the dust bin from the handheld vacuum on the counter and reinstall it. The bin is held by its two lower tabs on ledges at the bottom of the motor housing and by a spring latch at the top: the latch tooth on the red release button stops the bin's top catch from tilting out, and a fixed lip over the catch bridge stops it from being lifted straight out, so the top must tilt out from under the lip, which the tooth only allows while the button is pressed. Stages, in order: (1) release and remove: press the release button by at least 5.8 mm while the bin is still in its seat (bin origin within 5 mm of its seated pose), then take the bin away until its origin is more than 30 mm from its seated pose (both measured in the vacuum-body frame); (2) reinstall: put the bin back so that its origin is within 3 mm and its orientation within 0.05 rad of the seated pose (vacuum-body frame), the release button is back up (travel at most 1.5 mm, latch tooth raised) and the bin's catch is behind the tooth face (at most 0.5 mm in front of it); (3) let go: the stage-2 condition must hold with no hand contact on the bin, the vacuum body or the button, the bin and the vacuum body at rest (linear speed at most 0.01 m/s, bin angular speed at most 0.1 rad/s), for 50 consecutive controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 1 ms physics substep, when the vacuum body moves more than 50 mm or tilts more than 0.35 rad from its start pose, when the bin falls (centre-of-mass downward speed above 0.99 m/s, i.e. a free fall from 5 cm, or above 0.55 m/s while nothing touches it), touches the floor or a table leg, its origin drops below the counter top (z < 0.65 m) or leaves the workspace box x in [0.2, 1.1] m, y in [-0.45, 0.45] m, z in [0.6, 1.2] m, when bin and vacuum geometry interpenetrate by more than 4 mm, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets (the two wrist stages and the fingers of both hands) are allowed; no object teleports, welds or applied forces. The episode allows at most 3000 controls at 50 Hz.

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin (0.45, 0.0, 0.8) m) and
the left hand (the right hand's mirror image) on `left_wrist_stage` (origin (0.55, 0.3, 0.95) m).
Both are needed as in the real task: one hand steadies the vacuum (or works the button) while the other handles the
bin. The stages and the fingers are position actuated in the physics engine under native force bounds; the vacuum
body, the dust bin and the release button move only through contact and their passive dynamics (the button is a spring-loaded
slide). The controller runs at 50 Hz, with twenty 1 ms physics substeps.

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |
| `r.reset()` / `POST /reset` | `reset_episode()` |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the scene's world frame (+Z up; the wrist stage is fixed in it): the coordinates of
the task text. Space `native` sends rows in the robot's own action types exactly as the sections below describe them
(their frame, units and gripper values).

**This robot** (two Sharpa Wave dexterous hands (22 finger joints each), each on its own six-axis wrist stage, no arm):
right_hand (hand: 22 joints); right (arm: 6 joints); left (arm: 6 joints); left_hand (hand: 22 joints). Cameras:
`overview`, `closeup`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `reset_episode()`: a new episode from the same starting state (it uses one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** Two hands on two wrist stages (parts right, left: stage joints; right_hand, left_hand:
fingers), all joint positions; the right stage's measured hand-mount pose comes back as ee. Every column is a position
target (servo); grasping and carrying work only through contact. The parts follow the Sharpa Wave layout (describe_robot
spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20 finger joints per hand) the columns differ: use
execute_trajectory space native with the order in spec action_types.joint_position.layout. Rows are 0.02 s apart or a
multiple of it; a call covers at most 10 s. Measured poses are in the world frame of the task text, quaternions wxyz.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Two hands, each on its own six-axis wrist stage. Sharpa (56): right stage (6), right fingers (22), left stage (6), left fingers (22). Wuji (52): right stage (6), left stage (6), right fingers (20), left fingers (20). The left hand is the right Wave mirrored in y (shared arm_rig.mirrored_left_wave); one row is one 50 Hz control (twenty 1 ms physics substeps).
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`56` for `sharpa`, `52` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

## Scene and frames
The world frame has z up; lengths are in metres, angles in radians, quaternions WXYZ. A handheld vacuum (free body
`vacuum_body`, 0.752 kg) stands on its base skid on the counter (top at z = 0.65 m); its transparent dust bin (free body
`dust_container`, 0.18 kg) sits in front of the motor housing, with the nozzle overhanging the counter edge. The bin is
held at the bottom by two tabs resting on two ledges inside its mouth and at the top by the latch tooth of the red
release button (`release_button`, spring-loaded slide joint `button_depression`, 0 to 6 mm of travel, 600 N/m; the
source scene's values). The tooth's ramp lets the bin's catch push it down while the bin is closed; pressing the button
(nearly its full 6 mm) lowers the tooth below the catch. Latch tooth, catch and bridge have the source's plastic friction
0.55, so pushing the catch over the raised tooth needs a large closing force. A fixed lip on the housing sits 0.7 mm above the catch's bridge, so the seated bin cannot be
lifted straight out: its top has to tilt out from under the lip, which the raised tooth prevents. The vacuum-body frame is the body frame of `vacuum_body`; the seated bin pose in that frame is
fixed by the frozen start state (the bin starts seated). Cameras: `overview` (the counter
from the front left) and `closeup` (the latch and the bin).

## Episodes and resets
You have **20 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).

## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset. The service
records every action and watch step, then judges the graded episode as it ran (that is the verdict; nothing is replayed).
Leave your controller at `/app/output/gen.py`; no trajectory hand-in is needed.

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
res.save("/app/runs/001")
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `D` is 56 for `sharpa`: the right
stage `wrist_x, wrist_y, wrist_z` (metres, offsets of the stage from its origin) and `wrist_rx, wrist_ry, wrist_rz`
(radians, serial XYZ joints), the 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`, the
left stage `left_wrist_x` ... `left_wrist_rz` and the 22 left finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`.
`D` is 52 for `wuji`: right stage, left stage, the right Wuji Hand 2.2 fingers `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`
and the left Wuji fingers `l_wuji_l_...` (the layout list is authoritative). Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most
10 s. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.65 m. Cameras are overview
and closeup, at 640 x 480. Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the
service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing.

One call returns at most 1000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **10 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
