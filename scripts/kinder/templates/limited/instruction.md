# KinDER task, instance {{instance_tag}} — LIMITED MODE (robot as a service)

You control {{limited_robot}} -- **as if it were real hardware**: the simulator runs in a service you cannot open. You
get one client. **Task:** {{task_statement}}

## Rules (real-robot rules)
- **Episodes.** The first episode starts when the service comes up. An episode ends when the task succeeds, after
  {{max_steps}} control steps{{robot_time}}, when your time is up, or on a simulator error.
  Nothing else ends it.
- **Resets and grading.** `spec()["budget"]["reset"]` is how many times this run lets you call `reset()` (every
  observation carries `resets_left`). A reset starts a new episode from the same starting state and gives up the one
  in progress. The run passes the moment an episode reaches the goal, which also ends the run; otherwise it fails when
  an episode ends with no reset left, or when your time is up.
- **No privileged state, no score.** You get the robot's own sensors: {{sensors}}. Not where anything else
  is, not the goal check: the service judges the episode and only tells you that it ended and why (`obs["done"]`,
  `obs["reason"]`: `"success"`, or `"failed"` when it ended without success). `spec()` lists exactly what this run
  provides, and the robot's own facts, as its documentation would give them: each arm joint's axis, position and
  limits, each camera's field of view and pose. Depending on the run's configuration that can also include depth from
  `robot_wrist` (an RGB-D camera) and `room_camera`, a camera fixed in the room.
- Simulated time only moves when you step: between requests the robot waits, frozen, while you think.
- There is nothing to hand in: the service records the episode as the trajectory and grades it. Leave the script that
  drove the last episode at `/app/output/gen.py` for the record, complete and runnable.
- Wall-clock budget: {{agent_timeout_hours}} h. It ends without warning, and ending your session earlier ends the run
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
obs = r.step("delta", a)     # a: {{action_dim}} values = one {{step_name}} (below)
```
Measured cost per control step here: about {{ms_single}} ms sent one at a time, {{ms_images}} ms one at a time with
{{images_what}}, {{ms_batch}} ms in batches of 10 or more without images.

{{proprio_text}}

{{limited_action_layout}}
