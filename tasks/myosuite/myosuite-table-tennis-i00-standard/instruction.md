# MyoSuite · table_tennis (standard)

## Task
Return the served ball: after it bounces once on your half, hit it once with the paddle so that it lands on the
opponent's half, with no second paddle touch and no second bounce on your half.

## Goal
Success: after the serve bounces once on your half, you hit the ball once with the paddle and it then lands on the
opponent's half, with no second paddle touch and no second bounce on your half. This counts once it has happened, even
if the episode then ends as a failure. It ends when you call finish (Limits) or when your session ends. The robot never
tells you whether you have succeeded. It ends as a failure on any other outcome of the rally, if the ball falls toward
the floor, and after 3 s.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: the one running when you call finish or when your session ends.
- You get only the cameras and the body's own proprioception (joint positions, velocities and actuator torques, muscle
  activations and lengths): no object, ball, opponent or goal poses, no success signal.

## Robot Interface
The MyoArm with torso, a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor
(MyoSuite, MuJoCo), driven only through its actuators (273 muscles and 2 other actuators): there is no joint-level
controller. The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: default)
obs = r.get_obs(cameras=["topview"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.01)          # rows: (T, 275) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.hold(1.0)                              # hold the last command for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["topview"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last command). A reset (`POST /reset`,
the `_post` line above) puts the body and the scene back on the same frozen starting state and starts a new episode,
either abandoning the running one or after one has ended; it takes no simulated time and returns the start's images and
proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock is the run's
and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes (`meta["control_steps"]` is the
current episode's). If the service crashes, a call fails with a connection error: it restarts and resumes the same
episode (never a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check
`r.status()`. One call returns at most 1000 images. `r.fk(q)` (`/kinematics`) gives the fingertip sites and the camera
mounts for any joint positions.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in
  `fields`) and returns the service's reply `meta` unchanged; images, arrays and video are written as files under
  `/app/obs/` (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file
  (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
Action type `actuators` (275): 275 real numbers per control step, one per actuator in order: 273 muscles and 2
non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a
= -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10
ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and
velocity. The non-muscle actuators: `pelvis_x` (index 273): normalized: a in [-1, 1] maps linearly onto [-1, 0.05]
(position of joint pelvis_x); `pelvis_y` (index 274): normalized: a in [-1, 1] maps linearly onto [-1, 1] (position of
joint pelvis_y). Columns in `spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart (a whole multiple
of the 10 ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous command) or `"hold"`; the client sends them as float32. The control rate is 100 Hz (5 physics substeps); there
is no step budget.

### Observations
Cameras: `topview`, `default`, `close_up`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`,
`plam_lookat` (640x480; default `default`). `hand_top` and `hand_side_inter` are close-ups of the hand, mounted on the
forearm (the radius): they move with it (pronation turns them), so use the pose returned with each frame;
`spec["cameras"]` gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one)
and intrinsics, and every response carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`
(`q_<joint>`), `joint_vel` (`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m),
`joint_effort` (`effort_<joint>`, the actuators' generalized force on each joint).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
