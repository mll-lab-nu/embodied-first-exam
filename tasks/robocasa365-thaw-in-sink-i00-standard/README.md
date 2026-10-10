# robocasa365-thaw-in-sink-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa365 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa365-thaw-in-sink-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa365/ThawInSink` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robocasa365:0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa365-thaw-in-sink-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`images/robocasa365/standard/server_casa.py`, tool module `casa_tool`), which records the episode, replays it in a fresh simulator and judges it; the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its native controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 542 actions submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network) reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 3 |
| Memory | 9 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim p90 5.6 GB, privileged container p90 7.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only (OSMesa cameras); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; exceeding one fails the trial), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 19 GiB memory. Limits measured: memory: agent container docker peak 3.9 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 11 GiB (docker peak 6.4 GiB, 14 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Action type | `joint_position` (13 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand` (robot-mounted; calibration in every response) |
