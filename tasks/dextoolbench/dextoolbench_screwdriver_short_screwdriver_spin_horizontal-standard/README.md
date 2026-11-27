# DexToolBench · short screwdriver · spin_horizontal (standard)

| | |
|---|---|
| Task ID | `dextoolbench_screwdriver_short_screwdriver_spin_horizontal-standard` |
| Benchmark | [DexToolBench](https://simtoolreal.github.io/) (Kedia, Lum et al., 2026), upstream `tylerlum/simtoolreal@313d5ae` |
| Robot | KUKA iiwa 14 arm with a left Sharpa HA4 dexterous hand (22 joints): 29 position-controlled joints |
| Mode | standard |
| Instance | `dextoolbench/screwdriver/short_screwdriver/spin_horizontal`, seed 0 |
| Time limit | 1 h |
| Reference solution | Pipeline check only |

## Task
Pick up the screwdriver and spin it around a horizontal axis, following the green ghost screwdriver through its poses in
order.

## Success criteria
The goal is a fixed sequence of 38 poses of the short screwdriver (position and orientation in the
world frame), from DexToolBench's `short_screwdriver / spin_horizontal` demonstration; the scene shows the current
pose as a green ghost tool. The task passes only when all 38 poses have been reached, one after
another in the given order.

A pose is reached at a control step when each of the 8 corners of a box fixed to the tool (21.15 × 4.54 × 4.07 cm,
centred on the tool's frame origin; the same box for every tool) is less than 1.5 cm from where that corner is with the
tool at the pose. Only the current pose is tested, once after every control step; when it is reached, the next pose
becomes current from the next control step on.

Graded: the live episode, judged by the simulator service as it runs; nothing is replayed. The service tests the
current pose after every control step it executes, and poses have no time limit. Reaching the last pose neither ends
the episode nor is shown to the agent. The episode ends at the agent's `/finish`, after 360,000 control steps of the
episode (100 min of robot time), or when the agent's session ends (at the latest after 1 h). It passes if every
pose was reached in order at some control step before it ended; moving the tool afterwards does not undo that. The
agent has 20 resets; each abandons the running episode and starts a new one from the frozen start, with the first
pose current again. Only the last episode is graded.

An episode ended by a simulator error scores 0, and so does one ended because the service crashed repeatedly inside
the agent's own calls. An episode that does not start from the frozen instance (its state hash), a service that
crashes between calls or cannot resume the episode, or a missing verdict is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 16 GiB | 1024 | no GPU | 11 GiB |
| `sim` | 4 | 4 GiB | 1024 | 5 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
DexToolBench is part of SimToolReal ([tylerlum/simtoolreal](https://github.com/tylerlum/simtoolreal) @ `313d5ae`),
released under the [MIT License](https://github.com/tylerlum/simtoolreal/blob/313d5aea1f507c6cfe097b672b62945d7b0bbff5/LICENSE)
(Copyright (c) 2026 Tyler Lum). The tool meshes, the goal trajectories and the Sharpa HA4 hand model used here ship in
that repository. The KUKA iiwa 14 model is from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/1b86ece576591213e2b666ebf59508454200ca97/kuka_iiwa_14)
@ `1b86ece` (BSD 3-Clause License). The simulator is MuJoCo 3.3.7 (Apache License 2.0). No non-commercial terms apply.
SimToolReal's training code and pretrained policy are not part of the task image.
