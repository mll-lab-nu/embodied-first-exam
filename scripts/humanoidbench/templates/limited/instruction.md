# {{family}} — instance {{instance_tag}} — LIMITED MODE (robot as a service)

You control a simulated {{robot_label}} (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open. You get one client. **Task:** {{limited_task_statement}}

## Rules (real-robot rules)
- **Episodes.** The episode starts when the service comes up and ends when the task succeeds{{limited_ends}}, after {{max_steps}} control steps ({{robot_seconds}} s of robot time), when your time is up, or on a simulator error.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, {{image_hw}}) and its own joint angles and joint velocities. Not {{limited_hidden}}, not the reward: the service judges the episode and only tells you that it ended and why (`obs["done"]`, `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this run provides; depending on the task's configuration that can also include a pelvis IMU and a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it (the deliverable is the episode itself). Leave the script you drive the robot with at `/app/output/gen.py` for the record.
- Wall-clock budget: {{agent_timeout_hours}} h. It ends without warning, and the episode is graded as it stands at that moment.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**{{success_bar}}** (out of {{max_steps}} steps). {{limited_scoring_note}} The service ends the episode the moment
the pass mark is reached (`reason = "success"`).

## Client (`/opt/tools/rcb_client.py`, protocol `rcb-limited/1.1`)
The client is your whole interface to the robot, and its docstring is the full reference: every call,
batching, `images=`, the observation fields and the errors. Read it first
(`python -c "import rcb_client; help(rcb_client)"`).
```python
from rcb_client import Robot
r = Robot()                  # connects; r.spec() lists what this run provides
obs = r.step("qpos", a)      # a: {{nu}} position targets in [-1, 1] = one {{control_hz}} Hz control step
```
Measured cost per control step here: about {{ms_single}} ms sent one at a time, {{ms_images}} ms one at a time with
both head-camera images, {{ms_batch}} ms in batches of 10 or more without images.

{{limited_actuator_layout}}
