# KinDER task, instance i00 — LIMITED MODE (robot as a service)

You control a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) -- a holonomic base, a Kinova Gen3 7-DoF arm
and a Robotiq 2F-85 gripper -- **as if it were real hardware**: the simulator runs in a service you cannot open. You
get one client. **Task:** put the boxed drink (the small grey carton with an orange top) and the red can on either side of the red bowl on the kitchen island, along the island's length: the carton on the bowl's side toward the robot's right as it faces the island at the start (the side the can now stands on), the can on the side toward its left. The task succeeds the moment the carton's centre is 4 to 13 cm from the bowl's centre toward that right side and the can's centre 4 to 13 cm toward the left side, each within 6 cm of the bowl's centre across the island and between 1 cm below and 5 cm above it, all measured along the bowl's own axes, which start aligned with the island.

## Rules (real-robot rules)
- **Episodes.** The first episode starts when the service comes up. An episode ends when the task succeeds, after
  1000 control steps (100 s of robot time), when your time is up, or on a simulator error.
  Nothing else ends it.
- **Resets and grading.** `spec()["budget"]["reset"]` is how many times this run lets you call `reset()` (every
  observation carries `resets_left`). A reset starts a new episode from the same starting state and gives up the one
  in progress. The run passes the moment an episode reaches the goal, which also ends the run; otherwise it fails when
  an episode ends with no reset left, or when your time is up.
- **No privileged state, no score.** You get the robot's own sensors: its two cameras (RGB, 480×640:
  `robot_base` on the base, `robot_wrist` on the arm's last link), its joint encoders (the arm's angles and
  velocities, the gripper) and the base's odometry (where it is relative to where it started). Not where anything else
  is, not the goal check: the service judges the episode and only tells you that it ended and why (`obs["done"]`,
  `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this run
  provides, and the robot's own facts, as its documentation would give them: each arm joint's axis, position and
  limits, each camera's field of view and pose. Depending on the run's configuration that can also include depth from
  `robot_wrist` (an RGB-D camera) and `room_camera`, a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it. Leave the script that
  drove the last episode at `/app/output/gen.py` for the record, complete and runnable.
- Wall-clock budget: 1 h. It ends without warning, and ending your session earlier ends the run
  the same way, so do not stop early: while time and resets remain, another episode can still pass.

## Scoring
The run passes the moment an episode reaches the goal above, as KinDER's own goal check judges it
(`reason = "success"`). There is no partial credit.

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call, batching,
`images=`, the observation fields and the errors. Read it first (`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("delta", a)     # a: 11 values = one 10 Hz control step (below)
```
Measured cost per control step here: about 21.8 ms sent one at a time, 41.0 ms one at a time with
both robot cameras' images (and the wrist's depth), 20.2 ms in batches of 10 or more without images.

`obs["proprio"]` has `base_pose` ([x, y, yaw] in the odometry frame: where the base started, x the way it faced, y
left), `base_vel`, `arm_pos`, `arm_vel`, `gripper_pos` (the fingers' position: 0 open, 1 at their closed limit) and
`gripper_vel`; `spec()["proprio"]` gives the units.

Each action (`r.step("delta", a)`) is 11 numbers, one 10 Hz control step, in the order of `spec()["delta"]["layout"]`:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.1 a step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most 0.1.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the joints' new targets, which the arm's PD controller tracks.
- `gripper`: 0 = open, 1 = closed (a command, not a change).
