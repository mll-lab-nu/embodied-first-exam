# DexToolBench · flat spatula · serve_plate (privileged)

| | |
|---|---|
| Task ID | `dextoolbench_spatula_flat_spatula_serve_plate-privileged` |
| Benchmark | [DexToolBench](https://simtoolreal.github.io/) (Kedia, Lum et al., 2026), upstream `tylerlum/simtoolreal@313d5ae` |
| Robot | KUKA iiwa 14 arm with a left Sharpa HA4 dexterous hand (22 joints): 29 position-controlled joints |
| Mode | privileged |
| Instance | `dextoolbench/spatula/flat_spatula/serve_plate`, seed 0 |
| Time limit | 1 h |
| Reference solution | Pipeline check only |

## Task
Pick up the spatula and make a serving motion onto the plate, following the green ghost spatula through its poses in
order.

## Success criteria
The goal is a fixed sequence of 33 poses of the flat spatula (position and orientation in the
world frame), from DexToolBench's `flat_spatula / serve_plate` demonstration; the scene shows the current
pose as a green ghost tool. The task passes only when all 33 poses have been reached, one after
another in the given order.

A pose is reached at a control step when each of the 8 corners of a box fixed to the tool (21.15 × 4.54 × 4.07 cm,
centred on the tool's frame origin; the same box for every tool) is less than 1.5 cm from where that corner is with the
tool at the pose. Only the current pose is tested, once after every control step; when it is reached, the next pose
becomes current from the next control step on.

Graded file: `/app/output/trajectory.npz`, array `actions` of shape (T, 29) with T at most 360,000: one row of joint
position targets per control step (1/60 s); targets outside the joint limits are clipped. After the agent's session
the verifier, in a separate container without network, replays it once, open-loop, from the frozen start with its own
copy of the tooling and the instance. Each pose must be reached within 1,800 control steps (30 s) after the previous
one was reached (the first pose: after the start); otherwise the replay stops there and the task fails. The replay also
stops when the last pose is reached; later rows are not run. A trajectory whose rows run out before the last pose is
reached fails.

A missing file scores 0, and so does one that cannot be read as an `.npz` with a numeric `actions` array, or whose
array has another shape, more than 360,000 rows, or a NaN or infinite value. An error inside the grader also scores 0
and is flagged as `grader_error`.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 20 GiB | 1024 | 5 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 5 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
DexToolBench is part of SimToolReal ([tylerlum/simtoolreal](https://github.com/tylerlum/simtoolreal) @ `313d5ae`),
released under the [MIT License](https://github.com/tylerlum/simtoolreal/blob/313d5aea1f507c6cfe097b672b62945d7b0bbff5/LICENSE)
(Copyright (c) 2026 Tyler Lum). The tool meshes, the goal trajectories and the Sharpa HA4 hand model used here ship in
that repository. The KUKA iiwa 14 model is from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/1b86ece576591213e2b666ebf59508454200ca97/kuka_iiwa_14)
@ `1b86ece` (BSD 3-Clause License). The simulator is MuJoCo 3.3.7 (Apache License 2.0). No non-commercial terms apply.
SimToolReal's training code and pretrained policy are not part of the task image.
