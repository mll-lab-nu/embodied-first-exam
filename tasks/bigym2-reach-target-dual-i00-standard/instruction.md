# bigym2 reach-target-dual — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo) **as if it were real
hardware**: the simulator runs in a service you cannot open, and you reach it only through a client. NVIDIA's GR00T
whole-body controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the
robot balanced: you command where it walks, how high its pelvis is, its arm joints and its grippers.
**Task:** Touch the red sphere with your left hand and the green sphere with your right hand at the same time.

At the start the red sphere is about 0.6 m away, 25° to your left, 0.82 m above the floor and the green sphere about 0.6 m away, 22° to your right, 0.83 m above the floor. (Distances are from your pelvis along the floor, directions from the way you face,
heights above the floor; measured on this scene.)

## Rules (real-robot rules)
- **Episodes and resets.** The episode starts when the service comes up, from a fixed starting state; what ends it is under Success below. You have **10 resets** (`spec()["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the robot and the scene back on the same starting state and starts a new episode with its own 700 control steps, either abandoning the running episode or after one has ended; it takes no robot time and returns the start's frames. Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the last episode is graded**: a success ends the run at once, and when your time is up the episode then running is the one graded; `meta["episode"]` and `meta["resets_left"]` count the episodes.
- **Time moves only inside calls.** `submit` runs your commands and `get_obs(seconds=s)` stands still for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's three cameras see (RGB, 84×84: `head`, `left_wrist`, `right_wrist`) and its own proprioception (below). Not where any object is now (only the start sentence above), not the success check: the service judges the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`). `spec()` gives the robot's facts: the action slots and their bounds, each camera's field of view and its pose at the start.
- There is nothing to hand in: the service records every episode, replays the last one in a fresh simulator and grades the replay. Keep the script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Success
The episode succeeds when the following has held for **1 s (50 control steps in a row)**: the point between the left gripper's two finger pads is inside the red sphere and the right gripper's inside the green sphere at the same time: each within 0.05 m of its sphere's centre (the spheres' radius). The robot must not fall at any time: a fall (the pelvis tilted more than about 53 degrees from upright, or lower than 0.30 m) makes the episode a failure, but does not end it.

The episode ends when the success has held for 1 s (`reason = "success"`), when the pelvis gets more than
10 m from the scene's origin, on a simulator error, after **700 control steps** (14 s of robot
time), or when your time is up. A fresh replay of the recorded episode must succeed as well and end in the same
state.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); here the action type is `"whole_body"` (not the docstring's example name):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types["whole_body"]` (layout, lower, upper, units), `control_dt` (0.02 s), `max_control_steps` (700), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the starting state (at most 10 in all); returns the start's frames |
| `r.get_obs(cameras=None, seconds=0, video="frames")` | `POST /observe` | the current frames (free), or stand still and watch for `seconds` (at most 30) |
| `r.submit("whole_body", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 20 commands `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing. The response of the call that ends the
episode also carries `meta["outcome"]`, BiGym's own label of how it ended (`success`, `fell`, `timeout`, `terminated`,
`physics_error`). Standing still is the row with the current height,
lean, arm and gripper targets and zero `vx`, `vy`, `wz`; `get_obs(seconds=s)` does that from your last row.
Measured here: a control step costs about 14 ms of service time inside a `submit` (a 1 s chunk returns in about
0.7 s); `get_obs()` without seconds about 10 ms.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("whole_body", A, dt=0.02)   # A: (T, 20) commands, one row per control step
```

## Action rows (20 floats, physical units)
| slot | name | bounds | meaning | at the start |
|---|---|---|---|---|
| 0 | `vx` | [-1, 1] | walking velocity command, forward (m/s, the robot's frame) | 0 |
| 1 | `vy` | [-1, 1] | walking velocity command, to the left (m/s) | 0 |
| 2 | `height` | [0.4, 1] | pelvis height command (m) | 0.74 |
| 3 | `wz` | [-1, 1] | turning rate command, + turns left (rad/s) | 0 |
| 4 | `left_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 5 | `left_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 6 | `left_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 7 | `left_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 8 | `left_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 9 | `left_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 10 | `left_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 11 | `right_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 12 | `right_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 13 | `right_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 14 | `right_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 15 | `right_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 16 | `right_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 17 | `right_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 18 | `left_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |
| 19 | `right_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |

`right_shoulder_roll_joint`'s bounds are BiGym's action bounds, not the joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

The last column is the row that stands still at the start. The whole-body controller, as BiGym's own notes for its coding agents describe it: it follows velocity commands with some lag and wobble, so read the pelvis pose and close the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least 0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8 rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It keeps the robot balanced but does not stop it from walking into things.

`spec()["joints"]` gives each arm, waist and finger joint's axis, a point on it and its range (the pelvis frame with
every joint at 0: `spec()["joint_frame"]`; the sign convention: `spec()["joint_sign"]`), `spec()["grippers"]` the point between each gripper's finger
pads on its wrist link, and `spec()["cameras"][camera]["mount"]` each camera's pose on its link. Keep your own copy of the last row you sent: a row rebuilt from the measured joint angles sits a little below
the targets the arms were holding (the servos track with a small error), so holding with it lets the arms sag. The
client's docstring explains the protocol with another benchmark's examples (`joint_position`, bounds [-1, 1], `imu`,
`links`, `depth`): for this task `spec()` is authoritative.

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the positions (`*_pos`) of each arm's 7 joints (rad) and its gripper's 2 finger joints (slides, m), and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its heading, in rad: the room's frame, z up, heading 0 along the room's +x axis and counter-clockwise positive): 22 values; then their velocities (`*_vel`, per second) in the same order; then `left_gripper_state` and `right_gripper_state` (0 open .. 1 closed); then the pelvis pose again as the base controller tracks it (`pelvis_x`, `pelvis_y`, `pelvis_z`, `pelvis_yaw`). This is BiGym's own low-dimensional observation, the one its learned policies receive.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
