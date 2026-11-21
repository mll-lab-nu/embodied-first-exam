# RoboCasa-GR1 · PnPPotatoToMicrowaveClose — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service)

A **Fourier GR1 humanoid** (arms, waist and two dexterous six-command Fourier hands; fixed base) works at a kitchen counter: RoboCasa's GR1 tabletop `PnPPotatoToMicrowaveClose` task (robosuite, MuJoCo).
**Task: pick up the potato, place it into the microwave and close the microwave.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

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

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame (body robot0_base, fixed in the kitchen): +X the way the robot
faces, +Y its left, +Z up. Space `native` sends rows in the robot's own action types exactly as the sections below
describe them (their frame, units and gripper values).

**This robot** (Fourier GR1 humanoid (arms and waist, fixed in the kitchen) with two six-command Fourier hands; the arms
take absolute grip-site pose targets solved by whole-body inverse kinematics): right_hand (hand: 6 joints); left_hand
(hand: 6 joints). Cameras: `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `egoview`,
`robot0_eye_in_right_hand`, `robot0_eye_in_left_hand`.

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
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** The arms take absolute grip-site pose targets in the robot base frame, sent with
execute_trajectory space native, action_type ee_pose (24 numbers, one row per 0.05 s control step, each row a target the
whole-body inverse kinematics moves toward): right x, y, z (m), rx, ry, rz (axis-angle, rad), the same for the left,
then the six right-hand and six left-hand finger targets. cmd_* in proprio_now is the command in force (start from it
and change what should move; interpolate long moves over several rows). The grip site is the origin of the hand's
mounting frame at the wrist end of the hand, not a point between the fingertips; the four small pink spheres beside each
hand are markers of the robot model. move_robot and execute_trajectory space joint set the fingers (the hands'
joint_positions); the reported finger values are the commands in force. eef_left_*/eef_right_* in proprio_now are the
grip sites' positions in the world frame. The cameras ride on the robot; each frame comes with its current calibration.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it). There is nothing
  to hand in: the service records the episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then applies the environment's own success check for `PnPPotatoToMicrowaveClose` to
the state of the live episode **after the last executed control step**: the episode as the service ran it, nothing is
replayed. A success reached earlier and then lost does not count: end in the state you want graded and stop submitting.

Both of these hold on the graded state (upstream `_check_success`, `tabletop_microwave_pnp.py`):
- the potato's centre (its body origin) is inside the microwave's interior;
- the door is shut: upstream's opening fraction is at most 0.005 (0 = shut, 1 = fully open).

Where the hands end up is not checked.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, egoview, robot0_eye_in_right_hand, robot0_eye_in_left_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_pose", A, cameras=cams[:1], video="mp4")   # A: (T, 24) rows, one per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `ee_pose`: the robot's native controller command, applied once per control step (`control_dt` =
  0.05 s; float64). 24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` -- absolute, in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order `little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not a binary grip. The GR1 has no mobile base. Values are clipped to the limits. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
  most 10 s).
- `get_obs(seconds=s)` keeps applying the last command (before the first one: both grip sites' current poses and the
  current hand commands) while physics runs for `s` seconds; those control steps are part of the episode. Every
  channel is an absolute target, so the grip sites stay within about a millimetre, but the IK's posture term can still
  move the waist and elbows by a few hundredths of a radian while you watch.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- The hands: each hand command is the position target, in radians, of that finger's joints (`thumb_flexion` drives
  two thumb joints, `thumb_rotation` one): 0 is the straight, open finger, larger values bend it toward the palm
  (the hand closes), and every finger joint stops at the end of its range (1.22 to 1.74 rad), so values below 0 or
  above about 1.7 change nothing more. The grip site that the pose targets place is the origin of the hand's mounting
  frame (`gripper0_right_grip_site`, `gripper0_left_grip_site`), at the wrist end of the hand, not a point between
  the fingertips. The four small pink spheres beside each hand are part of the robot model (visual markers
  `robot0_<side>_pinch_spheres_0..3`, about 13.5 cm from its grip site, with no collision): they are not objects.
- World frame: metres, z up. In the proprio, `eef_left_*` / `eef_right_*` are the grip sites' positions in the world
  frame; the action's pose targets and the `cmd_*` entries (the last command) are in the robot's base frame.
  The robot's base frame (body `robot0_base`, fixed in the world) has its origin at world (2.65000, -2.17500, 0.97000) m and is turned +90.0 deg about z (quaternion w x y z (0.70711, 0, 0, 0.70711)): `p_world = R @ p_base + t` with R = [[0, -1, 0], [1, 0, 0], [0, 0, 1]].

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
