# vlabench-heat-food-i00-standard

| | |
|---|---|
| Benchmark | VLABench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `vlabench-heat-food-i00-privileged` |
| Simulator / robot | `vlabench` / `franka-panda` |
| Family / instance | `vlabench/heat_food` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:vlabench-0.2.0` |

## Task
VLABench's `heat_food` as a robot service: a Franka Panda arm at a table, instructed **"Please heat cooked_food from tray_seen: put it into microwave_seen, close the microwave's door and press its start button (heating itself is not simulated)."**
(a direct command), on the same frozen instance as `vlabench-heat-food-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning (a direct command).

## Reference solution
`solution/`: the privileged oracle's 793 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success (or at the 9000-step technical cap, when the agent's
time is up, or on a simulator error) and writes that live verdict to `/data/final.json` (`graded_by = "live"`);
nothing is replayed to grade it (owner, 2026-10-17). The scene is checked against the frozen instance (its
initial state and compiled model hashes) when it is built, and its start state when the episode begins (a mismatch is
`instance_mismatch`, infrastructure). `tests/grade.py` (separate sandbox, no network) grades `final.json`:
`success = live_success`. The video (`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and
never changes it.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 11 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Actions | `joint_position` (9, float64): absolute targets for the 7 arm joints (rad) and the 2 fingers (m), 0.1 s per control step |
| Episode cap | 9000 control steps (900 s of robot time; `spec.max_control_steps`, docs/protocol/standard_mode.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
| Instruction | restated; VLABench's own: "Please heat cooked_food from tray_seen." (graded (HeatFoodTask): cooked_food inside microwave_seen, the door closed and the start button in contact, all at once; no heating is simulated) |
