# BEHAVIOR-1K · rearrange_your_room (standard)

## Task
An R1Pro mobile bimanual robot in a simulated house (BEHAVIOR-1K: OmniGibson on Isaac Sim). Rearrange the bedroom. Move
the tissue dispenser from the armchair onto one of the stands, and put the two pillows that lie on the floor onto the
two beds, one pillow on each bed. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the tissue dispenser stands on one of the stands, and each bed has one of the two pillows on it. It counts only
once the scene has settled: nothing the task names (a tool included) is still in a gripper, and everything has come to
rest. The episode ends as soon as the task is done. When your session ends with the episode still running, the robot is
held still for a few seconds more (your last command, the base at 0), and a success that settles in that time counts.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- The robot can fall over: a fall ends the episode as a failure, and so does a simulator breakdown (a runaway or
  non-finite state of the robot or of an object, e.g. after the robot tumbles).

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and loads the scene (3-12 min measured; the
                                              # wait is on your clock, progress on stderr; it gives up after 3600 s, Robot(timeout=...))
spec = r.spec()                               # actions, cameras, robot_spec, world, kinematics, budget, static facts

obs = r.get_obs()                             # current frames from the robot's 3 cameras: obs.last[cam] -> uint8 (224,224,3)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: named columns (spec["proprio_groups"])
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl of the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 25) rows dt seconds apart; streamed at 30 Hz
res = r.submit("ee_pose", P)                  # P: (T, 16) end-effector targets for both arms; cuRobo IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio   # execution video / frames / last frame per camera, proprio per frame
```
- Optional inputs (nothing changes unless you ask): `depth=True` on `get_obs` / `submit` adds `res.last_depth[cam]`,
  float32 (224, 224); `depth="frames"` also returns `res.depth[cam]` (N, 224, 224), one per frame. Per frame:
  `res.frame_step`, `res.frame_time_s` and `res.extrinsic_cv[cam]` (N, 3, 4). Proprio groups: `res.group("tcp_pose")`
  per frame, `res.group("tcp_pose", now=True)` now.
- Kinematics (stateless: no physics, no time): `r.fk(q)`, `r.ik({"left_tcp": pose}, seed=q)`; q =
  `spec["kinematics"]["joint_names"]` (trunk + both arms, all proprio columns); poses in the robot's base frame, or in
  the world frame with `base_pose=` the 7 base proprio columns.
- A malformed request (a wrong type or shape, a value out of range, a `dt` that is not a whole number of control
  periods, `video_fps` outside 1-30) is refused with a 400 and nothing is executed: fix it and send it again.
- One call returns at most 5412 images. A call that runs longer than `spec["max_call_wall_s"]` (900 s) stops at the next
  control step and returns what it executed (`res.stopped`, `meta["executed_rows"]`).
- If the service crashes (a connection error or a 5xx answer), it restarts and resumes the same episode (never a reset)
  in the state after the last call it completed, which you may not have received: call `r.wait_ready()`, then check
  `r.status()` (`calls`, `control_steps`) before you continue. Resuming replays the episode so far (minutes in a long
  episode) on your wall clock.

### Actions
- The world frame is OmniGibson's (metres, +z up, the floor is the plane z = 0); poses are position + quaternion XYZW.
- `joint_position` (25), in the blocks `spec["action_types"]["joint_position"]["blocks"]` lists: base (3), trunk (4),
  left arm (7), left gripper (2), right arm (7), right gripper (2). Rows are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple
  of the 30 Hz control period: `k/30` s, e.g. 0.1 or 0.2; any other `dt` is refused, never rounded); a chunk covers at
  most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]`.
  - Trunk and arm entries are absolute joint targets (rad), linearly interpolated between rows (or held,
    `interpolate="hold"`).
  - The three base entries are different: they are position targets in the robot's own frame (x, y in m, yaw in rad),
    re-applied on every control step, so they act as a per-step displacement: a row held for N control steps drives
    roughly N times that far. They are bounded per step (0.15 m, 0.3 rad); zeros stand still. They switch at the row.
  - Each gripper is 2 finger targets in m (0 = closed, 0.05 = fully open); they switch at the row. Grasping is assisted:
    a finger commanded below 0.05 closes and holds what the pads touch; only both fingers at ≥ 0.05 let go, so open with
    0.07 (the service's open command).
- `ee_pose` (16): left `x y z qx qy qz qw gripper`, right the same; world frame, quaternions xyzw, gripper 1 = open, 0 =
  closed (switched at the start of the row). Each row is solved by cuRobo inverse kinematics for both end effectors
  together (the trunk may bend too; no collision checking) and driven to in joint space; `dt` is ignored and the base
  stands still. If no IK solution exists nothing moves, and `meta["plan"]` says so. The pose is the end-effector frame
  of the proprio `*_eef_*` entries, so an observed pose is a valid target. At most 50 rows per submit.

### Observations
- Cameras: `robot_r1:zed_link:Camera:0` (head; moves with the base and trunk), `robot_r1:left_realsense_link:Camera:0`
  and `robot_r1:right_realsense_link:Camera:0` (wrists), 224×224 each: RGB, and depth on request (z-depth in metres, 0 =
  no reading, pixel-aligned with the RGB). They all move, so always use the calibration that came with the image;
  intrinsics `spec["cameras"][cam]["intrinsic_cv"]`, mounting `spec["cameras"][cam]["mount"]` (parent link + fixed
  `link_T_cam_cv`). While the robot moves, a frame shows the scene 2 control steps before its step; the pose that comes
  with it is the one it was rendered with.
- Proprioception: joints, base pose, end-effector and fingertip poses, gripper openings, velocities and efforts, as
  named columns (`spec["proprio_layout"]`) in groups (`spec["proprio_groups"]`: joint_pos, joint_vel, joint_effort,
  gripper_opening, tcp_pose, eef_pose, base_pose, ...).
- Robot and world facts: `spec["robot_spec"]` has the joint names and real limits, the gripper stroke and open / close
  rule, the drive gains, the end-effector frame vs the fingertip centre (TCP, 1.88 cm further along the fingers), the
  base's per-step and speed limits; `spec["world"]` has the frame, units, quaternion order and camera axes.

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
- Before you finish, open the grippers, move clear and let the robot stand still for a moment (e.g.
  `r.get_obs(seconds=2.0)`).
- How the episode ended is in `meta["reason"]`: "success", "failure: the robot fell over", "failure: simulator
  breakdown" or `step_guard` (the runaway guard).
- For scale: the challenge's human teleoperators needed 428 s on average (12,855 control steps) for this task, and the
  simulator runs at ~7-11 control steps/s. Budget your time, drive before you reach, and check `meta["done"]`.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 24 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: no step budget (actions and simulated time are reported as cost); a runaway guard ends the episode at 200,000
  control steps (1.85 h of simulated time).
