# robotwin_2_0_place_bread_skillet-standard

| | |
|---|---|
| Benchmark | RoboTwin 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `robotwin_2_0_place_bread_skillet-privileged` |
| Simulator / robot | `robotwin` / `aloha-agilex` |
| Family / instance | `place_bread_skillet` / seed 28831 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robotwin-0.1.2` |

## Task
Standard-mode twin of `robotwin_2_0_place_bread_skillet-privileged` (same frozen instance, RoboTwin seed 28831): the agent gets
only the `eai-standard/2.1` client (docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar), which owns the seed, judges the live episode, records it as a
(T, 34) trajectory and renders the six-view video from it once after the verdict. The verifier runs in a separate
sandbox (`tests/Dockerfile`) over the sidecar's artifacts. Compare against the privileged task to
measure the cost of losing resets, privileged state and planning primitives.

## Difficulty
Same scene, instance and success rule as `robotwin_2_0_place_bread_skillet-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/`: streams the privileged-mode expert's joint targets (every 25 physics steps, dt = 0.1 s, linear interpolation) as `joint_position` chunks

## Verification
`success` = the live episode's: RoboTwin's `check_success` holds after one of the agent's calls (which ends the
episode) or on the final state when the agent's time is up, judged by the sim sidecar on the episode it ran
(`final.json`: `graded_by = "live"`, `replays = 0`, the end state's hash `live_sha`); nothing is replayed to grade it.
The scene is checked against the frozen instance's initial-state hash when it is built, before the agent is served
(a mismatch is `instance_mismatch`, an infrastructure failure). After the verdict the sidecar renders the recorded
trajectory once, on its GPU, into `replay.mp4` (six views) and `live.mp4` (labelled by call); the verifier copies them
to `/logs/verifier/`. A video that fails or runs out of time is lost, the verdict is not.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 7 GiB | 1024 | 13 GiB | — |
| verifier (as `main`) | 3 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: RTX 4090 24GB / L4 24GB.

## Details
| | |
|---|---|
| action space | `eai-standard/2.1`: `submit` chunks of `joint_position` (14, streamed at 250 Hz with the agent's `dt`) or `ee_pose` (16, CuRobo-planned); `observe` frames or a watch window; binary RCB1 responses |
