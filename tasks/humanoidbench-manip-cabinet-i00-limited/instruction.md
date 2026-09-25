# cabinet — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo) **as if
it were real hardware**: the simulator runs in a service you cannot open. You get one client. **Task:** open
the cabinet's compartments in order: slide open the sliding door, then pull out the drawer, then open one of
the double doors and lift the cube from the drawer into that compartment, then open the flip-up door and lift
the cube that started behind the double doors (not the one you put there) up into it.

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds, when the last
  compartment is done, after 1000 control steps (20 s of robot time), when your time is up, or on a simulator
  error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not the cabinet's or the cubes'
  state, not the reward: the service judges the episode and only tells you that it ended and why
  (`obs["done"]`, `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists
  exactly what this run provides; depending on the task's configuration that can also include a pelvis IMU and
  a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it. Leave the
  script you drive the robot with at `/app/output/gen.py` for the record.
- Wall-clock budget: 1 h. It ends without warning, and the episode is graded as it stands at that moment;
  ending your session earlier does the same, so do not stop early.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**2500** (out of 1000 steps). Only the compartment you are currently on is scored. Each step pays a small
share for standing steadily and the bulk for progress on that one compartment; completing it pays a one-off
bonus and moves the scoring on to the next. Those bonuses grow with how many you have finished, and together
they are a large fraction of the bar — so stalling on the first compartment caps the episode well short of it,
however cleanly that compartment is opened. The service ends the episode the moment the pass mark is reached
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
Measured cost per control step here: about 2.3 ms sent one at a time, 5.0 ms one at a time with
both head-camera images, 1.5 ms in batches of 10 or more without images.

The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`,
`left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`, `right_shoulder_roll`,
`right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are the fingers, 20 per Shadow hand —
`lh_A_*` then `rh_A_*` (`spec()["qpos"]["layout"]`). `obs["proprio"]` measures joints, not actuators: 69 of
them, in `spec()["proprio"]["joints"]` order. A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.
