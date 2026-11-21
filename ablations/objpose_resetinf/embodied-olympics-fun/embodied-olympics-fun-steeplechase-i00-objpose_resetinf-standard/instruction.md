# embodied-olympics steeplechase — instance i00 — STANDARD MODE (robot as a service)

You control a simulated Unitree H1-2 humanoid robot (27 joints, 1.78 m tall, 67 kg; the Embodied Olympics simulator on MuJoCo)
**as if it were real hardware**: the simulator runs in a service you cannot open, and you reach it only through a
client. **Task:** Go over the steeplechase hurdle in front of you and over or through the water pit behind it, get out beyond the pit's far edge and stand on your feet.

## The venue
You stand on the track facing the hurdle (+x), on the centre line of the water jump. The hurdle's near face is 10.0 m ahead; its bar is as high as your hip joints. Directly behind the bar the pit drops 0.5 m; its far edge is 3.66 m beyond the hurdle's near face. The track continues level beyond the pit and on both sides of it.

Directions are from the robot at the start: +x is the way you face, +y is to your left, +z is up; the floor is level.


## The rules
**Rule book:** World Athletics Competition and Technical Rules 2024, Technical Rule 23 (steeplechase races): the men's hurdle 0.914 m high with a top bar 0.127 m square; the hurdle at the water jump 3.66 m wide and fixed; the water jump 3.66 m long including the hurdle, the pit 3.66 m wide, 0.50 m deep at the hurdle for about 1.20 m, then a uniform slope up to the level of the track at the far end; each athlete shall go over each hurdle (in any manner) and over or through the water, and is disqualified for stepping to one side of the water jump or trailing a foot or leg below the horizontal plane of the top of the hurdle at the instant of clearance. Where this task departs from it:

- TR 23 (the race): one water jump from a 10.0 m approach instead of a 3000 m race with 28 hurdle and 7 water jumps (a single action; the family is the water jump)
- TR 23 (the water jump): the water itself is not simulated; the pit is dry and its floor is the hard, sloping bottom (the simulator has no free-surface water; what remains is the pit's real geometry)
- TR 23 (clearance): "foot or leg below the top of the hurdle" is judged on the centres of the two feet and the pelvis where each crosses the vertical plane through the middle of the hurdle's top bar (three points a referee can measure on a robot)
- the finish: with no race to run on to, the attempt ends when the whole body is beyond the pit's far edge and the robot has stood on its feet for 1.0 s

The hurdle is fixed (it does not move or topple): its top bar is 0.127 m square, 3.66 m wide, with its top 0.914 m above the track, on a post at each end. Its near face is 10.0 m ahead of where your pelvis starts. The water jump is 3.66 m long measured from the hurdle's near face, and 3.66 m wide, centred on your line: the pit is 0.5 m deep for the first 1.2 m and then slopes up evenly to the track's level at its far edge. There is no water in it. You must go over the hurdle: every time your pelvis or the centre of either foot crosses, going forward, the vertical plane through the middle of the top bar, that point must be higher than the bar's top (0.914 m), and your pelvis must also be between the two ends of the bar; otherwise you fail. You may go over the hurdle in any manner: your hands and feet may touch it or stand on it. Once your pelvis is beyond that plane and until your whole body is beyond the pit's far edge, you fail if your pelvis is outside the pit's width or if any part of you touches the track's surface beside the pit (a contact less than 0.05 m below the track's level; the pit's side walls below that may be touched). You may land in the pit or beyond it, and any part of you may touch the pit's floor and walls and the track before and beyond the pit: there is no fall rule. You succeed when your whole body is beyond the pit's far edge and you then stand for 1.0 s without a break: only your feet on the ground, your torso within 20.0 degrees of vertical, your pelvis moving no faster than 0.35 m/s. The attempt ends after 60 s of robot time.

A referee in the service decides this from the simulator's state. The events that must happen, in order, are
**hurdle → out of the water jump → stand**. An attempt (an episode) ends at the success, at the first rule violation, or after 60 s
(6000 control steps) of robot time.

## Real-robot rules
- **Attempts.** The first episode starts when the service comes up. `r.reset()` abandons the running attempt (or
  follows one that has ended) and starts a new one from the same start; `spec()["budget"]["reset"]` says how many
  resets you have (5 here). **Only your last attempt is graded**, and a success ends the trial at once.
- **Time moves only inside calls.** `submit` runs your rows and `get_obs(seconds=s)` holds the command in force for
  s seconds; both use up the attempt's time. Between calls the robot waits, frozen, while you think; `get_obs()` with
  no seconds is free.
- **No privileged state.** You get what the robot's own sensors give: its two head cameras (`head_left`,
  `head_right`, RGB 270 × 480, a stereo pair 5 cm apart, tilted 20° down; depth on `head_left`), its joint encoders,
  motor torques and two IMUs (below), and the venue's fixed cameras (`venue`, `water_jump`; `spec()["cameras"]` says
  where each is mounted). Not where you or any object is, not the
  referee's state. Once an attempt is over, every response carries the referee's call: `meta["outcome"]`
  (`"success"` or the rule that ended it) and `meta["stages_reached"]` of `meta["stages_total"]`.
