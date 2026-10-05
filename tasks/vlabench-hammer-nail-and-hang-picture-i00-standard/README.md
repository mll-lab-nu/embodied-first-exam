# vlabench-hammer-nail-and-hang-picture-i00-standard

| | |
|---|---|
| Benchmark | VLABench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `vlabench-hammer-nail-and-hang-picture-i00-privileged` |
| Simulator / robot | `vlabench` / `franka-panda` |
| Family / instance | `vlabench/hammer_nail_and_hang_picture` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-vlabench:0.1.0` |

## Task
VLABench's `hammer_nail_and_hang_picture` as a robot service: a Franka Panda arm at a table, instructed **"Please hang the 本所立川 on the wall safely and steadily: drive the nail into the wall with the hammer (VLABench checks that the nail's joint position is between 0.05 and 0.08) and bring the 本所立川 painting to the nail (its grasp point within 5 cm of the nail's)."**
(a direct command), on the same frozen instance as `vlabench-hammer-nail-and-hang-picture-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning (a direct command).

## Reference solution
`solution/`: the privileged oracle's 361 control steps (recorded offline; see the twin's README) submitted
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
| Instruction | restated; VLABench's own: "Please hang the 本所立川 on the wall safely and steadily." (graded (HangPictureTask): the nail's joint in [0.05, 0.08] (joint_in_range) and, at some step, the painting's grasp keypoint within 0.05 m of the nail's; upstream does not mention the nail) |
