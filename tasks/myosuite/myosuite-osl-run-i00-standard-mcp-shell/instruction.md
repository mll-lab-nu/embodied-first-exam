# MyoSuite · osl_run — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service, eai-standard/2.2)

You control the **MyoLeg + OSL**, a free-standing musculoskeletal model of a human whose right leg is an Open-Source Leg knee-ankle prosthesis, **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open. You get one client and up to 11 episodes, and you act only through its actuators (54 muscles and 2 other actuators).
**Task:** Run the track: move forward 29 m along it to the finish (MyoChallenge 2024 OSL Run, its own win condition), staying within 1 m of the track's centre line and on your feet; the right leg is the prosthesis (`osl_knee_angle_r`, `osl_ankle_angle_r`), driven by its own controller, so you command only the 54 muscles. Failure (the episode ends): falling, leaving the track sideways, or moving 2 m backwards. There is no time limit.

A musculoskeletal body whose right leg is an Open-Source Leg prosthesis (knee and ankle motors driven by its own controller) stands at the start of a straight, flat running track.

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
closed. Base frame of this robot: the simulator's world frame (z up): camera poses are given in it; no part here takes
an end-effector pose. Space `native` sends rows in the robot's own action types exactly as the sections below describe
them (their frame, units and gripper values).

**This robot** (MyoLeg with an Open-Source Leg prosthesis: a free-standing musculoskeletal human with the right leg's 54
muscles and a knee-ankle prosthesis on the left (MyoSuite, MuJoCo)): its own action types only (`execute_trajectory`
space `native`; `describe_robot` lists them). Cameras: `topview`, `side_view`, `agent_view`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
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

**Notes on this robot.** A muscle's command a sets its excitation u = 1 / (1 + exp(-5 (a - 0.5))), not clipped (a = -1:
about 0.0006, a = 0.5: 0.5, a = 1: 0.92); activation follows excitation with a short delay (about 10 ms up, 40 ms down);
muscles only pull, one muscle can cross several joints, and its force depends on its length and speed. Before your first
command of an episode every column holds -1 (all muscles relaxed). Action type actuators has 56 columns: 0-53 the
muscles, 54-55 the prosthesis's knee and ankle torques, which are ignored (the prosthesis's own impedance controller
sets them). Every command goes through execute_trajectory space native (action_type actuators, 56 numbers per row). The
root (pelvis) is free-standing: its pose and velocity in the world frame are proprio groups root_pose (x y z + wxyz
quaternion) and root_vel. The robot's own action type takes one row per control step (0.01 s, 100 Hz), columns in its
layout (describe_robot: action_types_native; spec_file has each actuator, muscle and joint). The state is proprio_now
(layout in spec_file: proprio_layout, proprio_groups): joint positions and velocities, muscle activations and lengths,
joint efforts. There is no joint-level controller: joints move only through muscle forces. Time passes only inside
calls; the service says when the episode ended and why, never the object or goal state.

## Rules
- **Episodes and resets.** The episode starts when the service comes up and ends on success (the challenge's own success event), on its failure conditions or its own time limit, when your time is up, or on
  a simulator error. You have **10 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says
  0, there is no reset and the one episode is the run). A reset (`POST /reset`, below) puts the body and the scene back
  on the same frozen starting state and starts a new episode, either abandoning the running one or after one has ended;
  it takes no simulated time and returns the start's images and proprioception. Once an episode has ended, `submit`
  raises `EpisodeOver` until you reset. **Only the last episode is graded**: an episode you reset away is never graded,
  a success ends the run at once (no reset after it), and when your time is up the episode then running is the one
  graded. The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the
  episodes (`meta["control_steps"]` is the current episode's).
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the body's own proprioception: joint positions, velocities and actuator torques, muscle activations and lengths and the pose and velocity of your free-standing root (the pelvis: `root_pose`, `root_vel`).
  No object, ball, opponent or goal poses, no success check: `meta["done"]` / `meta["reason"]` tell you when the episode
  is over and why.
- Steps are unlimited; your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). Do not stop early: while
  the episode runs, or a reset is left, the run can still pass.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: side_view)
obs = r.get_obs(cameras=["topview"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*, root_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.005)          # rows: (T, 56) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["topview"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```
Cameras: `topview`, `side_view`, `agent_view` (640x480; default `side_view`). `spec["cameras"]` gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every response carries each frame's pose. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a
chunk fastest. One call returns at most 1000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call"). Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`),
`muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort` (`effort_<joint>`, the
actuators' generalized force on each joint), `root_pose`, `root_vel`. `/kinematics` gives the camera mounts for any joint positions.

### Action type `actuators` (56)
56 real numbers per control step, one per actuator in order: 54 muscles and 2 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `osl_knee_torque_actuator` (index 54): ignored: the prosthesis's own impedance controller (MyoSuite's OSL state machine) sets it; `osl_ankle_torque_actuator` (index 55): ignored: the prosthesis's own impedance controller (MyoSuite's OSL state machine) sets it. Columns in `spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart (a whole multiple of the
5 ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous command) or `"hold"`; the client sends them as float32. The control rate is 200 Hz (5 physics
substeps); there is no step budget.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **7 GiB of memory**, **2048 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
