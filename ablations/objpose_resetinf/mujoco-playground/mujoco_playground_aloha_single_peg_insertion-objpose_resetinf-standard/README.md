# mujoco_playground_aloha_single_peg_insertion-standard

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `mujoco_playground_aloha_single_peg_insertion-privileged` |
| Simulator / robot | `mujoco` / `aloha-2` |
| Family / instance | `mujoco_playground/AlohaSinglePegInsertion` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2` |

## Task
Standard-mode twin of `mujoco_playground_aloha_single_peg_insertion-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_aloha`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `mujoco_playground_aloha_single_peg_insertion-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the live episode's verdict (`graded_by = "live"`, no grading replay): the task's check of the live final state. The frozen start is checked when the episode begins (instance `state_sha`)

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 7 GiB | 8192 | 6 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| video | `replay.mp4`: one render pass over the trajectory from the frozen start after the verdict (in the sidecar, EGL on its GPU); it never changes the verdict |
