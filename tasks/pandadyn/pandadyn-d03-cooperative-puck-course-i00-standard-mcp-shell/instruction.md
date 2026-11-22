# Panda Dynamic Scenes · Cooperative puck course (D03) — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service, eai-standard/2.1)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open, and you reach it only through a client. You get one client, one episode at a
time and 3 resets.
**Task:** A low-friction puck is already sliding across the table toward the left arm when the episode starts. The two Pandas each hold a paddle and must hit the same puck in turn: left, right, left, right. After each of the first three hits the puck must pass through a different gap in a row of posts standing across the table between the arms. First it goes toward the right arm through the gap at the -y end. Then it goes back toward the left arm through the gap at the +y end, next to a side rail. Then it goes toward the right arm again through the middle gap. The right arm's final hit must send the puck across a goal line in front of a backstop wall on the right arm's side.

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
closed. Base frame of this robot: the scene's world frame, shared by both arms: origin on the table top (z = 0), +X from
the left arm (panda-0, at the -X end, facing +X) towards the right arm (panda-1, at the +X end, facing -X), +Y left as
seen from the left arm, +Z up; positions in the task text are already in this frame, and each arm's base pose is in
describe_robot's spec_file (robot_spec.arms). Space `native` sends rows in the robot's own action types exactly as the
sections below describe them (their frame, units and gripper values).

**This robot** (two Franka Panda arms (7 joints each) facing each other across a table, panda-0 on the left and panda-1
on the right, each hand carrying the task's tool (or bare, with its two-finger gripper), torque-controlled behind
jerk-limited joint servos): left (arm: 7 joints); right (arm: 7 joints). Cameras: `overview`, `closeup`.

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
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** Each arm takes absolute joint-position targets (rad). Its servo turns every new target into a
smooth, jerk-limited motion (the joints arriving together, at most about 1.4 rad/s on joints 1-4 and 1.7 rad/s on joints
5-7) and tracks it with torque control, so a far target is reached smoothly: move_robot with a short duration_s (e.g.
0.01) sends the goal as one target and lets the servo set the pace, a longer duration_s ramps the target. There is no
end-effector pose command and no kinematics service: joints only. The scene moves by itself from the first control step,
and robot time passes only inside calls that move or wait (10 ms per control step; observe with seconds 0 is free), so
prepare a motion before sending it and use execute_trajectory (space joint, dt from 0.01 s) for timed sequences.
Positions in the task text are world coordinates (base_text says how they map to the base frame). describe_robot's
spec_file has robot_spec (base poses, joint, servo and safety limits) and proprio_groups for proprio_now (joint_pos,
tcp_pose, joint_vel, gripper_opening, joint_effort, tool_pose: world frame, quaternions wxyz; target: the targets in
force). Native rows (action type joint_position): per arm joint1..7 (rad) then the gripper aperture (m, 0 = closed ..
0.08 = open), panda-0 first.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each carries a flat rigid paddle, 0.10 m long (2 x `tool_half`, `tool_half` = 0.05 m), 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool -x) side: a horizontal bar 0.035 m above the tool origin (tool x from -0.132 to -0.038), a vertical post at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the paddle's back face (x from -0.044 to -0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool link. The tool frame is the paddle centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre (tool -x) and 0.04 m above it. Left paddle start: centre (-0.05, -0.18, 0.048), orientation identity (faces normal to world x, length along world y). Right paddle start: centre (0.28, 0.12, 0.048), quaternion (0, 0, 0, 1) (yawed 180 deg). At the start height each paddle's lower edge is 0.023 m above the table. In this task the servo damping on joints 5-7 is raised to (24, 20, 14) from the default (12, 10, 7). Role labels (panda-0 / panda-1) by phase: left_first_pass striker / preparing_receiver; right_return_route preparing_receiver / striker; left_diagonal_pass striker / preparing_receiver; right_terminal_shot cleared_partner / goal_striker. On both arms the tool's adapter runs between the fingertips: closing a gripper to less than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as `self_collision` (both grippers start fully open, at 0.08 m).

A small orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction, so it slows down only slowly. At t = 0 it is already moving toward the left arm. A row of four short orange posts stands across the table between the two arms; each post is 32 mm x 50 mm and 70 mm tall. The posts leave three gaps, and they are very bouncy. A long rail, 70 mm tall and also very bouncy, runs along the +y side of the course. A short backstop wall, 0.13 m wide and 70 mm tall and not bouncy, stands behind the goal line on the right arm's side. All of these are fixed, and only the puck moves by itself. The table top is the world's z = 0 plane.

