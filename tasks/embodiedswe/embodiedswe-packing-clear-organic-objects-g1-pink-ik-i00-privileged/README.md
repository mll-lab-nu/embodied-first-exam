# EmbodiedSWE · sort the front-row items into the crate and onto the tray, Unitree G1 (privileged)

| | |
|---|---|
| Task ID | `embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-privileged` |
| Benchmark | [EmbodiedSWE](https://github.com/EmbodiedSWE/EmbodiedSWE) (Shen et al., 2026), upstream `EmbodiedSWE/EmbodiedSWE@67f44e8` |
| Robot | Unitree G1 humanoid with three-finger Dex3 hands, upper body driven by Pink IK (wrist poses and hand joints) |
| Mode | privileged |
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
