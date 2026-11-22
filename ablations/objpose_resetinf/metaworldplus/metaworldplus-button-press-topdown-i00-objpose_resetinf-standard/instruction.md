# MetaWorld+ · button-press-topdown (standard)

## Task
A Sawyer arm at a table (Meta-World, MuJoCo). Press the button downward from above. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the button is pushed down, its top at the target point's height. What counts is how things stand at the end of
the episode: a success reached earlier and lost by the end does not count, so finish in the state you want graded and
stop sending commands.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; do not use Meta-World's scripted policies, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`.

```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # front, left, right, topview
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]["target_pos"]                # the task's target point (world frame)
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_delta", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 4)
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

One call returns at most 3000 images. `get_obs(seconds=s)` holds the hand still (zero motion, same grip) while physics
runs for `s` seconds; those control steps are part of the episode.

### Actions
- Action `ee_delta` (4: `dx, dy, dz, grip`, float64, each clipped to [-1, 1]) is Meta-World's native action, applied
  once per control step (`control_dt` = 0.0125 s). The hand's target moves by `[dx, dy, dz]` × 1 cm per control step and
  stays inside x ∈ [-0.5, 0.5], y ∈ [0.4, 1], z ∈ [0.05, 0.5]; the hand follows it. `grip` drives the two fingers (+1
  closes, -1 opens). The wrist does not rotate. Rows are `dt` apart (a multiple of `control_dt`); with `dt = control_dt`
  each row is one native action. A chunk covers at most 10 s.

### Observations
- Proprioception (names as in the spec's proprio layout): `tcp_x/y/z` (the point between the fingertips),
  `gripper_opening` (0 closed … 1 open), `mocap_x/y/z` (the hand's target), the arm joints' positions and velocities,
  the finger joints' positions, and `cmd_*` (the last action).
- World frame: metres; x to the robot's right, y forward (away from the robot's base), z up; the table top is at z = 0.
  Quaternions are w x y z. The four cameras are fixed.
- Calibration (`obs.meta["cameras"]`, per camera): `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4
  camera-to-world, OpenGL axes: x right, y up, the camera looks along -z; the viewpoint the image is rendered from).
  Depth is the distance along the viewing axis, in metres.
- The target point that Goal names is `target_pos` in `meta["task"]` (world frame), in every reply.

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
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
