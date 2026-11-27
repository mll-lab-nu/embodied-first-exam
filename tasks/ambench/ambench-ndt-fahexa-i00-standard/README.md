# AM-Bench · ambench-ndt-fahexa-i00 (standard)

| | |
|---|---|
| Task ID | `ambench-ndt-fahexa-i00-standard` |
| Benchmark | [AM-Bench](https://github.com/ambench/ambench) (Wang et al., 2026), upstream `ambench/ambench@60bf5b7` |
| Robot | AM-Bench's FA-Hexa: a fully actuated hexarotor with a 4-joint arm and a two-finger gripper |
| Mode | standard |
| Instance | `ndt_fahexa`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Hold the end effector at the inspection point (Robot Interface), in front of the taped rectangle high up on the
warehouse wall ahead, for almost a second.

## Success criteria
The end-effector link has been at the inspection point for at least 100 consecutive control steps (0.83 s) at the end
of the episode: less than 3 cm from it along x, and less than 8 cm from it in the y-z plane, at each of those steps.
When the episode ends at `/finish` or at the session's end without that, the robot holds its last command for up to
120 more control steps (1 s), and the episode succeeds if the count reaches 100 in that time (the steps already held
count).

The graded episode is the one live episode, as it ran; nothing is replayed to grade it. There is no reset, and the
simulated clock advances only with the control steps the agent runs (1/120 s each). The episode ends when the agent
sends `/finish`, when the agent's session ends (at the latest after 1 h), or at AM-Bench's own time-out, after
20 s of simulated time (control step 2399); the time-out is judged like the other ends. Meeting the
condition does not end the episode, and the service never reports success while it runs.

An episode that ends in a simulator error scores 0. A live episode whose physics logged GPU faults, a scene whose
rebuilt start does not match the frozen instance, and a service that never wrote its record are infrastructure
failures, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 11 | 21 GiB | 1024 | 16 GiB | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, RTX 4090, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB.

## License
AM-Bench ([ambench/ambench](https://github.com/ambench/ambench) @ `60bf5b7`) is released under the
[Apache License 2.0](https://github.com/ambench/ambench/blob/60bf5b73041df4eab571f7d9f0a297aeecbf2e0d/LICENSE); its
third-party notices are in `THIRD_PARTY_NOTICES.md` of that commit. It runs on Isaac Lab (BSD-3-Clause) and NVIDIA
Isaac Sim 5.1.0, under the [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html);
Isaac Sim may not be redistributed, so the simulator image is built locally and never published. The scenes load files
from NVIDIA's public asset buckets (baked into the image), under NVIDIA's terms.
