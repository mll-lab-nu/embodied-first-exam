# bigym2 wall-cupboard-open — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo) **as if it were real
hardware**: the simulator runs in a service you cannot open, and you reach it only through a client. NVIDIA's GR00T
whole-body controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the
robot balanced: you command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its grippers.
**Task:** Open both doors of the wall cabinet.

At the start the wall cabinet hangs above the counter in front of you; the handles of its two doors, on either side of the middle seam, are about 0.5 m away, straight ahead, 1.24 m above the floor and about 0.5 m away, straight ahead, 1.24 m above the floor. (Distances are from your pelvis along the floor, directions from the way you face,
heights above the floor; measured on this scene.)

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up, from a fixed starting state; what ends it is under Success below. `spec()["budget"]["reset"]` is authoritative: it is 0 here, so the one episode is the run. Once it has ended, the run is over and `submit` raises `EpisodeOver`.
- **Time moves only inside calls.** `submit` runs your commands and `get_obs(seconds=s)` stands still for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's three cameras see (RGB, 84×84: `head`, `left_wrist`, `right_wrist`) and its own proprioception (below). Not where any object is now (only the start sentence above), not the success check: the service judges the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`). `spec()` gives the robot's facts: the action slots and their bounds, each camera's field of view and its pose at the start.
- There is nothing to hand in: the service records the episode and grades it as it ran. Keep the script that drives the robot at `/app/output/gen.py` for the record: save it early and keep it current.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so do not stop early: while the episode runs, the run can still pass.

## Success
The episode succeeds when the following has held for **1 s (50 control steps in a row)**: both doors of the wall cabinet are open to within 10% of their travel (within about 9 degrees of fully open), at the same time. The robot must not fall at any time: a fall (the pelvis tilted more than about 53 degrees from upright, or lower than 0.30 m) makes the episode a failure, but does not end it.

The episode ends when the success has held for 1 s (`reason = "success"`), when the pelvis gets more than
10 m from the scene's origin, on a simulator error, after **1450 control steps** (29 s of robot
time), or when your time is up. That live episode is the verdict.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); here the action type is `"whole_body"` (not the docstring's example name):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types["whole_body"]` (layout, lower, upper, units), `control_dt` (0.02 s), `max_control_steps` (1450), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, video="frames")` | `POST /observe` | the current frames (free), or stand still and watch for `seconds` (at most 30) |
| `r.submit("whole_body", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 21 commands `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |

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
res = r.submit("whole_body", A, dt=0.02)   # A: (T, 21) commands, one row per control step
```

## Action rows (21 floats, physical units)
| slot | name | bounds | meaning | at the start |
|---|---|---|---|---|
| 0 | `vx` | [-1, 1] | walking velocity command, forward (m/s, the robot's frame) | 0 |
| 1 | `vy` | [-1, 1] | walking velocity command, to the left (m/s) | 0 |
| 2 | `height` | [0.4, 1] | pelvis height command (m) | 0.74 |
| 3 | `wz` | [-1, 1] | turning rate command, + turns left (rad/s) | 0 |
| 4 | `pitch` | [-0.2, 0.8] | torso lean command, + leans forward (rad) | 0 |
| 5 | `left_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 6 | `left_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 7 | `left_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 8 | `left_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 9 | `left_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 10 | `left_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 11 | `left_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 12 | `right_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 13 | `right_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 14 | `right_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 15 | `right_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 16 | `right_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 17 | `right_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 18 | `right_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 19 | `left_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |
| 20 | `right_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |

`right_shoulder_roll_joint`'s bounds are BiGym's action bounds, not the joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

The last column is the row that stands still at the start. The whole-body controller, as BiGym's own notes for its coding agents describe it: it follows velocity commands with some lag and wobble, so read the pelvis pose and close the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least 0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8 rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It keeps the robot balanced but does not stop it from walking into things.

`spec()["joints"]` gives each arm, waist and finger joint's axis, a point on it and its range (the pelvis frame with
every joint at 0: `spec()["joint_frame"]`; the sign convention: `spec()["joint_sign"]`), `spec()["grippers"]` the point between each gripper's finger
pads on its wrist link, and `spec()["cameras"][camera]["mount"]` each camera's pose on its link. Keep your own copy of the last row you sent: a row rebuilt from the measured joint angles sits a little below
the targets the arms were holding (the servos track with a small error), so holding with it lets the arms sag. The
client's docstring explains the protocol with another benchmark's examples (`joint_position`, bounds [-1, 1], `imu`,
`links`, `depth`): for this task `spec()` is authoritative.

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the positions (`*_pos`) of the 3 waist joints (they show the lean you command), each arm's 7 joints (rad) and its gripper's 2 finger joints (slides, m), and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its heading, in rad: the room's frame, z up, heading 0 along the room's +x axis and counter-clockwise positive): 25 values; then their velocities (`*_vel`, per second) in the same order; then `left_gripper_state` and `right_gripper_state` (0 open .. 1 closed); then the pelvis pose again as the base controller tracks it (`pelvis_x`, `pelvis_y`, `pelvis_z`, `pelvis_yaw`). This is BiGym's own low-dimensional observation, the one its learned policies receive.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
