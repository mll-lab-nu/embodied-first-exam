# vlabench-add-condiment-i00-standard

| | |
|---|---|
| Benchmark | VLABench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `vlabench-add-condiment-i00-privileged` |
| Simulator / robot | `vlabench` / `franka-panda` |
| Family / instance | `vlabench/add_condiment` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-vlabench:0.1.0` |

## Task
VLABench's `add_condiment` as a robot service: a Franka Panda arm at a table, instructed **"Add bbq_sauce to the dish: hold the bbq_sauce bottle over pan_seen and tip it past horizontal, so that its top is lower than its bottom (pouring itself is not simulated)."**
(a direct command), on the same frozen instance as `vlabench-add-condiment-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning (a direct command).

## Reference solution
`solution/`: the privileged oracle's 180 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success (or at the 9000-step technical cap, when the agent's
time is up, or on a simulator error), replays the recorded episode in a fresh simulator and writes `/data/final.json`;
`tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧ replay_success ∧ deterministic`.

## Details
| | |
|---|---|
| Actions | `joint_position` (9, float64): absolute targets for the 7 arm joints (rad) and the 2 fingers (m), 0.1 s per control step |
| Episode cap | 9000 control steps (900 s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
| Instruction | restated; VLABench's own: "Add bbq_sauce to the dish" (graded: the bottle is above pan_seen (above) and tipped so that its top site is lower than its bottom site (pour); no liquid is simulated) |
