# VLABench · select_book_spatial — instance i00 — STANDARD MODE (robot as a service)

You control a simulated **Franka Panda** arm (VLABench on MuJoCo) **as if it were real hardware**: the simulator runs in
a service you cannot open, and you reach it only through a client. **Task: Please take the second book from the left (as seen from the robot) on the top layer out of the bookshelf.**

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
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so
  do not stop early.
- Do not use VLABench's expert solutions or any published solution for this benchmark; write your own controller.

## Scoring
VLABench's own success check for `select_book_spatial` (the task's termination condition). The service ends the episode the
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

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
