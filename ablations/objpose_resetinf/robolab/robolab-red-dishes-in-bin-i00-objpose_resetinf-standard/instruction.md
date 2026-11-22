# RoboLab · red_dishes_in_bin (standard)

## Task
A Franka Panda arm with a Robotiq 2F-85 gripper at a table (NVIDIA RoboLab's DROID setup, Isaac Sim / PhysX). Put the
red dishware in the grey bin. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the red mug and the red bowl are both in the grey bin, and the gripper has let go of both. "The gripper" means
both fingers: an object that still touches either finger counts as held. The episode ends as soon as the task is done,
when your time is up, or on a simulator error. When your session ends with the episode still running, your last command
is held for 2 s more (30 control steps) while the task is still judged, so a release you sent last completes.

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
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while Isaac Sim starts and builds the scene, ~2 min; longer on a
                                              # busy host: it reports its progress on stderr and gives up after 3600 s)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (H,W,3)
obs.meta["proprio"]                           # {"layout": [...32 names], "now": [...]}: joints, gripper, end-effector pose, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.2)   # A: (T, 8) rows dt seconds apart; streamed at 15 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 8) fingertip-centre targets; differential IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["wrist_cam"]                        # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["wrist_cam"]                       # uint8 (N,H,W,3) at video_fps if requested
res.last["egocentric_mirrored_camera"]; res.proprio   # last frame per camera; float32 (N, 32) proprio at each video frame
```
- Optional inputs (ask only for what you need): `r.get_obs(depth=True)` -> `obs.last_depth[cam]`, float32 (H, W);
  `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N, H, W), one map per frame. Per frame: `res.frame_step`
  (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N, 3, 4, world -> camera, OpenCV axes). Proprio groups:
  `res.group("joint_vel")`.
- Kinematics: `r.fk(q7)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"tcp": pose7}, seed=q7)` ->
  `{"ok", "q", "error"}`: a stateless model of the arm (no physics, no simulated time).
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing. One
  call returns at most 2712 images.
- A busy service has not crashed. The service answers one request at a time: while a call runs (a long `submit` or a
  watching `get_obs` can take minutes; one call stops at `spec["max_call_wall_s"]`), every other request waits for it,
  `r.status()` from another process included. A client-side timeout while a call is in flight (for example a `requests`
  ReadTimeout on `r.status()`) means "busy": nothing restarts, the call runs to its end and the episode goes on from
  there. Keep one client process and wait for your call's answer.
- If the service crashes, the connection is refused or reset and the call is lost: the simulator restarts and resumes
  the same episode (never a reset) in the state after the last call it completed, which you may not have received.
  `r.wait_ready()` waits until it answers again (resuming replays the episode so far, which can take minutes; the wall
  clock keeps running); then check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).

### Actions
- `joint_position` (8): `panda_joint1..7, gripper`; radians, and the gripper command is binary (0 = open, 1 = closed; it
  switches at the row, never interpolated). Absolute targets tracked by PD controllers. Rows are `dt` apart
  (`1/15 ≤ dt ≤ 0.5` s, a multiple of the 15 Hz control period: 1/15, 2/15, ...; any other `dt` is rejected, never
  rounded); a chunk covers at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the
  spec). Use `obs.meta["proprio"]["now"][:7]` for the current joints to move smoothly.
- `ee_pose` (8): `x y z qw qx qy qz gripper` in the env-local frame (the robot's root frame: the Franka base at the
  origin, x forward towards the table, y to its left, z up); quaternions wxyz. Each row is driven to by differential IK
  in closed loop (at most 0.25 m/s); a row that does not converge within 6 mm is reported in `meta["plan"]`. The pose is
  the fingertip-centre tool frame: the gripper flange moved 0.162 m along the approach axis to the ends of the closed
  fingertips (the pads extend ~5.7 cm back from there). At the reset pose the gripper points straight down. At most 50
  rows per submit; a position more than 2 m from the robot's base on any axis, or a zero quaternion, is rejected (400)
  and nothing moves.
- The Robotiq opens to 8.5 cm.

### Observations
- Cameras: `egocentric_mirrored_camera` (static, facing the robot across the table, 864×480),
  `over_shoulder_left_camera` (static, over the robot's left shoulder, 1280×720) and `wrist_cam` (on the gripper,
  1280×720; it moves: each frame comes with its pose). Depth on request: z-depth in metres (1 mm steps), 0 = no reading,
  pixel-aligned with the RGB. Calibration: `spec["cameras"][cam]` has `intrinsic_cv` and `mount` (a static pose, or
  `wrist_cam` on link `base_link` with a fixed `link_T_cam_cv`).
- Proprioception (32 columns): joints, gripper, end-effector pose, velocities and drive efforts, in the groups of
  `spec["proprio_groups"]` (joint_pos, joint_vel, tcp_pose, gripper_opening, joint_effort).
- Robot and world facts: `spec["robot_spec"]` has the joints and their limits, the gripper, the controller gains and the
  tool frames; `spec["world"]` has the frame, units and quaternion order (wxyz).

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

## Others
- Objects here: a bowl, a Rubik's cube, a banana, a grey bin and a mug.

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
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: no step budget (actions and simulated time are reported as cost); a technical cap ends the episode after
  100,000 control steps (1.9 h of simulated time), graded as it stands; at this service's speed (3-15 control steps/s)
  your time runs out long before.
