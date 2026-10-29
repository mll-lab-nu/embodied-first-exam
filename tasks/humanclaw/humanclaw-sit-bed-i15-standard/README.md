# humanclaw-sit-bed-i15-standard

| | |
|---|---|
| Benchmark | HumanCLAW |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `humanclaw-sit-bed-i15-privileged` |
| Simulator / robot | `humanclaw` / `smplx-human` |
| Family / instance | `sit-bed` / seed 0 |
| Oracle | `full` — the privileged oracle's 15 actions streamed as skill rows through the client (open loop: they succeed on L40S) |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:humanclaw-0.1.0` |

## Task
HumanCLAW find-navigate-interact (bed), standard mode: the same frozen
episode and success rule as `humanclaw-sit-bed-i15-privileged`, with the head camera only, one episode and no reset. Find the bed and move until your body is touching the target, with zero distance to the target object. Finally, sit on the bed.
Modes and rules: `tasks/humanclaw/README.md`.

## Difficulty
Same scene, instance and success rule as `humanclaw-sit-bed-i15-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged oracle's 15 actions as `skill` rows through the client.

## Verification
The live episode's verdict: the sim service judges the episode it ran with HumanCLAW's metric code
(HumanCLAW's InteractSR) and the verifier transcribes it; nothing is replayed. `nop` scores 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 3 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 6 GiB | 1024 | 5 GiB | — |
| verifier (as `main`) | 4 | 3 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: an NVIDIA GPU of compute capability 8.0-9.0 with EGL (RTX 4090 / L40S / L4).
