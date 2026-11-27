# MyoSuite · dex_hammer_use (standard)

## Task
Pick up the hammer and swing it, following the recorded reference motion.

## Goal
Success: the hammer follows the recorded reference motion closely, in where it goes and how it turns, nearly all the way
and at the end, and never strays far from it. Success is judged on the whole episode. It ends early, as a failure, if
the hammer gets far from the reference motion or from your wrist.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded.
- You get only the cameras and the body's own proprioception (joint positions, velocities and actuator torques, muscle
  activations and lengths): no object, ball, opponent or goal poses, no success signal.

## Robot Interface
The MyoHand, a musculoskeletal model of a human forearm and hand (MyoSuite, MuJoCo), driven only through its actuators
(39 muscles and 6 other actuators): there is no joint-level controller. The robot runs as a service you reach through
its client or its MCP tools, as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: center_cam)
obs = r.get_obs(cameras=["left_cam"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.02)          # rows: (T, 45) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.hold(1.0)                              # hold the last command for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["left_cam"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last command). A reset (`POST /reset`,
the `_post` line above) puts the body and the scene back in the same frozen starting state and starts a new episode. You
can reset during an episode (abandoning it) or after one has ended. It takes no simulated time and returns the start's
images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock
covers the whole run and never restarts. `meta["episode"]` and `meta["resets_left"]` count the episodes;
`meta["control_steps"]` counts only the current episode's steps. If the service crashes, a call fails with a connection
error. The service restarts and resumes the same episode (never a reset), in the state after the last call it completed.
`r.wait_ready()` waits for it; then check `r.status()`. One call returns at most 1000 images. `r.fk(q)` (`/kinematics`)
gives the fingertip sites and the camera mounts for any joint positions.

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
Action type `actuators` (45): 45 real numbers per control step, one per actuator in order: 39 muscles and 6 non-muscle
actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~
0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994). Activation follows excitation with a first-order delay (~10 ms up,
~40 ms down). Muscles only pull, and one muscle can cross several joints. A muscle's force also depends on its length
and velocity. The non-muscle actuators: `A_ARTx` (index 0): position target of joint ARTx in [-0.75, 0.5]; `A_ARTy`
(index 1): position target of joint ARTy in [-0.5, 0.5]; `A_ARTz` (index 2): position target of joint ARTz in [-0.5,
0.3]; `A_ARRx` (index 3): position target of joint ARRx in [-1.75, 1.75]; `A_ARRy` (index 4): position target of joint
ARRy in [-1.75, 1.75]; `A_ARRz` (index 5): position target of joint ARRz in [-1.75, 1.75]. Columns in
`spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart: a whole multiple of the 20 ms control period,
at most 0.5 s. A chunk covers at most 10 s. Interpolation: `interpolate="linear"` (default, from the previous command)
or `"hold"`. The client sends the rows as float32. The control rate is 50 Hz (10 physics substeps); there is no step
budget.

### Observations
Cameras: `left_cam`, `right_cam`, `center_cam`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`,
`plam_lookat` (640x480; default `center_cam`). `hand_top` and `hand_side_inter` are close-ups of the hand, mounted on
the forearm (the radius). They move with it (pronation turns them), so use the pose returned with each frame.
`spec["cameras"]` gives each camera's intrinsics and mounting: static, fixed to a body, or a MuJoCo tracking camera that
follows one. Every response carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`
(`q_<joint>`), `joint_vel` (`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m),
`joint_effort` (`effort_<joint>`, the actuators' generalized force on each joint). The goal is a reference motion:
`spec["reference_motion"]` gives, per control step, the object's centre of mass relative to where it starts and its
orientation.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: the episode ends when the reference motion ends.
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
