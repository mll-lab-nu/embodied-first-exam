# robocasa-pnp-cab-to-counter-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa-pnp-cab-to-counter-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa/PnPCabToCounter` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robocasa:0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa-pnp-cab-to-counter-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`images/robocasa/standard/server_casa.py`, tool module `casa_tool`), which records the episode, replays it in a fresh simulator and judges it; the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its native controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 276 actions submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network) reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 3 |
| Memory | 14 GB | 13 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: robosuite sim p90 9.7 GB, verifier p90 4.0 GB (RoboCasa and RoboCasa-GR1 together), mem_guard (docker memory per container, mll-4090-1, 10-02..10); CPU-only (OSMesa cameras); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; exceeding one fails the trial), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 30 GiB memory. Limits measured: memory: agent container docker peak 2.3 GiB over 9 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, mll-4090-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 22 GiB (docker peak 14.1 GiB, 14 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Action type | `ee_delta` (12 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand` (robot-mounted; calibration in every response) |
