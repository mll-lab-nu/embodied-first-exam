# RoboCasa365 · CerealAndBowl (standard)

## Task
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa365, robosuite / MuJoCo).
Open the cabinet. Pick the cereal and bowl from the cabinet and place them on the counter next to the milk. Then close
the cabinet. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the cereal and the bowl both stand on the counter nearest the cabinet, and the cabinet is fully closed again.
What counts is how things stand at the end of the episode: a success reached earlier and lost by the end does not count,
so finish in the state you want graded and stop sending commands.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("joint_position", A, cameras=cams[:1], video="mp4")   # A: (T, 13) rows, one per control step
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

`get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs for `s`
seconds; those control steps are part of the episode. One call returns at most 3000 images.

### Actions
- Action `joint_position`: the robot's native controller command, applied once per control step (`control_dt` = 0.05 s;
  float64). 13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint
  limits in `spec["action_types"]["joint_position"]` (`lower` / `upper`, from `r.spec()`)); `grip` (+1 closes, -1
  opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` --
  the torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the
  limits. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at most 10 s).
- World frame: metres, z up.

### Observations
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.

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
- Resources: 4 CPUs, 6 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
