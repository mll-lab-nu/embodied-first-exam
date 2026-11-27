# EmbodiedSWE · carry the box from the shelf to the bin, Unitree G1 (standard)

| | |
|---|---|
| Task ID | `embodiedswe-locomanip-box-to-bin-g1-loco-pink-ik-i00-standard` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Unitree G1 humanoid with three-finger Dex3 hands, upper body driven by Pink IK (wrist poses and hand joints) |
| Mode | standard |
| Instance | `locomanip.box_to_bin.g1.loco_pink_ik`, seed 0 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Take the box off the shelf in front of you, carry it to the blue bin on the table to your right, and leave it in the
bin.

## Success criteria
Three conditions. Taken off the shelf (counted when it happens): at some physics step the box's origin rose more than
5 cm above its resting height on the shelf board, or was held more than 0.35 m above the floor in the area in front of
the shelf (5 to 40 cm out from the shelf's face, within 50 cm sideways of the box's starting position). Carried over
(counted when it happens): after that, the box's horizontal distance to the bin's centre fell below 10 % of its
starting distance. In the bin (on the final state): the box's origin lies within 14 cm (along x) and 26 cm (along y)
of the bin's centre, so the whole box is inside the walls, and less than 13.6 cm above the table top (a box lying
across the rim is higher), and every component of the box's linear (m/s) and angular (rad/s) velocity is below 0.20.
Whether the robot still holds the box is not checked.

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
