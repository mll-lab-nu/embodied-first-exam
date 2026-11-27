# EmbodiedSWE · install a graphics card and two RAM sticks, Franka (standard)

| | |
|---|---|
| Task ID | `embodiedswe-assembly-pc-gpu-ram-franka-osc-i00-standard` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Franka Emika Panda arm with its parallel-jaw gripper, under EmbodiedSWE's operational-space controller |
| Mode | standard |
| Instance | `assembly.pc_gpu_ram.franka.osc`, seed 0 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Install the graphics card and the two RAM sticks in the PC. The card goes in the PCIe x16 slot, the stick from the
holder farther from the robot in the outermost memory slot, and the other stick in the second slot from the CPU socket.

## Success criteria
The graphics card and both memory sticks are seated, each at its own seated position, measured in the case's frame.
The card: its edge connector at least 4 mm below the x16 slot's mouth, its origin within 3 mm horizontally of its
seated position, its up axis within 3° of the slot's axis and its length axis within 3° of the seated heading,
pointing the same way; the seated heading is a quarter turn clockwise, seen from above, from the way the card stands
in its holder. Each stick in its assigned slot (the stick from the farther holder in the outermost slot, the other in
the second slot from the CPU socket): its edge at least 3.7 mm below the slot's mouth, its origin within 3 mm
horizontally of its seated position, its up axis within 6° of the slot's axis and its length axis within 3° of the
seated heading, pointing the same way (a reversed stick fails).

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
