# YAMLab · HangMugOnTree-v0 (standard)

| | |
|---|---|
| Task ID | `yamlab-hang-mug-on-tree-i15-standard` |
| Benchmark | [YAMLab](https://github.com/ARISE-Initiative/yamlab) (Dai, 2026), upstream `ARISE-Initiative/yamlab@ec0455d` |
| Robot | Two I2RT YAM arms (6 joints each) with parallel two-finger grippers, on a workstation table |
| Mode | standard |
| Instance | `hang_mug_on_tree`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Pick up the mug with the left arm, pass it to the right arm in the air, and hang it on the mug tree.

## Success criteria
Three stages, in this order; a stage is counted only after the one before it has latched.

1. Pick: the left gripper is grasping the mug and the mug's centre is more than 5 cm above its resting height (the
   height of its centre when it stands on the table, 5.3 cm above the table top), on 8 consecutive control
   steps. The right gripper is not checked.
2. Handover: the right gripper is grasping the mug, the left gripper is not, and the mug's centre is more than 5 cm
   above its resting height, on 30 consecutive control steps (about 1 s).
3. Hang: the mug's centre is less than 11.5 cm from the mug tree's centre horizontally (half the tree's footprint
   diagonal, at least 10 cm), more than 9.8 cm above the table top (half the mug's height plus 5 cm), neither
   gripper is grasping the mug, and the mug's height stays within 3 cm of its height on the first step of the run, on 30
   consecutive control steps (about 1 s).

A gripper is grasping the mug when both its fingers touch the mug with a contact force of at least 0.1 N, at a point on
their pads.

Graded is the one live episode (no reset). The earlier stages count from the control step they latch, and stay counted.
The last stage must hold when the episode ends: its condition holds on the last control step and has held on every
control step of a run of at least 30 consecutive steps (about 1 s) up to it. If such a run has begun but is shorter when
the episode ends, the service holds the robot's last command until the run reaches 30 steps or breaks.

The episode ends at the agent's `POST /finish`, when the agent's session ends, or after 100,000 control steps; the
state at that moment is judged. It also ends, with 0, when the mug or the mug tree falls more than 1 cm below the
table top, even after the stages had latched, and on a simulator error raised by the agent's calls. The
service never reports success while the episode runs. A frozen scene that does not rebuild as recorded at the start,
or service crashes the episode cannot be resumed from, are infrastructure errors, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 5 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 16 | 21 GiB | 2048 | 16 GiB | — |
| verifier (as `main`) | 5 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
YAMLab ([ARISE-Initiative/yamlab](https://github.com/ARISE-Initiative/yamlab) @ `ec0455d`), its scene and object USDs
and its dataset (`yamlab/yamlab_datasets` on Hugging Face) are released under the MIT License (Copyright (c) 2026
Tianyuan Dai). Isaac Lab is BSD-3-Clause; YAMLab's LeRobot fork is Apache-2.0. NVIDIA Isaac Sim 5.1 and its wheels are
proprietary: NVIDIA licenses them for use, not for redistribution, so the simulator image is built on your machine and
building it accepts NVIDIA's Isaac Sim / Omniverse licence terms. No non-commercial terms apply.
