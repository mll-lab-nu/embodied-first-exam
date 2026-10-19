# robocasa365-turn-on-toaster-oven-i00-standard-realtime

| | |
|---|---|
| Benchmark | RoboCasa365 |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `robocasa365-turn-on-toaster-oven-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa365/TurnOnToasterOven` |
| Oracle | `none` — the privileged reference planned from step 0 through this service at S = 2 succeeds live and in the fresh replay, deterministic, no stall (board 0112, 2026-10-14); human review in PR #205 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 2 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robocasa365-0.1.0` |

## Task
Standard-realtime mode (`eai-standard/2.3`, slowdown S = 2) of `robocasa365-turn-on-toaster-oven-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar on a clock that does not stop (the shared realtime layer of HumanoidBench, BiGym 2.0 and RoboOlympics with `environment/sim/server.py`, this benchmark's adapter on `casa_tool`). The scene is dynamic (scripts/task_dynamics.toml): the timer knob, once set, turns back by itself (1/3000 of its range per simulated second). The agent sees the robot's cameras (RGB-D; intrinsics, and each camera's pose in every proprioception row), its own joints and end effector, and the instruction; 10 resets, only the last episode graded.

## Difficulty
The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its native controller, and act on a clock that does not stop, with resets.

## Reference solution
`solution/`: none for this mode. Solvability: the privileged reference's 271 actions planned from step 0 (`submit(..., at=0)`, then `at=200`) through this service at S = 2 succeed live (at control step 256) and in the fresh replay, deterministic, with no stall (board 0112, 2026-10-14).

## Verification
The sim service judges the episode live (it ends at the first step after which the success check holds; `graded_by = live`, nothing is replayed), records every control step it ran, and after the agent's time writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded and the scene was not solved at its start (the adapter's `live_verdict`). The first episode's start is checked against the frozen instance (`RCB_START_SHA`; a mismatch is an infrastructure failure, `instance_mismatch`). The video is rendered from the trajectory after the verdict and decides nothing. The clock's record (`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the episode never starts (its clock starts at the first submit), reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 3 | 3 |
| Memory | 9 GB | 8 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: as the standard twin (the same service process and fresh-replay session; board 0112); memory: sim p90 5.6 GB, privileged container p90 7.2 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only (OSMesa cameras); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 19 GiB memory. Limits measured: as the standard twin (board 0112); memory: agent container docker peak 3.9 GiB over 6 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 16 GiB cap; whole trial: + the sim service's 11 GiB (docker peak 6.4 GiB, 14 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Slowdown | S = 2 (`RCB_SLOWDOWN`'s default): measured RTF 1.27-1.29 (2026-10-14, board 0112, ws-1 (32 cores, load 35-45), the service capped at 4 CPUs: 1.29 with the realtime service's clock flat out (RCB_SLOWDOWN = 0.01, 3 episodes of 600 control steps), 1.27 for the bare physics holding still; S = ceil(1.5 / 1.29) = 2) |
| Episode | at most 3000 control steps (150 s of robot time; the privileged deliverable's cap); ends at the first success |
| Reset budget | 10 (`RCB_RESET_BUDGET`; PROTOCOL §4b); a reset rebuilds the scene (about 20 s) |
| Action type | `joint_position` (13 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand` (robot-mounted; poses in the proprioception) |

### Change Log
- 2026-10-14 (owner, board 0112): added. The scene is dynamic (PROTOCOL §2.14), so the task gets a standard-realtime twin, S = 2, 10 resets.
- 2026-10-17 (owner, boards 0150 and 0151): the verdict is the live episode's. The sim service no longer replays the graded episode in a fresh simulator: success = the live episode succeeded and the scene was not solved at its start (`graded_by = live`, `replays = 0`; `deterministic` and `replay_success` are gone). The first episode's start is checked against the frozen instance (`RCB_START_SHA`); a mismatch is an infrastructure failure. The video is rendered from the trajectory after the verdict and decides nothing. The scene, the success check, S, the resets and the agent's time are unchanged, so the task keeps its name.
