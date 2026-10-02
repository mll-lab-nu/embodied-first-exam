# VLABench · select_mahjong — instance i00 — STANDARD MODE (robot as a service)

You control a simulated **Franka Panda** arm (VLABench on MuJoCo) **as if it were real hardware**: the simulator runs in
a service you cannot open, and you reach it only through a client. **Task: Put the mahjong of 6 sou on the placemat.**

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up. It ends when the task succeeds, after
  9000 control steps (900 s of robot time; a technical cap so that the grading replay fits in its
  time limit), when your time is up, or on a simulator error. `spec()["budget"]["reset"]` is 0.
- **Time moves only inside calls.** `submit` runs your targets and `get_obs(seconds=s)` holds the last ones for `s`
  seconds; both use up control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no
  seconds is free.
- **No privileged state, no score.** You see four cameras (`forward`, `left`, `right` fixed, `wrist` on the hand; RGB
  320×320, depth on request, each camera's intrinsics and pose in `spec()["cameras"]`) and the robot's
  own state: joint angles and velocities, finger positions, the hand's pose (`tcp_*`) and the last command. Not the
  objects' poses, not the task's conditions or success check: the service only tells you that the episode ended and
  why (`meta["done"]`, `meta["reason"]`: `"success"`, `"failed"` at the step cap, `"error"` after a simulator error).
- There is nothing to hand in: the service records the episode, replays it and grades the replay. Keep the script that
  drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: 60 minutes. It ends without warning, and ending your session earlier ends the run the same way, so
  do not stop early.
- Do not use VLABench's expert solutions or any published solution for this benchmark; write your own controller.

## Scoring
VLABench's own success check for `select_mahjong` (the task's termination condition). The service ends the episode the
moment it holds (`reason = "success"`), and a fresh replay of the recorded episode must reach it as well and end in
the same state.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; its examples come from another benchmark: the numbers here and in `spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.1 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold the last targets and watch for `seconds` (at most 30) |
| `r.submit("joint_position", A, dt=0.1, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 9 targets `dt` seconds apart (a multiple of 0.1; a chunk covers at most 10 s); stops early when the episode ends |

The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`), `res.last[cam]`
(the last frame), `res.frames` or `res.video` (what the cameras saw during the call), `res.proprio` (rows).
```python
from rcb_client import Robot
r = Robot()
res = r.submit("joint_position", A, dt=0.1, cameras=["forward"], video="none")   # A: (T, 9)
```
- Action `joint_position` (9, float64): absolute position targets for VLABench's own actuators, the 7 arm joints (rad)
  and the 2 fingers (m, 0 closed … 0.04 open), each row held for its control steps (0.1 s, 100 physics steps each).
  The model sets no arm joint limits; stay inside the Panda's own, `spec()["action_types"]["joint_position"]
  ["panda_joint_limits_rad"]`.
- Proprioception (`spec()["proprio_layout"]`): `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `finger1_pos`,
  `finger2_pos` (m), `tcp_x/y/z` (m) and `tcp_qw/qx/qy/qz` (the hand's pose), `cmd_*` (the last command).
- World frame: metres; the robot's base is at (0, -0.4, 0.78) facing +y: x to the robot's right, y forward (across the
  table), z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along
  its -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels.
- Measured cost here: about 40 ms of simulation per control step, plus about 15 ms per camera image.
