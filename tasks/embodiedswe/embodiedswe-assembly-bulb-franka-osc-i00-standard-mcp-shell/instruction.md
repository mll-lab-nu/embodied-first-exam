# Screw a light bulb into its socket (Franka, operational-space control) — standard mode — MCP tools and shell

The task of `embodiedswe-assembly-bulb-franka-osc-i00-privileged`, on the same frozen scene. You drive a Franka Panda arm with its parallel gripper, under EmbodiedSWE's operational-space (torque) controller, as if it were real hardware: the simulator runs in a service you cannot open, and you get its client, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

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
closed. Base frame of this robot: the arm's base (panda_link0), at the world origin with the world's axes: +X forward,
+Y left, +Z up. Space `native` sends rows in the robot's own action types exactly as the sections below describe them
(their frame, units and gripper values).

**This robot** (Franka Emika Panda arm with the Franka Hand parallel gripper on a fixed base, driven by EmbodiedSWE's
operational-space (torque) controller): arm (arm: 2 joints, end-effector pose). Cameras: `front`, `overview`, `wrist`.

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
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** The arm takes end-effector poses only, tracked by EmbodiedSWE's operational-space (torque)
controller; its seven joints take no direct command. The end-effector pose is the panda_hand frame, not the fingertips:
the point midway between the fingertips is 0.1034 m along the hand's own +Z (approach) axis from it, so for a top-down
grasp put panda_hand 0.1034 m above the grasp point. The arm's two joint_positions are the finger position targets
(finger_1, finger_2, metres each: 0 = closed, 0.04 = open): send both together, e.g. [0.04, 0.04] to open and [0.0, 0.0]
to close; a closed target on an object squeezes it. gripper_opening_m in the state is the measured distance between the
finger pads (about 0.08 fully open). The measured joint angles are in observe's proprio_now (its layout:
describe_robot's spec_file, proprio_layout). One episode, no reset; it ends by itself once the task is complete.

## The task
1 lamp socket standing upright, fixed on a sturdy table, and 1 loose light bulb lying on the table beside it, ready to be picked up and fitted. Each socket carries a real internal thread.
Goal: pick up the bulb, set it on the socket, and screw it down (turn it clockwise while pressing down) until it seats. A seated bulb is held by its thread, and GLOWS ever brighter as it screws home — from a faint orange at first electrical contact to fully bright warm white exactly when seated. The task is complete once the bulb is seated.

Success, exactly: at the end of the run, the light bulb's lowest point (the bottom tip of its metal screw cap) is at most 27 mm above the base of the fixed lamp socket where it stands on the table (the socket's bore mouth is 38.5 mm above that base; a bulb merely resting on the mouth sits at about 35 mm or more), that point lies within 15 mm horizontally of the socket's vertical axis, and the bulb's axis from cap to glass is within 12° of the socket axis (glass up). Not true at the start (the bulb lies on the table beside the socket). No speed or release condition. [grader: seated().all(); bulb origin = its lowest point; socket origin on the table top at world (0.41, 0, 0)]

## This robot
- Action: `ee_pose` only, 9 values: the world pose of `panda_hand` (`x y z qw qx qy qz`) and the two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).
- Cameras (RGB 640×480, depth on request): `front`, `overview` (static) and `wrist` (on the hand). One call returns at most 240 images (`max_frames_per_call`, PROTOCOL §3 "Images per call": cameras × the frames captured, the first, one every round(15 / `video_fps`) control steps and the last, a per-frame depth one more image; `video="none"` captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no cameras gets `front`, `wrist` at 4 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.
- The episode ends after the first call at whose end the success condition holds (judged on the live simulator), when your time is up, on a simulator error, or after 400,000 control steps (7.4 h of simulated time, reason `step_guard`); it is graded as it stands then. Simulated time advances only inside your calls.
- The service answers one request at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
- Leave your scripts in `/app/output/` for the record.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **24 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