**Goal geometry.** The puck's centre must cross three passage lines. P0 = (0.12, -0.13), P1 = (0.12, 0.19) and P2 = (0.12, 0.025); each is a crossing of x = 0.12 with |y - y_P| < 0.055 m. The goal line, is a crossing of x = 0.46 in +x with |y + 0.02| < 0.05 m.

## Time in this scene
The scene is dynamic: from the episode's first control step on, things move by themselves (as described above), and they do not wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and
every second of an `observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you
think. A call that runs control steps runs them all (unless the episode ends during it), whatever happens meanwhile, and
returns what the cameras saw. The episode lasts at most **25 s of robot time** (the task's horizon,
2500 control steps): when it is reached before the task is complete, the task has failed. The puck is already sliding toward the left arm at t = 0 and keeps sliding for a long time, so it is moving from the very first frame. A paddle touch counts as a strike only while the paddle itself is moving.

## Success
The task has 4 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_first_pass**: First, a strike by the left paddle is registered: the first moment in this phase when the puck touches the left paddle while the paddle body moves faster than 0.035 m/s, more than 0.06 s after the previous registered strike. Only that first qualifying contact counts as the strike; later touches are allowed but do not register again. Then, more than 0.035 s after the strike and while the puck is not touching the left paddle, the puck's centre crosses the line x = 0.12 moving in +x, with |y - (-0.13)| < 0.055 m. Moving in +x means x was <= 0.12 on the previous physics step and is > 0.12 now. This line passes through the gap between the first and second posts from the -y side.
2. **right_return_route**: A strike by the right paddle is registered under the same rule: the puck touches the right paddle while that paddle moves faster than 0.035 m/s, more than 0.06 s after the previous registered strike. Then, more than 0.035 s after it and while the puck is not touching the right paddle, the puck's centre crosses x = 0.12 moving in -x, with |y - 0.19| < 0.055 m. This is the gap between the third and fourth posts, next to the side rail.
3. **left_diagonal_pass**: A strike by the left paddle is registered (same rule). Then, more than 0.035 s after it and while the puck is not touching the left paddle, the puck's centre crosses x = 0.12 moving in +x, with |y - 0.025| < 0.055 m. This is the middle gap, between the second and third posts.
4. **right_terminal_shot**: A strike by the right paddle is registered (same rule). Then, more than 0.035 s after it and while the puck is not touching the right paddle, the puck's centre crosses x = 0.46 moving in +x, with |y - (-0.02)| < 0.05 m. This is the goal line in front of the backstop. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`; `meta["reason"]`: `success`, `failed`, or `error` after a simulator error; the `submit` that
ended it also names the failure in `meta["why"]`).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each paddle may touch only the puck. The paddles must not touch the posts, the rail, the backstop, the table or the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their paddles must never touch each other, and a paddle must not touch its own arm. In every task: the two arms (and their tools) never touch each other
(`arm_arm_or_tool_collision`), an arm never touches itself (`self_collision`), no robot part touches the table or the floor
(`forbidden_collision`, `tool_table_collision`), a robot link other than an allowed one touches no object or fixture
(`forbidden_arm_object_contact`, `forbidden_arm_scene_contact`, `forbidden_arm_fixture_contact`), a tool touches only the
task's objects and the fixtures the task allows (`forbidden_tool_fixture_contact`), and no contact penetrates deeper than
4 mm (`excessive_penetration`).

**Safety limits** (the Franka Panda's own limits, checked every 1 ms on each arm; `spec()["robot_spec"]["safety_limits"]`):
measured joint positions within the joint limits (+0.002 rad); measured joint speeds at most 1.01 x (2.175, 2.175, 2.175,
2.175, 2.61, 2.61, 2.61) rad/s; finger speeds at most 0.051 m/s; the hand's TCP at most 1.01 x 1.7 m/s and 1.01 x
2.5 rad/s; joint accelerations (measured over every 20 ms window) at most 1.05 x (15, 7.5, 10, 12.5, 15, 20, 20) rad/s²
and jerks at most 1.05 x (7500, 3750, 5000, 6250, 7500, 10000, 10000) rad/s³; the TCP's acceleration (20 ms windows) at
most 1.05 x 13 m/s² and 1.05 x 25 rad/s²; motor torques at most (87, 87, 87, 87, 12, 12, 12) N m, changing at most
1000 N m/s. The servo's own reference motion is checked against the same speed, acceleration and jerk limits. A contact
(a catch, a strike) moves the arm too: what is measured counts, whatever was commanded.

## Rules (real-robot rules)
- **Episodes and resets.** The first episode starts when the service comes up. An episode ends on success, on a failure,
  when your time is up, or on a simulator error. You have **3 resets** (`spec()["budget"]["reset"]`, which is
  authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot and the scene
  back on the same frozen starting state (the scene is rebuilt, about a second; no robot time passes) and starts a new
  episode, either abandoning the running episode or after one has ended; it returns the start's frames and
  proprioception. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives
  `resets_left`) until you reset. **Only the last episode is graded**: an episode you reset away is never graded, a
  success ends the run at once (no reset after it), and when your time is up the episode then running is the one graded.
  The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, fingers, hand TCP and tool poses, velocities, motor torques, the targets in force). No object poses, no success
  signal before the end: the service tells you that an episode ended and why (`meta["done"]`, `meta["reason"]`:
  `"success"`, `"error"` after a simulator error, else `"failed"`).
