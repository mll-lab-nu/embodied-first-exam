# DexToolBench · long screwdriver · spin_horizontal (MuJoCo) — STANDARD MODE, MCP TOOLS ONLY (robot as a service)

A KUKA iiwa 14 arm with a 22-joint **Sharpa HA4** dexterous hand stands next to a table with a **long screwdriver** on it.
**Task:** pick up the long screwdriver and move it through the demonstrated motion (spinning it about a horizontal axis): bring it to each
of the **31 goal poses in order** (the green ghost tool shows the current goal). This is task `screwdriver / long_screwdriver /
spin_horizontal` of DexToolBench (SimToolReal), run here in plain MuJoCo.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get the `efe-robot` tools and **20 resets**: at most 21 episodes, of which the last is graded.

## Robot tools (MCP server `efe-robot`)
You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for
example `mcp__efe-robot__move_robot`). You may write and run code to compute; every robot command and observation must
go through the efe-robot MCP tools; code must not contact the simulator. Each robot command or observation is a tool
call you make yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is
checked against the server's. To send a trajectory your code computed, save it as a file under `/app` and pass its path
as `rows_file` to `execute_trajectory`. The robot service and its rules are as described in this text; where it names
calls of the Python client `rcb_client.py`, which is not installed for your code here, use the tool that does the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |
| `r.reset()` / `POST /reset` | `reset_episode()` |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the scene's world frame (z up), not the arm's base: the table's centre is at x = y = 0
with its top at z = 0.53 m, and the iiwa's base stands at (0, 0.8, 0); no part here takes an end-effector pose. Space
`native` sends rows in the robot's own action types exactly as the sections below describe them (their frame, units and
gripper values).

**This robot** (KUKA iiwa 14 arm with a 22-joint Sharpa HA4 left hand on its flange (DexToolBench scene, MuJoCo): 29
joint position targets): arm (arm: 7 joints); left_hand (hand: 22 joints). Cameras: `front`, `side`, `top`, `oblique`.

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
  apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` (2-D float array) or `.csv` (one
  row per line, comma-separated) of native rows for space `native` (with `action_type`), or a `.json` list: of number
  arrays (native rows) or of row objects as in `rows` (the other spaces). Long arrays go this way rather than inline.
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `reset_episode()`: a new episode from the same starting state (it uses one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** The arm and the hand take joint positions only: there is no end-effector pose command and no
kinematics service here, so placing the hand or the tool means choosing the iiwa's 7 joint angles (limits in
describe_robot). Rows are one control step apart (1/60 s) and each row's targets are held or ramped linearly between
rows. The goals are shown in the images as a green ghost copy of the tool, one goal at a time in order; the current goal
counts as reached when the tool's grasp box is within 1.5 cm of it at every corner, and the next one then appears. Goals
have no time limit; the episode ends when every goal is reached, at its control-step limit, or when your time is up.
Time passes only inside calls.

## Rules (real-robot rules)
- **Episodes and resets.** You have **20 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0,
  there is no reset and the one episode is the run). `r.reset()` puts the robot, the tool and the goals back to the same
  starting state and starts a new episode, either abandoning the running one or after one has ended. Within an episode
  nothing is undone: a tool knocked off the table stays there until you reset. **Only the last episode is graded**: a
  success (every goal reached) ends the run at once, and when your time is up the episode then running is the one
  graded, so do not reset away a good episode late. Resetting does not stop or restore the clock.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration) plus the
  robot's own joint positions, velocities and targets. No object poses, no success predicate.
- Your only budget is the time limit (`## Time limit`). `meta["time_left_s"]` is the service's count of it, from your first
  request to the service: it never runs out before your time does, so plan by it. There is nothing to hand in: the
  service records every episode, and grades the last one as the trajectory.
- Do not use pretrained manipulation policies or any published solution for this benchmark.
- **Images are files.** The tools write camera images, depth and video under `/app/obs/` and return their paths with small JSON; open an image with your file-reading tool, or ask for small images in the result with `inline_cameras`.

## Scoring
The current goal counts as reached when all 8 corners of the tool's grasp box (0.141 × 0.030 × 0.027 m, scaled by
1.5, in the tool's frame) are within **1.5 cm** of the same corners at the goal pose; then the next goal becomes
current. In this mode goals have **no time limit** (the benchmark gives each goal 10 s). An episode ends when every goal is reached, when your time is up, or after **360,000 control steps (100 min of robot time)**. **Only the last episode is scored.**
**Score: 1 if all 31 goals are reached, else 0.** Goals reached / 31 is reported as `progress`; there is no partial credit.

## The robot service through its Python client (reference; your code cannot reach it: act through the `efe-robot` tools above)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # camera names
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> float16 metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joint positions, velocities, current targets
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]                              # see below
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold the targets and watch for 2 s (max 30)
res = r.submit("joint_position", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 29) rows dt apart
res.meta["done"], res.meta["reason"], res.meta["task"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
obs = r.reset(cameras=cams)                   # a new episode from the starting state; obs.meta["resets_left"]
```
- Actions `joint_position` (29: `joint1..joint7` (iiwa), then the 22 Sharpa hand joints (names in `spec["action_types"]["joint_position"]["layout"]`)); rows are `dt` apart (a multiple of `control_dt`), each held
  (`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
  limits in the spec. A chunk covers at most 10 s.
- `meta["task"]` = the current goal (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`, `goals_reached`, `steps_left_on_goal`
(the benchmark shows the controller the current goal, as SimToolReal's deployment does). The episode **ends** when every
goal is reached or at the step limit (`spec["max_control_steps"]`); after that `submit` raises `EpisodeOver` (409) until you reset.
`steps_left_on_goal` is null: no goal has a time limit here.
- `r.reset(cameras=None, include_depth=False)` (`POST /reset`): a new episode from the same starting state (at most 20 in all);
  it returns the start's frames, and `meta` (also `r.status()`) carries `episode`, `resets_left` and `control_steps_total`.
- Calibration: `meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world,
  OpenGL axes: x right, y up, the camera looks along -z; the viewpoint the image is rendered from), for the state at the
  **end** of that call (the `last` image and the last frame of every stack). Depth is the distance along the viewing
  axis, in metres. The four cameras are fixed.

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **11 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
