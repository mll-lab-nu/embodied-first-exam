# DexToolBench · spoon spatula · serve_plate (standard)

## Task
A KUKA iiwa 14 arm with a 22-joint Sharpa HA4 dexterous hand stands next to a table with a spoon spatula on it
(DexToolBench, MuJoCo). Pick up the spoon spatula and move it through the demonstrated motion (serving onto a plate):
bring it to each of the 48 goal poses in order (the green ghost tool shows the current goal).
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the spoon spatula has been brought to each of its 48 goal poses in turn, in order; a goal counts once the whole
tool matches the ghost's pose closely (position and orientation), and the next one then appears. The episode ends as
soon as the task is done. Goals have no time limit here. There is no partial credit (goals reached / 48 is only
reported, as `progress`).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: a success ends the run at
  once (no reset after it), and when your time is up the episode then running is graded.
- No privileged state: you get the robot's camera images (with their calibration), its own joint positions, velocities
  and targets, and the current goal pose with the count of goals reached; no object poses, no scene layout; the episode
  ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
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
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
obs = r.reset(cameras=cams)                   # a new episode from the starting state; obs.meta["resets_left"]
```
The episode ends when every goal is reached or at the step limit (`spec()["max_control_steps"]`); after that `submit`
raises `EpisodeOver` (409) until you reset. `r.reset(cameras=None, include_depth=False)` (`POST /reset`): a new episode
from the same starting state; it returns the start's frames, and `meta` (also `r.status()`) carries `episode`,
`resets_left` and `control_steps_total`. Resetting does not stop or restore the clock. Calibration:
`meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world, OpenGL axes: x
right, y up, the camera looks along -z; the viewpoint the image is rendered from), for the state at the end of that call
(the `last` image and the last frame of every stack). One call returns at most 3000 images.

### Actions
`joint_position`, 29 numbers per row: `joint1..joint7` (iiwa), then the 22 Sharpa hand joints (names in
`spec()["action_types"]["joint_position"]["layout"]`); rows are `dt` apart (a multiple of `control_dt`), each held
(`interpolate="hold"`) or ramped from the previous row (`"linear"`, default) over its control steps; clipped to the
limits in the spec. A chunk covers at most 10 s.

### Observations
- Cameras: `front`, `side`, `top`, `oblique`, all fixed; RGB 240 × 320, depth on request (metres).
- Each image comes with its camera's calibration (intrinsics and pose); depth is the distance along the viewing axis, in
  metres.
- Proprioception (`obs.meta["proprio"]`): the joint positions, velocities and current targets.
- The current goal (`meta["task"]`): its pose (`goal`, x y z qx qy qz qw), `goal_index`, `n_goals`, `goals_reached`,
  `steps_left_on_goal` (null: goals have no time limit here). The benchmark shows the controller the current goal, and
  the images show it as the green ghost tool.

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
- Resources: 3 CPUs, 16 GiB memory, 1024 processes and threads, 11 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: each episode ends after 360,000 control steps (100 min of robot time).
