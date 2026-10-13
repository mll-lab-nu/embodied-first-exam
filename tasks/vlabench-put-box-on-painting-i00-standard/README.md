# vlabench-put-box-on-painting-i00-standard

| | |
|---|---|
| Benchmark | VLABench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `vlabench-put-box-on-painting-i00-privileged` |
| Simulator / robot | `vlabench` / `franka-panda` |
| Family / instance | `vlabench/put_box_on_painting` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-vlabench:0.1.0` |

## Task
VLABench's `put_box_on_painting` as a robot service: a Franka Panda arm at a table, instructed **"Please put the box on the Dinner and Love on the River."**
(a direct command), on the same frozen instance as `vlabench-put-box-on-painting-i00-privileged`. The simulator runs in the
`sim` sidecar (`environment/sim/server.py` on main's `rcb_service.py`); the agent only has the client: four cameras
(RGB 320×320, depth on request, calibrated), the robot's own state, and joint-position chunks. One episode, no reset,
no object poses; nothing to hand in.

## Difficulty
The agent has to find the objects in the images, close the loop through the cameras with joint-position targets, and
finish in one episode without a reset, on top of the task's own reasoning (a direct command).

## Reference solution
`solution/`: the privileged oracle's 131 control steps (recorded offline; see the twin's README) submitted
through the client; the episode ends with `reason = "success"` at the last of them.

## Verification
The sim service ends the episode at the task's success (or at the 9000-step technical cap, when the agent's
time is up, or on a simulator error), replays the recorded episode in a fresh simulator and writes `/data/final.json`;
`tests/grade.py` (separate sandbox, no network) grades it: `success = live_success ∧ replay_success ∧ deterministic`.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 11 GB | 10 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim p90 6.9 GB, privileged container p90 8.1 GB, verifier 4.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 20 GiB memory. Limits measured: memory: agent container docker peak 2.2 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 12 GiB (docker peak 7.2 GiB, 16 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Actions | `joint_position` (9, float64): absolute targets for the 7 arm joints (rad) and the 2 fingers (m), 0.1 s per control step |
| Episode cap | 9000 control steps (900 s of robot time; `spec.max_control_steps`, PROTOCOL §4.5 MAY) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