- There is nothing to hand in: the service records every control step it ran and grades the last episode as it ran.
  Keep the program that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current. Do
  not stop early: while the episode runs, or a reset is left, the run can still pass.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and
  simulated time are reported as cost.
- **If the service crashes**, a call fails with a connection error (or a 5xx): it restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.status()` answers
  again once it is back; check `control_steps` before you continue (`spec()["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring (`python -c "import rcb_client; help(rcb_client)"`) lists the calls and
their arguments; it is the client of every `eai-standard/2.1` service, so the robot facts it names as examples are not
this robot's: this robot's are in `r.spec()` and below. The calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: the action layout and limits, `control_dt` (0.01 s), `max_chunk_s`, `max_watch_s`, the cameras and their calibration, `proprio_layout` / `proprio_groups`, `robot_spec` (bases, servo and safety limits), `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("joint_position", A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 16 targets `dt` seconds apart (a chunk covers at most 10 s), and returns what the cameras saw meanwhile; stops early when the episode ends |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free, no time passes), or hold the last targets and watch for `seconds` (at most 30) |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state (at most 3 in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch),
`res.depth[camera]` (with `include_depth=True`, metres), `res.proprio` (proprioception rows: one at the call's start, one
every 1/`video_fps` s of robot time, one at its end). `video_fps` (1..30, default 10) sets how many frames a call returns. One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call"). A malformed request raises `ValueError` and runs nothing; once an
episode has ended, `submit` raises `EpisodeOver` (409) and `get_obs` still answers (no time passes).
```python
from rcb_client import Robot
import numpy as np
r = Robot()
obs = r.get_obs(cameras="overview")                                    # the robot at the frozen start (no time passes)
q0 = np.asarray(obs.meta["proprio"]["now"])
rows = ...                                                             # (T, 16) targets, one per control step
res = r.submit("joint_position", rows, dt=0.01, interpolate="hold", cameras="closeup", video="frames", video_fps=25)
res.frames["closeup"], res.proprio, res.meta["done"], res.meta["reason"]
if res.meta["done"] and not res.meta["reason"] == "success":
    r.reset()                                                          # a new episode (while resets are left)
```
Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area), with their
calibration in `spec()["cameras"]` (`intrinsic_cv`, `extrinsic_cv`, `cam2world_gl`); z-depth on request.
`cameras=None` (or `[]`) means both: name the one you need. `video="none"` returns only the last frame (the fastest call).

### Action type
- `joint_position` (16 per row): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at most
  0.025 m/s). Rows are `dt` apart (a multiple of the 0.01 s control period); `interpolate="linear"` (default: a straight
  line from the targets in force) or `"hold"`; a chunk may cover at most 10 s; out-of-limit values are clipped and listed
  in `meta["clipped"]` (limits in `spec()["action_types"]["joint_position"]`). The client sends the rows as float64, and
  the service executes them as sent. `observe` with `seconds > 0` keeps the last targets in force.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 5 % (jerk) of the Panda's joint
  speed, acceleration and jerk limits, and the arm tracks that reference with torque control (PD + inverse dynamics, the
  Panda's torque and torque-rate limits). A new target replans from the current reference motion, so a target far away is
  reached smoothly, not in one step. `spec()["robot_spec"]["servo"]` has the exact limits and gains.

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- `spec()["proprio_groups"]` names the proprio columns: `joint_pos` (per arm joint1..7, finger_left, finger_right), `tcp_pose`
  (the hand TCP, between the fingertips), `joint_vel`, `gripper_opening`, `joint_effort` (motor torques), `tool_pose` (the
  task tool's frame), `target` (the targets in force). The arms are listed panda-0 first.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **2048 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
