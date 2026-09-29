# KinDER task, instance i00 — LIMITED MODE (robot as a service)

You control a simulated mobile manipulator (KinDER / PyBullet, kinematic) -- a TidyBot++ base, a Kinova Gen3
7-DoF arm and a Robotiq 2F-85 gripper -- **as if it were real hardware**: the simulator runs in a service you cannot open. You
get one client. **Task:** put the yellow cube and the dark grey metal cube, both on the floor, and the open-topped box with a blue flower print onto the wooden table (its top 0.4 m above the floor). The task succeeds the moment the gripper is fully open (`gripper_pos` at most 0.0125) and the centres of both cubes and of the box are each at least 0.3 m above the floor and at least 0.2 m from the arm's end-effector point (`spec()["arm"]["end_effector"]`).

## Rules (real-robot rules)
- **Episodes.** The first episode starts when the service comes up. An episode ends when the task succeeds, after
  1200 control steps, when your time is up, or on a simulator error.
  Nothing else ends it.
- **Resets and grading.** `spec()["budget"]["reset"]` is how many times this run lets you call `reset()` (every
  observation carries `resets_left`). A reset starts a new episode from the same starting state and gives up the one
  in progress. The run passes the moment an episode reaches the goal, which also ends the run; otherwise it fails when
  an episode ends with no reset left, or when your time is up.
- **No privileged state, no score.** You get the robot's own sensors: its two cameras (RGB, 480×640:
  `robot_base` on the base, `robot_wrist` on the arm's last link), its joint encoders (the arm's angles, the
  gripper) and the base's odometry (where it is relative to where it started). Not where anything else
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
obs = r.step("delta", a)     # a: 11 values = one control step (below)
```
Measured cost per control step here: about 1.8 ms sent one at a time, 381.1 ms one at a time with
both robot cameras' images (and the wrist's depth), 0.9 ms in batches of 10 or more without images.

`obs["proprio"]` has `base_pose` ([x, y, yaw] in the odometry frame: where the base started, x the way it faced, y
left), `arm_pos` and `gripper_pos` (the fingers' position: 0 open, 1 at their closed limit); the robot is
kinematic, so it reports no velocities. `spec()["proprio"]` gives the units.

Each action (`r.step("delta", a)`) is 11 numbers, one control step, in the order of `spec()["delta"]["layout"]`:
- `base_x`, `base_y`: how far to move the base, metres in the odometry frame, together at most 0.2 a step; `base_yaw`: how far to turn it, radians (+ = counter-clockwise), at most 0.2.
- `arm_1` ... `arm_7`: radians to add to each of the 7 arm joints' angles, each at most 0.2 a step; the arm moves there at once.
- `gripper`: below -0.5 closes the gripper, above 0.5 opens it, in between leaves it as it is; when that takes hold or lets go: `spec()["delta"]["units"]`.
