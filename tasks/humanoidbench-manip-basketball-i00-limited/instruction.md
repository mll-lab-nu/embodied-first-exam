# basketball — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open. You get one client. **Task:** a ball is thrown at the robot.
Catch it, then throw it through the hoop.

## Rules (real-robot rules)
- **Episodes.** The first episode starts when the service comes up. An episode ends when the task succeeds,
  when the ball goes through the hoop, when the ball drops low, when the robot falls, after 500 control steps
  (10 s of robot time), when your time is up, or on a simulator error. Nothing else ends it: a robot that has
  fallen without meeting one of these (lying on its side, sitting, face down) goes on until step 500, so an
  episode that is still running does not mean the robot is still up.
- **Resets and grading.** `spec()["budget"]["reset"]` is how many times this run lets you call `reset()`
  (every observation carries `resets_left`). A reset starts a new episode from the same starting state and
  gives up the one in progress. The run passes the moment an episode reaches the pass mark, which also ends
  the run; otherwise it fails when an episode ends with no reset left, or when your time is up.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not where the ball or the hoop is,
  not the reward: the service judges the episode and only tells you that it ended and why (`obs["done"]`,
  `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this
  run provides, and the robot's own facts you need to read it: each actuator's range, each joint's axis, the
  IMU's frame, each camera's field of view and pose. Depending on the task's configuration that can also
  include a pelvis IMU, depth from the head cameras and a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it. Leave the
  script that drove the last episode at `/app/output/gen.py` for the record, complete and runnable.
- Wall-clock budget: 1 h. It ends without warning, and ending your session earlier ends the run the same way,
  so do not stop early: while time and resets remain, another episode can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**1200**: a total of rewards, not a number of steps (an episode is at most 500 steps). Scoring runs in two
stages and switches by itself the first time the robot contacts the ball. Before that it rewards standing
steadily and getting both hands to the ball; after it, the dominant term is how close the ball is to the hoop.
Sinking it pays a one-off bonus that covers most of the bar but not all of it, and ends the episode
immediately, so the rest has to be earned per step before the ball goes in. That bonus is not optional: no
amount of good positioning reaches the bar without it. The service ends the episode the moment the pass mark
is reached (`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: 19 position targets in [-1, 1] = one 50 Hz control step
```
Measured cost per control step here: about 1.3 ms sent one at a time, 5.2 ms one at a time with
both head-camera images, 0.6 ms in batches of 10 or more without images.

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`,
`torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`
(`spec()["qpos"]["layout"]`; `obs["proprio"]` measures the same joints in the same order). An action value of
−1 or +1 commands one end of that servo's range, `spec()["qpos"]["range"]` in radians, and the scale is
linear, so 0 is mid-range, not 0 rad. A constant action commands joint *targets*, not a pose: whether the
robot stays there depends on whether that pose is stable under gravity and contact.
