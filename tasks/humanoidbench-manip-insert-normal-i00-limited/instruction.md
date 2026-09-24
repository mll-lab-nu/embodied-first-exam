# insert_normal — instance 00 — LIMITED MODE (robot as a service)

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo) **as if
it were real hardware**: the simulator runs in a service you cannot open. You get one client. **Task:** a bar
and two small open sockets lie on the table in front of the robot. Fit each end of the bar into the socket of
the matching colour, then lift the assembly to about 1.1 m and hold it there, without dropping anything.

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds, when the robot
  falls (its pelvis drops too low), or when the bar or either socket drops, after 500 control steps (10 s of
  robot time), when your time is up, or on a simulator error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, 256×256) and its own
  joint angles and joint velocities. Not where the robot is in the room, not the poses of the bar and the
  sockets, not the reward: the service judges the episode and only tells you that it ended and why
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
**350** (out of 500 steps). The step is a product of two groups: one covering posture and how close each end
of the bar is to its socket, the other covering how high the sockets are and whether a hand is at a socket.
Because the groups multiply, doing one of them well is worth little while the other is near zero — both have
to come along together. The episode ends the moment the bar or either socket drops below a height, which a
dropped part does immediately, or the torso does. The episode limit here is 500 steps, not 1000. The service
ends the episode the moment the pass mark is reached (`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: 61 position targets in [-1, 1] = one 50 Hz control step
```
Measured cost per control step here: about 2.4 ms sent one at a time, 5.5 ms one at a time with
both head-camera images, 1.5 ms in batches of 10 or more without images.

The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`,
`left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`, `right_shoulder_roll`,
`right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are the fingers, 20 per Shadow hand —
`lh_A_*` then `rh_A_*` (`spec()["qpos"]["layout"]`). `obs["proprio"]` measures joints, not actuators: 69 of
them, in `spec()["proprio"]["joints"]` order. A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.
