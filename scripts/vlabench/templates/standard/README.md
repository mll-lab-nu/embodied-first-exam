# vlabench-{{dash}}-i00-standard

## Task
VLABench's `{{task}}` as a robot service: a Franka Panda arm at a table, instructed **"{{instruction}}"**
({{instruction_kind}}), on the same frozen instance as `vlabench-{{dash}}-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning ({{instruction_kind}}).

## Reference solution
`solution/`: the privileged oracle's {{n_actions}} control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success (or at the {{max_steps}}-step technical cap, when the agent's
time is up, or on a simulator error), replays the recorded episode in a fresh simulator and writes `/data/final.json`;
`tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧ replay_success ∧ deterministic`.

## Details
| | |
|---|---|
| Actions | `joint_position` (9, float64): absolute targets for the 7 arm joints (rad) and the 2 fingers (m), 0.1 s per control step |
| Episode cap | {{max_steps}} control steps ({{robot_seconds}} s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |{{instruction_row}}
