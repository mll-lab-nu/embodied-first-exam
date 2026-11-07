# robocasa365-turn-on-toaster-oven-i00-realtime

| | |
|---|---|
| Benchmark | RoboCasa365 |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `robocasa365-turn-on-toaster-oven-i00-privileged` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa365/TurnOnToasterOven` / seed 0 |
| Oracle | `none` — the privileged reference planned from step 0 through this service at S = 2 succeeds live and in the fresh replay, deterministic, no stall (2026-10-14); human review in PR #205 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 2 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 0 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0` |

## Task
Realtime mode (`eai-standard/2.3`, slowdown S = 2) of `robocasa365-turn-on-toaster-oven-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar on a clock that does not stop (the shared realtime layer of HumanoidBench, BiGym 2.0 and RoboOlympics with `environment/sim/server.py`, this benchmark's adapter on `casa_tool`). The scene is dynamic: the timer knob, once set, turns back by itself (1/3000 of its range per simulated second). The agent sees the robot's cameras (RGB-D; intrinsics, and each camera's pose in every proprioception row), its own joints and end effector, and the instruction; one episode, no reset.

## Difficulty
The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its native controller, and act on a clock that does not stop, in one episode without a reset.

## Reference solution
`solution/`: none for this mode. Solvability: the privileged reference's 271 actions planned from step 0 (`submit(..., at=0)`, then `at=200`) through this service at S = 2 succeed live (at control step 256) and in the fresh replay, deterministic, with no stall (2026-10-14).

## Verification
The sim service judges the episode live (it ends at the first step after which the success check holds; `graded_by = live`, nothing is replayed), records every control step it ran, and after the agent's time writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded and the scene was not solved at its start (the adapter's `live_verdict`). The first episode's start is checked against the frozen instance (`RCB_START_SHA`; a mismatch is an infrastructure failure, `instance_mismatch`). The video is rendered from the trajectory after the verdict and decides nothing. The clock's record (`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the episode never starts (its clock starts at the first submit), reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 6 | 14 GiB | 8192 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Slowdown | S = 2 (`RCB_SLOWDOWN`'s default): measured RTF 1.27-1.29 (2026-10-14, an RTX 4090 workstation (32 cores, load 35-45), the service capped at 4 CPUs: 1.29 with the realtime service's clock flat out (RCB_SLOWDOWN = 0.01, 3 episodes of 600 control steps), 1.27 for the bare physics holding still; S = ceil(1.5 / 1.29) = 2) |
| Episode | at most 3000 control steps (150 s of robot time; the privileged deliverable's cap); ends at the first success |
| Reset budget | 0 (`RCB_RESET_BUDGET`; PROTOCOL §2): one episode, as the standard twin |
| Action type | `joint_position` (13 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `robot0_eye_in_hand` (robot-mounted; poses in the proprioception) |
