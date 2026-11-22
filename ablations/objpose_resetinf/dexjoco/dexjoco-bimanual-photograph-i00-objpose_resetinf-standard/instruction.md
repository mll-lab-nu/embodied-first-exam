# DexJoCo · bimanual_photograph (standard)

## Task
Two Franka Panda arms, each with a 16-joint Allegro hand (DexJoCo, MuJoCo). Hold the camera with the left hand in front
of the logo and press its shutter with the right hand. The camera lies on the table between the robots; the logo disk
stands at the far side of the table.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the left hand holds the camera in front of the logo, about 0.4 m from it and about 0.3 m above the table,
looking straight at it (along +x), while something other than the camera, the right hand, presses its shutter button.
The episode ends as soon as the task is done.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # action types, cameras (+ calibration), proprio layout, robot_spec, kinematics, budget
obs = r.get_obs()                             # current frames of spec["default_cameras"]: obs.last[cam] -> uint8 (480, 640, 3)
obs = r.get_obs(cameras=["front", "handcam_rgb_right"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640) z-depth (m)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}; obs.group("tcp_pose", now=True)
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl for these frames
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the current targets and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("ee_pose", rows, dt=0.1)       # rows: (T, 46) targets dt seconds apart, executed at 50 Hz with interpolation
res = r.submit("joint_position", q_rows, dt=0.1)   # (T, 46) joint targets instead (see below)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["front"]; res.last["front"]; res.proprio   # mp4 of the chunk, last frame, float32 (N, P) proprio per frame
r.fk(q); r.ik({"tcp_right": pose}, seed=q)  # kinematics of the robot (stateless: no physics, no time)
r.status()                                    # calls, control steps, done, reason, elapsed time
```
One call returns at most 1000 images. If a call fails with a connection error the service may have crashed: it resumes
the same episode; `r.wait_ready()`, then check `r.status()` (`spec["on_service_error"]`).

### Actions
- `ee_pose` (46 numbers, DexJoCo's own action): per arm, right first: tcp target position (3, metres, world frame), tcp
  target orientation (4, quaternion wxyz), 16 Allegro joint targets (rad). The arm tracks the target through DexJoCo's
  operational-space controller (it lags a moving target and stops where contact blocks it); the hand joints are
  position-controlled. Rows are `dt` apart (a whole multiple of 1/50 s, at most 0.5 s); between rows positions and
  joints move linearly and orientations by slerp (`interpolate="linear"`) or jump (`"hold"`); a chunk may cover at most
  10 s. Hand targets outside the ranges (`spec["action_types"]["ee_pose"]["hand_limits"]`) are clamped by the simulator
  and listed in `meta["clipped"]`. Build the next row from the `tcp_target` and `hand_target` proprio groups to move
  smoothly.
- `joint_position` (46 numbers): per arm, right first: 7 Panda joint targets, then the 16 Allegro joint targets (rad).
  The service turns the arm's targets into a tcp target by forward kinematics and the same controller tracks it: the tcp
  reaches FK(q), but the measured arm joints may differ from q in the arm's redundant direction (the controller's null
  space pulls towards a home posture). Out-of-limit values are clipped and reported.
- Control runs at 50 Hz (10 physics substeps of 2 ms).

### Observations
- Cameras: `front`, `back`, `left`, `right`, `top0` (static), `handcam_rgb_right`, `handcam_rgb_left` (on the hand
  mounts; they move, so use the calibration that comes with each response; `spec["cameras"][cam]["mount"]` gives the
  static pose or the mount link), `cam_pos_z` (on an object of the scene and moves with it: images and depth only, no
  mount and no pose -- `extrinsic_cv` / `cam2world_gl` are null in `meta["cameras"]` and NaN per frame -- because its
  pose would be that object's). Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you need;
  `video="none"` makes a chunk fastest.
- Proprioception (`obs.meta["proprio"]`, its layout in `spec()["proprio_layout"]`): the joints, the tcp poses
  (`tcp_pose`), the current targets (`tcp_target`, `hand_target`).
- When the episode has ended, `meta["done"]` is set and `meta["reason"]` says why.

### Frames and joint order
- World frame, metres, z up; the robots stand at low x and reach towards +x (right arm at y < 0, left arm at y > 0);
  each arm's base pose is in `spec["robot_spec"]["base"]`. No other world coordinates are given (the cameras are
  calibrated, depth is available). Quaternions are WXYZ.
- The tcp (`tcp_right`, `tcp_left`) is the hand's mounting flange (`spec["robot_spec"]["tcp"]`), not the fingertips.
- Allegro joint order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread,
  1-3 = flexion from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle
  4-7, index 8-11, thumb 12-15 (the joint names in `spec["proprio_layout"]` say which).

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
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: no limit; actions and simulated time are reported, as cost.
