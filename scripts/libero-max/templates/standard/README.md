# {{name}}-standard

## Task
LIBERO-MAX case `{{case_id}}` as a robot service: a Franka Panda arm at a table, instructed **"{{instruction}}"**, on
the same frozen instance as `{{name}}-privileged`, with the same online event ({{event_words}}: {{event_detail}}, the
first time the gripper comes within {{trigger_m}} m of `{{trigger_object}}`). The simulator runs in the `sim` sidecar
(`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: two cameras (RGB
{{image_hw}}×{{image_hw}}, depth on request, calibrated), the robot's own state, and OSC control steps in chunks. One
episode, no reset, no object poses; nothing to hand in. The agent is told that the scene may change once, not how or
when.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with OSC deltas, notice the change
when it happens and adapt, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged oracle's {{n_actions}} control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at LIBERO's success (or at the {{std_cap}}-step technical cap, when the agent's time
is up, or on a simulator error), replays the recorded episode in a fresh process and writes `/data/final.json`;
`tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧ replay_success ∧ deterministic`.

## Details
| | |
|---|---|
| Actions | `ee_delta` (7, float64): OSC hand-target delta (1.0 = {{pos_scale}} m, {{rot_scale}} rad per control step) and gripper |
| Episode cap | {{std_cap}} control steps ({{robot_seconds}} s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
