# robocasa-gr1-potato-to-microwave-close-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa-GR1 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa-gr1-potato-to-microwave-close-i00-privileged` |
| Simulator / robot | `robosuite` / `fourier-gr1` |
| Family / instance | `robocasa-gr1/PnPPotatoToMicrowaveClose` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robocasa-gr1-0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa-gr1-potato-to-microwave-close-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`embodied_first_exam/benchmarks/robocasa/sim/server_casa.py`, tool module `casa_tool`), which records the episode and judges it live (nothing is replayed); the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the objects in the humanoid's camera images, coordinate two arms and two dexterous hands through the IK controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 336 actions submitted through the client, one row per control step.

## Verification
The sim service judges the live episode when the agent's time is up (the environment's success check on the state after the last executed control step; nothing is replayed) and writes the verdict, final at once; `tests/grade.py` (separate sandbox, no network) reads its `final.json` (`graded_by = live`): `success = live_success ∧ not solved at the start ∧ no simulator error`. The episode's start is checked against the frozen instance before the agent is served (`RCB_INSTANCE_SHA`, `RCB_START_SHA`; a mismatch is an infrastructure failure, `instance_mismatch`). The video is rendered from the trajectory after the verdict (one render pass) and never decides it.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 16 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 3 | 14 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Action type | `ee_pose` (24 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `egoview`, `robot0_eye_in_right_hand`, `robot0_eye_in_left_hand` (robot-mounted; calibration in every response) |
