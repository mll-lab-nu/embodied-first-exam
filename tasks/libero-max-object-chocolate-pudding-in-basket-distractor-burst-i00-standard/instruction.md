# LIBERO-MAX · libero_object · distractor burst — instance i00 — STANDARD MODE (robot as a service)

You control a simulated **Franka Panda** arm (LIBERO on robosuite / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open, and you reach it only through a client. **Task: Pick the chocolate pudding and place it in the basket.**

The scene can change while you work: once during the episode, when your gripper first gets close to one of the task's
objects, the scene changes (as in LIBERO-MAX): an object or a receptacle may be moved, an obstacle or a few other
objects may appear, a camera may shift, or the lighting, the colours or the image noise may change. Nothing tells you
when; the task and its success check stay the same, so keep checking what the cameras show.

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up. It ends when the task succeeds, after
  9000 control steps (450 s of robot time; a technical cap so that the grading replay fits in its
  time limit), when your time is up, or on a simulator error. `spec()["budget"]["reset"]` is 0.
- **Time moves only inside calls.** `submit` runs your actions and `get_obs(seconds=s)` holds still for `s` seconds;
  both use up control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see two cameras (`agentview` fixed in front of the robot, `wrist` on the hand;
  RGB 256×256, depth on request) with their intrinsics and pose (`spec()["cameras"]` at the start;
  every submit response carries the current ones in `meta["cameras_now"]`) and the robot's own state. Not the objects'
  poses, not the goal or the success check: the service only tells you that the episode ended and why
  (`meta["done"]`, `meta["reason"]`: `"success"`, `"failed"` at the step cap, `"error"` after a simulator error).
- There is nothing to hand in: the service records the episode, replays it and grades the replay. Keep the script that
  drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: 60 minutes. It ends without warning, and ending your session earlier ends the run the same way, so
  do not stop early.
- Do not use LIBERO's demonstrations, LIBERO-MAX's policies or any published solution; write your own controller.

## Scoring
LIBERO's own success check for this task: all of
- `chocolate_pudding_1` is in `basket_1_contain_region` (LIBERO's In: `chocolate_pudding_1`'s origin lies inside the region's box, whose floor counts 1 cm lower, and it touches the region's object)
The service ends the episode the moment it holds (`reason = "success"`), and a fresh replay of the recorded episode
(with the same scene change at the same moment) must reach it as well and end in the same state.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; its examples come from another benchmark: the numbers here and in `spec()` are this task's).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types`, `control_dt` (0.05 s), `max_control_steps` (9000), `cameras`, `proprio_layout`, `frames`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the current frames (free), or hold still and watch for `seconds` (at most 30) |
| `r.submit("ee_delta", A, dt=0.05, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 7 numbers `dt` seconds apart (a multiple of 0.05; a chunk covers at most 10 s); stops early when the episode ends |

The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`,
`cameras_now`), `res.last[cam]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (rows).
```python
from rcb_client import Robot
r = Robot()
res = r.submit("ee_delta", A, dt=0.05, cameras=["agentview"], video="none")   # A: (T, 7)
```
- Action `ee_delta` (7, float64, each clipped to [-1, 1]): LIBERO's native operational-space control (OSC_POSE). Per
  control step the hand's target moves by `[dx, dy, dz]` × 0.05 m and turns by `[drx, dry, drz]` × 0.5
  rad (axis-angle, world frame); `grip` +1 closes, -1 opens the gripper. With `dt = 0.05` each row is one control step;
  `get_obs(seconds=s)` holds still (zero motion, the gripper as last commanded).
- Proprioception (`spec()["proprio_layout"]`): `eef_x/y/z` (m) and `eef_qw/qx/qy/qz` (the hand), `finger_left`,
  `finger_right` (m), `joint1..7_pos` (rad), `joint1..7_vel` (rad/s), `cmd_*` (the last action).
- World frame: metres; the robot's base is at (-0.6, 0, 0) facing +x: x forward (across the table), y to the robot's
  left, z up; quaternions are w x y z. Each camera's `cam2world_gl` is its pose (OpenGL convention: it looks along its
  -z axis, +y up); `intrinsic_cv` its pinhole intrinsics in pixels (upright images).
- Measured cost here: about 20 ms of simulation per control step, plus about 70 ms per camera image.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
