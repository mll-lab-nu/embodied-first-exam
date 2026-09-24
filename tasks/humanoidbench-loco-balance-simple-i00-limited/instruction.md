# balance_simple — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open. You get one client. **Task:** stand on the balance board and stay
on it, upright and still, for the whole episode.

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds, when the robot
  falls, or anything but the fulcrum under the board touches the ground (see Scoring), after 1000 control
  steps (20 s of robot time), when your time is up, or on a simulator error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not the board's pose, not the reward:
  the service judges the episode and only tells you that it ended and why (`obs["done"]`, `obs["reason"]`:
  `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this run provides;
  depending on the task's configuration that can also include a pelvis IMU and a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it (the
  deliverable is the episode itself). Leave the script you drive the robot with at `/app/output/gen.py`
  for the record.
- Wall-clock budget: 1 h. It ends without warning, and the episode is graded as it stands at that moment.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**800** (out of 1000 steps). A good step asks for only three things — low actuator force, staying upright, and
near-zero horizontal velocity — so scoring well for one step is not the difficulty. The difficulty is that the
episode ends the moment the pelvis drops too low, anything but the fulcrum sphere touches the ground — the
board included — or the sphere touches anything other than the ground and the board, and every step after that
is worth nothing. The service ends the episode the moment the pass mark is reached (`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: 19 position targets in [-1, 1] = one 50 Hz control step
```
Measured cost per control step here: about 1.3 ms sent one at a time, 4.3 ms one at a time with both
head-camera images, 0.5 ms in batches of 10 or more without images.

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`,
`torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow` (`spec()["qpos"]["layout"]`;
`obs["proprio"]` measures the same joints in the same order). A constant action commands joint *targets*, not
a pose: whether the robot stays there depends on whether that pose is stable under gravity and contact.
