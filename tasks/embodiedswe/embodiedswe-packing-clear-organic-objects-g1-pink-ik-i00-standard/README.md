# EmbodiedSWE · sort the front-row items into the crate and onto the tray, Unitree G1 (standard)

| | |
|---|---|
| Task ID | `embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-standard` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Unitree G1 humanoid with three-finger Dex3 hands, upper body driven by Pink IK (wrist poses and hand joints) |
| Mode | standard |
| Instance | `packing.clear_organic_objects.g1.pink_ik`, seed 0 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Put the two lemons from the front row of the table in the blue crate on your right, and the two limes from that row on
the round tray on your left.

## Success criteria
The two lemons and the two limes that start in the front row are placed, and nothing that is not food is in the blue
crate. Each lemon: its origin inside the crate's interior (within the inner walls, between the floor and the rim,
judged in the crate's frame) and moving slower than 0.06 m/s. Each lime: its origin over the round tray's counted
disc (85 % of the tray's radius), between the tray and 14 cm above its plate top, and moving slower than 0.06 m/s. No
non-food item (the jugs, the bottle, the pen holder, the bowl) has its origin inside the crate's interior. The other
food items may be anywhere. The crate is fixed in this scene and stays upright.

The graded episode: the one live episode, as it ran; nothing is replayed. There is no reset. The episode ends when
the agent sends `/finish`, when the agent's session ends (at the latest after 4 h), on a simulator error, at
400,000 control steps (a technical cap), or, where the task has a tool-only rule, at the first touch. The conditions
above are checked on the live state when the episode ends; a condition stated as having happened counts from the
moment it happened in the episode. Meeting the conditions earlier does not end the episode, and the service never
reports success while it runs.

An episode ended by a simulator error scores 0. The rebuilt start state is compared with the frozen instance before
the agent is served; on the GPU model that froze it (NVIDIA L40S) a mismatch is an infrastructure failure, not a score,
and so is an episode the service never finalizes.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 24 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 24 GiB | 2048 | 18 GiB | — |
| verifier (as `main`) | 8 | 24 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
EmbodiedSWE ([EmbodiedSWE/EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) @ `67f44e8`): code under the
Apache License 2.0. The scenes load EmbodiedSWE's asset bundle (Hugging Face `EmbodiedSWE/robobench-assets`, revision
`62fab5b`), whose assets carry mixed licences, some of them **non-commercial (CC BY-NC)** or store-licensed (Fab /
Objaverse models); each asset's licence ships with the bundle. The simulator is NVIDIA Isaac Sim 5.1 with Isaac Lab
2.3.2, under NVIDIA's licence terms (use, no redistribution), built with RoboLab's recipe (Apache License 2.0). For
these reasons the task image is built locally and never published.
