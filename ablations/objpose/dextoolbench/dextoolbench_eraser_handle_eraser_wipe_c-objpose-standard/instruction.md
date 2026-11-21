# DexToolBench · handle eraser · wipe_c (MuJoCo) — STANDARD MODE (robot as a service)

A KUKA iiwa 14 arm with a 22-joint **Sharpa HA4** dexterous hand stands next to a table with a **handle eraser** on it.
**Task:** pick up the handle eraser and move it through the demonstrated motion (wiping the letter C): bring it to each
of the **31 goal poses in order** (the green ghost tool shows the current goal). This is task `eraser / handle_eraser /
wipe_c` of DexToolBench (SimToolReal), run here in plain MuJoCo.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and **20 resets**: at most 21 episodes, of which the last is graded.

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
  service records every episode, and grades the last one as the trajectory. Leave your script at `/app/output/gen.py` for the
  record.
- Do not use pretrained manipulation policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The current goal counts as reached when all 8 corners of the tool's grasp box (0.141 × 0.030 × 0.027 m, scaled by
1.5, in the tool's frame) are within **1.5 cm** of the same corners at the goal pose; then the next goal becomes
current. In this mode goals have **no time limit** (the benchmark gives each goal 10 s). An episode ends when every goal is reached, when your time is up, or after **360,000 control steps (100 min of robot time)**. **Only the last episode is scored.**
**Score: 1 if all 31 goals are reached, else 0.** Goals reached / 31 is reported as `progress`; there is no partial credit.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
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

## This run: privileged state queries

This run lets you query the simulator's state. This section overrides anything above, and anything in `/spec`, that
says object poses or the scene's state are never given.

- `GET /state/entities` (on the same base URL as your other calls) lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}}}}`. The
  kinds are `robot` (the robot's base or root), `robot_link` (a hand, a foot, an end effector), `object`,
  `articulation` (a door, a drawer, a faucet: its joints) and `scene_feature` (a zone, a line, a hazard, a canvas
  region). The list is fixed for the run.
- `POST /state/query` with `{"names": ["robot", ...], "fields": ["pos", "quat"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the
  current values. `fields` is optional: without it you get every field of each name. In Python:
  `requests.post(base + "/state/query", json={"names": ["robot"]}).json()["state"]`.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s,
    `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents), and `bbox`
    [[min x, y, z], [max x, y, z]] m. A task may add its own; each field's unit is in the list.
  - All values are in the world frame that `frame` describes.
  - A field that an entity does not have is left out of its entry.
  - An unknown name or field is a 400 that lists the valid ones.
- A query only reads. It takes no control step, and it does not advance or pause the clock. In standard-realtime it
  answers at the current simulation time while the robot keeps moving. It is served while the episode runs (409 after
  the episode ended). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: the goal, the success rule and its thresholds are not given, and no answer says whether the
  task is done.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **11 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
