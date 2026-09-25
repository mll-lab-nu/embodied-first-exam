# truck — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open. You get one client. **Task:** unload the five loose packages from
the truck (the wall of boxes behind them is fixed) and put them on the table — all of them.

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds, when the last
  package is on the table, after 1000 control steps (20 s of robot time), when your time is up, or on a
  simulator error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not where the packages are, not the
  reward: the service judges the episode and only tells you that it ended and why (`obs["done"]`,
  `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this
  run provides; depending on the task's configuration that can also include a pelvis IMU and a camera fixed in
  the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it. Leave the
  script you drive the robot with at `/app/output/gen.py` for the record.
- Wall-clock budget: 1 h. It ends without warning, and the episode is graded as it stands at that moment;
  ending your session earlier does the same, so do not stop early.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**3000** (out of 1000 steps). Each step is your uprightness multiplied by a base amount plus three progress
terms: how close the robot is to a package still on the truck, how close it is to a package it has picked up,
and how close a picked-up package is to the table. On top of that, lifting a package off the truck and placing
one on the table each pay a one-off bonus (taken back if a package comes off the table again), and delivering
the last package pays a larger one and ends the episode. Uprightness is a *factor*, so lying down costs a
large part of every step. The one-off bonuses are most of the bar but not all of it, so the rest has to come
from the per-step terms before the last delivery. The service ends the episode the moment the pass mark is
reached (`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: 19 position targets in [-1, 1] = one 50 Hz control step
```
Measured cost per control step here: about 1.5 ms sent one at a time, 4.3 ms one at a time with
both head-camera images, 0.8 ms in batches of 10 or more without images.

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`,
`torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`
(`spec()["qpos"]["layout"]`; `obs["proprio"]` measures the same joints in the same order). A constant action
commands joint *targets*, not a pose: whether the robot stays there depends on whether that pose is stable
under gravity and contact.
