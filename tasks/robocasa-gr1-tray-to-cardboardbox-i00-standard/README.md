# robocasa-gr1-tray-to-cardboardbox-i00-standard

| | |
|---|---|
| Benchmark | RoboCasa-GR1 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robocasa-gr1-tray-to-cardboardbox-i00-privileged` |
| Simulator / robot | `robosuite` / `fourier-gr1` |
| Family / instance | `robocasa-gr1/PosttrainPnPNovelFromTrayToCardboardboxSplitA` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/embodied-agent-interface-v2-internal/eai-robocasa-gr1:0.1.0` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `robocasa-gr1-tray-to-cardboardbox-i00-privileged`: the same frozen instance and success check, served by the `sim` sidecar (`images/robocasa-gr1/standard/server_casa.py`, tool module `casa_tool`), which records the episode, replays it in a fresh simulator and judges it; the verifier grades the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its own joints and end effector, and the instruction.

## Difficulty
The agent has to find the objects in the humanoid's camera images, coordinate two arms and two dexterous hands through the IK controller, and finish in one episode without a reset.

## Reference solution
`solution/`: the privileged reference's 201 actions submitted through the client, one row per control step.

## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network) reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Details
| | |
|---|---|
| Action type | `ee_pose` (24 channels, `control_dt` 0.05 s) |
| Cameras | `robot0_agentview_center`, `robot0_agentview_left`, `robot0_agentview_right`, `egoview`, `robot0_eye_in_right_hand`, `robot0_eye_in_left_hand` (robot-mounted; calibration in every response) |
