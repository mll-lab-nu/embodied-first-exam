# EmbodiedSWE · assemble the SO101 arm's elbow: servo, four tab screws, forearm, eight horn screws, two Frankas (standard)

| | |
|---|---|
| Task ID | `embodiedswe-assembly-so101-bimanual-franka-osc-i00-standard` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Two Franka Emika Panda arms with parallel-jaw grippers, each under EmbodiedSWE's operational-space controller |
| Mode | standard |
| Instance | `assembly.so101.bimanual_franka.osc`, seed 0 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Put the SO101 arm's elbow together with the screwdriver: seat the servo in the upper arm and fasten it with the four
small screws, then fit the forearm onto the servo and fasten it with the eight larger screws.

## Success criteria
The elbow is assembled. All twelve screws are fastened, each driven home and locked in a hole of its own group: the
four M2 tab screws in the servo's four tab holes, the eight M3 screws in the eight holes around the horn, any screw in
any hole of its group. The servo sits in the upper arm's pocket: its pose within 4 mm and 10° of the pocket's. The
forearm sits on the servo's output horn: its origin within 4 mm of its seat on the servo, and its orientation within
10° of the seat's once the rotation about the horn's axis is set aside (the elbow may stand at any angle).

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
