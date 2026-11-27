# EmbodiedSWE · flip a slice of bread in the pan with a spatula, then serve it onto the plate, Franka (standard)

| | |
|---|---|
| Task ID | `embodiedswe-puzzle-spatula-franka-osc-i00-standard` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Franka Emika Panda arm with its parallel-jaw gripper, under EmbodiedSWE's operational-space controller |
| Mode | standard |
| Instance | `puzzle.spatula.franka.osc`, seed 0 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Flip the bread in the pan with the spatula, then lift it out on the spatula and set it down flat on the plate.

## Success criteria
Three conditions, plus a tool-only rule. Flipped (counted when it happens): at some physics step the bread's top face
(the one up at the start) pointed within 30° of straight down while the bread lay flat in the pan (centre within
10.95 cm of the pan's centre, bottom within 12 mm of the pan floor, tilted at most 15°) and moved slower than
0.05 m/s. Served (counted when it happens): at some physics step the bread lay at rest on the plate (as below) within
600 physics steps (5 s) after the last step at which it rode the spatula's blade (on the blade, bottom 0.5 to 15 mm
above it, tilted at most 30° from the blade) with its bottom more than 5 cm above the table. On the plate (on the
final state): the bread's centre within 11.3 cm (75 % of the plate's radius) of the plate's centre, its bottom within
12 mm of the plate's resting height, tilted at most 15° from flat (either side up), moving slower than 0.05 m/s. The
order of the flip and the serve is not checked.

Tool-only rule: a contact with nonzero force between the bread and the hand or a finger (`panda_hand`,
`panda_leftfinger`, `panda_rightfinger`) at any physics step scores 0, also after the conditions were met. The spatula
may touch the bread.

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
