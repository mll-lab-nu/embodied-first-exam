# MyoSuite · osl_run (standard)

## Task
Run 29 m down the track to the finish, staying on your feet and near the middle of the track.

## Goal
Success: you reach the finish, 29 m down the track. Once this has happened the task is passed, whatever happens
afterwards. Before that, the episode ends as a failure if you fall, stray from the middle of the track, or run
backwards. There is no time limit.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded.
- You get only the cameras and the body's own proprioception (joint positions, velocities and actuator torques, muscle
  activations and lengths): no object, ball, opponent or goal poses, no success signal.

## Robot Interface
The MyoLeg + OSL, a free-standing musculoskeletal model of a human whose right leg is an Open-Source Leg knee-ankle
prosthesis (MyoSuite, MuJoCo), driven only through its actuators (54 muscles and 2 other actuators): there is no
joint-level controller. The prosthesis's knee and ankle (`osl_knee_angle_r`, `osl_ankle_angle_r`) are driven by its own
controller, so you command only the 54 muscles. The robot runs as a service you reach through its client or its MCP
tools, as if it were real hardware.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

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
obs = r.hold(1.0)                              # hold the last command for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
# a new episode: POST /reset, or the MCP tool `reset` (this client has no reset() call)
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last command). A reset (`POST /reset`,
the `_post` line above) puts the body and the scene back in the same frozen starting state and starts a new episode. You
can reset during an episode (abandoning it) or after one has ended. It takes no simulated time and returns the start's
images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock
covers the whole run and never restarts. `meta["episode"]` and `meta["resets_left"]` count the episodes;
`meta["control_steps"]` counts only the current episode's steps. If the service crashes, a call fails with a connection
error. The service restarts and resumes the same episode (never a reset), in the state after the last call it completed.
`r.wait_ready()` waits for it; then check `r.status()`. One call returns at most 1000 images. `r.fk(q)` (`/kinematics`)
gives the camera mounts for any joint positions.

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
Action type `actuators` (56): 56 real numbers per control step, one per actuator in order: 54 muscles and 2 non-muscle
actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~
0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994). Activation follows excitation with a first-order delay (~10 ms up,
~40 ms down). Muscles only pull, and one muscle can cross several joints. A muscle's force also depends on its length
and velocity. The non-muscle actuators: `osl_knee_torque_actuator` (index 54): ignored: the prosthesis's own impedance
controller (MyoSuite's OSL state machine) sets it; `osl_ankle_torque_actuator` (index 55): ignored: the prosthesis's own
impedance controller (MyoSuite's OSL state machine) sets it. Columns in `spec["action_types"]["actuators"]["layout"]`
order. Rows are `dt` apart (a whole multiple of the 5 ms control period, at most 0.5 s; a chunk covers at most 10 s),
`interpolate="linear"` (default, from the previous command) or `"hold"`; the client sends them as float32. The control
rate is 200 Hz (5 physics substeps); there is no step budget.

### Observations
Cameras: `topview`, `side_view`, `agent_view` (640x480; default `side_view`). `spec["cameras"]` gives each camera's
mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every response
carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel`
(`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort`
(`effort_<joint>`, the actuators' generalized force on each joint), `root_pose`, `root_vel`.

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
- Finish: if you never send `/finish`, the last episode is graded when your session ends.
