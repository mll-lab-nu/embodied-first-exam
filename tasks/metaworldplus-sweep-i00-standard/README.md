# metaworldplus-sweep-i00-standard

| | |
|---|---|
| Benchmark | MetaWorld+ |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `metaworldplus-sweep-i00-privileged` |
| Simulator / robot | `mujoco` / `sawyer` |
| Family / instance | `metaworld/sweep` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-metaworld:0.1.0` |

## Task
Standard-mode twin of `metaworldplus-sweep-i00-privileged`: the same instance and success check (Sweep the object to the target position.), served
as a robot service (`images/metaworld/standard/server_mw.py`, protocol eai-standard/2.1, tool module `mw_tool`). The
agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset; one episode.

## Difficulty
The agent has to find the objects in the images, place a mocap-driven hand whose wrist does not rotate, close the loop
through the cameras and finish in one episode without a reset: a pushed-away object or a dropped part stays where it
is. Success is judged on the final state, so the agent must also end the episode while the task is achieved.

## Reference solution
`solution/`: the privileged oracle's 103 actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network)
reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: privileged container p90 2.7 GB, sim 0.7 GB, mem_guard (docker memory per container, mll-4090-1, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; exceeding one fails the trial), the agent's container: no GPU, 8 GB memory, 512 processes, 10 GB written under `/app`; sustained 60 s. Expected peak of the whole trial: 0 GB GPU memory, 11 GB memory.

## Details
| | |
|---|---|
| actions | `ee_delta` = Meta-World's native `[dx, dy, dz, grip]` (no `joint_position`: the Sawyer has no arm actuators) |
| observations | four fixed cameras (RGB-D, calibration), proprioception, `meta.task.target_pos`; no object poses |
| episode | no step limit; runs until the agent's time is up; the state after the last control step is graded |
