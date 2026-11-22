# MyoSuite · osl_run (standard)

## Task
The MyoLeg + OSL, a free-standing musculoskeletal model of a human whose right leg is an Open-Source Leg knee-ankle
prosthesis (MyoSuite, MuJoCo), driven only through its actuators (54 muscles and 2 other actuators): there is no
joint-level controller. The body stands at the start of a straight, flat running track. Run the track: move forward 29 m
along it to the finish (MyoChallenge 2024 OSL Run), staying near the track's centre line and on your feet. The
prosthesis's knee and ankle (`osl_knee_angle_r`, `osl_ankle_angle_r`) are driven by its own controller, so you command
only the 54 muscles. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: you reach the finish, 29 m down the track. The episode ends as soon as the task is done; it ends as a failure
when you fall, leave the track sideways (more than about a metre from its centre line) or move 2 m backwards; there is
no time limit.

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
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
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

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). A reset
(`POST /reset`, the `_post` line above) puts the body and the scene back on the same frozen starting state and starts a
new episode, either abandoning the running one or after one has ended; it takes no simulated time and returns the
start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall
clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes
(`meta["control_steps"]` is the current episode's). If the service crashes, a call fails with a connection error: it
restarts and resumes the same episode (never a reset) in the state after the last call it completed. `r.wait_ready()`
waits for it; then check `r.status()`. One call returns at most 1000 images. `r.fk(q)` (`/kinematics`) gives the camera
mounts for any joint positions.

### Actions
Action type `actuators` (56): 56 real numbers per control step, one per actuator in order: 54 muscles and 2 non-muscle
actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~
0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up,
~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
The non-muscle actuators: `osl_knee_torque_actuator` (index 54): ignored: the prosthesis's own impedance controller
(MyoSuite's OSL state machine) sets it; `osl_ankle_torque_actuator` (index 55): ignored: the prosthesis's own impedance
controller (MyoSuite's OSL state machine) sets it. Columns in `spec["action_types"]["actuators"]["layout"]` order. Rows
are `dt` apart (a whole multiple of the 5 ms control period, at most 0.5 s; a chunk covers at most 10 s),
`interpolate="linear"` (default, from the previous command) or `"hold"`; the client sends them as float32. The control
rate is 200 Hz (5 physics substeps); there is no step budget.

### Observations
Cameras: `topview`, `side_view`, `agent_view` (640x480; default `side_view`). `spec["cameras"]` gives each camera's
mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every response
carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel`
(`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort`
(`effort_<joint>`, the actuators' generalized force on each joint), `root_pose`, `root_vel`.

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
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
