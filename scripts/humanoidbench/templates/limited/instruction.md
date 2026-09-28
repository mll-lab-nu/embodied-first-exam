# {{family}} — instance {{instance_tag}} — LIMITED MODE (robot as a service)

You control a simulated {{robot_label}} (HumanoidBench / MuJoCo) **as if it were real hardware**: the
simulator runs in a service you cannot open. You get one client. **Task:** {{limited_task_statement}}

## Rules (real-robot rules)
- **Episodes.** The first episode starts when the service comes up. An episode ends when the task succeeds{{limited_ends}}, after {{max_steps}} control steps ({{robot_seconds}} s of robot time), when your time is up, or on a simulator error. Nothing else ends it: a robot that has fallen without meeting one of these (lying on its side, sitting, face down) goes on until step {{max_steps}}, so an episode that is still running does not mean the robot is still up.
- **Resets and grading.** `spec()["budget"]["reset"]` is how many times this run lets you call `reset()` (every observation carries `resets_left`). A reset starts a new episode from the same starting state and gives up the one in progress. The run passes the moment an episode reaches the pass mark, which also ends the run; otherwise it fails when an episode ends with no reset left, or when your time is up.
- **No privileged state, no score.** You see what the robot's two head cameras see (RGB, {{image_hw}}) and its own joint angles and joint velocities. Not {{limited_hidden}}, not the reward: the service judges the episode and only tells you that it ended and why (`obs["done"]`, `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this run provides, and the robot's own facts, as its URDF would give them: each actuator's range, each joint's axis and position, each link's mass and centre of mass, the feet's collision boxes, the IMU's frame, each camera's field of view and pose. Depending on the task's configuration that can also include a pelvis IMU, depth from the head cameras and a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it. Leave the script that drove the last episode at `/app/output/gen.py` for the record, complete and runnable.
- Wall-clock budget: {{agent_timeout_hours}} h. It ends without warning, and ending your session earlier ends the run the same way, so do not stop early: while time and resets remain, another episode can still pass.

## Scoring
HumanoidBench scores the *whole episode*, not a final state: it passes iff the summed per-step reward reaches
**{{success_bar}}**: a total of rewards, not a number of steps (an episode is at most {{max_steps}} steps).
{{limited_scoring_note}} The service ends the episode the moment
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
