# EmbodiedSWE · carry the box from the shelf to the bin, Unitree G1 (privileged)

| | |
|---|---|
| Task ID | `embodiedswe-locomanip-box-to-bin-g1-loco-pink-ik-i00-privileged` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Unitree G1 humanoid with three-finger Dex3 hands, upper body driven by Pink IK (wrist poses and hand joints) |
| Mode | privileged |
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

The graded runs: the verifier, in a separate sandbox without network, grades each checkpoint the agent froze with
`submit` (`/app/output/submissions/NNNNNN/`, at most 64) and the final `/app/output/solution/`. Each distinct candidate
runs once in a fresh process: the simulator is built from the frozen instance (seed 0, GPU PhysX) and the candidate's
`solve(env)` drives it from another process, without network or GPU, through a proxy env in which `env.step(action)`
is the only call that changes anything. The run ends when `solve` returns or raises, when its process ends, or 30 min
after the grading process started (start-up and import count). The conditions above are checked on the state at that
moment; a condition stated as having happened counts from the moment it happened in that run. There is no reset.

A candidate without `solve.py`, a checkpoint whose files differ from its receipt (`submission.json`), and a run whose
process ends without a verdict while solving score 0. Byte-identical candidates are graded once. The result is one
candidate: the one with the highest progress (EmbodiedSWE's rubric score for the task, the peak recorded during its
run), ties going to success, then to the earliest (the final folder counts last). That candidate's success is the
task's. The rebuilt start state is compared with the frozen instance; on the GPU model that froze it (NVIDIA L40S) a
mismatch is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 16384 | 16 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
EmbodiedSWE ([EmbodiedSWE/EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) @ `67f44e8`): code under the
Apache License 2.0. The scenes load EmbodiedSWE's asset bundle (Hugging Face `EmbodiedSWE/robobench-assets`, revision
`62fab5b`), whose assets carry mixed licences, some of them **non-commercial (CC BY-NC)** or store-licensed (Fab /
Objaverse models); each asset's licence ships with the bundle. The simulator is NVIDIA Isaac Sim 5.1 with Isaac Lab
2.3.2, under NVIDIA's licence terms (use, no redistribution), built with RoboLab's recipe (Apache License 2.0). For
these reasons the task image is built locally and never published.
