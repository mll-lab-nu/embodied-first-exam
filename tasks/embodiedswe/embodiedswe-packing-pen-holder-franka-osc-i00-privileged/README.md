# EmbodiedSWE · fill the pen holder with pencils, tips up, Franka (privileged)

| | |
|---|---|
| Task ID | `embodiedswe-packing-pen-holder-franka-osc-i00-privileged` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Franka Emika Panda arm with its parallel-jaw gripper, under EmbodiedSWE's operational-space controller |
| Mode | privileged |
| Instance | `packing.pen_holder.franka.osc`, seed 0 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Put every pencil in the pen holder, writing tip up, and leave the holder standing upright on the table.

## Success criteria
Every pencil in the scene stands in the holder, and the holder stands upright on the table, everything at rest. A
pencil counts when, measured in the holder's frame, its button end is within 35 mm of the holder's axis, more than
35 mm below the rim and not below the cup's floor, and its axis points tip up within 45° of the holder's axis. The
holder: its axis within 10° of vertical and its bottom within 10 mm of the table top. Every pencil and the holder move
slower than 0.05 m/s.

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