- There is nothing to hand in: the service records your last attempt and grades it as it ran live (the referee's
  call). Keep the script that drives the robot at `/app/output/gen.py` and a `NOTES.md` of at most 20 lines (your
  approach, what failed, what you downloaded or installed) for the record: save them early and keep them current.
- Wall clock: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same
  way, so do not stop early: while you have attempts left, the run can still pass.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
Your whole interface to the robot. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`; it explains the protocol with another benchmark's example names: for this task `spec()` is
authoritative).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the service is ready |
| `r.spec()` | `GET /spec` | the facts: `action_types` (each type's layout, lower, upper, meaning), `control_dt` (0.01 s), `max_control_steps` (6000), `cameras` (field of view, pose at the start), `proprio_layout`, `robot_facts` (joints, limits, default gains, the stance), `rules`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `resets_left` |
| `r.get_obs(cameras=None, seconds=0, video="frames", include_depth=False)` | `POST /observe` | the current frames (free), or hold the command in force and watch for `seconds` (at most 30) |
| `r.submit(type, A, dt=0.01, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of that action type `dt` seconds apart (a multiple of 0.01; a chunk covers at most 10 s); stops early when the attempt ends |
| `r.reset()` | `POST /reset` | a new attempt from the same start (see above) |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.depth`, `res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in
`meta["clipped"]`, never refused; a malformed request raises `ValueError` and runs nothing. Rendering is most of a
call's cost: a controller's call should ask for no video (`video="none"`, `cameras=["head_left"]` or fewer) and read
`res.proprio`. With `interpolate="linear"` (the default) each control step's command is a straight line from the
command in force to the row; `"hold"` applies the row as it is.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("walk", A, dt=0.02, video="none")   # A: (T, 20) rows of the `walk` type
```

## Actions
One row is one control step (10 ms; the physics runs at 1 kHz) unless `dt` spreads it. Every row ends with `grip_left`,
`grip_right`.

| type | row (then `grip_left`, `grip_right`) | floats | who drives what |
|---|---|---|---|
| `stand` | waist 1 + arms 14 joint targets | 17 | the platform holds the legs in the stance; you give the waist's 1 and the arms' 14 joint targets (rad) |
| `walk` | `vx`, `vy`, `wz` + waist 1 + arms 14 joint targets | 20 | Unitree's walking policy drives the legs from the velocity command (vx forward, vy to the left, m/s; wz turning left, rad/s; the robot's own frame); you give the waist and arm joint targets |
| `joints` | all 27 joint targets | 29 | you give all 27 joint targets (rad); the default PD gains, no feed-forward |
| `lowcmd` | all 27 joints × (`q`, `dq`, `tau`, `kp`, `kd`): 27 targets, then 27 velocities, 27 torques, 27 kp, 27 kd | 137 | Unitree's LowCmd for all 27 joints: position targets (rad), velocity targets (rad/s), feed-forward torques (N m), kp, kd; the motor torque is kp (q - q_measured) + kd (dq - dq_measured) + tau, evaluated at 1 kHz |

Velocity commands are in the robot's own frame (`vx` forward, `vy` to its left, m/s; `wz` turning left, rad/s). Bounds: `walk` |vx| ≤ 0.8, |vy| ≤ 0.5, |wz| ≤ 1.57. Joint targets are absolute angles (rad). Values outside the bounds are clipped. `grip_left`, `grip_right`: ≥ 0.5 closes the hand's grip, < 0.5 opens it. At the start the robot stands in `stand` mode with the arms at rest: the `stand` row with the table's start angles and both grips open keeps it there.

Joint order everywhere (Unitree's SDK order), with each joint's range, speed limit, torque limit and default gains
(also in `spec()["robot_facts"]`):

| # | joint | range (rad) | speed (rad/s) | torque (N m) | kp | kd | at the start (rad) |
|---|---|---|---|---|---|---|---|
| 0 | `left_hip_yaw` | [-0.43, 0.43] | 23 | 360 | 800 | 10 | 0 |
| 1 | `left_hip_pitch` | [-3.14, 2.5] | 23 | 360 | 800 | 10 | -0.16 |
| 2 | `left_hip_roll` | [-0.43, 3.14] | 23 | 360 | 800 | 10 | 0 |
| 3 | `left_knee` | [-0.26, 2.05] | 14 | 360 | 1200 | 16 | 0.36 |
| 4 | `left_ankle_pitch` | [-0.8973, 0.5236] | 9 | 66.88 | 160 | 8 | -0.2 |
| 5 | `left_ankle_roll` | [-0.2618, 0.2618] | 9 | 40 | 160 | 8 | 0 |
| 6 | `right_hip_yaw` | [-0.43, 0.43] | 23 | 360 | 800 | 10 | 0 |
| 7 | `right_hip_pitch` | [-3.14, 2.5] | 23 | 360 | 800 | 10 | -0.16 |
| 8 | `right_hip_roll` | [-3.14, 0.43] | 23 | 360 | 800 | 10 | 0 |
| 9 | `right_knee` | [-0.26, 2.05] | 14 | 360 | 1200 | 16 | 0.36 |
| 10 | `right_ankle_pitch` | [-0.8973, 0.5236] | 9 | 66.88 | 160 | 8 | -0.2 |
| 11 | `right_ankle_roll` | [-0.2618, 0.2618] | 9 | 40 | 160 | 8 | 0 |
| 12 | `torso` | [-2.35, 2.35] | 23 | 200 | 600 | 15 | 0 |
| 13 | `left_shoulder_pitch` | [-3.14, 1.57] | 9 | 130 | 300 | 6 | 0 |
| 14 | `left_shoulder_roll` | [-0.38, 3.4] | 9 | 60 | 300 | 6 | 0 |
| 15 | `left_shoulder_yaw` | [-2.66, 3.01] | 20 | 60 | 200 | 4 | 0 |
| 16 | `left_elbow_pitch` | [-0.95, 3.18] | 20 | 60 | 200 | 4 | 0 |
| 17 | `left_elbow_roll` | [-3.01, 2.75] | 31.4 | 60 | 80 | 1.5 | 0 |
| 18 | `left_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | 0 |
| 19 | `left_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | 0 |
| 20 | `right_shoulder_pitch` | [-3.14, 1.57] | 9 | 130 | 300 | 6 | 0 |
| 21 | `right_shoulder_roll` | [-3.4, 0.38] | 9 | 60 | 300 | 6 | 0 |
| 22 | `right_shoulder_yaw` | [-3.01, 2.66] | 20 | 60 | 200 | 4 | 0 |
| 23 | `right_elbow_pitch` | [-0.95, 3.18] | 20 | 60 | 200 | 4 | 0 |
| 24 | `right_elbow_roll` | [-2.75, 3.01] | 31.4 | 60 | 80 | 1.5 | 0 |
| 25 | `right_wrist_pitch` | [-0.47, 0.47] | 31.4 | 19 | 60 | 1 | 0 |
| 26 | `right_wrist_yaw` | [-1.27, 1.27] | 31.4 | 19 | 60 | 1 | 0 |

What the platform does and does not do for you:

- **`stand`** holds the legs at the standing pose with stiff gains and a gravity-support torque. It is not a balance
  controller: it does not step and it has no feedback. After an arm movement the body sways a few centimetres for a
  few seconds; a hard or fast swing of the arms, a push or a load can tip the robot over within a second or two.
- **`walk`** runs Unitree's own H1-2 walking policy (50 Hz) on the legs. At the largest forward command (0.8) it walks at
  about 0.6 m/s and its heading drifts (close the loop on the IMU); `vy` up to 0.5 and `wz` up to 1.57 rad/s. At a
  zero command it marks time on the spot and recovers from small disturbances, which `stand` does not. When the legs
  come to it from another mode it first blends them to the stance (0.3 s) and holds a zero command until the robot is
  steady (up to 2 s). It was trained with the arms at their zero pose (upper arms down, forearms forward): moving the
  arms disturbs it. This robot has no running policy: anything faster than a walk is yours to build or to find. The
  G1's two other walking policies (FALCON, AGILE) are not offered for it: driven on this robot (joints matched by name)
  they keep it upright but do not walk it.
- **`joints` / `lowcmd`** are yours: each motor's torque is `kp (q − q_measured) + kd (dq − dq_measured) + tau`, evaluated
  at 1 kHz with your row held for its 10 ms, then limited by the motor's torque-speed curve and torque limit. `joints`
  uses the default gains of the table and zero `dq` and `tau`; `lowcmd` takes yours (kp up to 1500 / 800 / 400 and kd up to
  30 / 20 / 10 for legs / waist / arms). Nothing balances the robot in these modes but your own targets.
- **Every joint target** is clipped into the joint's range and moves at most the joint's speed limit × 10 ms per step
  from the target in force. Joints a type does not name keep their targets. The speed limit is a limit on targets;
  what bounds the joint itself is the motor's torque-speed curve (a `lowcmd` feed-forward torque can turn a joint up to
  about 1.15 times that speed, where the motor's torque has fallen to zero).
- **The hands** have no working fingers here; each carries a fist pad (a box of 4.4 × 8 × 10 cm beyond the wrist, the
  10 cm along the forearm). Nothing in this task is grippable: `grip_left` and `grip_right` have no effect.
- **A tool on a hand** (a racket, a paddle, a club; where the task has one) is fixed to the wrist in place of the pad.
  It collides with the world, the ball and the rest of your own body.
- **The air** is real: balls and implements feel drag and, when they spin, lift.
- **If the physics diverges** (a numerical blow-up, typically from a violent joint command), the attempt ends as a
  failure: "the simulation became unstable".

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the 27 joint positions
(`*_pos`, rad), their velocities (`*_vel`, rad/s), the motor torques applied (`*_torque`, N m), the joint targets in
force (`*_target`, rad), the pelvis IMU and the torso IMU (each: orientation quaternion `qw, qx, qy, qz`, world from
sensor; angular velocity `gx, gy, gz`, rad/s; acceleration `ax, ay, az`, m/s², gravity included; in the sensor's frame),
`holding_left`, `holding_right` (1 while that hand grips something), `mode` (0 stand, 1 walk, 2 run, 3 run_arms,
4 joints / lowcmd; the G1 also 5 walk_falcon, 6 walk_agile), the velocity command in force (`cmd_vx`, `cmd_vy`, `cmd_wz`) and `time_s`, the attempt's time. A
real H1-2 has no sensor for its position in the venue, and neither do you: that is what the cameras are for.

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

## This run: unlimited resets, save and load

This run changes the reset budget and adds two calls. This section overrides anything above, and anything in `/spec`,
that says there is no reset, one episode only, or fewer resets.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON body
  such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state.
  The answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`,
  `loads` and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets.
  Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a
  load until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved
  state followed by what you did after the load. The success rule is checked again from your next command on. A
  success still ends the run: no reset, save or load after it.

## External material
The network is open. You may install packages (pip, apt), and you may search for, download and use public tools, robot models and pretrained controllers (for example a published Unitree G1 walking, jumping or whole-body policy): finding existing work and adapting it to this robot is encouraged. Say in your notes what you used. You may read anything installed in your container, this benchmark's own source code included. The one thing not to look up is a ready-made solution to this exact task, such as this benchmark's reference solutions. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **8192 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
