# bookshelf_simple — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo) **as if
it were real hardware**: the simulator runs in a service you cannot open. You get one client. **Task:** put
each of the five objects onto its assigned place on the bookshelf, one at a time, in order.

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds, when the robot
  falls (its pelvis drops too low), when the object being placed drops, or once all five are placed, after
  1000 control steps (20 s of robot time), when your time is up, or on a simulator error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not where the objects or their places
  are, not the reward: the service judges the episode and only tells you that it ended and why (`obs["done"]`,
  `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this
  run provides; depending on the task's configuration that can also include a pelvis IMU and a camera fixed in
  the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it (the
  deliverable is the episode itself). Leave the script you drive the robot with at `/app/output/gen.py` for
  the record.
- Wall-clock budget: 1 h. It ends without warning, and the episode is graded as it stands at that moment.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**2000** (out of 1000 steps). Only the object you are currently on is scored: each step pays for standing
steadily, for a hand being near that object and for its progress towards its assigned slot. Placing it pays a
one-off bonus that grows with how many you have placed — together the bonuses are most of the bar — and moves
the scoring on to the next one. So the return is cut into five plateaus and stalling on the first caps the
episode low. The episode ends early if the torso drops or if the object currently being scored falls, and it
ends once all five are placed. The service ends the episode the moment the pass mark is reached
(`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: 61 position targets in [-1, 1] = one 50 Hz control step
```
Measured cost per control step here: about 3.4 ms sent one at a time, 11.1 ms one at a time with
both head-camera images, 2.5 ms in batches of 10 or more without images.

The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`,
`left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`, `right_shoulder_roll`,
`right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are the fingers, 20 per Shadow hand —
`lh_A_*` then `rh_A_*` (`spec()["qpos"]["layout"]`). `obs["proprio"]` measures joints, not actuators: 69 of
them, in `spec()["proprio"]["joints"]` order. A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.
