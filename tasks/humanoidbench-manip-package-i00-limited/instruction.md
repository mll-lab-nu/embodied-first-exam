# package — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open. You get one client. **Task:** walk to the package, pick it up,
carry it to the destination, marked in the scene by a translucent cyan ball, and set it down there, standing
upright.

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds, when the package
  reaches the destination, after 1000 control steps (20 s of robot time), when your time is up, or on a
  simulator error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not where the package or the
  destination is, not the reward: the service judges the episode and only tells you that it ended and why
  (`obs["done"]`, `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists
  exactly what this run provides; depending on the task's configuration that can also include a pelvis IMU and
  a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it (the
  deliverable is the episode itself). Leave the script you drive the robot with at `/app/output/gen.py` for
  the record.
- Wall-clock budget: 1 h. It ends without warning, and the episode is graded as it stands at that moment.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**1500** (out of 1000 steps). Every step charges you for the distance from the package to its destination —
the largest term by far — and a little for the distance from each hand to the package; against that you earn a
share for standing steadily and a share for how high the package is off the ground. So the return is strongly
negative while the package sits on the floor across the room, and improves as you close the distance with it
lifted. Landing the package on the destination pays a one-off bonus worth more than a thousand ordinary steps
and ends the episode. Getting to the bar means both carrying it there *and* not spending long about it. The
service ends the episode the moment the pass mark is reached (`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: 19 position targets in [-1, 1] = one 50 Hz control step
```
Measured cost per control step here: about 1.2 ms sent one at a time, 3.9 ms one at a time with
both head-camera images, 0.5 ms in batches of 10 or more without images.

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`,
`left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`,
`torso`, `left_shoulder_pitch`, `left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`,
`right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`
(`spec()["qpos"]["layout"]`; `obs["proprio"]` measures the same joints in the same order). A constant action
commands joint *targets*, not a pose: whether the robot stays there depends on whether that pose is stable
under gravity and contact.
